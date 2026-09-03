from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

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


@lru_cache(maxsize=8)
def _load_document_json_cached(path_str: str, modified_ns: int) -> dict[str, Any]:
    """按文件修改时间缓存原始 JSON，分页请求无需反复解析整份文档。"""
    del modified_ns  # 仅作为缓存版本键
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_document_json(paper_id: str) -> dict[str, Any] | None:
    path = document_path(paper_id)
    if not path.exists():
        return None
    return _load_document_json_cached(str(path), path.stat().st_mtime_ns)


def document_chunk_payload(
    document: dict[str, Any],
    *,
    start_page: int,
    page_limit: int,
    include_manifest: bool,
) -> dict[str, Any]:
    """从标准文档生成页面分片；manifest 只含尺寸，不携带重型 blocks。"""
    end_page = start_page + page_limit
    all_pages = document.get("pages") or []
    selected_pages = [
        page
        for page in all_pages
        if start_page <= int(page.get("page") or 0) < end_page
    ]
    payload: dict[str, Any] = {
        "paper_id": document.get("paper_id", ""),
        "parser": document.get("parser", ""),
        "parser_version": document.get("parser_version", "1"),
        "page_count": int(document.get("page_count") or len(all_pages)),
        "title": document.get("title"),
        "pages": selected_pages,
    }
    if include_manifest:
        payload["toc"] = document.get("toc") or []
        payload["page_manifest"] = [
            {
                "page": int(page.get("page") or index + 1),
                "width": float(page.get("width") or 1),
                "height": float(page.get("height") or 1),
            }
            for index, page in enumerate(all_pages)
        ]
    return payload


def clear_paper_derived(paper_id: str) -> None:
    import shutil

    d = paper_dir(paper_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
