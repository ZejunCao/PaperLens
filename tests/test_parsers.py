from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import ParserError, get_parser, parse_pdf
from app.parsers.mineru_map import document_from_content_list, document_from_middle
from app.parsers.pymupdf_parser import PyMuPDFParser

FIXTURE = Path(__file__).parent / "fixtures" / "mineru_middle.json"


def test_get_parser_pymupdf(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "pymupdf")
    from app.config import get_settings

    get_settings.cache_clear()
    assert isinstance(get_parser(), PyMuPDFParser)


def test_get_parser_unknown(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "nope")
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ParserError, match="未知解析器"):
        get_parser()


def test_get_parser_mineru(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "mineru")
    from app.config import get_settings
    from app.parsers.mineru_parser import MinerUParser

    get_settings.cache_clear()
    assert isinstance(get_parser(), MinerUParser)


def test_get_parser_mineru_api(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "mineru_api")
    from app.config import get_settings
    from app.parsers.mineru_api import MinerUApiParser

    get_settings.cache_clear()
    assert isinstance(get_parser(), MinerUApiParser)


def test_join_lines_spaces_and_hyphens():
    from app.parsers.mineru_map import _join_plain, _strip_markup

    assert _join_plain('program the “fast', "weights” of") == 'program the “fast weights” of'
    assert _join_plain("ele-", "mentary") == "elementary"
    assert _join_plain("self-", "attention") == "self-attention"
    assert _strip_markup("Imanol Schlag<sup>∗</sup> <sup>1</sup>") == "Imanol Schlag∗ 1"


def test_page_overflow_lines_move_to_next():
    from app.parsers.mineru_map import _split_page_overflow_lines

    block = {
        "type": "text",
        "lines": [
            {"bbox": [300, 700, 540, 712], "spans": [{"content": "end of page", "type": "text", "bbox": [300, 700, 540, 712]}]},
            {"bbox": [55, 69, 289, 78], "spans": [{"content": "next page start", "type": "text", "bbox": [55, 69, 289, 78]}]},
        ],
    }
    overflow = _split_page_overflow_lines(block, 792.0)
    assert overflow is not None
    assert overflow["lines"][0]["spans"][0]["content"] == "next page start"
    assert len(block["lines"]) == 1

    col = {
        "type": "text",
        "lines": [
            {"bbox": [54, 627, 290, 637], "spans": [{"content": "left col", "type": "text"}]},
            {"bbox": [307, 178, 541, 186], "spans": [{"content": "right col", "type": "text"}]},
        ],
    }
    assert _split_page_overflow_lines(col, 792.0) is None

    right_to_next_left = {
        "type": "text",
        "lines": [
            {"bbox": [311, 695, 558, 704], "spans": [{"content": "sentence starts", "type": "text"}]},
            {"bbox": [54, 617, 300, 626], "spans": [{"content": "and continues", "type": "text"}]},
        ],
    }
    overflow = _split_page_overflow_lines(right_to_next_left, 792.0)
    assert overflow is not None
    assert overflow["lines"][0]["spans"][0]["content"] == "and continues"


def test_cross_page_sentence_belongs_to_start_page():
    from app.parsers.mineru_map import _stitch_cross_page_sentences
    from app.schemas.document import ContentBlock, PageLayout, Sentence

    left = ContentBlock(
        id="b_left",
        page=1,
        order=0,
        bbox=[310, 690, 560, 705],
        source_text="Sentence C starts",
        sentences=[Sentence(id="s_c", text="Sentence C starts", order=0)],
        meta={"continues_to": "flow_1"},
    )
    right = ContentBlock(
        id="b_right",
        page=2,
        order=1,
        bbox=[54, 617, 300, 650],
        source_text="and finishes. Sentence D.",
        sentences=[
            Sentence(id="s_tail", text="and finishes.", order=0),
            Sentence(id="s_d", text="Sentence D.", order=1),
        ],
        meta={"continues_from": "flow_1"},
    )
    pages = [
        PageLayout(page=1, width=612, height=792, blocks=[left]),
        PageLayout(page=2, width=612, height=792, blocks=[right]),
    ]
    _stitch_cross_page_sentences(pages)

    assert left.sentences[-1].full_text == "Sentence C starts and finishes."
    assert left.sentences[-1].owner_page == 1
    assert right.sentences[0].id == left.sentences[-1].id
    assert right.sentences[0].owner_page == 1
    assert right.sentences[1].owner_page is None


