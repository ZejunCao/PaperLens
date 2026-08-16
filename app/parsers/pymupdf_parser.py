"""基于 PyMuPDF 的版式解析器：保留页内坐标，便于网页复现原排版。

图/表与公式优先按区域裁剪成位图原样保存；图/公式内文字不再单独抽成文本。
侧边 arXiv / 来源类竖排页眉忽略。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

from app.parsers.base import BaseParser, ParserError
from app.parsers.utils import new_id, split_sentences
from app.parsers.latex_rebuild import segments_plain_text, spans_to_segments
from app.schemas.document import (
    ContentBlock,
    Document,
    PageLayout,
    Sentence,
    TextSpan,
    TocItem,
)

_SOURCE_RE = re.compile(
    r"(arxiv\s*:|doi\s*:|openreview\.net|creativecommons\.org|licensed under)",
    re.I,
)
_MATH_FONT_RE = re.compile(
    r"(CMEX|CMSY|CMMI|CMMIB|CMR\d|CMBX|MSBM|MSAM|EUEX|EUFM)",
    re.I,
)
_BODY_FONT_RE = re.compile(
    r"(Nimbus|TimesNewRoman|Times-Roman|LiberationSerif|Liberation|Arial|Helvetica|"
    r"Minion|Palatino|Charter|DejaVu|Ghostscript)",
    re.I,
)


def _rect_area(r: fitz.Rect) -> float:
    return abs(r.width * r.height)


def _merge_rects(rects: list[fitz.Rect], gap: float = 8.0) -> list[fitz.Rect]:
    """合并相交或邻近的矩形。"""
    boxes = [fitz.Rect(r) for r in rects if r.width > 1 and r.height > 1]
    if not boxes:
        return []

    changed = True
    while changed:
        changed = False
        out: list[fitz.Rect] = []
        used = [False] * len(boxes)
        for i, a in enumerate(boxes):
            if used[i]:
                continue
            cur = fitz.Rect(a)
            used[i] = True
            growing = True
            while growing:
                growing = False
                pad = fitz.Rect(cur.x0 - gap, cur.y0 - gap, cur.x1 + gap, cur.y1 + gap)
                for j, b in enumerate(boxes):
                    if used[j]:
                        continue
                    if pad.intersects(b):
                        cur |= b
                        used[j] = True
                        growing = True
                        changed = True
                        pad = fitz.Rect(cur.x0 - gap, cur.y0 - gap, cur.x1 + gap, cur.y1 + gap)
            out.append(cur)
        boxes = out
    return boxes


def _point_in_rects(x: float, y: float, rects: list[fitz.Rect], pad: float = 1.0) -> bool:
    for r in rects:
        if (r.x0 - pad) <= x <= (r.x1 + pad) and (r.y0 - pad) <= y <= (r.y1 + pad):
            return True
    return False


def _span_overlap_ratio(bbox: list[float], rects: list[fitz.Rect]) -> float:
    """span 与任一矩形相交面积 / span 面积。"""
    x0, y0, x1, y1 = bbox
    span = fitz.Rect(x0, y0, x1, y1)
    area = _rect_area(span)
    if area <= 0:
        return 0.0
    best = 0.0
    for r in rects:
        inter = span & r
        if not inter.is_empty:
            best = max(best, _rect_area(inter) / area)
    return best


def _is_vertical_dir(direction: tuple[float, float] | list[float] | None) -> bool:
    if not direction or len(direction) < 2:
        return False
    dx, dy = float(direction[0]), float(direction[1])
    return abs(dx) < 0.35 and abs(dy) > 0.65


def _is_margin_source(
    text: str,
    bbox: list[float],
    page_w: float,
    page_h: float,
    direction: tuple[float, float] | list[float] | None,
) -> bool:
    """侧边来源标识（如竖排 arXiv 行）不进入正文。"""
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    margin_x = max(36.0, page_w * 0.07)
    margin_y = max(28.0, page_h * 0.04)
    near_side = cx <= margin_x or cx >= page_w - margin_x
    near_edge = near_side or cy <= margin_y or cy >= page_h - margin_y
    tall_thin = (y1 - y0) > max(40.0, 3.0 * max(x1 - x0, 1.0))

    if _is_vertical_dir(direction) and near_side:
        return True
    if near_edge and _SOURCE_RE.search(text):
        return True
    if tall_thin and near_side and ("arxiv" in text.lower() or _SOURCE_RE.search(text)):
        return True
    return False


class PyMuPDFParser(BaseParser):
    name = "pymupdf"
    version = "10"

    def parse(self, pdf_path: Path, paper_id: str, output_dir: Path) -> Document:
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir = output_dir / "images"
        if images_dir.exists():
            for old in images_dir.glob("*"):
                if old.is_file():
                    old.unlink(missing_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:  # noqa: BLE001
            raise ParserError(f"无法打开 PDF: {e}") from e

        pages: list[PageLayout] = []
        flat_blocks: list[ContentBlock] = []
        toc: list[TocItem] = []
        order = 0
        font_sizes: list[float] = []

        try:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                page_no = page_index + 1
                width, height = float(page.rect.width), float(page.rect.height)
                page_area = width * height
                raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

                figure_rects = self._collect_figure_rects(page, raw, page_area)
                formula_rects = self._collect_formula_rects(raw, page_area, figure_rects)
                suppress_rects = figure_rects + formula_rects

                images = self._export_clip_images(
                    page, page_no, figure_rects, images_dir, prefix="fig", kind="figure"
                )
                formula_images = self._export_clip_images(
                    page, page_no, formula_rects, images_dir, prefix="eq", kind="formula"
                )
                images.extend(formula_images)

                page_blocks: list[ContentBlock] = []
                for block in raw.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    spans: list[TextSpan] = []
                    texts: list[str] = []
                    bx0, by0, bx1, by1 = width, height, 0.0, 0.0
                    max_size = 0.0

                    for line in block.get("lines", []):
                        direction = line.get("dir") or (1.0, 0.0)
                        for span in line.get("spans", []):
                            text = span.get("text") or ""
                            if not text.strip() and text != " ":
                                continue
                            sb = span.get("bbox", [0, 0, 0, 0])
                            sb_list = [float(sb[0]), float(sb[1]), float(sb[2]), float(sb[3])]
                            if _is_margin_source(text, sb_list, width, height, direction):
                                continue
                            if _span_overlap_ratio(sb_list, suppress_rects) >= 0.35:
                                continue
                            # TeX 特殊符号抽失败时的占位符，不进入正文
                            if "\ufffd" in text:
                                continue
                            size = float(span.get("size") or 12)
                            font_sizes.append(size)
                            max_size = max(max_size, size)
                            bx0 = min(bx0, sb_list[0])
                            by0 = min(by0, sb_list[1])
                            bx1 = max(bx1, sb_list[2])
                            by1 = max(by1, sb_list[3])
                            origin = span.get("origin")
                            origin_y = float(origin[1]) if origin and len(origin) >= 2 else sb_list[3]
                            asc = span.get("ascender")
                            asc_f = float(asc) if asc is not None else None
                            # 正文 span 的 origin 有时会被上一枚下标“污染”，导致整句被画成下标
                            font_name = span.get("font") or ""
                            if _BODY_FONT_RE.search(font_name):
                                expected_oy = sb_list[1] + size * min(max(asc_f or 0.85, 0.6), 0.95)
                                if origin_y > expected_oy + size * 0.08:
                                    origin_y = expected_oy
                            spans.append(
                                TextSpan(
                                    id=new_id("span"),
                                    text=text,
                                    bbox=sb_list,
                                    font_size=size,
                                    font_name=font_name,
                                    color=span.get("color"),
                                    flags=int(span.get("flags") or 0),
                                    origin_y=origin_y,
                                    ascender=asc_f,
                                )
                            )
                            texts.append(text)

                    source = "".join(texts).strip()
                    if not source and not spans:
                        continue

                    bbox = [bx0, by0, bx1, by1]
                    segments = spans_to_segments(spans)
                    # 有公式片段时，纯文本摘要带 $...$，便于检索；展示以 segments 为准
                    if any(s.kind == "math" for s in segments):
                        source = segments_plain_text(segments).strip() or source
                    block_type = self._classify(source, max_size, font_sizes)
                    sentences = [
                        Sentence(id=new_id("sent"), text=s, order=i)
                        for i, s in enumerate(split_sentences(re.sub(r"\$[^$]*\$", " ", source)))
                    ]
                    content = ContentBlock(
                        id=new_id("block"),
                        type=block_type,
                        page=page_no,
                        order=order,
                        bbox=bbox,
                        source_text=source,
                        sentences=sentences,
                        spans=spans,
                        segments=segments,
                    )
                    order += 1
                    page_blocks.append(content)

                    if block_type in ("title", "section"):
                        level = 1 if block_type == "title" else 2
                        toc.append(
                            TocItem(
                                id=new_id("toc"),
                                title=source[:200],
                                page=page_no,
                                level=level,
                                block_id=content.id,
                            )
                        )

                # 合并被 PyMuPDF 拆碎的相邻正文块，减轻「换行错位 / 楼梯缩进」
                page_blocks = self._merge_nearby_text_blocks(page_blocks)
                # 左侧保真：置信行内公式裁成位图（latex 仍保留供复制/右侧）
                self._export_inline_math_images(page, page_no, page_blocks, images_dir)

                for img in images:
                    block_type = "formula" if img.get("kind") == "formula" else "figure"
                    fig_block = ContentBlock(
                        id=new_id("block"),
                        type=block_type,
                        page=page_no,
                        order=order,
                        bbox=img["bbox"],
                        source_text="",
                        sentences=[],
                        spans=[],
                        meta={
                            "image_path": img["path"],
                            "image_id": img["id"],
                            "kind": img.get("kind", "figure"),
                        },
                    )
                    order += 1
                    page_blocks.append(fig_block)

                for b in page_blocks:
                    flat_blocks.append(b)

                pages.append(
                    PageLayout(
                        page=page_no,
                        width=width,
                        height=height,
                        blocks=page_blocks,
                        images=images,
                    )
                )
        finally:
            doc.close()

        flat_blocks.sort(key=lambda b: (b.page, b.bbox[1], b.bbox[0]))
        for i, b in enumerate(flat_blocks):
            b.order = i

        title = None
        for b in flat_blocks[:12]:
            if b.type == "title" and b.source_text:
                title = b.source_text[:300]
                break
        if not title:
            for b in flat_blocks:
                if b.source_text:
                    title = b.source_text[:300]
                    break

        document = Document(
            paper_id=paper_id,
            parser=self.name,
            parser_version=self.version,
            page_count=len(pages),
            title=title,
            pages=pages,
            toc=toc,
            blocks=flat_blocks,
        )

        (output_dir / "raw_pymupdf.json").write_text(
            json.dumps(
                {
                    "page_count": len(pages),
                    "block_count": len(flat_blocks),
                    "image_count": sum(len(p.images) for p in pages),
                    "formula_count": sum(1 for b in flat_blocks if b.type == "formula"),
                    "parser_version": self.version,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return document

    def _merge_nearby_text_blocks(self, blocks: list[ContentBlock]) -> list[ContentBlock]:
        """仅合并「上一行未写满 + 下一行接续」的碎块，避免整页粘成一段。"""
        if not blocks:
            return blocks
        out: list[ContentBlock] = []
        for b in blocks:
            if not out or b.type in ("figure", "formula", "title") or out[-1].type in (
                "figure",
                "formula",
                "title",
            ):
                out.append(b)
                continue
            prev = out[-1]
            gap = b.bbox[1] - prev.bbox[3]
            # 只接受紧邻换行；大幅重叠多半是并列碎片，勿盲合并
            if gap > 5.0 or gap < -2.5:
                out.append(b)
                continue
            if b.page != prev.page:
                out.append(b)
                continue
            # 上一块明显写满整行且本块也是整行 → 新段落，不合并
            prev_w = prev.bbox[2] - prev.bbox[0]
            cur_w = b.bbox[2] - b.bbox[0]
            if prev_w > 380 and cur_w > 380 and gap > 1.0:
                out.append(b)
                continue
            if len(prev.spans) + len(b.spans) > 80:
                out.append(b)
                continue

            spans = list(prev.spans) + list(b.spans)
            spans.sort(key=lambda s: (s.bbox[1], s.bbox[0]))
            segments = spans_to_segments(spans)
            source = (
                segments_plain_text(segments).strip()
                if any(s.kind == "math" for s in segments)
                else (prev.source_text + b.source_text).strip()
            )
            bbox = [
                min(prev.bbox[0], b.bbox[0]),
                min(prev.bbox[1], b.bbox[1]),
                max(prev.bbox[2], b.bbox[2]),
                max(prev.bbox[3], b.bbox[3]),
            ]
            prev.spans = spans
            prev.segments = segments
            prev.source_text = source
            prev.bbox = bbox
            prev.sentences = [
                Sentence(id=new_id("sent"), text=s, order=i)
                for i, s in enumerate(split_sentences(re.sub(r"\$[^$]*\$", " ", source)))
            ]
        return out

    def _export_inline_math_images(
        self,
        page: fitz.Page,
        page_no: int,
        blocks: list[ContentBlock],
        images_dir: Path,
    ) -> None:
        """把置信行内公式按 bbox 裁成 PNG，左侧叠图对齐原版式。"""
        zoom = 3.0
        mat = fitz.Matrix(zoom, zoom)
        idx = 0
        for block in blocks:
            for seg in block.segments:
                if seg.kind != "math" or not seg.latex or not seg.bbox or len(seg.bbox) < 4:
                    continue
                x0, y0, x1, y1 = seg.bbox
                # 过小的碎片跳过
                if (x1 - x0) < 6 or (y1 - y0) < 4:
                    continue
                pad = 0.8
                clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
                if clip.is_empty or clip.width < 2 or clip.height < 2:
                    continue
                # 再限制高度，防止裁进邻行
                if clip.height > max((seg.font_size or 10) * 1.7, 14):
                    cy = 0.5 * (clip.y0 + clip.y1)
                    half = max((seg.font_size or 10) * 0.85, 6)
                    clip = fitz.Rect(clip.x0, cy - half, clip.x1, cy + half) & page.rect
                img_name = f"p{page_no}_im{idx}.png"
                img_path = images_dir / img_name
                try:
                    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                    pix.save(img_path.as_posix())
                except Exception:  # noqa: BLE001
                    continue
                seg.image_path = f"images/{img_name}"
                # 同步裁剪后的 bbox，便于前端贴齐
                seg.bbox = [clip.x0, clip.y0, clip.x1, clip.y1]
                idx += 1

    def _collect_figure_rects(self, page: fitz.Page, raw: dict, page_area: float) -> list[fitz.Rect]:
        candidates: list[fitz.Rect] = []

        for block in raw.get("blocks", []):
            if block.get("type") == 1:
                bb = block.get("bbox")
                if bb:
                    r = fitz.Rect(bb)
                    if _rect_area(r) >= 80:
                        candidates.append(r)

        try:
            for info in page.get_image_info(xrefs=True):
                bb = info.get("bbox")
                if not bb:
                    continue
                r = fitz.Rect(bb)
                if _rect_area(r) >= 400:
                    candidates.append(r)
        except Exception:  # noqa: BLE001
            pass

        draw_rects: list[fitz.Rect] = []
        try:
            for d in page.get_drawings():
                rect = d.get("rect")
                if rect is None:
                    continue
                r = fitz.Rect(rect)
                if r.width < 0.5 or r.height < 0.5:
                    continue
                if _rect_area(r) > page_area * 0.9:
                    continue
                draw_rects.append(r)
        except Exception:  # noqa: BLE001
            pass

        if draw_rects:
            merged = _merge_rects(draw_rects, gap=10.0)
            for r in merged:
                area = _rect_area(r)
                if area >= 6000 and area < page_area * 0.88:
                    if r.width >= 40 and r.height >= 40:
                        candidates.append(r)

        merged = _merge_rects(candidates, gap=12.0)
        out: list[fitz.Rect] = []
        for r in merged:
            area = _rect_area(r)
            if area < 400:
                continue
            if area > page_area * 0.92:
                continue
            pad = 2.0
            rr = fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad) & page.rect
            if rr.width > 2 and rr.height > 2:
                out.append(rr)
        return out

    def _collect_formula_rects(
        self,
        raw: dict,
        page_area: float,
        figure_rects: list[fitz.Rect],
    ) -> list[fitz.Rect]:
        """把 TeX 公式（CMEX 括号等抽成 �）的区域聚成裁剪框。"""
        _ATTACH_FONT_RE = re.compile(r"(CMMI|CMMIB|CMSY|MSBM|MSAM|CMEX|EUEX|EUFM|CMR\d|CMBX)", re.I)

        blocks_meta: list[dict] = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            bb = block.get("bbox")
            if not bb:
                continue
            rect = fitz.Rect(bb)
            if any(rect.intersects(fr) and _rect_area(rect & fr) > _rect_area(rect) * 0.5 for fr in figure_rects):
                continue

            math_chars = 0
            body_chars = 0
            attach_chars = 0
            bad = 0
            total = 0
            has_cmex = False
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text") or ""
                    font = span.get("font") or ""
                    total += len(text)
                    bad += text.count("\ufffd")
                    if "CMEX" in font.upper():
                        has_cmex = True
                    if _MATH_FONT_RE.search(font):
                        math_chars += len(text)
                    if _ATTACH_FONT_RE.search(font):
                        attach_chars += len(text)
                    if _BODY_FONT_RE.search(font):
                        body_chars += len(text)

            if total == 0:
                continue
            blocks_meta.append(
                {
                    "rect": rect,
                    "total": total,
                    "bad": bad,
                    "has_cmex": has_cmex,
                    "math_chars": math_chars,
                    "body_chars": body_chars,
                    "attach_chars": attach_chars,
                    "is_body": body_chars >= 35 and body_chars >= math_chars * 0.8 and bad == 0 and not has_cmex,
                }
            )

        def band_body_score(y0: float, y1: float) -> int:
            score = 0
            for m in blocks_meta:
                r = m["rect"]
                if r.y1 < y0 or r.y0 > y1:
                    continue
                if m["is_body"]:
                    score += m["body_chars"]
            return score

        seeds: list[fitz.Rect] = []
        for m in blocks_meta:
            if m["bad"] >= 1 or m["has_cmex"]:
                if m["is_body"]:
                    continue
                seeds.append(fitz.Rect(m["rect"]))

        if not seeds:
            return []

        cluster = _merge_rects(seeds, gap=6.0)

        # 反复吸附同一公式带上的数学碎片；跳过正文行带里的 CMR 单词
        changed = True
        while changed:
            changed = False
            for m in blocks_meta:
                if m["is_body"]:
                    continue
                if m["attach_chars"] < 1:
                    continue
                # 过长且含较多正文特征的不吸
                if m["total"] > 60 and m["body_chars"] > 0:
                    continue
                if m["attach_chars"] < max(1, int(m["total"] * 0.5)):
                    continue
                r = fitz.Rect(m["rect"])
                cy0, cy1 = r.y0, r.y1
                # 落在正文主导行带则跳过（避免 ShortConv 等被并进公式）
                if band_body_score(cy0 - 2, cy1 + 2) >= 30:
                    continue
                pad = fitz.Rect(r.x0 - 14, r.y0 - 7, r.x1 + 14, r.y1 + 7)
                if any(pad.intersects(c) for c in cluster):
                    # 已包含则跳过
                    if any(_rect_area(r & c) > _rect_area(r) * 0.85 for c in cluster):
                        continue
                    cluster = _merge_rects([*cluster, r], gap=6.0)
                    changed = True

        out: list[fitz.Rect] = []
        for r in cluster:
            rr = fitz.Rect(r)
            # 若下沿侵入正文块，裁到正文顶
            for m in blocks_meta:
                if not m["is_body"]:
                    continue
                top = m["rect"].y0
                if rr.y0 < top < rr.y1 and (rr.y1 - top) <= max(18.0, rr.height * 0.4):
                    rr.y1 = min(rr.y1, top - 1.0)
            area = _rect_area(rr)
            if area < 280:
                continue
            if area > page_area * 0.55:
                continue
            if rr.height < 10 or rr.width < 20:
                continue
            pad = 2.0
            out.append(fitz.Rect(rr.x0 - pad, rr.y0 - pad, rr.x1 + pad, rr.y1 + pad))
        return out

    def _export_clip_images(
        self,
        page: fitz.Page,
        page_no: int,
        rects: list[fitz.Rect],
        images_dir: Path,
        *,
        prefix: str,
        kind: str,
    ) -> list[dict]:
        images: list[dict] = []
        zoom = 2.5
        mat = fitz.Matrix(zoom, zoom)
        for i, rect in enumerate(rects):
            clip = fitz.Rect(rect) & page.rect
            if clip.is_empty or clip.width < 2 or clip.height < 2:
                continue
            img_name = f"p{page_no}_{prefix}{i}.png"
            img_path = images_dir / img_name
            try:
                pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                pix.save(img_path.as_posix())
            except Exception:  # noqa: BLE001
                continue
            images.append(
                {
                    "id": new_id("img"),
                    "page": page_no,
                    "bbox": [clip.x0, clip.y0, clip.x1, clip.y1],
                    "path": f"images/{img_name}",
                    "kind": kind,
                }
            )
        return images

    def _classify(self, text: str, size: float, all_sizes: list[float]) -> str:
        lower = text.lower().strip()
        if lower.startswith("abstract") or lower == "abstract":
            return "section"
        if lower.startswith("references") or lower.startswith("bibliography"):
            return "section"
        if lower.startswith("figure ") or lower.startswith("fig."):
            return "caption"
        if lower.startswith("table "):
            return "caption"
        if all_sizes:
            median = sorted(all_sizes)[len(all_sizes) // 2]
            if size >= median * 1.55 and len(text) < 180:
                return "title" if size >= median * 1.9 else "section"
            if size >= median * 1.35 and len(text) < 120 and not text.endswith("."):
                return "section"
        if text.startswith("[") and "]" in text[:6]:
            return "reference"
        return "paragraph"
