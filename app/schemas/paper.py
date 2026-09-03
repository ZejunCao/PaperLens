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
    parse_stage: str | None = None
    parse_progress: int | None = None
    folder_id: str | None = None
    deleted_at: datetime | None = None
    last_opened_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaperUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    folder_id: str | None = None


class PaperFromUrl(BaseModel):
    """从 arXiv 链接或裸 ID 导入。"""

    url: str = Field(min_length=3, max_length=512, description="arXiv abs/pdf 链接或 ID")
    folder_id: str | None = None


class PaperListResponse(BaseModel):
    items: list[PaperOut]
    total: int
