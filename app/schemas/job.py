from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus, JobType


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: str
    type: JobType
    status: JobStatus
    error_message: str | None = None
    stage: str | None = None
    progress: int | None = None
    attempt: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
