"""标准 Document JSON —— 与具体解析器解耦。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

BlockType = Literal[
    "title",
    "section",
    "paragraph",
    "list_item",
    "formula",
    "table",
    "figure",
    "caption",
    "reference",
    "footer",
    "header",
    "other",
]


class Sentence(BaseModel):
    id: str
    text: str
    order: int = 0
    bbox: list[float] | None = None  # [x0, y0, x1, y1] 页面坐标


class TextSpan(BaseModel):
    """用于网页复现的细粒度文字片（尽量保留原版式）。"""

    id: str
    text: str
    bbox: list[float]  # [x0, y0, x1, y1]
    font_size: float = 12.0
    font_name: str | None = None
    color: int | None = None  # RGB packed or 0
    flags: int = 0  # bit flags: bold/italic etc.
    origin_y: float | None = None  # PDF 文字基线 y，用于跨字体垂直对齐
    ascender: float | None = None  # 相对字号的升部（PyMuPDF）


class RichSegment(BaseModel):
    """段落内富文本片段：普通文字或行内公式（LaTeX）。"""

    kind: Literal["text", "math"] = "text"
    text: str = ""
    latex: str = ""
    bbox: list[float] | None = None
    display: bool = False
    font_size: float | None = None  # 主体字号，供左侧对齐渲染
    origin_y: float | None = None  # 基线
    image_path: str | None = None  # 左侧用裁剪位图保真；latex 仍保留


class ContentBlock(BaseModel):
    id: str
    type: BlockType = "paragraph"
    page: int
    order: int
    bbox: list[float]
    source_text: str = ""
    sentences: list[Sentence] = Field(default_factory=list)
    spans: list[TextSpan] = Field(default_factory=list)
    segments: list[RichSegment] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class PageLayout(BaseModel):
    page: int
    width: float
    height: float
    blocks: list[ContentBlock] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)


class TocItem(BaseModel):
    id: str
    title: str
    page: int
    level: int = 1
    block_id: str | None = None


class Document(BaseModel):
    paper_id: str
    parser: str
    parser_version: str = "1"
    page_count: int
    title: str | None = None
    pages: list[PageLayout] = Field(default_factory=list)
    toc: list[TocItem] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)  # 阅读顺序扁平列表
