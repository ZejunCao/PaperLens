from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmConfigUpdate(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    model: str = ""


class LlmConfigOut(BaseModel):
    base_url: str
    api_key_set: bool
    api_key_masked: str = ""
    model: str
    configured: bool


class PageTranslation(BaseModel):
    status: Literal["pending", "ready", "failed"] = "pending"
    error: str | None = None
    sentences: dict[str, str] = Field(default_factory=dict)


class TranslationFile(BaseModel):
    paper_id: str
    target_lang: str = "zh-CN"
    prompt_version: int = 1
    provider: str = "openai_compatible"
    model: str = ""
    updated_at: str = ""
    pages: dict[str, PageTranslation] = Field(default_factory=dict)


class TranslationOut(BaseModel):
    paper_id: str
    target_lang: str
    configured: bool
    pages: dict[str, PageTranslation]
