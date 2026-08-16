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
        attempt=0,
    )
    paper.status = PaperStatus.queued.value
    paper.error_message = None
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
    paper = db.get(Paper, job.paper_id)
    if paper:
        paper.status = PaperStatus.parsing.value
        paper.error_message = None
    db.commit()
    db.refresh(job)
    return job
