"""arXiv ID 解析与导入 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.arxiv import arxiv_pdf_url, normalize_arxiv_id


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2301.07041", "2301.07041"),
        ("arxiv:2301.07041v2", "2301.07041v2"),
        ("https://arxiv.org/abs/2301.07041", "2301.07041"),
        ("https://arxiv.org/pdf/2301.07041", "2301.07041"),
        ("https://arxiv.org/pdf/2301.07041.pdf", "2301.07041"),
        ("http://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
        ("https://export.arxiv.org/pdf/1706.03762.pdf", "1706.03762"),
    ],
)
def test_normalize_arxiv_id(raw: str, expected: str) -> None:
    assert normalize_arxiv_id(raw) == expected


def test_normalize_arxiv_id_rejects_garbage() -> None:
    with pytest.raises(HTTPException) as ei:
        normalize_arxiv_id("https://example.com/paper.pdf")
    assert ei.value.status_code == 400


def test_arxiv_pdf_url() -> None:
    assert arxiv_pdf_url("2301.07041") == "https://arxiv.org/pdf/2301.07041.pdf"


def test_import_from_url_downloads_and_queues(client, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _Session = client
    pdf = b"%PDF-1.1\n%\xe2\xe3\xcf\xd3\ntrailer\n%%EOF\n"

    def fake_download(arxiv_id: str, *, max_bytes: int, timeout: float = 120.0) -> bytes:
        assert arxiv_id == "2301.07041"
        assert max_bytes > 0
        return pdf

    monkeypatch.setattr("app.services.papers.download_arxiv_pdf", fake_download)
    monkeypatch.setattr(
        "app.services.papers.fetch_arxiv_metadata",
        lambda arxiv_id: {
            "title": "Imported arXiv Paper",
            "authors": ["Ada Lovelace"],
            "institutions": ["Analytical Engine Institute"],
            "abstract": "Metadata from arXiv.",
            "arxiv_id": arxiv_id,
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "metadata_source": "arxiv",
        },
    )

    res = c.post("/api/papers/from-url", json={"url": "https://arxiv.org/abs/2301.07041"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["filename"].startswith("arxiv-2301.07041")
    assert body["file_size"] == len(pdf)
    assert body["title"] == "Imported arXiv Paper"
    assert body["authors"] == ["Ada Lovelace"]
    assert body["institutions"] == ["Analytical Engine Institute"]
    assert body["arxiv_id"] == "2301.07041"

    paper_id = body["id"]
    file_res = c.get(f"/api/papers/{paper_id}/file")
    assert file_res.status_code == 200
    assert file_res.content.startswith(b"%PDF")
