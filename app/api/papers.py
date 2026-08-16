from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.document import Document
from app.schemas.job import JobOut
from app.schemas.paper import PaperListResponse, PaperOut, PaperRename
from app.services import jobs as jobs_service
from app.services import papers as papers_service
from app.services.documents import load_document, paper_dir

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=PaperListResponse)
def list_papers(db: Session = Depends(get_db)) -> PaperListResponse:
    items = papers_service.list_papers(db)
    return PaperListResponse(items=items, total=len(items))


@router.post("", response_model=PaperOut, status_code=201)
async def upload_paper(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PaperOut:
    paper = await papers_service.create_paper_from_upload(db, file)
    return PaperOut.model_validate(paper)


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    return PaperOut.model_validate(papers_service.get_paper(db, paper_id))


@router.patch("/{paper_id}", response_model=PaperOut)
def rename_paper(paper_id: str, body: PaperRename, db: Session = Depends(get_db)) -> PaperOut:
    paper = papers_service.rename_paper(db, paper_id, body.title)
    return PaperOut.model_validate(paper)


@router.delete("/{paper_id}", status_code=204)
def delete_paper(paper_id: str, db: Session = Depends(get_db)) -> None:
    papers_service.delete_paper(db, paper_id)


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


@router.get("/{paper_id}/document", response_model=Document)
def get_document(paper_id: str, db: Session = Depends(get_db)) -> Document:
    papers_service.get_paper(db, paper_id)
    doc = load_document(paper_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档尚未解析完成")
    return doc


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
