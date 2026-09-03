from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.folder import Folder
from app.models.paper import Paper
from app.schemas.folder import FolderCreate, FolderOut, FolderUpdate


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="文件夹名称不能为空")
    return cleaned


def get_folder(db: Session, folder_id: str) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    return folder


def _ensure_unique_name(
    db: Session, name: str, parent_id: str | None, *, exclude_id: str | None = None
) -> None:
    query = select(Folder.id).where(func.lower(Folder.name) == name.lower())
    query = query.where(Folder.parent_id == parent_id)
    if exclude_id:
        query = query.where(Folder.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同级已有同名文件夹")


def _assert_valid_parent(db: Session, folder_id: str, parent_id: str | None) -> None:
    if parent_id is None:
        return
    if parent_id == folder_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件夹不能移入自身")
    current = get_folder(db, parent_id)
    seen = {folder_id}
    while current is not None:
        if current.id in seen:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能把文件夹移入其子文件夹")
        seen.add(current.id)
        current = db.get(Folder, current.parent_id) if current.parent_id else None


def list_folders(db: Session) -> list[FolderOut]:
    rows = db.execute(
        select(Folder, func.count(Paper.id))
        .outerjoin(Paper, (Paper.folder_id == Folder.id) & Paper.deleted_at.is_(None))
        .group_by(Folder.id)
        .order_by(Folder.sort_order.asc(), Folder.created_at.asc())
    ).all()
    return [
        FolderOut.model_validate(folder).model_copy(update={"paper_count": int(count)})
        for folder, count in rows
    ]


def create_folder(db: Session, body: FolderCreate) -> Folder:
    name = _clean_name(body.name)
    if body.parent_id:
        get_folder(db, body.parent_id)
    _ensure_unique_name(db, name, body.parent_id)
    max_order = db.scalar(
        select(func.max(Folder.sort_order)).where(Folder.parent_id == body.parent_id)
    )
    folder = Folder(name=name, parent_id=body.parent_id, sort_order=int(max_order or 0) + 1)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def update_folder(db: Session, folder_id: str, body: FolderUpdate) -> Folder:
    folder = get_folder(db, folder_id)
    fields = body.model_fields_set
    next_name = _clean_name(body.name) if "name" in fields and body.name is not None else folder.name
    next_parent = body.parent_id if "parent_id" in fields else folder.parent_id
    if "parent_id" in fields:
        _assert_valid_parent(db, folder.id, next_parent)
    _ensure_unique_name(db, next_name, next_parent, exclude_id=folder.id)
    folder.name = next_name
    folder.parent_id = next_parent
    if "sort_order" in fields and body.sort_order is not None:
        folder.sort_order = body.sort_order
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, folder_id: str) -> None:
    folder = get_folder(db, folder_id)
    # 删除分类不删除文献；直接论文回到未归档，子目录提升一级。
    db.execute(update(Paper).where(Paper.folder_id == folder.id).values(folder_id=None))
    db.execute(update(Folder).where(Folder.parent_id == folder.id).values(parent_id=folder.parent_id))
    db.delete(folder)
    db.commit()
