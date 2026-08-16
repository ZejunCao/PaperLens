from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.paper import PaperStatus


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    title: str | None = None
    page_count: int | None = None
    file_size: int
    status: PaperStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PaperRename(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class PaperListResponse(BaseModel):
    items: list[PaperOut]
    total: int
