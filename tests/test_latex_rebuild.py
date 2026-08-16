"""规则重建行内 LaTeX 的单元测试。"""

from app.parsers.latex_rebuild import spans_to_segments
from app.schemas.document import TextSpan


def _span(text, font, size, x0, y0, x1, y1, origin_y):
    return TextSpan(
        id="s",
        text=text,
        bbox=[x0, y0, x1, y1],
        font_size=size,
        font_name=font,
        origin_y=origin_y,
    )


def test_mathbb_r_and_in():
    spans = [
        _span("Here, ", "NimbusRomNo9L-Regu", 10, 0, 0, 40, 12, 10),
        _span("β", "CMMI10", 10, 40, 1, 48, 11, 10),
        _span("t", "CMMI7", 7, 48, 4, 52, 11, 11.5),
        _span("∈", "CMSY10", 10, 54, 1, 62, 11, 10),
        _span("R", "MSBM10", 10, 64, 1, 72, 11, 10),
        _span(" is ok", "NimbusRomNo9L-Regu", 10, 74, 0, 120, 12, 10),
    ]
    segs = spans_to_segments(spans)
    assert segs[0].kind == "text" and "Here" in segs[0].text
    math = next(s for s in segs if s.kind == "math")
    assert r"\beta" in math.latex
    assert r"\in" in math.latex
    assert r"\mathbb{R}" in math.latex
    assert "_{t}" in math.latex or "_t" in math.latex.replace("{", "").replace("}", "")


def test_shortconv_stays_text_near_body():
    spans = [
        _span("apply ", "NimbusRomNo9L-Regu", 10, 0, 0, 40, 12, 10),
        _span("ShortConv", "CMR10", 10, 40, 1, 90, 11, 10),
        _span(" followed", "NimbusRomNo9L-Regu", 10, 90, 0, 140, 12, 10),
    ]
    segs = spans_to_segments(spans)
    assert all(s.kind == "text" for s in segs)


def test_lone_letter_not_math():
    spans = [
        _span("chunk size ", "NimbusRomNo9L-Regu", 10, 0, 0, 50, 12, 10),
        _span("C", "CMMI10", 10, 50, 1, 58, 11, 10),
        _span(". For a", "NimbusRomNo9L-Regu", 10, 58, 0, 100, 12, 10),
    ]
    segs = spans_to_segments(spans)
    assert all(s.kind == "text" for s in segs)
    assert "C" in "".join(s.text for s in segs)


def test_zt_with_script_is_math():
    spans = [
        _span("logit ", "NimbusRomNo9L-Regu", 10, 0, 0, 40, 12, 10),
        _span("z", "CMMIB10", 10, 40, 1, 48, 11, 10),
        _span("t", "CMMI7", 7, 48, 4, 52, 11, 11.5),
        _span("h", "CMMI7", 7, 52, 0, 56, 8, 8.5),
        _span(" for", "NimbusRomNo9L-Regu", 10, 56, 0, 80, 12, 10),
    ]
    segs = spans_to_segments(spans)
    maths = [s for s in segs if s.kind == "math"]
    assert maths, "expected inline math for z_t^h-like cluster"
