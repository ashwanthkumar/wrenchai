"""Aggregate API routers under /api prefix."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.sessions import router as sessions_router
from app.api.messages import router as messages_router
from app.api.manuals import router as manuals_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(sessions_router)
api_router.include_router(messages_router)
api_router.include_router(manuals_router)