def test_text_block_bbox_covers_both_columns():
    from app.parsers.mineru_map import _content_bbox_from_lines

    block = {
        "bbox": [50, 547, 302, 689],
        "lines": [
            {"bbox": [52, 642, 300, 652], "spans": []},
            {"bbox": [310, 191, 557, 201], "spans": []},
            {"bbox": [310, 203, 558, 213], "spans": []},
        ],
    }
    assert _content_bbox_from_lines(block) == [52.0, 191.0, 558.0, 652.0]
    import json

    middle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    image_map = {"fig_abc.png": "images/fig_abc.png", "images/fig_abc.png": "images/fig_abc.png"}
    doc = document_from_middle(
        middle,
        paper_id="p1",
        parser="mineru",
        parser_version="test",
        image_map=image_map,
    )
    assert doc.page_count == 1
    assert doc.pages[0].width == 612.0
    assert doc.title and "Flow Duration" in doc.title
    types = {b.type for b in doc.blocks}
    assert "title" in types
    assert "paragraph" in types
    assert "figure" in types
    assert "formula" in types
    fig = next(b for b in doc.blocks if b.type == "figure")
    assert fig.meta.get("image_path") == "images/fig_abc.png"
    formula = next(b for b in doc.blocks if b.type == "formula")
    assert any(s.kind == "math" for s in formula.segments)
    para = next(b for b in doc.blocks if b.type == "paragraph")
    assert para.spans
    assert any(s.kind == "math" for s in para.segments)


def test_inline_equation_not_dumped_as_layout_text():
    from app.parsers.mineru_map import _lines_to_spans_segments

    block = {
        "lines": [
            {
                "spans": [
                    {"type": "text", "content": "where", "bbox": [0, 0, 20, 10]},
                    {
                        "type": "inline_equation",
                        "content": "\\kappa ( k )",
                        "bbox": [20, 0, 80, 10],
                    },
                ]
            }
        ]
    }
    spans, segs, source = _lines_to_spans_segments(block, {})
    assert all("\\" not in (s.text or "") for s in spans)
    assert any(s.kind == "math" and "kappa" in (s.latex or "") for s in segs)
    assert "kappa" in source


def test_split_line_keeps_runin_bold():
    from app.parsers.layout_enrich import split_line_by_pdf_styles

    parts = split_line_by_pdf_styles(
        [300, 440, 545, 452],
        "Normalisation. In the equations above, no normalisation",
        [
            {
                "bbox": [306, 441, 368, 451],
                "size": 10.0,
                "font": "NimbusRomNo9L-Medi",
                "flags": 20,
                "color": 0,
                "origin": [306, 449],
                "text": "Normalisation. ",
            },
            {
                "bbox": [368, 441, 541, 451],
                "size": 10.0,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "color": 0,
                "origin": [368, 449],
                "text": "In the equations above, no normalisation",
            },
        ],
    )
    assert parts is not None
    assert len(parts) == 2
    assert parts[0].text.strip().startswith("Normalisation")
    assert (parts[0].flags & 16) != 0 or "Medi" in (parts[0].font_name or "")
    assert (parts[1].flags & 16) == 0


