"""规则法：把 PyMuPDF span 序列重建为文本 + 行内 LaTeX（不依赖模型）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.document import RichSegment, TextSpan

_MATH_FONT_RE = re.compile(
    r"(CMEX|CMSY|CMMI|CMMIB|CMR\d|CMBX|MSBM|MSAM|EUEX|EUFM|Euler)",
    re.I,
)
_BODY_FONT_RE = re.compile(
    r"(Nimbus|TimesNewRoman|Times-Roman|Liberation|Arial|Helvetica|Minion|Palatino|Charter|DejaVu)",
    re.I,
)

# Unicode → LaTeX（KaTeX 可渲染）
_CHAR_LATEX: dict[str, str] = {
    "∈": r"\in",
    "∉": r"\notin",
    "→": r"\to",
    "←": r"\leftarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "↔": r"\leftrightarrow",
    "×": r"\times",
    "·": r"\cdot",
    "−": r"-",
    "–": r"-",
    "—": r"-",
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∼": r"\sim",
    "⊤": r"\top",
    "⊥": r"\bot",
    "∞": r"\infty",
    "∂": r"\partial",
    "∇": r"\nabla",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "√": r"\sqrt",
    "±": r"\pm",
    "∓": r"\mp",
    "⊕": r"\oplus",
    "⊗": r"\otimes",
    "⊙": r"\odot",
    "∘": r"\circ",
    "★": r"\star",
    "†": r"\dagger",
    "ℓ": r"\ell",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "ϵ": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ϑ": r"\vartheta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ϖ": r"\varpi",
    "ρ": r"\rho",
    "ϱ": r"\varrho",
    "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "ϕ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℂ": r"\mathbb{C}",
    "ℓ": r"\ell",
}

# 字体前缀 + 字符 → 强制 LaTeX（解决 MSBM 的 R 被抽成普通 R 等）
_FONT_CHAR_LATEX: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (
        re.compile(r"MSBM", re.I),
        {
            "R": r"\mathbb{R}",
            "N": r"\mathbb{N}",
            "Z": r"\mathbb{Z}",
            "Q": r"\mathbb{Q}",
            "C": r"\mathbb{C}",
            "A": r"\mathbb{A}",
            "F": r"\mathbb{F}",
            "H": r"\mathbb{H}",
            "P": r"\mathbb{P}",
        },
    ),
    (
        re.compile(r"MSAM", re.I),
        {
            "R": r"\mathbb{R}",
        },
    ),
]


@dataclass
class _Tok:
    latex: str
    raw: str
    size: float
    origin_y: float
    x0: float
    x1: float
    y0: float
    y1: float
    font: str
    is_math: bool


def _font_name(span: TextSpan) -> str:
    return span.font_name or ""


def _is_math_font(font: str) -> bool:
    return bool(_MATH_FONT_RE.search(font))


def _is_body_font(font: str) -> bool:
    return bool(_BODY_FONT_RE.search(font))


def _char_to_latex(ch: str, font: str) -> str:
    for fre, table in _FONT_CHAR_LATEX:
        if fre.search(font) and ch in table:
            return table[ch]
    if ch in _CHAR_LATEX:
        return _CHAR_LATEX[ch]
    if ch == "\\":
        return r"\backslash"
    if ch in "{}":
        return "\\" + ch
    return ch


def _wrap_math_atom(latex: str, font: str) -> str:
    if latex.startswith("\\mathbb"):
        return latex
    if re.search(r"CMMIB|CMBX", font, re.I):
        if re.match(r"\\[A-Za-z]+$", latex):
            return rf"\mathbf{{{latex}}}"
        return rf"\mathbf{{{latex}}}"
    if re.search(r"CMMI", font, re.I):
        if re.match(r"\\[A-Za-z]+$", latex):
            return latex
        return latex
    return latex


def _span_to_latex_piece(span: TextSpan) -> str:
    font = _font_name(span)
    parts: list[str] = []
    for ch in span.text:
        if ch == " ":
            parts.append(r"\,")
            continue
        piece = _char_to_latex(ch, font)
        piece = _wrap_math_atom(piece, font) if ch != " " else piece
        parts.append(piece)
    return "".join(parts)


def _math_strength(span: TextSpan) -> str:
    """返回 'strong' | 'weak' | ''。

    strong：符号字体 / 特殊 Unicode / blackboard
    weak：数学斜体字母、短 CMR 符号（须挂靠 strong 簇才算公式）
    """
    font = _font_name(span)
    text = span.text or ""
    if any(ch in _CHAR_LATEX for ch in text):
        return "strong"
    if any(ord(ch) > 127 for ch in text):
        return "strong"
    if re.search(r"CMSY|CMEX|MSBM|MSAM|EUEX|EUFM", font, re.I):
        return "strong"
    if re.search(r"CMMIB", font, re.I):
        # 粗斜体变量常是公式核心，但仍可能是单字母；标 weak，靠簇判断
        return "weak"
    if re.search(r"CMMI", font, re.I):
        return "weak"
    if re.search(r"CMR\d|CMBX", font, re.I):
        raw = text.strip()
        if not raw:
            return "weak"
        # ShortConv / Swish 等函数名不当公式
        if len(raw) >= 4 and raw.replace("-", "").isalpha():
            return ""
        if re.fullmatch(r"[\d()\[\]\{\}.,;:=+\-*/|]+", raw) or len(raw) <= 2:
            return "weak"
        return ""
    return ""


def _is_math_span(span: TextSpan) -> bool:
    return _math_strength(span) != ""


def _run_is_confident(group: list[TextSpan]) -> bool:
    """避免把单独的 t、C、h 等英文字母当成公式。"""
    if not group:
        return False
    strengths = [_math_strength(s) for s in group]
    if any(s == "strong" for s in strengths):
        return True
    texts = "".join(s.text for s in group)
    if any(ch in _CHAR_LATEX or ord(ch) > 127 for ch in texts):
        return True
    # 至少两个数学 span，且有明显上下标字号差（如 z_t^h）
    if len(group) >= 2 and any(s == "weak" for s in strengths):
        sizes = [s.font_size for s in group]
        if max(sizes) / max(min(sizes), 1e-3) >= 1.28:
            return True
        # 粗体变量 + 下标/括号：\mathbf{S}_{[t]}
        fonts = [_font_name(s) for s in group]
        if any(re.search(r"CMMIB|CMBX", f, re.I) for f in fonts) and len(group) >= 2:
            return True
    return False


def _script_role(tok: _Tok, base_size: float, base_oy: float) -> str:
    """返回 '' | 'sub' | 'sup'。"""
    if tok.size >= base_size * 0.88:
        return ""
    dy = tok.origin_y - base_oy
    # PDF y 向下增大：下标 origin 更大，上标更小
    if dy >= base_size * 0.12:
        return "sub"
    if dy <= -base_size * 0.08:
        return "sup"
    # 字号明显更小但基线接近：偏下标（如 d_k）
    if tok.size <= base_size * 0.75:
        return "sub" if dy >= 0 else "sup"
    return ""


def _merge_scripts(toks: list[_Tok]) -> str:
    if not toks:
        return ""
    sizes = sorted(t.size for t in toks)
    base_size = sizes[len(sizes) // 2]
    # 主体字号：偏大的一档
    large = [t.size for t in toks if t.size >= base_size * 0.9]
    if large:
        base_size = sorted(large)[len(large) // 2]

    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        role = _script_role(t, base_size, t.origin_y)
        # 找一个「核」：非脚本或当前就是核
        if role:
            # 孤立脚本：并到前一个原子
            if out:
                prev = out.pop()
                wrap = "_{%s}" % t.latex if role == "sub" else "^{%s}" % t.latex
                out.append(prev + wrap)
                i += 1
                continue
        # 以当前为核，吞后续脚本
        core = t.latex
        base_oy = t.origin_y
        i += 1
        sub_toks: list[_Tok] = []
        sup_toks: list[_Tok] = []
        while i < len(toks):
            n = toks[i]
            r = _script_role(n, max(base_size, t.size), base_oy)
            if not r:
                break
            # 水平过远则不算脚本
            if n.x0 - toks[i - 1].x1 > max(base_size * 1.8, 10):
                break
            if r == "sub":
                sub_toks.append(n)
            else:
                sup_toks.append(n)
            i += 1
        if sub_toks:
            core += "_{%s}" % _join_latex_atoms(_nest_script_parts(sub_toks))
        if sup_toks:
            core += "^{%s}" % _join_latex_atoms(_nest_script_parts(sup_toks))
        out.append(core)
    return _join_latex_atoms(out)


def _nest_script_parts(toks: list[_Tok]) -> list[str]:
    """上/下标内部再套一层，如 d,k → d_{k}。"""
    if not toks:
        return []
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if i + 1 < len(toks):
            n = toks[i + 1]
            if n.size <= t.size * 0.85 and abs(n.origin_y - t.origin_y) < max(t.size, 4):
                # 更小且基线接近：作为下标挂到前一个
                if n.origin_y >= t.origin_y - t.size * 0.05:
                    out.append(t.latex + "_{%s}" % n.latex)
                    i += 2
                    continue
        out.append(t.latex)
        i += 1
    return out


def _join_latex_atoms(atoms: list[str]) -> str:
    """避免 \\le + i → \\lei 这类命令粘连。"""
    if not atoms:
        return ""
    res = atoms[0]
    for a in atoms[1:]:
        if re.search(r"\\[A-Za-z]+$", res) and a and (a[0].isalpha() or a.startswith("\\")):
            res += "{}"
        elif res.endswith("}") and a[:1].isalpha():
            pass
        res += a
    res = re.sub(r"\\,+", r"\\,", res)
    return res


def _union_bbox(spans: list[TextSpan]) -> list[float]:
    x0 = min(s.bbox[0] for s in spans)
    y0 = min(s.bbox[1] for s in spans)
    x1 = max(s.bbox[2] for s in spans)
    y1 = max(s.bbox[3] for s in spans)
    return [x0, y0, x1, y1]


def _tight_math_bbox(spans: list[TextSpan]) -> list[float]:
    """按基线+字号收紧垂直范围，避免 CMSY 等超高 descender 盖住下一行。"""
    if not spans:
        return [0.0, 0.0, 0.0, 0.0]
    x0 = min(s.bbox[0] for s in spans)
    x1 = max(s.bbox[2] for s in spans)
    tops: list[float] = []
    bots: list[float] = []
    for s in spans:
        oy = s.origin_y if s.origin_y is not None else s.bbox[3]
        size = max(s.font_size, 1.0)
        asc = s.ascender if s.ascender and s.ascender > 0 else 0.75
        # 限制异常 descender（CMSY 可到 -0.96）
        asc = min(max(asc, 0.55), 0.95)
        tops.append(oy - size * asc)
        bots.append(oy + size * 0.32)
    y0, y1 = min(tops), max(bots)
    max_h = max(s.font_size for s in spans) * 1.55
    if y1 - y0 > max_h:
        mid = 0.5 * (y0 + y1)
        y0, y1 = mid - max_h * 0.5, mid + max_h * 0.5
    # 水平微扩，垂直不再用原始夸张 bbox
    return [x0 - 0.5, y0, x1 + 0.5, y1]


def _to_tok(span: TextSpan, math: bool) -> _Tok:
    oy = span.origin_y if span.origin_y is not None else span.bbox[3]
    return _Tok(
        latex=_span_to_latex_piece(span) if math else span.text,
        raw=span.text,
        size=span.font_size,
        origin_y=oy,
        x0=span.bbox[0],
        x1=span.bbox[2],
        y0=span.bbox[1],
        y1=span.bbox[3],
        font=_font_name(span),
        is_math=math,
    )


def spans_to_segments(spans: list[TextSpan]) -> list[RichSegment]:
    """将一块内的 spans 切成 text / math 片段。"""
    if not spans:
        return []

    flags = [_is_math_span(s) for s in spans]
    # 去掉旧的 ShortConv 降级逻辑（已在 _is_math_span 处理）

    segments: list[RichSegment] = []
    i = 0
    while i < len(spans):
        if not flags[i]:
            j = i + 1
            while j < len(spans) and not flags[j]:
                j += 1
            text = "".join(spans[k].text for k in range(i, j))
            segments.append(
                RichSegment(kind="text", text=text, bbox=_union_bbox(spans[i:j]))
            )
            i = j
            continue

        j = i + 1
        while j < len(spans) and flags[j]:
            prev, cur = spans[j - 1], spans[j]
            gap_x = cur.bbox[0] - prev.bbox[2]
            mid_y_prev = (prev.bbox[1] + prev.bbox[3]) / 2
            mid_y_cur = (cur.bbox[1] + cur.bbox[3]) / 2
            # 换行且回到行首：仍可能是同一行内公式被拆到下一视觉行——若 gap 太大则断开
            if abs(mid_y_cur - mid_y_prev) > max(prev.font_size * 1.35, 12):
                break
            if gap_x > max(prev.font_size * 3.5, 22):
                break
            j += 1

        group = spans[i:j]
        if not _run_is_confident(group):
            # 置信不足：当普通文字，避免 t/C/h 等误识别
            text = "".join(s.text for s in group)
            segments.append(RichSegment(kind="text", text=text, bbox=_union_bbox(group)))
            i = j
            continue
        toks = [_to_tok(s, True) for s in group]
        latex = _merge_scripts(toks)
        latex = re.sub(r"^(\\,)+|(\\,)+$", "", latex.strip())
        # 过滤过短/过无聊的 latex（单独字母）
        if latex and not re.fullmatch(r"(\\mathbf\{)?[A-Za-z]\}?", latex):
            sizes = sorted(s.font_size for s in group)
            # 主体字号取偏大的中位，避免被下标拉低
            large = [s.font_size for s in group if s.font_size >= sizes[len(sizes) // 2] * 0.9]
            base_size = sorted(large)[len(large) // 2] if large else sizes[len(sizes) // 2]
            base_oy = min(
                (s.origin_y if s.origin_y is not None else s.bbox[3]) for s in group
            )
            # 取主体 span 的基线（字号接近 base_size）
            mains = [
                s
                for s in group
                if s.font_size >= base_size * 0.9
            ]
            if mains:
                base_oy = sorted(
                    (s.origin_y if s.origin_y is not None else s.bbox[3]) for s in mains
                )[len(mains) // 2]
            segments.append(
                RichSegment(
                    kind="math",
                    latex=latex,
                    text="".join(s.text for s in group),
                    bbox=_tight_math_bbox(group),
                    display=False,
                    font_size=base_size,
                    origin_y=base_oy,
                )
            )
        else:
            text = "".join(s.text for s in group)
            if text:
                segments.append(RichSegment(kind="text", text=text, bbox=_union_bbox(group)))
        i = j

    merged: list[RichSegment] = []
    for seg in segments:
        if merged and seg.kind == "text" and merged[-1].kind == "text":
            prev = merged[-1]
            pb, sb = prev.bbox, seg.bbox
            bbox = None
            if pb and sb:
                bbox = [min(pb[0], sb[0]), min(pb[1], sb[1]), max(pb[2], sb[2]), max(pb[3], sb[3])]
            merged[-1] = RichSegment(kind="text", text=prev.text + seg.text, bbox=bbox)
        else:
            merged.append(seg)
    return merged


def segments_plain_text(segments: list[RichSegment]) -> str:
    parts: list[str] = []
    for seg in segments:
        if seg.kind == "text":
            parts.append(seg.text)
        else:
            parts.append(f"${seg.latex}$")
    return "".join(parts)
