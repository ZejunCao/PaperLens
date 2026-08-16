from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.llm import TranslationOut
from app.services import papers as papers_service
from app.services.translate import get_translations, translate_page

router = APIRouter(prefix="/papers", tags=["translations"])


@router.get("/{paper_id}/translations", response_model=TranslationOut)
def read_translations(paper_id: str, db: Session = Depends(get_db)) -> TranslationOut:
    papers_service.get_paper(db, paper_id)
    return get_translations(paper_id)


@router.post("/{paper_id}/translations/pages/{page}", response_model=TranslationOut)
def translate_paper_page(
    paper_id: str,
    page: int,
    db: Session = Depends(get_db),
) -> TranslationOut:
    papers_service.get_paper(db, paper_id)
    return translate_page(paper_id, page)
