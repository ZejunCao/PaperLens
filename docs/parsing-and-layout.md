# PaperLens 解析与版式复现

本文记录当前（Milestone 1）的实现手段：如何把 PDF 变成与解析器解耦的 `Document`，以及左侧阅读器如何按页坐标复现排版。目标是**同一套规则适配单栏、双栏及通栏混排**，不为某一篇论文写死特例。

相关代码以仓库现状为准；产品范围见根目录 [PRD.md](../PRD.md)。

---

## 1. 设计约束

- **解析器可替换**：MinerU / PyMuPDF / MinerU 远程 API 都产出同一套 `app/schemas/document.py`。
- **版式保真优先于 Markdown**：左侧不是把论文重排成网页文章，而是用 PDF 页坐标系（原点在页面左上，单位 pt）绝对定位。
- **阅读文本可复制**：行内公式用 KaTeX；块间公式用 PDF 裁剪图 + 栏右编号，LaTeX 仍保留在数据里。
- **运行时数据不进 Git**：上传 PDF、`document.json`、裁图、SQLite 均在 `data/`。
- **后处理可单独重跑**：映射与 PDF 补全（字号、残缺图）不依赖重跑 MinerU 模型。

---

## 2. 端到端流水线

```text
上传 PDF
  → SQLite 记 Paper（queued）
  → 后台线程 Worker claim Job
  → parse_pdf() 选解析器
  → 映射为 Document
  → enrich_layout_from_pdf()（非 PyMuPDF）
  → 写入 data/papers/{id}/document.json
  → Paper.status = ready
  → 前端拉取 Document + /assets 图片
  → LayoutPage 按页绘制
```

| 步骤 | 模块 |
|------|------|
| 上传与元数据 | `app/api/papers.py`、`app/services/papers.py` |
| 任务队列 | `app/services/jobs.py`、`app/workers/parse_worker.py` |
| 解析入口 | `app/parsers/__init__.py` → `get_parser()` / `parse_pdf()` |
| MinerU 调用 | `app/parsers/mineru_parser.py` |
| JSON → Document | `app/parsers/mineru_map.py` |
| PDF 补全 | `app/parsers/layout_enrich.py` |
| 左栏绘制 | `frontend/src/components/reader/LayoutPage.vue` |
| 左右分栏壳 | `frontend/src/components/reader/SplitDocumentView.vue` |

Worker 在 FastAPI `lifespan` 里起独立线程，轮询 `jobs` 表，避免阻塞 HTTP。失败可 `POST /api/papers/{id}/parse`（`reset_document=True` 会清派生文件再解析）。

环境变量前缀 `PAPERLENS_`，见 `.env.example`。默认 `PAPERLENS_PARSER=mineru`。

---

## 3. 解析器

### 3.1 工厂

`get_parser()` 按配置选择：

| `PAPERLENS_PARSER` | 实现 | 用途 |
|--------------------|------|------|
| `mineru` | `MinerUParser` | 默认。本地 pipeline，公式/图表/版面 |
| `pymupdf` | `PyMuPDFParser` | 无 GPU / 快速路径；规则重建行内公式 |
| `mineru_api` | `MinerUApiParser` | mineru.net 远程精准解析 |

`parse_pdf()` 在非 PyMuPDF 结果上再跑 `enrich_layout_from_pdf`。

### 3.2 本地 MinerU

- 调用 `mineru.cli.common.do_parse`，写出 `middle.json` 与 `content_list`。
- 公式、表格开启；不画 layout/span 调试框。
- CUDA 不可用时回退 CPU；加载模型前读取实时空闲显存，低于后端预算时直接失败并给出所需/空闲显存，不再等模型 OOM。默认预算为 pipeline 4 GiB、VLM/hybrid 8 GiB，可用 `PAPERLENS_MINERU_GPU_MEMORY_GB` 覆盖。
- 预检通过后若仍发生动态 OOM（例如超大页面或显存碎片），仍保留回退 CPU 的兜底。
- 图片从 MinerU 输出目录拷到 `data/papers/{id}/images/`，路径写入 Document。
- **优先用 `middle.json`**（行/span 级 bbox）。`content_list` 的框常是段级 0–1000 归一化，只作回退。

Windows 上 MinerU extra 需要 **Python 3.11/3.12**（本仓库 `.python-version` 为 3.12）。`uv sync --extra mineru` 可能装到 CPU 版 torch，需按 `.env.example` 换成 CUDA 轮子。模型由 MinerU 自行下载（如 ModelScope），**不放进本仓库**。

### 3.3 PyMuPDF 路径

