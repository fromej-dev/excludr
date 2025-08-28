from fastapi import APIRouter

from app.core.config import get_settings
from app.features.auth.routers import router as auth_router
from app.features.projects.routers import router as projects_router
from app.features.users.routers import router as users_router

settings = get_settings()

router = APIRouter(prefix=settings.api_prefix)

router.include_router(auth_router)
router.include_router(projects_router)
router.include_router(users_router)
