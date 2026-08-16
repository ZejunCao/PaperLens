from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.parsers.base import BaseParser, ParserError
from app.parsers.pymupdf_parser import PyMuPDFParser
from app.schemas.document import Document

__all__ = ["BaseParser", "ParserError", "PyMuPDFParser", "get_parser", "parse_pdf"]


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


def parse_pdf(pdf_path: Path, paper_id: str, output_dir: Path) -> Document:
    document = get_parser().parse(pdf_path, paper_id, output_dir)
    if document.parser != "pymupdf":
        from app.parsers.layout_enrich import enrich_layout_from_pdf

        enrich_layout_from_pdf(document, pdf_path)
    return document
