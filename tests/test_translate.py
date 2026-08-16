from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.schemas.document import ContentBlock, Document, PageLayout, Sentence
from app.services.documents import save_document


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
    monkeypatch.setenv("PAPERLENS_PARSER", "pymupdf")

    from app.config import get_settings
    from app.models import Job, Paper  # noqa: F401
    from app.workers.parse_worker import stop_worker

    get_settings.cache_clear()
    settings = get_settings()
    settings.data_dir = tmp_path
    settings.uploads_dir = uploads
    settings.papers_dir = papers
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.disable_worker = True

    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def _override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    stop_worker()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_llm_settings_roundtrip(client: TestClient):
    empty = client.get("/api/settings/llm").json()
    assert empty["configured"] is False
    assert empty["api_key_set"] is False

    saved = client.put(
        "/api/settings/llm",
        json={"base_url": "http://127.0.0.1:11434/v1", "api_key": "sk-test-key-1234", "model": "qwen"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert body["api_key_set"] is True
    assert "1234" in body["api_key_masked"]
    assert "sk-test-key-1234" not in body["api_key_masked"]

    keep = client.put(
        "/api/settings/llm",
        json={"base_url": "http://127.0.0.1:11434/v1", "api_key": "", "model": "qwen2"},
    ).json()
    assert keep["model"] == "qwen2"
    assert keep["api_key_set"] is True


def test_translate_page_uses_sentence_ids(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings
    from app.models.paper import PaperStatus
    from app.services import papers as papers_service

    settings = get_settings()
    papers_dir = settings.papers_dir
    pid = "paper-trans-1"
    doc = Document(
        paper_id=pid,
        parser="test",
        parser_version="1",
        page_count=1,
        pages=[
            PageLayout(
                page=1,
                width=612,
                height=792,
                blocks=[
                    ContentBlock(
                        id="b1",
                        type="paragraph",
                        page=1,
                        order=0,
                        bbox=[70, 80, 500, 120],
                        source_text="Hello world. Second sentence.",
                        sentences=[
                            Sentence(id="s_aaa", text="Hello world.", order=0),
                            Sentence(id="s_bbb", text="Second sentence.", order=1),
                        ],
                    )
                ],
            )
        ],
        blocks=[],
    )
    save_document(doc)

    class FakePaper:
        id = pid
        status = PaperStatus.ready.value

    monkeypatch.setattr(papers_service, "get_paper", lambda db, paper_id: FakePaper())

    client.put(
        "/api/settings/llm",
        json={"base_url": "http://127.0.0.1:9/v1", "api_key": "k", "model": "m"},
    )

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "sentences": [
                                        {"id": "s_aaa", "zh": "你好，世界。"},
                                        {"id": "s_bbb", "zh": "第二句。"},
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr("app.services.translate.httpx.Client", FakeClient)
    res = client.post(f"/api/papers/{pid}/translations/pages/1")
    assert res.status_code == 200, res.text
    pages = res.json()["pages"]
    assert pages["1"]["status"] == "ready"
    assert pages["1"]["sentences"]["s_aaa"] == "你好，世界。"
    cached = json.loads((papers_dir / pid / "translations" / "zh-CN.json").read_text(encoding="utf-8"))
    assert cached["pages"]["1"]["sentences"]["s_bbb"] == "第二句。"