`pymupdf_parser.py` 抽文本 span、粗分块、裁图。`latex_rebuild.py` 用数学字体名与 Unicode→LaTeX 表，把相邻 glyph 拼成行内公式，不调用视觉模型。

### 3.4 远程 API

上传 PDF、轮询、解 Zip，再走同一套 `document_from_middle` / `document_from_content_list`。

---

## 4. Document 模型

`Document` 与具体解析器无关，前后端 TypeScript 类型在 `frontend/src/types/document.ts` 对齐。

要点：

- **页**：`width` / `height`（pt）、`blocks`、`images`。
- **块**：`title` / `section` / `paragraph` / `formula` / `figure` / `caption` / `table` 等；`bbox`；`spans`（绘制用）；`segments`（text | math）。
- **TextSpan**：`bbox`、`font_size`、`font_name`、`flags`、`origin_y`（PDF 基线）、`ascender`。
- **RichSegment (math)**：`latex`、`display`、`image_path`（块间公式裁图）。
- **扁平 `blocks` + `toc`**：右栏阅读顺序与目录。

坐标一律为**该页 PDF 空间**，前端乘 `scale` 变成 CSS 像素。

---

## 5. MinerU 映射（`mineru_map.py`）

### 5.1 容器展开

`image` / `table` / `chart` 是嵌套容器。`_iter_para_blocks` 拆出 `*_body`（图/表）与 caption/footnote，避免只拿到外壳、丢掉贴图。

### 5.2 行与 span

`_lines_to_spans_segments`：

- 普通文本 → `TextSpan` + 合并后的 text segment。
- `inline_equation` / `interline_equation` → `kind=math`，`display` 由类型决定；带 `image_path` 则左侧画图。
- 去掉 MinerU 的 HTML/`<sup>` 标记，作者角标等改由后续 PDF 样式切开。
- `_join_plain` 处理粘词与断词，避免 `combination` 与 `v_new` 一类错误空格。

### 5.3 跨页串行

MinerU 常把下一页开头接到当前页末。`_split_page_overflow_lines`：若行的 y 从页下半突然跳回页顶、且不是右栏换列，则把后续行 `carry` 到下一页。

### 5.4 公式编号

块间公式的 LaTeX 常带 `\tag{1}`。编号**不画在公式图里**（MinerU 公式 bbox 通常不含栏右 eqno），由前端在栏右叠加。

---

## 6. PDF 后处理（`layout_enrich.py`）

MinerU 的 middle.json **通常没有可用字号**。打开原 PDF，用 PyMuPDF span 对齐 MinerU 行框：

1. **字号 / 基线 / 粗斜体**：`style_from_pdf_styles`、`split_line_by_pdf_styles`（段首加粗、蓝色引用拆成多个 span）。数学字体 span 不参与正文切开。
2. **残缺图补裁**：若 figure 底边到最近 `Figure N` 标题之间空隙 ≥ 36pt，且空隙里没有大段 paragraph，则从 PDF 按扩展 bbox 重裁，写成 `images/fig_ext_{id}.jpg`（换文件名避免浏览器缓存半截图）。落在新图内部的图注 OCR（非 `Figure N`）打 `meta.layout_skip`，前端不再叠字。
3. **公式裁图**（`clip_math_from_pdf`）：按 math segment bbox 从 PDF 光栅化，避免把 LaTeX 源码画在左栏。

后处理失败则保留映射结果，不让整篇解析失败。

只改映射/后处理时：**不必重跑 MinerU**，对已有 `middle.json` 再 `document_from_middle` + `enrich_layout_from_pdf` + `save_document` 即可。

---

## 7. 左侧版式引擎（`LayoutPage.vue`）

每一页是一个 `position: relative` 的盒子，宽高 = 页尺寸 × `scale`。子元素 `position: absolute`，`left/top/width/height` 由 bbox 换算。

### 7.1 分栏检测（按页、非按篇）

同一 PDF 可以第一页通栏摘要、后面双栏。对**当前页**的块聚类：

**双栏候选**（同时满足才定为双栏）：

- 忽略 `formula` 以及过窄（&lt; 70pt）或过宽（&gt; 0.62 × 页宽）的块，避免通栏标题/大图、公式自身宽度污染聚类。
- 按块中心 x 相对页中线分成左右，得到 `[l0,l1]`、`[r0,r1]`。
- 两栏宽度都 &gt; 90pt，栏缝 `r0 - l1 > 10`。
- 缝必须在页中附近：`l1 < 0.55 × 页宽` 且 `r0 > 0.45 × 页宽`，避免单栏论文里左右碎片被判成双栏。

