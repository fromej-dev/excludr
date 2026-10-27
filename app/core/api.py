from fastapi import APIRouter

from app.core.config import get_settings
from app.features.audit.routers import router as audit_router
from app.features.auth.routers import router as auth_router
from app.features.billing.routers import router as billing_router
from app.features.criteria.routers import router as criteria_router
from app.features.members.routers import router as members_router
from app.features.projects.routers import router as projects_router
from app.features.reporting.routers import router as reporting_router
from app.features.research.routers import router as research_router
from app.features.screening.routers import router as screening_router
from app.features.users.routers import router as users_router
from app.features.websocket.routers import router as websocket_router

settings = get_settings()

router = APIRouter(prefix=settings.api_prefix)

router.include_router(audit_router)
router.include_router(auth_router)
router.include_router(billing_router)
router.include_router(criteria_router)
router.include_router(members_router)
router.include_router(projects_router)
router.include_router(reporting_router)
router.include_router(research_router)
router.include_router(screening_router)
router.include_router(users_router)
router.include_router(websocket_router)
