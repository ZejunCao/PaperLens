"""默认测试走 PyMuPDF，避免拉起 MinerU 模型。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _force_pymupdf_parser(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PAPERLENS_PARSER", "pymupdf")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    papers = tmp_path / "papers"
    uploads.mkdir()
    papers.mkdir()

    monkeypatch.setenv("PAPERLENS_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("PAPERLENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PAPERLENS_UPLOADS_DIR", str(uploads))
    monkeypatch.setenv("PAPERLENS_PAPERS_DIR", str(papers))
    monkeypatch.setenv("PAPERLENS_DISABLE_WORKER", "true")

    from app.config import get_settings
    from app.models import Folder, Job, Paper  # noqa: F401
    from app.workers.parse_worker import stop_worker

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    import app.database as dbmod

    dbmod.engine = engine
    dbmod.SessionLocal = testing_session
    app = create_app()

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, testing_session
    stop_worker()
    app.dependency_overrides.clear()
    get_settings.cache_clear()
