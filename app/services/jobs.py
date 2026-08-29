from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus, JobType
from app.models.paper import Paper, PaperStatus
from app.services import papers as papers_service
from app.services.documents import clear_paper_derived


def set_parse_progress(
    db: Session,
    job: Job,
    *,
    stage: str,
    progress: int,
    paper: Paper | None = None,
) -> None:
    """写入任务/论文的解析阶段与进度（0–100），立即 commit 供前端轮询。"""
    progress = max(0, min(100, int(progress)))
    job.stage = stage
    job.progress = progress
    target = paper or db.get(Paper, job.paper_id)
    if target is not None:
        target.parse_stage = stage
        target.parse_progress = progress
    db.commit()


def enqueue_parse_job(db: Session, paper_id: str, *, reset_document: bool = False) -> Job:
    paper = papers_service.get_paper(db, paper_id)
    if reset_document:
        clear_paper_derived(paper_id)

    # 取消同论文尚未开始的旧任务
    pending = db.scalars(
        select(Job).where(
            Job.paper_id == paper_id,
            Job.type == JobType.parse.value,
            Job.status == JobStatus.queued.value,
        )
    ).all()
    for old in pending:
        old.status = JobStatus.cancelled.value
        old.finished_at = datetime.now(timezone.utc)

    job = Job(
        id=str(uuid.uuid4()),
        paper_id=paper.id,
        type=JobType.parse.value,
        status=JobStatus.queued.value,
        stage="queued",
        progress=0,
        attempt=0,
    )
    paper.status = PaperStatus.queued.value
    paper.error_message = None
    paper.parse_stage = "queued"
    paper.parse_progress = 0
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return job


def latest_parse_job(db: Session, paper_id: str) -> Job | None:
    return db.scalar(
        select(Job)
        .where(Job.paper_id == paper_id, Job.type == JobType.parse.value)
        .order_by(Job.created_at.desc())
        .limit(1)
    )


def claim_next_parse_job(db: Session) -> Job | None:
    job = db.scalar(
        select(Job)
        .where(Job.type == JobType.parse.value, Job.status == JobStatus.queued.value)
        .order_by(Job.created_at.asc())
        .limit(1)
    )
    if job is None:
        return None
    job.status = JobStatus.running.value
    job.attempt = (job.attempt or 0) + 1
    job.started_at = datetime.now(timezone.utc)
    job.error_message = None
    job.stage = "preparing"
    job.progress = 5
    paper = db.get(Paper, job.paper_id)
    if paper:
        paper.status = PaperStatus.parsing.value
        paper.error_message = None
        paper.parse_stage = "preparing"
        paper.parse_progress = 5
    db.commit()
    db.refresh(job)
    return job
