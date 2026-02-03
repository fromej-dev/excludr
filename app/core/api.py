from fastapi import APIRouter

from app.core.config import get_settings
from app.features.auth.routers import router as auth_router
from app.features.criteria.routers import router as criteria_router
from app.features.projects.routers import router as projects_router
from app.features.research.routers import router as research_router
from app.features.screening.routers import router as screening_router
from app.features.users.routers import router as users_router
from app.features.websocket.routers import router as websocket_router

settings = get_settings()

router = APIRouter(prefix=settings.api_prefix)

router.include_router(auth_router)
router.include_router(criteria_router)
router.include_router(projects_router)
router.include_router(research_router)
router.include_router(screening_router)
router.include_router(users_router)
router.include_router(websocket_router)
