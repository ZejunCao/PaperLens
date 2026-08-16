from fastapi import APIRouter

from app.api.jobs import router as jobs_router
from app.api.papers import router as papers_router

api_router = APIRouter(prefix="/api")
api_router.include_router(papers_router)
api_router.include_router(jobs_router)
