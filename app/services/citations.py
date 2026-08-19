"""按整篇论文的统一格式识别并清理右栏译文中的行内引用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.schemas.document import Document

CitationStyle = Literal[
    "none",
    "numeric_square",
    "numeric_parenthetical",
    "author_date",
    "author_page",
    "alpha_square",
]


@dataclass(frozen=True)
class CitationProfile:
    style: CitationStyle = "none"
    matches: int = 0


_NUM = r"\d{1,4}[a-z]?"
_NUM_ITEM = rf"{_NUM}(?:\s*[-–—]\s*{_NUM})?"
_NUM_SQUARE_ONE = rf"[\[［](?:{_NUM_ITEM})(?:\s*[,;，；]\s*{_NUM_ITEM})*[\]］]"
_NUM_SQUARE_CLUSTER = re.compile(
    rf"{_NUM_SQUARE_ONE}(?:\s*[,;，；、]\s*{_NUM_SQUARE_ONE})*",
    re.I,
)
_NUM_PAREN = re.compile(
    rf"[（(](?:{_NUM_ITEM})(?:\s*[,;，；]\s*{_NUM_ITEM})*[）)]",
    re.I,
)
_ALPHA_LABEL = r"[A-Za-z][A-Za-z0-9]*(?:[+:.][A-Za-z0-9]+)*(?:[-–]\d{2,4})?"
_ALPHA_SQUARE_ONE = rf"[\[［]{_ALPHA_LABEL}[\]］]"
_ALPHA_SQUARE_CLUSTER = re.compile(
    rf"{_ALPHA_SQUARE_ONE}(?:\s*[,;，；、]\s*{_ALPHA_SQUARE_ONE})*"
)

# 至少包含一个首字母大写的作者/机构词和一个独立年份，避免把 (introduced in 2020) 当引用。
_AUTHOR_DATE = re.compile(
    r"[（(](?=[^()（）]{1,180}[）)])"
    r"(?=[^()（）]*\b(?:[A-Z][\w'’.-]+|[A-Z]{2,})\b)"
    r"(?=[^()（）]*\b(?:19|20)\d{2}[a-z]?\b)"
    r"[^()（）]*[）)]",
    re.UNICODE,
)

# MLA/作者页码形式；不处理单独 (Smith)，因为与普通括号短语太难可靠区分。
_AUTHOR_PAGE = re.compile(
    r"[（(](?:[A-Z][\w'’.-]+(?:\s+(?:and|&|et\s+al\.|[A-Z][\w'’.-]+)){0,4})"
    r"\s+\d{1,4}(?:\s*[-–]\s*\d{1,4})?[）)]",
    re.UNICODE,
)

_REFERENCE_HEADING = re.compile(r"^\s*(?:references|bibliography|works\s+cited)\s*$", re.I)
_SQUARE_REFERENCE = re.compile(r"^\s*\[\d{1,4}\]\s+", re.M)
_PAREN_REFERENCE = re.compile(r"^\s*\(\d{1,4}\)\s+", re.M)
_DOT_REFERENCE = re.compile(r"^\s*\d{1,4}[.)]\s+", re.M)
_SKIP_TYPES = {"formula", "figure", "table", "header", "footer"}


def _ordered_blocks(document: Document):
    if document.blocks:
        return sorted(document.blocks, key=lambda block: block.order)
    return sorted(
        (block for page in document.pages for block in page.blocks),
        key=lambda block: block.order,
    )


def _body_and_reference_texts(document: Document) -> tuple[list[str], list[str]]:
    blocks = _ordered_blocks(document)
    cutoff = len(blocks)
    # 无明确标题/类型时，只在论文后半部附近尝试用连续编号推断参考文献表，
    # 避免把方法章节中的 1) / 2) / 3) 枚举误当成参考文献。
    inferred_reference_start = max(3, int(len(blocks) * 0.35))
    for i, block in enumerate(blocks):
        text = (block.source_text or "").strip()
        if block.type == "reference" or _REFERENCE_HEADING.match(text):
            cutoff = i
            break
        # MinerU 有时不标 reference；连续编号条目可可靠定位参考文献表起点。
        nearby = blocks[i : i + 4]
        current_is_reference = bool(
            _SQUARE_REFERENCE.match(text)
            or _PAREN_REFERENCE.match(text)
            or _DOT_REFERENCE.match(text)
        )
        if i >= inferred_reference_start and current_is_reference and len(nearby) >= 3 and sum(
            bool(
                _SQUARE_REFERENCE.match((item.source_text or "").strip())
                or _PAREN_REFERENCE.match((item.source_text or "").strip())
                or _DOT_REFERENCE.match((item.source_text or "").strip())
            )
            for item in nearby
        ) >= 3:
            cutoff = i
            break

    body = [
        block.source_text
        for block in blocks[:cutoff]
        if block.type not in _SKIP_TYPES and (block.source_text or "").strip()
    ]
    refs = [block.source_text for block in blocks[cutoff:] if (block.source_text or "").strip()]
    return body, refs


def _match_count(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def detect_citation_profile(document: Document) -> CitationProfile:
    """在论文级别选择一种主引用格式；证据不足时保持 none。"""
    body_parts, ref_parts = _body_and_reference_texts(document)
    body = "\n".join(body_parts)
    refs = "\n".join(ref_parts)

    square_count = _match_count(_NUM_SQUARE_CLUSTER, body)
    alpha_count = _match_count(_ALPHA_SQUARE_CLUSTER, body)
    author_date_count = _match_count(_AUTHOR_DATE, body)
    author_page_count = _match_count(_AUTHOR_PAGE, body)
    paren_count = _match_count(_NUM_PAREN, body)

    ref_square = len(_SQUARE_REFERENCE.findall(refs))
    ref_paren = len(_PAREN_REFERENCE.findall(refs))
    ref_dot = len(_DOT_REFERENCE.findall(refs))

    candidates: list[tuple[float, CitationStyle, int]] = []
    if square_count >= 3:
        candidates.append((square_count + min(ref_square, 5) * 0.25, "numeric_square", square_count))
    if alpha_count >= 3:
        candidates.append((alpha_count, "alpha_square", alpha_count))
    if author_date_count >= 3:
        candidates.append((author_date_count * 1.15, "author_date", author_date_count))
    if author_page_count >= 4:
        candidates.append((author_page_count, "author_page", author_page_count))
    # 单个 (1) 很可能是公式编号；必须同时在文末看到一致的编号参考文献表。
    if paren_count >= 3 and ref_paren + ref_dot >= 3:
        candidates.append((paren_count + min(ref_paren + ref_dot, 5) * 0.25,
                           "numeric_parenthetical", paren_count))

    if not candidates:
        return CitationProfile()
    _, style, matches = max(candidates, key=lambda item: item[0])
    return CitationProfile(style=style, matches=matches)


def strip_citations(text: str, profile: CitationProfile | CitationStyle) -> str:
    """只应用已由整篇论文确认的引用格式，并做最小标点/空白整理。"""
    style = profile.style if isinstance(profile, CitationProfile) else profile
    if style == "numeric_square":
        cleaned = _NUM_SQUARE_CLUSTER.sub("", text)
    elif style == "numeric_parenthetical":
        cleaned = _NUM_PAREN.sub("", text)
    elif style == "author_date":
        cleaned = _AUTHOR_DATE.sub("", text)
    elif style == "author_page":
        cleaned = _AUTHOR_PAGE.sub("", text)
    elif style == "alpha_square":
        cleaned = _ALPHA_SQUARE_CLUSTER.sub("", text)
    else:
        return text

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?，。；：！？、])", r"\1", cleaned)
    cleaned = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", cleaned)
    return cleaned.strip()
