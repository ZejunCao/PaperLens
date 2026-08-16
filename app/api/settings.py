from fastapi import APIRouter

from app.schemas.llm import LlmConfigOut, LlmConfigUpdate
from app.services.llm_settings import load_llm_config_raw, save_llm_config, to_llm_out

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm", response_model=LlmConfigOut)
def get_llm_settings() -> LlmConfigOut:
    return to_llm_out()


@router.put("/llm", response_model=LlmConfigOut)
def put_llm_settings(body: LlmConfigUpdate) -> LlmConfigOut:
    return save_llm_config(body)
