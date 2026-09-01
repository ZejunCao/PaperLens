from __future__ import annotations

import re
import uuid

# 句号/问叹号后接大写、引号或开括号 → 疑似新句（中文标点直接切）
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])|(?<=。|！|？)\s*")

# 学术写作里句号不表示句末的缩写（匹配到缩写末尾的 '.'）
# 例：et al. (2020) / Fig. A / e.g. / Eqs. 4-7
_ABBREV = re.compile(
    r"(?i)\b(?:"
    r"et\s+al|"
    r"e\.g|i\.e|cf|vs|viz|etc|"
    r"fig(?:s|ure)?|eq(?:s|n|uation)?|tab(?:s|le)?|"
    r"sec(?:t|tion)?|ch(?:ap(?:ter)?)?|ref(?:s)?|"
    r"vol|nos?|pp|"
    r"dr|mr|mrs|ms|prof|jr|sr|"
    r"inc|ltd|approx|ca|eds?|trans|"
    r"ph\.d|m\.d|"
    r"jan|feb|mar|apr|jun|jul|aug|sep(?:t)?|oct|nov|dec"
    r")\."
)

_PLACEHOLDER = re.compile(r"\x00ABBR(\d+)\x00")


def split_sentences(text: str) -> list[str]:
    """按句切分；先保护 et al. / Fig. / e.g. 等缩写，避免把缩写句号当句界。"""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    held: list[str] = []

    def _hold(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"\x00ABBR{len(held) - 1}\x00"

    protected = _ABBREV.sub(_hold, cleaned)
    parts = [p.strip() for p in _SENT_SPLIT.split(protected) if p.strip()]
    if not parts:
        parts = [protected]

    def _restore(s: str) -> str:
        return _PLACEHOLDER.sub(lambda m: held[int(m.group(1))], s)

    return [_restore(p) for p in parts]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
