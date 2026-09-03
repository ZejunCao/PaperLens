"""Deterministic bibliographic metadata extraction for imported papers."""

from __future__ import annotations

import re
from typing import Any

import fitz

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def _clean(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \x00")
    return text or None


def _split_authors(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"\s*;\s*|\s+and\s+", value) if item.strip()]


def _split_keywords(value: str | None) -> list[str]:
    return [item.strip() for item in re.split(r"[,;]", value or "") if item.strip()]


def extract_pdf_metadata(data: bytes) -> dict[str, Any]:
    """Read embedded PDF properties and explicit identifiers from the first page."""
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            raw = document.metadata or {}
            first_page = document[0].get_text("text")[:12000] if document.page_count else ""
    except Exception:
        return {}

    title = _clean(raw.get("title"))
    author_text = _clean(raw.get("author"))
    subject = _clean(raw.get("subject"))
    keyword_text = _clean(raw.get("keywords"))
    identifier_text = "\n".join(filter(None, [subject, keyword_text, first_page]))
    doi_match = DOI_RE.search(identifier_text)
    doi = doi_match.group(0).rstrip(".,;)") if doi_match else None

    result: dict[str, Any] = {
        "authors": _split_authors(author_text),
        "abstract": subject,
        "doi": doi,
        "keywords": _split_keywords(keyword_text),
        "metadata_source": "pdf",
    }
    if title and title.lower() not in {"untitled", "microsoft word"}:
        result["title"] = title
    return {key: value for key, value in result.items() if value not in (None, [], "")}
