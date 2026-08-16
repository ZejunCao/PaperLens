from __future__ import annotations

import re
import uuid

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])|(?<=。|！|？)\s*")


def split_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(cleaned) if p.strip()]
    return parts or [cleaned]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
