from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.schemas.document import Document


def paper_dir(paper_id: str) -> Path:
    return get_settings().papers_dir / paper_id


def document_path(paper_id: str) -> Path:
    return paper_dir(paper_id) / "document.json"


def save_document(doc: Document) -> Path:
    d = paper_dir(doc.paper_id)
    d.mkdir(parents=True, exist_ok=True)
    path = document_path(doc.paper_id)
    path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_document(paper_id: str) -> Document | None:
    path = document_path(paper_id)
    if not path.exists():
        return None
    return Document.model_validate_json(path.read_text(encoding="utf-8"))


def clear_paper_derived(paper_id: str) -> None:
    import shutil

    d = paper_dir(paper_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
