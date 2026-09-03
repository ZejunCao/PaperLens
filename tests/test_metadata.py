from __future__ import annotations

import fitz

from app.services.metadata import extract_pdf_metadata


def make_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example paper DOI: 10.1234/example.2026")
    document.set_metadata(
        {
            "title": "Reliable Paper Metadata",
            "author": "Ada Lovelace; Alan Turing",
            "subject": "A deterministic metadata extraction example.",
            "keywords": "layout, parsing, metadata",
            "creationDate": "D:20260903",
        }
    )
    data = document.tobytes()
    document.close()
    return data


def test_extract_pdf_metadata() -> None:
    metadata = extract_pdf_metadata(make_pdf())

    assert metadata["title"] == "Reliable Paper Metadata"
    assert metadata["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert metadata["abstract"] == "A deterministic metadata extraction example."
    assert metadata["doi"] == "10.1234/example.2026"
    assert metadata["keywords"] == ["layout", "parsing", "metadata"]
    assert "published_at" not in metadata
    assert metadata["metadata_source"] == "pdf"


def test_extract_invalid_pdf_is_empty() -> None:
    assert extract_pdf_metadata(b"not a pdf") == {}