def test_split_line_keeps_spaces_from_mineru():
    from app.parsers.layout_enrich import split_line_by_pdf_styles

    parts = split_line_by_pdf_styles(
        [50, 100, 290, 112],
        "we can rewrite Eqs. 4-7 such that they",
        [
            {
                "bbox": [50, 101, 120, 111],
                "size": 10.0,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "color": 0,
                "text": "wecanrewrite",
            },
            {
                "bbox": [122, 101, 170, 111],
                "size": 10.0,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "color": 255,
                "text": "Eqs.4-7",
            },
            {
                "bbox": [172, 101, 280, 111],
                "size": 10.0,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "color": 0,
                "text": "suchthatthey",
            },
        ],
    )
    assert parts is not None
    assert "we can rewrite" in parts[0].text
    assert "Eqs. 4-7" in parts[1].text
    assert "such that they" in parts[2].text


def test_layout_style_from_pdf_spans():
    from app.parsers.layout_enrich import style_from_pdf_spans

    style = style_from_pdf_spans(
        [100, 100, 300, 112],
        [
            {
                "bbox": [100, 101, 200, 111],
                "size": 10.02,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "color": 0,
                "origin": [100, 109],
                "ascender": 0.8,
                "text": "Hello world ",
            },
            {
                "bbox": [200, 101, 240, 111],
                "size": 7.0,
                "font": "NimbusRomNo9L-Regu",
                "flags": 4,
                "text": "*",
            },
        ],
    )
    assert style is not None
    assert abs(style["font_size"] - 10.02) < 0.2
    assert style["font_name"] == "NimbusRomNo9L-Regu"


def test_layout_style_ignores_neighbor_line_origin():
    from app.parsers.layout_enrich import _apply_style, style_from_pdf_spans
    from app.schemas.document import TextSpan

    pdf_spans = [
        {
            "bbox": [52, 211, 300, 219],
            "size": 8.8,
            "font": "NimbusRomNo9L-Regu",
            "origin": [52, 218.64],
            "text": "tical character recognition (OCR), document restoration, and",
        },
        {
            "bbox": [52, 221, 300, 229],
            "size": 8.8,
            "font": "NimbusRomNo9L-Regu",
            "origin": [52, 228.4],
            "text": "the evaluation of enhancement systems. We introduce DIQA-",
        },
    ]
    line_bbox = [52.0, 220.0, 300.0, 230.0]
    style = style_from_pdf_spans(line_bbox, pdf_spans)
    assert style is not None
    span = TextSpan(
        id="sp_test",
        text="the evaluation of enhancement systems. We introduce DIQA-",
        bbox=line_bbox,
        font_size=8.8,
        origin_y=230.0,
    )
    _apply_style(span, {**style, "origin_y": 218.64})
    assert span.origin_y != 218.64
    _apply_style(span, style)
    assert abs((span.origin_y or 0) - 228.4) < 0.2


def test_content_list_denormalizes_bbox():
    items = [
        {
            "type": "text",
            "text": "Hello",
            "text_level": 1,
            "bbox": [0, 0, 1000, 500],
            "page_idx": 0,
        }
    ]
    doc = document_from_content_list(
        items,
        paper_id="p1",
        parser="mineru_api",
        parser_version="v4",
        image_map={},
        page_sizes=[(200.0, 400.0)],
    )
    assert doc.blocks[0].type == "title"
    assert doc.blocks[0].bbox == [0.0, 0.0, 200.0, 200.0]


def test_api_parser_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "mineru_api")
    monkeypatch.setenv("PAPERLENS_MINERU_API_TOKEN", "")
    from app.config import get_settings
    from app.parsers.mineru_api import MinerUApiParser

    get_settings.cache_clear()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.1\n")
    with pytest.raises(ParserError, match="TOKEN"):
        MinerUApiParser().parse(pdf, "id", tmp_path / "out")


def test_parse_pdf_uses_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PAPERLENS_PARSER", "pymupdf")
    from app.config import get_settings

    get_settings.cache_clear()
    import fitz

    pdf = tmp_path / "s.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 40), "Factory path.")
    doc.save(pdf.as_posix())
    doc.close()
    result = parse_pdf(pdf, "id", tmp_path / "out")
    assert result.parser == "pymupdf"
    assert result.blocks
