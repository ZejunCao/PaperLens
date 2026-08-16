"""用原 PDF 的字号/字体补全 MinerU 版式（middle.json 通常没有 font_size）。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.parsers.utils import new_id
from app.schemas.document import Document, TextSpan

logger = logging.getLogger("paperlens.parser.layout")

_FIG_CAPTION = re.compile(r"^\s*Figure\s+\d+", re.I)
_BOLD_FONT = re.compile(r"bold|medi|black|heavy|cmbx", re.I)
_ITALIC_FONT = re.compile(r"italic|oblique|cmmi", re.I)
_MATH_FONT = re.compile(r"cmmi|cmsy|cmex|msam|msbm|math|symbol|stix|cambria.?math", re.I)


def _center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _expand(bbox: list[float], pad: float) -> list[float]:
    return [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad]


def _contains_point(bbox: list[float], x: float, y: float) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _hits_in_bbox(line_bbox: list[float], pdf_spans: list[dict[str, Any]], pad: float) -> list[dict[str, Any]]:
    region = _expand(line_bbox, pad)
    hits: list[dict[str, Any]] = []
    for sp in pdf_spans:
        bb = sp.get("bbox") or [0, 0, 0, 0]
        cx, cy = _center([float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])])
        if _contains_point(region, cx, cy):
            hits.append(sp)
    return hits


def _is_bold(sp: dict[str, Any]) -> bool:
    flags = int(sp.get("flags") or 0)
    font = str(sp.get("font") or sp.get("font_name") or "")
    return (flags & 16) != 0 or bool(_BOLD_FONT.search(font))


def _is_italic(sp: dict[str, Any]) -> bool:
    flags = int(sp.get("flags") or 0)
    font = str(sp.get("font") or sp.get("font_name") or "")
    return (flags & 2) != 0 or bool(_ITALIC_FONT.search(font))


def _style_key(sp: dict[str, Any]) -> tuple[bool, bool, int]:
    color = int(sp.get("color") or 0)
    return (_is_bold(sp), _is_italic(sp), color)


def _join_pdf_parts(parts: list[dict[str, Any]]) -> str:
    """PDF span 常不含空格，用框间距补回。"""
    if not parts:
        return ""
    out = str(parts[0].get("text") or "")
    for prev, cur in zip(parts, parts[1:]):
        t = str(cur.get("text") or "")
        if not t:
            continue
        gap = float(cur["bbox"][0]) - float(prev["bbox"][2])
        if (
            out
            and gap > 1.15
            and not out[-1].isspace()
            and not t[0].isspace()
            and t[0] not in ".,;:!?)]}%'\"”’"
            and out[-1] not in "([{'\"“‘"
        ):
            out += " "
        out += t
    return out


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _mineru_slices(mineru: str, group_texts: list[str]) -> list[str] | None:
    """按 PDF 各组的去空格串，从 MinerU 原文切回带空格的片段。"""
    ns = _nospace(mineru)
    mapping: list[int] = [i for i, ch in enumerate(mineru) if not ch.isspace()]
    if not ns or len(mapping) != len(ns):
        return None
    ns_l = ns.lower()
    cursor = 0
    cuts: list[int] = []
    for g in group_texts:
        ng = _nospace(g)
        if not ng:
            return None
        at = ns_l.find(ng.lower(), cursor)
        if at < 0:
            return None
        cuts.append(mapping[at])
        cursor = at + len(ng)
    slices: list[str] = []
    for i, start in enumerate(cuts):
        end = cuts[i + 1] if i + 1 < len(cuts) else len(mineru)
        piece = mineru[start:end]
        if not piece.strip():
            return None
        slices.append(piece)
    return slices


def _span_from_pdf_group(parts: list[dict[str, Any]], text: str) -> TextSpan:
    first = parts[0]
    boxes = [p["bbox"] for p in parts]
    bbox = [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]
    origin = first.get("origin")
    origin_y = float(origin[1]) if origin and len(origin) >= 2 else bbox[3]
    asc = first.get("ascender")
    return TextSpan(
        id=new_id("sp"),
        text=text,
        bbox=bbox,
        font_size=float(first.get("size") or 10),
        font_name=first.get("font") or first.get("font_name"),
        color=first.get("color"),
        flags=int(first.get("flags") or 0),
        origin_y=origin_y,
        ascender=float(asc) if asc is not None else None,
    )


def split_line_by_pdf_styles(
    line_bbox: list[float],
    mineru_text: str,
    pdf_spans: list[dict[str, Any]],
    *,
    pad: float = 4.0,
) -> list[TextSpan] | None:
    """同一行里段首加粗、蓝色引用等，按 PDF 字体切开。"""
    line_cy = (line_bbox[1] + line_bbox[3]) / 2.0
    y_tol = max(3.5, (line_bbox[3] - line_bbox[1]) * 0.55)
    hits = [
        sp
        for sp in _hits_in_bbox(line_bbox, pdf_spans, min(pad, 1.5))
        if not _MATH_FONT.search(str(sp.get("font") or ""))
        and str(sp.get("text") or "").strip()
        and abs(_center(sp["bbox"])[1] - line_cy) <= y_tol
        and sp["bbox"][2] > line_bbox[0] - 2
        and sp["bbox"][0] < line_bbox[2] + 2
    ]
    if len(hits) < 2:
        return None
    hits.sort(key=lambda sp: (float(sp["bbox"][0]), float(sp["bbox"][1])))
    groups: list[tuple[tuple[bool, bool, int], list[dict[str, Any]]]] = []
    for sp in hits:
        key = _style_key(sp)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(sp)
        else:
            groups.append((key, [sp]))
    if len(groups) < 2:
        return None
    pdf_texts = [_join_pdf_parts(parts) for _, parts in groups]
    joined = "".join(pdf_texts)
    compact_a = re.sub(r"\W+", "", mineru_text or "").lower()
    compact_b = re.sub(r"\W+", "", joined).lower()
    if compact_a and compact_b and compact_a[:12] not in compact_b and compact_b[:12] not in compact_a:
        return None
    slices = _mineru_slices(mineru_text or "", pdf_texts)
    texts = slices if slices and len(slices) == len(groups) else pdf_texts
    return [_span_from_pdf_group(parts, txt) for (_, parts), txt in zip(groups, texts)]


def style_from_pdf_spans(
    line_bbox: list[float],
    pdf_spans: list[dict[str, Any]],
    *,
    pad: float = 4.0,
) -> dict[str, Any] | None:
    """在行框内找 PDF span，取字符最多的那一截作为主字号。"""
    hits = _hits_in_bbox(line_bbox, pdf_spans, pad)
    if not hits:
        return None
    weighted = [(max(len(str(sp.get("text") or "").strip()), 1), sp) for sp in hits]
    _, main = max(weighted, key=lambda item: item[0])
    origin = main.get("origin")
    origin_y: float | None = None
    if origin and len(origin) >= 2:
        origin_y = float(origin[1])
    elif main.get("bbox") and len(main["bbox"]) >= 4:
        origin_y = float(main["bbox"][3])
    asc = main.get("ascender")
    return {
        "font_size": float(main.get("size") or 0) or None,
        "font_name": main.get("font") or main.get("font_name"),
        "flags": int(main.get("flags") or 0),
        "color": main.get("color"),
        "origin_y": origin_y,
        "ascender": float(asc) if asc is not None else None,
    }


def _apply_style(span: TextSpan, style: dict[str, Any]) -> None:
    size = style.get("font_size")
    if size and size > 1:
        span.font_size = float(size)
    if style.get("font_name"):
        span.font_name = str(style["font_name"])
    if style.get("flags") is not None:
        span.flags = int(style["flags"])
    if style.get("color") is not None:
        span.color = int(style["color"])
    if style.get("origin_y") is not None:
        span.origin_y = float(style["origin_y"])
    if style.get("ascender") is not None:
        span.ascender = float(style["ascender"])


def _page_pdf_spans(page: Any) -> list[dict[str, Any]]:
    import fitz

    flags = getattr(fitz, "TEXT_PRESERVE_WHITESPACE", 0)
    raw = page.get_text("dict", flags=flags)
    out: list[dict[str, Any]] = []
    for block in raw.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for sp in line.get("spans") or []:
                text = sp.get("text") or ""
                if not text:
                    continue
                bb = sp.get("bbox") or [0, 0, 0, 0]
                out.append(
                    {
                        "text": text,
                        "bbox": [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])],
                        "size": float(sp.get("size") or 0),
                        "font": sp.get("font"),
                        "flags": int(sp.get("flags") or 0),
                        "color": sp.get("color"),
                        "origin": sp.get("origin"),
                        "ascender": sp.get("ascender"),
                    }
                )
    return out


def _extend_incomplete_figures(page: Any, pdf_page: Any, images_dir: Path) -> None:
    """MinerU 常只裁到图的上半幅；若下方直到 Figure 标题之间是空档，从 PDF 补裁。"""
    import fitz

    images_dir.mkdir(parents=True, exist_ok=True)
    captions = [
        b
        for b in page.blocks
        if _FIG_CAPTION.match((b.source_text or "").strip())
    ]
    for fig in page.blocks:
        if fig.type != "figure" or not fig.bbox or len(fig.bbox) < 4:
            continue
        below = [c for c in captions if c.bbox[1] > fig.bbox[3] - 4]
        if not below:
            continue
        cap = min(below, key=lambda c: c.bbox[1])
        gap = cap.bbox[1] - fig.bbox[3]
        if gap < 36:
            continue
        y0, y1 = fig.bbox[3] + 1, cap.bbox[1] - 2
        blocked = False
        for other in page.blocks:
            if other.id in {fig.id, cap.id}:
                continue
            if other.type in {"figure", "caption"}:
                continue
            oy0, oy1 = other.bbox[1], other.bbox[3]
            if min(oy1, y1) - max(oy0, y0) < 10:
                continue
            if other.type == "paragraph" and len(other.source_text or "") > 48:
                blocked = True
                break
        if blocked:
            continue
        x0, x1 = fig.bbox[0], fig.bbox[2]
        new_bbox = [x0, fig.bbox[1], x1, y1]
        name = f"fig_ext_{fig.id}.jpg"
        dest = images_dir / name
        clip = fitz.Rect(new_bbox[0], new_bbox[1], new_bbox[2], new_bbox[3]) & pdf_page.rect
        if clip.is_empty or clip.height < 20:
            continue
        try:
            pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip, alpha=False)
            pix.save(dest.as_posix())
        except Exception:  # noqa: BLE001
            continue
        fig.bbox = new_bbox
        path = f"images/{name}"
        fig.meta["image_path"] = path
        updated = False
        for img in page.images or []:
            if img.get("id") == fig.meta.get("image_id") or img.get("path") == path:
                img["bbox"] = new_bbox
                img["path"] = path
                updated = True
                break
        if not updated:
            page.images.append(
                {
                    "id": fig.meta.get("image_id") or new_id("img"),
                    "page": page.page,
                    "bbox": new_bbox,
                    "path": path,
                    "kind": "figure",
                }
            )
        for other in page.blocks:
            if other.id in {fig.id, cap.id}:
                continue
            if _FIG_CAPTION.match((other.source_text or "").strip()):
                continue
            oy0, oy1 = other.bbox[1], other.bbox[3]
            if min(oy1, new_bbox[3]) - max(oy0, new_bbox[1]) < 8:
                continue
            if other.type in {"caption", "paragraph", "other"}:
                other.meta["layout_skip"] = True


def enrich_layout_from_pdf(document: Document, pdf_path: Path | None) -> Document:
    """就地写入 PDF 字号；失败则保持 bbox 估算。"""
    if pdf_path is None or not Path(pdf_path).exists():
        return document
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return document

    try:
        pdf = fitz.open(pdf_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("无法打开 PDF 补字号: %s", e)
        return document

    try:
        from app.config import get_settings

        images_dir = get_settings().papers_dir / document.paper_id / "images"
        for page in document.pages:
            idx = page.page - 1
            if idx < 0 or idx >= pdf.page_count:
                continue
            pdf_page = pdf.load_page(idx)
            _extend_incomplete_figures(page, pdf_page, images_dir)
            pdf_spans = _page_pdf_spans(pdf_page)
            if not pdf_spans:
                continue
            for block in page.blocks:
                new_spans: list[TextSpan] = []
                for span in block.spans:
                    if "\\" in (span.text or ""):
                        new_spans.append(span)
                        continue
                    split = split_line_by_pdf_styles(span.bbox, span.text, pdf_spans)
                    if split:
                        new_spans.extend(split)
                        continue
                    style = style_from_pdf_spans(span.bbox, pdf_spans)
                    if style and style.get("font_size"):
                        _apply_style(span, style)
                    new_spans.append(span)
                block.spans = new_spans
                for span in block.spans:
                    if span.font_size and not (block.segments or []):
                        continue
                    for seg in block.segments or []:
                        if seg.kind != "text" or not seg.bbox:
                            continue
                        if abs(seg.bbox[1] - span.bbox[1]) < 2 and abs(seg.bbox[0] - span.bbox[0]) < 2:
                            seg.font_size = span.font_size
                            seg.origin_y = span.origin_y
    finally:
        pdf.close()
    return document


def clip_math_from_pdf(document: Document, pdf_path: Path | None, images_dir: Path) -> Document:
    """行内/独立公式按 bbox 从原 PDF 裁图，避免把 LaTeX 源码画在版式上。"""
    if pdf_path is None or not Path(pdf_path).exists():
        return document
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return document
    try:
        pdf = fitz.open(pdf_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("无法打开 PDF 裁公式: %s", e)
        return document

    images_dir.mkdir(parents=True, exist_ok=True)
    zoom = 3.0
    mat = fitz.Matrix(zoom, zoom)
    try:
        for page in document.pages:
            idx = page.page - 1
            if idx < 0 or idx >= pdf.page_count:
                continue
            pdf_page = pdf.load_page(idx)
            n = 0
            for block in page.blocks:
                for seg in block.segments:
                    if seg.kind != "math" or not seg.bbox or len(seg.bbox) < 4:
                        continue
                    x0, y0, x1, y1 = (float(v) for v in seg.bbox[:4])
                    if (x1 - x0) < 4 or (y1 - y0) < 3:
                        continue
                    pad = 0.8
                    clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & pdf_page.rect
                    if clip.is_empty or clip.width < 2 or clip.height < 2:
                        continue
                    body = float(seg.font_size or 10)
                    if not seg.display and clip.height > max(body * 1.8, 14):
                        cy = 0.5 * (clip.y0 + clip.y1)
                        half = max(body * 0.85, 6)
                        clip = fitz.Rect(clip.x0, cy - half, clip.x1, cy + half) & pdf_page.rect
                    name = f"p{page.page}_im{n}.png"
                    dest = images_dir / name
                    try:
                        pix = pdf_page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                        pix.save(dest.as_posix())
                    except Exception:  # noqa: BLE001
                        continue
                    seg.image_path = f"images/{name}"
                    seg.bbox = [float(clip.x0), float(clip.y0), float(clip.x1), float(clip.y1)]
                    n += 1
    finally:
        pdf.close()
    return document
