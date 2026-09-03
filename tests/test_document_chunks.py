from app.services.documents import document_chunk_payload


def _document(page_count: int = 5) -> dict:
    pages = [
        {
            "page": page,
            "width": 600.0,
            "height": 800.0 + page,
            "blocks": [{"id": f"block-{page}"}],
            "images": [],
        }
        for page in range(1, page_count + 1)
    ]
    return {
        "paper_id": "paper-id",
        "parser": "mineru",
        "parser_version": "3",
        "page_count": page_count,
        "title": "Paper",
        "pages": pages,
        "toc": [{"id": "toc-1", "title": "Intro", "page": 1}],
        "blocks": [block for page in pages for block in page["blocks"]],
    }


def test_initial_document_chunk_contains_manifest_and_first_page_only():
    payload = document_chunk_payload(
        _document(),
        start_page=1,
        page_limit=1,
        include_manifest=True,
    )

    assert [page["page"] for page in payload["pages"]] == [1]
    assert [page["page"] for page in payload["page_manifest"]] == [1, 2, 3, 4, 5]
    assert payload["page_manifest"][0] == {"page": 1, "width": 600.0, "height": 801.0}
    assert payload["toc"][0]["title"] == "Intro"
    assert "blocks" not in payload


def test_background_document_chunk_returns_requested_page_range_without_manifest():
    payload = document_chunk_payload(
        _document(),
        start_page=2,
        page_limit=2,
        include_manifest=False,
    )

    assert [page["page"] for page in payload["pages"]] == [2, 3]
    assert "page_manifest" not in payload
    assert "toc" not in payload
