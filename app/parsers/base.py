from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.document import Document


class ParserError(Exception):
    """解析失败。"""


class BaseParser(ABC):
    name: str
    version: str = "1"

    @abstractmethod
    def parse(self, pdf_path: Path, paper_id: str, output_dir: Path) -> Document:
        """解析 PDF，写入 output_dir（原始产物可选），返回标准 Document。"""