**否则单栏**：在段落等块上取宽度 ∈ `[0.4, 0.96] × 页宽` 的左右包络作为正文栏（再排除 formula/figure）。包络过窄则回退到页宽的 10%–90%。

块间公式的绘制盒用 `columnBox(公式中心 x)`：双栏时落在左栏或右栏全宽，单栏时落在正文栏全宽。公式图在盒内 **flex 水平居中**；`\tag` 解析为 `(n)`，`position: absolute; right: 0` 贴**该栏右缘**。KaTeX 回退路径会去掉 `\tag`，避免与叠加编号重复。

### 7.2 正文文字

- 基线优先用 `origin_y`，而不是 span 框底（框常偏高，上标会被切）。
- 两端对齐用 **word-spacing** 按行宽分配，**不再对单词 `scaleX`**（否则像 `pair` 会被拉成假加粗）。
- 行距给上标留空；正文框**不是**不透明挡板。
- 行内公式：KaTeX `font-size: 1em`，`vertical-align: baseline`，strut 约 0.72em；与词之间用 `inlineMathGapX` 补约 0.22em，避免 `combination` 和公式粘在一起。
- 行内公式 z 高于行间公式图，避免白底图盖住上一行。
- 只有与**行间公式图**重叠时才收缩正文绘制区；不用 `clip-path` 硬切上下沿。

### 7.3 图层

| 层 | 内容 |
|----|------|
| z-0 | 页面插图（`page.images`，排除 formula） |
| z-1 | 行间公式图 + 栏右编号 |
| z-3 | 行内公式与正文 |

`meta.layout_skip` 的块不进入绘制列表。

### 7.4 选择与复制

绝对定位下，浏览器从空白拖选会选中「上面所有字」，且左右栏会交错。因此：

- `readingItems` 排序：**先栏、再 y、再 x**。
- 自定义 pointer 选区：从指针所在行/栏开始；栏内只选本栏；拖到另一栏才按阅读顺序跨栏。
- 复制时按栏、按行拼接纯文本。

实现细节见 `LayoutPage.vue` 中 `onSelDown` / `onSelCopy`。注意 `columns` / `itemColumn` 必须定义在 `readingItems` 之前，避免 immediate watch 触发 TDZ。

---

## 8. 右侧阅读栏与文库

- `SplitDocumentView`：左栏版式、右栏按页/块展示阅读文本；解析中轮询论文状态。
- 文库 `PaperCard`：上传、重命名、删除、重试解析；`queued`/`parsing` 时 Pinia 约 1.5s 拉列表更新徽章。
- 静态资源：`GET /api/papers/{id}/assets/...` 映射到 `data/papers/{id}/`。

---

## 9. 适配「所有论文」时的原则

启发式全部基于 **页宽比例、栏缝、块类型**，禁止写入某 arXiv id 或某页号。

已用来回归的两类版式：

- **双栏**（如 Linear Transformers 类双栏 PDF）：多数正文页应判双栏；公式在**所在栏**居中、编号靠该栏右。
- **单栏宽页**（如 Kimi K3 一类）：应判单栏；公式相对正文栏居中；Figure 被 MinerU 裁成半幅时由后处理补全。

仍会失败的典型情况（已知限制，不是某篇特例）：

- 三栏、不规则杂志栏、极不对称双栏。
- 扫描件 / 纯图 PDF（PRD 非目标）。
- MinerU 漏检的独立图（空隙里夹着大段正文时，补裁会主动放弃，以免把文字画进图）。
- 公式图与正文 bbox 严重错位。

新增论文出问题时：先看该**页**是单栏还是双栏判错，再看是映射 bbox、后处理，还是 CSS 盒宽；不要为单篇加 if。

---

## 10. 关键路径速查

```text
app/parsers/__init__.py          解析器工厂 + enrich 接线
app/parsers/mineru_parser.py     本地 MinerU
app/parsers/mineru_map.py        middle.json → Document
app/parsers/layout_enrich.py     字号、残缺图、公式裁图
app/parsers/pymupdf_parser.py    无 MinerU 时的解析
app/parsers/latex_rebuild.py     PyMuPDF 行内公式规则重建
app/schemas/document.py          标准 JSON
app/workers/parse_worker.py      异步解析
frontend/src/components/reader/LayoutPage.vue
frontend/src/components/reader/KatexView.vue
frontend/src/components/reader/SplitDocumentView.vue
```

产物目录：

```text
data/uploads/{paper_id}.pdf
data/papers/{paper_id}/document.json
data/papers/{paper_id}/images/
data/papers/{paper_id}/mineru/          # MinerU 原始输出，可重映射
data/paperlens.db
```
