# PaperLens

本地单用户 AI 论文阅读器。当前进度：**Milestone 1（内容解析 + 版式复现）**。

上传 PDF 后异步结构化解析，左侧按原页坐标复现排版（单栏 / 双栏），右侧按阅读顺序展示文本。UI 视觉对齐 [WeChatOA_Aggregation](https://github.com/ZejunCao/WeChatOA_Aggregation)（米白亮色）。产品范围见 [PRD.md](./PRD.md)，解析与版式技术说明见 [docs/parsing-and-layout.md](./docs/parsing-and-layout.md)。

## 技术栈

| 层级 | 选用 |
|------|------|
| 前端 | Vue 3、TypeScript、Vite、Tailwind CSS v4、Pinia、Vue Router、KaTeX |
| 后端 | FastAPI、Pydantic、SQLAlchemy、Alembic、Uvicorn |
| 解析 | **MinerU**（默认）/ PyMuPDF / MinerU 远程 API；PyMuPDF 补字号与残缺图 |
| 数据 | SQLite（`data/paperlens.db`）+ `data/uploads/` + `data/papers/{id}/` |

## 环境要求

- Python **3.12**（MinerU extra 需要 3.11 或 3.12；见 `.python-version`）
- [uv](https://github.com/astral-sh/uv)
- Node.js LTS（含 npm）
- 本地 MinerU 建议 NVIDIA GPU + CUDA；无 GPU 时可回退 CPU（较慢）

## 快速开始

```bash
cp .env.example .env   # 可按需修改 PAPERLENS_PARSER 等
uv sync --extra mineru
uv run alembic upgrade head
cd frontend && npm install && cd ..
```

Windows 上 `uv sync --extra mineru` 常会装到 CPU 版 PyTorch。若 `import torch; torch.cuda.is_available()` 为 `False`，按 `.env.example` 中的注释换成 CUDA 轮子。

### Windows（PowerShell）

```powershell
.\start_all.ps1
```

### Linux / macOS

```bash
chmod +x start_all.sh
./start_all.sh
```

| 服务 | 地址 |
|------|------|
| 后端 API | http://127.0.0.1:8000 |
| 前端 | http://127.0.0.1:5173 |

无 GPU、或不装 MinerU 时：`.env` 里设 `PAPERLENS_PARSER=pymupdf`，并只执行 `uv sync`（不要 `--extra mineru`）。

## 已实现能力

### Milestone 0

- PDF 上传 / 论文库 / 重命名 / 删除

### Milestone 1

- 上传后自动排队异步解析（`queued → parsing → ready / failed`）
- 标准 Document JSON（块、句子、span 坐标、公式、目录）
- 左侧按 bbox 网页复现原 PDF 排版（分栏、行内/行间公式、插图）
- 右侧按页展示阅读文本；版式层支持按栏选择与复制
- 失败可重试：`POST /api/papers/{id}/parse`

## 仓库里有什么、没有什么

**会提交：**源码、`uv.lock`、前端依赖清单、Alembic 迁移、文档。

**不会提交（已写入 `.gitignore`）：**

- `data/` 下的 PDF、解析产物、SQLite
- `.venv/`、`frontend/node_modules/`
- `.env` 与 API Token

MinerU 权重由 MinerU 自行下载到其默认缓存目录，不要放进本仓库。

## 目录结构

```text
PaperLens/
├── app/                 # FastAPI 与解析管线
│   ├── parsers/         # mineru / pymupdf / 映射 / PDF 后处理
│   └── workers/         # 异步解析 Worker
├── alembic/             # 数据库迁移
├── docs/                # 技术说明
├── frontend/            # Vue 阅读器
├── tests/
├── PRD.md
└── data/                # 运行时数据（本地生成，不入库）
```
