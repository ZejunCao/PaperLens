from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.job import JobOut
from app.schemas.paper import PaperFromUrl, PaperListResponse, PaperOut, PaperUpdate
from app.services import jobs as jobs_service
from app.services import papers as papers_service
from app.services.documents import (
    document_chunk_payload,
    document_path,
    load_document_json,
    paper_dir,
)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=PaperListResponse)
def list_papers(
    folder_id: str | None = Query(None),
    view: Literal["all", "unfiled", "processing", "recent", "trash"] = Query("all"),
    query: str = Query("", max_length=200),
    sort: Literal["updated", "created", "title", "opened"] = Query("updated"),
    db: Session = Depends(get_db),
) -> PaperListResponse:
    items = papers_service.list_papers(
        db, folder_id=folder_id, view=view, query=query, sort=sort
    )
    return PaperListResponse(items=items, total=len(items))


@router.post("", response_model=PaperOut, status_code=201)
async def upload_paper(
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
    db: Session = Depends(get_db),
) -> PaperOut:
    paper = await papers_service.create_paper_from_upload(db, file, folder_id)
    return PaperOut.model_validate(paper)


@router.post("/from-url", response_model=PaperOut, status_code=201)
def import_paper_from_url(body: PaperFromUrl, db: Session = Depends(get_db)) -> PaperOut:
    """下载 arXiv PDF 到本地 uploads，再入队解析。"""
    paper = papers_service.create_paper_from_arxiv(db, body.url, body.folder_id)
    return PaperOut.model_validate(paper)


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    return PaperOut.model_validate(papers_service.get_paper(db, paper_id))


@router.patch("/{paper_id}", response_model=PaperOut)
def update_paper(paper_id: str, body: PaperUpdate, db: Session = Depends(get_db)) -> PaperOut:
    fields = body.model_fields_set
    paper = papers_service.update_paper(
        db,
        paper_id,
        title=body.title,
        set_title="title" in fields,
        folder_id=body.folder_id,
        set_folder="folder_id" in fields,
    )
    return PaperOut.model_validate(paper)


@router.delete("/{paper_id}", status_code=204)
def delete_paper(paper_id: str, db: Session = Depends(get_db)) -> None:
    papers_service.delete_paper(db, paper_id)


@router.post("/{paper_id}/restore", response_model=PaperOut)
def restore_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    return PaperOut.model_validate(papers_service.restore_paper(db, paper_id))


@router.post("/{paper_id}/opened", response_model=PaperOut)
def mark_paper_opened(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    return PaperOut.model_validate(papers_service.mark_opened(db, paper_id))


@router.post("/{paper_id}/metadata", response_model=PaperOut)
def refresh_paper_metadata(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    return PaperOut.model_validate(papers_service.refresh_paper_metadata(db, paper_id))


@router.delete("/{paper_id}/permanent", status_code=204)
def permanently_delete_paper(paper_id: str, db: Session = Depends(get_db)) -> None:
    papers_service.permanently_delete_paper(db, paper_id)


@router.get("/{paper_id}/file")
def download_paper_file(paper_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path: Path = papers_service.resolve_paper_file(db, paper_id)
    paper = papers_service.get_paper(db, paper_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=paper.filename,
        content_disposition_type="inline",
    )


@router.get("/{paper_id}/document")
def get_document(paper_id: str, db: Session = Depends(get_db)) -> FileResponse:
    papers_service.get_paper(db, paper_id)
    path = document_path(paper_id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档尚未解析完成")
    return FileResponse(path, media_type="application/json")


@router.get("/{paper_id}/document/chunk")
def get_document_chunk(
    paper_id: str,
    start_page: int = Query(1, ge=1),
    page_limit: int = Query(8, ge=1, le=32),
    include_manifest: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    papers_service.get_paper(db, paper_id)
    document = load_document_json(paper_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档尚未解析完成")
    return document_chunk_payload(
        document,
        start_page=start_page,
        page_limit=page_limit,
        include_manifest=include_manifest,
    )


@router.post("/{paper_id}/parse", response_model=JobOut, status_code=202)
def retry_parse(paper_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = jobs_service.enqueue_parse_job(db, paper_id, reset_document=True)
    return JobOut.model_validate(job)


@router.get("/{paper_id}/jobs/latest", response_model=JobOut)
def latest_job(paper_id: str, db: Session = Depends(get_db)) -> JobOut:
    papers_service.get_paper(db, paper_id)
    job = jobs_service.latest_parse_job(db, paper_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无解析任务")
    return JobOut.model_validate(job)


@router.get("/{paper_id}/assets/{asset_path:path}")
def get_asset(paper_id: str, asset_path: str, db: Session = Depends(get_db)) -> FileResponse:
    papers_service.get_paper(db, paper_id)
    base = paper_dir(paper_id).resolve()
    target = (base / asset_path).resolve()
    if not str(target).startswith(str(base)) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
    return FileResponse(target)
