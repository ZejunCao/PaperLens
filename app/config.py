from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PAPERS_DIR = DATA_DIR / "papers"
DB_PATH = DATA_DIR / "paperlens.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPERLENS_", env_file=".env", extra="ignore")

    app_name: str = "PaperLens"
    debug: bool = True
    database_url: str = f"sqlite:///{DB_PATH.as_posix()}"
    data_dir: Path = DATA_DIR
    uploads_dir: Path = UPLOADS_DIR
    papers_dir: Path = PAPERS_DIR
    max_upload_bytes: int = 200 * 1024 * 1024
    disable_worker: bool = False

    parser: str = "mineru"
    mineru_backend: str = "pipeline"
    mineru_device: str = "cuda"
    mineru_lang: str = "en"
    mineru_model_source: str = "modelscope"
    # 0 表示按 MinerU 后端自动估算；可按实际模型/批量覆盖。
    mineru_gpu_memory_gb: float = 0.0
    mineru_api_token: str = ""
    mineru_api_base: str = "https://mineru.net"
    mineru_api_model: str = "vlm"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_runtime_dirs() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.papers_dir.mkdir(parents=True, exist_ok=True)
