from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.config import get_settings
from app.parsers.base import BaseParser, ParserError
from app.parsers.pymupdf_parser import PyMuPDFParser
from app.schemas.document import Document

__all__ = ["BaseParser", "ParserError", "PyMuPDFParser", "get_parser", "parse_pdf"]

ProgressCallback = Callable[[str, int], None]


def get_parser() -> BaseParser:
    name = (get_settings().parser or "mineru").strip().lower()
    if name == "pymupdf":
        return PyMuPDFParser()
    if name == "mineru":
        from app.parsers.mineru_parser import MinerUParser

        return MinerUParser()
    if name in {"mineru_api", "mineru-api"}:
        from app.parsers.mineru_api import MinerUApiParser

        return MinerUApiParser()
    raise ParserError(f"未知解析器: {name}")


def parse_pdf(
    pdf_path: Path,
    paper_id: str,
    output_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
) -> Document:
    def report(stage: str, progress: int) -> None:
        if on_progress:
            on_progress(stage, progress)

    report("extracting", 12)
    document = get_parser().parse(pdf_path, paper_id, output_dir)
    report("extracting", 68)

    if document.parser != "pymupdf":
        from app.parsers.layout_enrich import enrich_layout_from_pdf

        report("enriching", 75)
        enrich_layout_from_pdf(document, pdf_path)
        report("enriching", 90)
    else:
        report("enriching", 88)

    return document
