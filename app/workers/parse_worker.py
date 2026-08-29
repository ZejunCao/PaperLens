"""后台解析 Worker：独立线程轮询 jobs 表，避免阻塞 API。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import ensure_runtime_dirs, get_settings
from app import database as dbmod
from app.models.job import Job, JobStatus
from app.models.paper import Paper, PaperStatus
from app.parsers import parse_pdf
from app.parsers.base import ParserError
from app.services.documents import paper_dir, save_document
from app.services.jobs import claim_next_parse_job, set_parse_progress
from app.services.papers import paper_file_path

logger = logging.getLogger("paperlens.worker")

_worker_thread: threading.Thread | None = None
_stop = threading.Event()


def execute_parse_job(db: Session, job: Job) -> None:
    """同步执行已 claim 的解析任务（测试与 worker 共用）。"""
    paper = db.get(Paper, job.paper_id)
    if paper is None:
        job.status = JobStatus.failed.value
        job.error_message = "论文记录不存在"
        job.stage = "failed"
        job.progress = 0
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        return

    pdf_path = paper_file_path(paper)
    out_dir = paper_dir(paper.id)
    try:
        if not pdf_path.exists():
            raise ParserError("PDF 文件缺失")

        def on_progress(stage: str, progress: int) -> None:
            set_parse_progress(db, job, stage=stage, progress=progress, paper=paper)

        document = parse_pdf(pdf_path, paper.id, out_dir, on_progress=on_progress)
        set_parse_progress(db, job, stage="saving", progress=92, paper=paper)
        save_document(document)
        paper.page_count = document.page_count
        if document.title and (not paper.title or paper.title == Path(paper.filename).stem):
            paper.title = document.title[:512]
        paper.status = PaperStatus.ready.value
        paper.error_message = None
        paper.parse_stage = "done"
        paper.parse_progress = 100
        job.status = JobStatus.succeeded.value
        job.error_message = None
        job.stage = "done"
        job.progress = 100
    except Exception as e:  # noqa: BLE001
        logger.exception("parse failed paper=%s", paper.id)
        paper.status = PaperStatus.failed.value
        paper.error_message = str(e)[:2000]
        paper.parse_stage = "failed"
        job.status = JobStatus.failed.value
        job.error_message = str(e)[:2000]
        job.stage = "failed"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _process_one() -> bool:
    db = dbmod.SessionLocal()
    try:
        job = claim_next_parse_job(db)
        if job is None:
            return False
        execute_parse_job(db, job)
        return True
    finally:
        db.close()


def _loop(poll_seconds: float = 0.8) -> None:
    ensure_runtime_dirs()
    logger.info("parse worker started")
    while not _stop.is_set():
        try:
            worked = _process_one()
            if not worked:
                _stop.wait(poll_seconds)
        except Exception:  # noqa: BLE001
            logger.exception("worker loop error")
            _stop.wait(1.5)
    logger.info("parse worker stopped")


def start_worker() -> None:
    global _worker_thread
    if get_settings().disable_worker:
        logger.info("parse worker disabled by settings")
        return
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop.clear()
    _worker_thread = threading.Thread(target=_loop, name="paperlens-parse-worker", daemon=True)
    _worker_thread.start()


def stop_worker() -> None:
    _stop.set()
