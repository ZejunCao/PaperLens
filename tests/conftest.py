"""默认测试走 PyMuPDF，避免拉起 MinerU 模型。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_pymupdf_parser(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "pymupdf")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
