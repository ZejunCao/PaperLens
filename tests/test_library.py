from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Folder, Job, Paper  # noqa: F401
from app.schemas.folder import FolderCreate, FolderUpdate
from app.services import folders as folder_service
from app.services import papers as paper_service


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def make_paper(db: Session, *, folder_id: str | None = None, title: str = "Demo") -> Paper:
    paper_id = str(uuid.uuid4())
    paper = Paper(
        id=paper_id,
        filename=f"{paper_id}.pdf",
        title=title,
        storage_name=f"{paper_id}.pdf",
        content_hash=paper_id.replace("-", ""),
        page_count=10,
        file_size=100,
        status="ready",
        folder_id=folder_id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


def test_nested_folder_move_and_safe_folder_delete(db: Session):
    root = folder_service.create_folder(db, FolderCreate(name="研究方向"))
    child = folder_service.create_folder(
        db, FolderCreate(name="线性注意力", parent_id=root.id)
    )
    paper = make_paper(db, folder_id=root.id)

    moved = paper_service.update_paper(
        db, paper.id, folder_id=child.id, set_folder=True
    )
    assert moved.folder_id == child.id
    assert paper_service.list_papers(db, folder_id=root.id) == []
    assert paper_service.list_papers(db, folder_id=child.id)[0].id == paper.id

    folder_service.delete_folder(db, root.id)
    assert db.get(Folder, child.id).parent_id is None
    assert db.get(Paper, paper.id).folder_id == child.id

    folder_service.delete_folder(db, child.id)
    assert db.get(Paper, paper.id).folder_id is None
    assert paper_service.list_papers(db, view="unfiled")[0].id == paper.id


def test_folder_cycle_and_duplicate_name_are_rejected(db: Session):
    root = folder_service.create_folder(db, FolderCreate(name="研究方向"))
    child = folder_service.create_folder(db, FolderCreate(name="架构", parent_id=root.id))

    with pytest.raises(HTTPException) as duplicate:
        folder_service.create_folder(db, FolderCreate(name="研究方向"))
    assert duplicate.value.status_code == 409

    with pytest.raises(HTTPException) as cycle:
        folder_service.update_folder(db, root.id, FolderUpdate(parent_id=child.id))
    assert cycle.value.status_code == 409


def test_trash_restore_and_library_filters(db: Session):
    folder = folder_service.create_folder(db, FolderCreate(name="待读"))
    first = make_paper(db, folder_id=folder.id, title="Delta Network")
    second = make_paper(db, title="State Space Model")

    assert [p.id for p in paper_service.list_papers(db, folder_id=folder.id)] == [first.id]
    assert [p.id for p in paper_service.list_papers(db, view="unfiled")] == [second.id]
    assert paper_service.list_papers(db, query="Delta")[0].id == first.id

    paper_service.delete_paper(db, first.id)
    assert paper_service.list_papers(db, folder_id=folder.id) == []
    assert paper_service.list_papers(db, view="trash")[0].id == first.id
    paper_service.restore_paper(db, first.id)
    assert paper_service.list_papers(db, folder_id=folder.id)[0].id == first.id
