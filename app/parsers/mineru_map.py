"""把 MinerU middle.json / content_list.json 映射为 PaperLens Document。"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path
from typing import Any

from app.parsers.utils import new_id, split_sentences
from app.schemas.document import (
    ContentBlock,
    Document,
    PageLayout,
    RichSegment,
    Sentence,
    TextSpan,
    TocItem,
)

_CONTAINER_TYPES = {"image", "table", "chart", "code"}
_CAPTION_TYPES = {
    "image_caption",
    "table_caption",
    "chart_caption",
    "image_footnote",
    "table_footnote",
    "chart_footnote",
}
_BODY_TYPES = {"image_body", "table_body", "chart_body", "code_body"}
_HTML_TAG = re.compile(r"<[^>]+>")
# MinerU 偶发把上标数字识别成 \widehat{2}
_LATEX_WIDEHAT_DIGIT = re.compile(r"\\widehat\s*\{\s*(\d+)\s*\}")
_LATEX_SPACEY = re.compile(r"\s+")
_COMPOUND_PREFIXES = {
    "self",
    "well",
    "end",
    "co",
    "pre",
    "non",
    "multi",
    "sub",
    "fine",
    "real",
    "low",
    "high",
    "long",
    "short",
    "open",
    "cross",
    "state",
    "data",
    "task",
    "text",
    "time",
    "full",
    "semi",
    "meta",
    "auto",
    "post",
    "over",
    "under",
    "re",
    "mid",
}


def _as_bbox(raw: Any) -> list[float]:
    if not raw or not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return [0.0, 0.0, 0.0, 0.0]
    return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]


def _denorm_bbox(bbox_1000: list[float], width: float, height: float) -> list[float]:
    x0, y0, x1, y1 = _as_bbox(bbox_1000)
    return [
        x0 / 1000.0 * width,
        y0 / 1000.0 * height,
        x1 / 1000.0 * width,
        y1 / 1000.0 * height,
    ]


def _span_font_size(span: dict[str, Any], bbox: list[float]) -> float:
    size = span.get("font_size") or span.get("size")
    if size:
        return float(size)
    h = max(0.0, bbox[3] - bbox[1])
    return h if h > 1.0 else 12.0


def _strip_markup(text: str) -> str:
    cleaned = _HTML_TAG.sub("", html.unescape(text or ""))
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _join_plain(left: str, right: str) -> str:
    """拼接相邻行/片段：补空格，并尽量还原行末断词。"""
    a = left.rstrip()
    b = right.lstrip()
    if not a:
        return b
    if not b:
        return a
    if a.endswith("-"):
        stem = a[:-1]
        last = re.split(r"\W+", stem)[-1].lower() if stem else ""
        if last in _COMPOUND_PREFIXES or (b[:1].isupper() and last):
            return f"{stem}-{b}"
        if b[:1].isalpha() and b[:1].islower():
            return stem + b
        return a + b
    if a[-1] in "([{\"'“‘" or b[0] in ".,;:!?%)]}'\"”’":
        return a + b
    return a + " " + b


def _join_text(parts: list[str]) -> str:
    out = ""
    for part in parts:
        piece = _strip_markup(str(part))
        if not piece:
            continue
        out = _join_plain(out, piece) if out else piece
    return out


def _normalize_latex(tex: str) -> str:
    """清理 MinerU 公式里常见的识别噪声。"""
    s = (tex or "").strip()
    if not s:
        return s
    s = _LATEX_WIDEHAT_DIGIT.sub(r"\1", s)
    # \times 是 LaTeX 乘号 ×；N{\times}F 避免 KaTeX 把 N\times 里的 \t 当 tab
    s = re.sub(r"([0-9A-Za-z])\s*\\times\s*([0-9A-Za-z])", r"\1{\\times}\2", s)
    s = _LATEX_SPACEY.sub(" ", s)
    return s


def _sentences_from(text: str, bbox: list[float]) -> list[Sentence]:
    out: list[Sentence] = []
    for i, sent in enumerate(split_sentences(text)):
        out.append(Sentence(id=new_id("s"), text=sent, order=i, bbox=bbox))
    return out


def copy_mineru_images(src_root: Path, dest_images: Path) -> dict[str, str]:
    """复制 MinerU 导出图到 output/images，返回 原路径片段 -> images/<name>。"""
    dest_images.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    if not src_root.exists():
        return mapping
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        if src.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            continue
        dest = dest_images / src.name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
        rel = f"images/{src.name}"
        mapping[src.name] = rel
        mapping[src.as_posix().replace("\\", "/")] = rel
        try:
            mapping[src.relative_to(src_root).as_posix()] = rel
        except ValueError:
            pass
        # MinerU 常用 images/<hash>.jpg
        mapping[f"images/{src.name}"] = rel
    return mapping


def resolve_image_path(raw: str | None, image_map: dict[str, str]) -> str | None:
    if not raw:
        return None
    key = str(raw).replace("\\", "/")
    if key in image_map:
        return image_map[key]
    name = Path(key).name
    if name in image_map:
        return image_map[name]
    if key.startswith("images/"):
        return key
    return f"images/{name}" if name else None


def _collect_span_image(block: dict[str, Any]) -> str | None:
    for line in block.get("lines") or []:
        for span in line.get("spans") or []:
            path = span.get("image_path") or span.get("img_path")
            if path:
                return str(path)
    return block.get("image_path") or block.get("img_path")


def _split_page_overflow_lines(
    block: dict[str, Any],
    page_height: float,
) -> dict[str, Any] | None:
    """MinerU 常把下一页开头几行接到当前页末；y 从页底跳回页顶时拆走。"""
    lines = list(block.get("lines") or [])
    if len(lines) < 2 or page_height <= 0:
        return None
    mtype = str(block.get("type") or "").lower()
    # 标题/小节多行常居中：下一行更宽、x0 更靠左，绝不能当成「右栏→左栏翻页」
    title_like = mtype in {"title", "doc_title", "section"}
    keep: list[dict[str, Any]] = [lines[0]]
    overflow: list[dict[str, Any]] = []
    spilled = False
    prev_box = _as_bbox(lines[0].get("bbox"))
    for line in lines[1:]:
        box = _as_bbox(line.get("bbox"))
        y, x0 = box[1], box[0]
        prev_y, prev_x0 = prev_box[1], prev_box[0]
        jumped_up = prev_y > page_height * 0.62 and y < page_height * 0.28
        to_right_column = x0 > prev_x0 + 80
        # 同一页双栏正文按左栏 -> 右栏流动；右栏 -> 左栏通常意味着翻到下一页。
        # 仅当上一行已在页面下半部时才启用，避免论文标题第二行误拆。
        wrapped_to_left = (
            not title_like
            and prev_y > page_height * 0.40
            and x0 < prev_x0 - 80
        )
        if not spilled and (wrapped_to_left or (jumped_up and not to_right_column)):
            spilled = True
        if spilled:
            overflow.append(line)
        else:
            keep.append(line)
            prev_box = box
    if not overflow:
        return None
    block["lines"] = keep
    keep_boxes = [_as_bbox(ln.get("bbox")) for ln in keep]
    block["bbox"] = [
        min(b[0] for b in keep_boxes),
        min(b[1] for b in keep_boxes),
        max(b[2] for b in keep_boxes),
        max(b[3] for b in keep_boxes),
    ]
    over_boxes = [_as_bbox(ln.get("bbox")) for ln in overflow]
    return {
        "type": block.get("type") or "text",
        "lines": overflow,
        "bbox": [
            min(b[0] for b in over_boxes),
            min(b[1] for b in over_boxes),
            max(b[2] for b in over_boxes),
            max(b[3] for b in over_boxes),
        ],
    }


def _content_bbox_from_lines(block: dict[str, Any]) -> list[float] | None:
    """以实际行/片段坐标重算文本块边界，覆盖 MinerU 只框住首栏的情况。"""
    boxes: list[list[float]] = []
    for line in block.get("lines") or []:
        line_box = _as_bbox(line.get("bbox"))
        if line_box[2] > line_box[0] and line_box[3] > line_box[1]:
            boxes.append(line_box)
            continue
        for span in line.get("spans") or []:
            span_box = _as_bbox(span.get("bbox"))
            if span_box[2] > span_box[0] and span_box[3] > span_box[1]:
                boxes.append(span_box)
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


_SENTENCE_END = re.compile(r"[.!?。！？][\"'”’）)]*$")


def _stitch_cross_page_sentences(pages: list[PageLayout]) -> None:
    """连接跨页句子的物理片段，并把完整句子归到起始页。"""
    blocks = [block for page in pages for block in page.blocks]
    starts = {
        str(block.meta.get("continues_to")): block
        for block in blocks
        if block.meta.get("continues_to")
    }
    ends = {
        str(block.meta.get("continues_from")): block
        for block in blocks
        if block.meta.get("continues_from")
    }
    for continuation_id, left in starts.items():
        right = ends.get(continuation_id)
        if right is None or not left.sentences or not right.sentences:
            continue
        left_sent = left.sentences[-1]
        right_sent = right.sentences[0]
        left_text = (left_sent.full_text or left_sent.text or "").strip()
        right_text = (right_sent.full_text or right_sent.text or "").strip()
        if not left_text or not right_text or _SENTENCE_END.search(left_text):
            continue

        full_text = _join_plain(left_text, right_text)
        owner_page = left_sent.owner_page or left.page
        sentence_id = left_sent.id
        linked_ids = {left_sent.id, right_sent.id}
        # 多页连续时，更新此前已经共享该句 ID 的所有物理片段。
        for block in blocks:
            for sent in block.sentences:
                if sent.id not in linked_ids:
                    continue
                sent.id = sentence_id
                sent.full_text = full_text
                sent.owner_page = owner_page


def _flush_text_seg(
    segments: list[RichSegment],
    buf: str,
    bbox: list[float] | None,
    font_size: float | None,
    origin_y: float | None,
) -> None:
    if not buf:
        return
    segments.append(
        RichSegment(
            kind="text",
            text=buf,
            bbox=bbox,
            font_size=font_size,
            origin_y=origin_y,
        )
    )


def _lines_to_spans_segments(
    block: dict[str, Any],
    image_map: dict[str, str],
) -> tuple[list[TextSpan], list[RichSegment], str]:
    spans: list[TextSpan] = []
    segments: list[RichSegment] = []
    texts: list[str] = []
    text_buf = ""
    buf_bbox: list[float] | None = None
    buf_size: float | None = None
    buf_origin: float | None = None

    for line in block.get("lines") or []:
        for span in line.get("spans") or []:
            stype = str(span.get("type") or "text")
            bbox = _as_bbox(span.get("bbox"))
            content = _strip_markup(str(span.get("content") or span.get("text") or ""))
            font_size = _span_font_size(span, bbox)
            origin_y = bbox[3] if bbox[3] else None

            if stype in {"image", "table", "chart"}:
                continue
            if stype in {"inline_equation", "interline_equation", "equation"}:
                latex = _normalize_latex(content)
                if not latex:
                    continue
                _flush_text_seg(segments, text_buf, buf_bbox, buf_size, buf_origin)
                text_buf, buf_bbox, buf_size, buf_origin = "", None, None, None
                img = resolve_image_path(span.get("image_path") or span.get("img_path"), image_map)
                segments.append(
                    RichSegment(
                        kind="math",
                        text=latex,
                        latex=latex,
                        bbox=bbox,
                        display=stype != "inline_equation",
                        font_size=font_size,
                        origin_y=origin_y,
                        image_path=img,
                    )
                )
                texts.append(latex)
                continue

            if not content:
                continue
            texts.append(content)
            spans.append(
                TextSpan(
                    id=new_id("sp"),
                    text=content,
                    bbox=bbox,
                    font_size=font_size,
                    font_name=span.get("font") or span.get("font_name"),
                    origin_y=origin_y,
                )
            )
            text_buf = _join_plain(text_buf, content) if text_buf else content
            buf_bbox = bbox
            buf_size = font_size
            buf_origin = origin_y

    _flush_text_seg(segments, text_buf, buf_bbox, buf_size, buf_origin)
    source = _join_text(texts)
    if not source:
        source = _strip_markup(str(block.get("text") or ""))
    if source and not segments:
        segments.append(RichSegment(kind="text", text=source, bbox=_as_bbox(block.get("bbox"))))
    return spans, segments, source


def _block_type_from_mineru(mtype: str, text_level: int | None, source: str) -> str:
    t = (mtype or "text").lower()
    if t in {"title", "doc_title"}:
        if text_level is None or text_level <= 1:
            return "title"
        return "section"
    if t in {"header", "page_header"}:
        return "header"
    if t in {"footer", "page_footer", "page_number"}:
        return "footer"
    if t in {"list", "list_item"}:
        low = source.lower()
        if low.startswith("references") or "doi:" in low:
            return "reference"
        return "list_item"
    if t in {"interline_equation", "equation"}:
        return "formula"
    if t in {"image", "chart", "image_body", "chart_body", "figure"}:
        return "figure"
    if t in {"table", "table_body"}:
        return "table"
    if t in _CAPTION_TYPES or t == "caption":
        return "caption"
    if t in {"index"}:
        return "other"
    if t in {"code", "code_body"}:
        return "other"
    if text_level and text_level >= 1:
        return "section" if text_level > 1 else "title"
    return "paragraph"


def _emit_content_block(
    *,
    mtype: str,
    page: int,
    order: int,
    bbox: list[float],
    source: str,
    spans: list[TextSpan],
    segments: list[RichSegment],
    meta: dict[str, Any],
    text_level: int | None = None,
) -> ContentBlock:
    btype = _block_type_from_mineru(mtype, text_level, source)
    if not source and meta.get("image_path"):
        source = Path(str(meta["image_path"])).stem
    return ContentBlock(
        id=new_id("b"),
        type=btype,  # type: ignore[arg-type]
        page=page,
        order=order,
        bbox=bbox,
        source_text=source,
        sentences=_sentences_from(source, bbox) if source else [],
        spans=spans,
        segments=segments,
        meta=meta,
    )


def _iter_para_blocks(blocks: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """展开 image/table/chart 容器，产出 (logical_type, block)。"""
    out: list[tuple[str, dict[str, Any]]] = []
    for block in blocks or []:
        mtype = str(block.get("type") or "text")
        if mtype in _CONTAINER_TYPES:
            nested = block.get("blocks") or []
            if nested:
                for child in nested:
                    ctype = str(child.get("type") or mtype)
                    if ctype in _BODY_TYPES:
                        logical = "figure" if "table" not in ctype else "table"
                        if "table" in ctype:
                            logical = "table"
                        elif "image" in ctype or "chart" in ctype:
                            logical = "figure"
                        elif "code" in ctype:
                            logical = "code"
                        else:
                            logical = mtype
                        merged = dict(child)
                        if not merged.get("bbox"):
                            merged["bbox"] = block.get("bbox")
                        out.append((logical, merged))
                    elif ctype in _CAPTION_TYPES:
                        out.append(("caption", child))
                    else:
                        out.append((ctype, child))
            else:
                logical = "table" if mtype == "table" else "figure"
                out.append((logical, block))
            continue
        if mtype == "list":
            if block.get("blocks"):
                for child in block["blocks"]:
                    out.append(("list_item", child))
            else:
                out.append(("list_item", block))
            continue
        out.append((mtype, block))
    return out


def document_from_middle(
    middle: dict[str, Any],
    *,
    paper_id: str,
    parser: str,
    parser_version: str,
    image_map: dict[str, str],
) -> Document:
    pdf_info = middle.get("pdf_info") or []
    pages: list[PageLayout] = []
    flat: list[ContentBlock] = []
    toc: list[TocItem] = []
    title: str | None = None
    order = 0
    carry: list[dict[str, Any]] = []

    for page_info in pdf_info:
        page_idx = int(page_info.get("page_idx") or 0)
        page_no = page_idx + 1
        size = page_info.get("page_size") or [612.0, 792.0]
        width, height = float(size[0]), float(size[1])
        page_images: list[dict[str, Any]] = []
        page_blocks: list[ContentBlock] = []

        para = list(page_info.get("para_blocks") or page_info.get("preproc_blocks") or [])
        if carry:
            para = carry + para
            carry = []
        for logical, raw in _iter_para_blocks(para):
            overflow = _split_page_overflow_lines(raw, height)
            if overflow:
                continuation_id = new_id("flow")
                raw["_paperlens_continues_to"] = continuation_id
                overflow["_paperlens_continues_from"] = continuation_id
                carry.append(overflow)
            bbox = _content_bbox_from_lines(raw) or _as_bbox(raw.get("bbox"))
            spans, segments, source = _lines_to_spans_segments(raw, image_map)
            img_raw = _collect_span_image(raw)
            img_path = resolve_image_path(img_raw, image_map)
            meta: dict[str, Any] = {}
            if raw.get("_paperlens_continues_from"):
                meta["continues_from"] = str(raw["_paperlens_continues_from"])
            if raw.get("_paperlens_continues_to"):
                meta["continues_to"] = str(raw["_paperlens_continues_to"])
            if img_path:
                meta["image_path"] = img_path
                meta["kind"] = "formula" if logical in {"formula", "interline_equation", "equation"} else (
                    "table" if logical == "table" else ("code" if logical == "code" else "figure")
                )
                img_id = new_id("img")
                meta["image_id"] = img_id
                if meta["kind"] != "formula":
                    page_images.append(
                        {
                            "id": img_id,
                            "page": page_no,
                            "bbox": bbox,
                            "path": img_path,
                            "kind": meta["kind"],
                        }
                    )

            if not source and not img_path and not spans:
                continue
            level = raw.get("level") or raw.get("text_level")
            level_i = int(level) if level is not None else None
            if logical == "code":
                meta.setdefault("kind", "code")
            block = _emit_content_block(
                mtype=logical,
                page=page_no,
                order=order,
                bbox=bbox,
                source=source,
                spans=spans,
                segments=segments,
                meta=meta,
                text_level=level_i,
            )
            order += 1
            page_blocks.append(block)
            flat.append(block)
            if block.type in {"title", "section"} and block.source_text:
                if title is None and block.type == "title":
                    title = block.source_text[:512]
                toc.append(
                    TocItem(
                        id=new_id("toc"),
                        title=block.source_text[:200],
                        page=page_no,
                        level=level_i or (1 if block.type == "title" else 2),
                        block_id=block.id,
                    )
                )

        pages.append(
            PageLayout(
                page=page_no,
                width=width,
                height=height,
                blocks=page_blocks,
                images=page_images,
            )
        )

    if title is None:
        for b in flat:
            if b.type == "section" and b.source_text:
                title = b.source_text[:512]
                break

    _stitch_cross_page_sentences(pages)
    return Document(
        paper_id=paper_id,
        parser=parser,
        parser_version=parser_version,
        page_count=len(pages),
        title=title,
        pages=pages,
        toc=toc,
        blocks=flat,
    )


def document_from_content_list(
    items: list[dict[str, Any]],
    *,
    paper_id: str,
    parser: str,
    parser_version: str,
    image_map: dict[str, str],
    page_sizes: list[tuple[float, float]],
) -> Document:
    """content_list bbox 为 0–1000，需按页宽高还原。"""
    page_count = max((int(it.get("page_idx") or 0) + 1 for it in items), default=len(page_sizes))
    if page_count < 1:
        page_count = max(len(page_sizes), 1)
    while len(page_sizes) < page_count:
        page_sizes.append((612.0, 792.0))

    pages_blocks: list[list[ContentBlock]] = [[] for _ in range(page_count)]
    pages_images: list[list[dict[str, Any]]] = [[] for _ in range(page_count)]
    flat: list[ContentBlock] = []
    toc: list[TocItem] = []
    title: str | None = None
    order = 0

    for it in items:
        page_idx = int(it.get("page_idx") or 0)
        page_no = page_idx + 1
        width, height = page_sizes[page_idx] if page_idx < len(page_sizes) else (612.0, 792.0)
        bbox = _denorm_bbox(_as_bbox(it.get("bbox")), width, height)
        mtype = str(it.get("type") or "text")
        text_level = it.get("text_level")
        level_i = int(text_level) if text_level is not None else None
        source = str(it.get("text") or it.get("content") or "").strip()
        source = _join_text([source]) if source else ""
        latex = str(it.get("latex") or it.get("text") or "").strip() if mtype in {"equation", "interline_equation"} else ""
        img_path = resolve_image_path(it.get("img_path") or it.get("image_path"), image_map)

        spans: list[TextSpan] = []
        segments: list[RichSegment] = []
        meta: dict[str, Any] = {}
        if img_path:
            meta["image_path"] = img_path
            meta["kind"] = "table" if mtype == "table" else ("formula" if mtype in {"equation"} else "figure")
            img_id = new_id("img")
            meta["image_id"] = img_id
            pages_images[page_idx].append(
                {"id": img_id, "page": page_no, "bbox": bbox, "path": img_path, "kind": meta["kind"]}
            )
        if latex:
            segments.append(
                RichSegment(kind="math", text=latex, latex=latex, bbox=bbox, display=True)
            )
            source = source or latex
        elif source:
            segments.append(RichSegment(kind="text", text=source, bbox=bbox))
            spans.append(
                TextSpan(
                    id=new_id("sp"),
                    text=source,
                    bbox=bbox,
                    font_size=max(8.0, bbox[3] - bbox[1]),
                    origin_y=bbox[3],
                )
            )

        logical = mtype
        if mtype in {"image", "chart"}:
            logical = "figure"
        block = _emit_content_block(
            mtype=logical,
            page=page_no,
            order=order,
            bbox=bbox,
            source=source,
            spans=spans,
            segments=segments,
            meta=meta,
            text_level=level_i,
        )
        order += 1
        pages_blocks[page_idx].append(block)
        flat.append(block)
        if block.type in {"title", "section"} and block.source_text:
            if title is None and block.type == "title":
                title = block.source_text[:512]
            toc.append(
                TocItem(
                    id=new_id("toc"),
                    title=block.source_text[:200],
                    page=page_no,
                    level=level_i or 1,
                    block_id=block.id,
                )
            )

    pages = [
        PageLayout(
            page=i + 1,
            width=page_sizes[i][0],
            height=page_sizes[i][1],
            blocks=pages_blocks[i],
            images=pages_images[i],
        )
        for i in range(page_count)
    ]
    return Document(
        paper_id=paper_id,
        parser=parser,
        parser_version=parser_version,
        page_count=page_count,
        title=title,
        pages=pages,
        toc=toc,
        blocks=flat,
    )


def pdf_page_sizes(pdf_path: Path) -> list[tuple[float, float]]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        return [(float(p.rect.width), float(p.rect.height)) for p in doc]
    finally:
        doc.close()


def find_json(root: Path, *suffixes: str) -> Path | None:
    for suf in suffixes:
        hits = sorted(root.rglob(f"*{suf}"))
        if hits:
            return hits[0]
    return None
