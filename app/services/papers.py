from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.folder import Folder
from app.models.paper import Paper, PaperStatus
from app.services.arxiv import download_arxiv_pdf, normalize_arxiv_id

PDF_MAGIC = b"%PDF"
SAFE_FILENAME_RE = re.compile(r"[^\w.\-()+\[\]\u4e00-\u9fff ]+", re.UNICODE)


def sanitize_filename(name: str) -> str:
    base = Path(name).name.strip() or "untitled.pdf"
    cleaned = SAFE_FILENAME_RE.sub("_", base).strip(" ._")
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned[:200]


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def paper_file_path(paper: Paper, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.uploads_dir / paper.storage_name


def estimate_page_count(data: bytes) -> int | None:
    """粗略统计 /Type /Page 出现次数，仅作库列表展示，非权威页数。"""
    try:
        text = data.decode("latin-1", errors="ignore")
    except Exception:
        return None
    # 排除 /Type /Pages（目录对象）
    count = len(re.findall(r"/Type\s*/Page(?!\s*s)", text))
    return count if count > 0 else None


def _validate_folder(db: Session, folder_id: str | None) -> None:
    if folder_id is not None and db.get(Folder, folder_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")


def create_paper_from_bytes(
    db: Session, data: bytes, original_filename: str, folder_id: str | None = None
) -> Paper:
    """落盘 PDF、去重、入库并入队解析。"""
    settings = get_settings()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大（上限 {settings.max_upload_bytes} 字节）",
        )
    if not data.startswith(PDF_MAGIC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件头不是有效 PDF")

    _validate_folder(db, folder_id)
    content_hash = compute_sha256(data)
    existing = db.scalar(select(Paper).where(Paper.content_hash == content_hash))
    if existing is not None:
        if folder_id is not None:
            existing.folder_id = folder_id
        existing.deleted_at = None
        db.commit()
        db.refresh(existing)
        return existing

    paper_id = str(uuid.uuid4())
    storage_name = f"{paper_id}.pdf"
    dest = settings.uploads_dir / storage_name
    dest.write_bytes(data)

    filename = sanitize_filename(original_filename)
    title = Path(filename).stem
    paper = Paper(
        id=paper_id,
        filename=filename,
        title=title,
        storage_name=storage_name,
        content_hash=content_hash,
        page_count=estimate_page_count(data),
        file_size=len(data),
        status=PaperStatus.queued.value,
        error_message=None,
        folder_id=folder_id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    from app.services.jobs import enqueue_parse_job

    enqueue_parse_job(db, paper.id)
    db.refresh(paper)
    return paper


async def create_paper_from_upload(
    db: Session, upload: UploadFile, folder_id: str | None = None
) -> Paper:
    original = upload.filename or "untitled.pdf"
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 PDF 文件")

    data = await upload.read()
    return create_paper_from_bytes(db, data, original, folder_id)


def create_paper_from_arxiv(
    db: Session, url_or_id: str, folder_id: str | None = None
) -> Paper:
    """解析 arXiv 链接/ID → 本地下载 PDF → 入库并排队解析。"""
    settings = get_settings()
    arxiv_id = normalize_arxiv_id(url_or_id)
    data = download_arxiv_pdf(arxiv_id, max_bytes=settings.max_upload_bytes)
    safe_id = arxiv_id.replace("/", "_")
    return create_paper_from_bytes(db, data, f"arxiv-{safe_id}.pdf", folder_id)


def list_papers(
    db: Session,
    *,
    folder_id: str | None = None,
    view: str = "all",
    query: str = "",
    sort: str = "updated",
) -> list[Paper]:
    stmt = select(Paper)
    if view == "trash":
        stmt = stmt.where(Paper.deleted_at.is_not(None))
    else:
        stmt = stmt.where(Paper.deleted_at.is_(None))
    if folder_id is not None:
        _validate_folder(db, folder_id)
        stmt = stmt.where(Paper.folder_id == folder_id)
    elif view == "unfiled":
        stmt = stmt.where(Paper.folder_id.is_(None))
    elif view == "processing":
        stmt = stmt.where(Paper.status.in_([PaperStatus.queued.value, PaperStatus.parsing.value]))
    elif view == "recent":
        stmt = stmt.where(Paper.last_opened_at.is_not(None))
    term = query.strip()
    if term:
        pattern = f"%{term}%"
        stmt = stmt.where(or_(Paper.title.ilike(pattern), Paper.filename.ilike(pattern)))
    order = {
        "created": Paper.created_at.desc(),
        "title": Paper.title.asc(),
        "opened": Paper.last_opened_at.desc(),
    }.get(sort, Paper.updated_at.desc())
    return list(db.scalars(stmt.order_by(order, Paper.created_at.desc())).all())


def get_paper(db: Session, paper_id: str, *, include_deleted: bool = False) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None or (paper.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="论文不存在")
    return paper


def rename_paper(db: Session, paper_id: str, title: str) -> Paper:
    paper = get_paper(db, paper_id)
    paper.title = title.strip()
    db.commit()
    db.refresh(paper)
    return paper


def update_paper(
    db: Session,
    paper_id: str,
    *,
    title: str | None = None,
    set_title: bool = False,
    folder_id: str | None = None,
    set_folder: bool = False,
) -> Paper:
    paper = get_paper(db, paper_id)
    if set_title:
        cleaned = (title or "").strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="论文标题不能为空"
            )
        paper.title = cleaned
    if set_folder:
        _validate_folder(db, folder_id)
        paper.folder_id = folder_id
    db.commit()
    db.refresh(paper)
    return paper


def delete_paper(db: Session, paper_id: str) -> None:
    paper = get_paper(db, paper_id)
    paper.deleted_at = datetime.now(timezone.utc)
    db.commit()


def restore_paper(db: Session, paper_id: str) -> Paper:
    paper = get_paper(db, paper_id, include_deleted=True)
    paper.deleted_at = None
    db.commit()
    db.refresh(paper)
    return paper


def mark_opened(db: Session, paper_id: str) -> Paper:
    paper = get_paper(db, paper_id)
    paper.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(paper)
    return paper


def permanently_delete_paper(db: Session, paper_id: str) -> None:
    paper = get_paper(db, paper_id, include_deleted=True)
    path = paper_file_path(paper)
    db.delete(paper)
    db.commit()
    if path.exists():
        path.unlink()
    from app.services.documents import clear_paper_derived

    clear_paper_derived(paper_id)


def resolve_paper_file(db: Session, paper_id: str) -> Path:
    paper = get_paper(db, paper_id)
    path = paper_file_path(paper)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF 文件缺失")
    return path
