from fastapi import APIRouter

from app.api.folders import router as folders_router
from app.api.jobs import router as jobs_router
from app.api.papers import router as papers_router
from app.api.settings import router as settings_router
from app.api.translations import router as translations_router

api_router = APIRouter(prefix="/api")
api_router.include_router(folders_router)
api_router.include_router(papers_router)
api_router.include_router(translations_router)
api_router.include_router(jobs_router)
api_router.include_router(settings_router)
