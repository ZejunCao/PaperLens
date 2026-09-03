from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.folder import FolderCreate, FolderListResponse, FolderOut, FolderUpdate
from app.services import folders as folders_service

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=FolderListResponse)
def list_folders(db: Session = Depends(get_db)) -> FolderListResponse:
    return FolderListResponse(items=folders_service.list_folders(db))


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(body: FolderCreate, db: Session = Depends(get_db)) -> FolderOut:
    folder = folders_service.create_folder(db, body)
    return FolderOut.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderOut)
def update_folder(
    folder_id: str, body: FolderUpdate, db: Session = Depends(get_db)
) -> FolderOut:
    folder = folders_service.update_folder(db, folder_id, body)
    return FolderOut.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str, db: Session = Depends(get_db)) -> None:
    folders_service.delete_folder(db, folder_id)
