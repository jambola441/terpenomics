from fastapi import APIRouter

from .portal import router as portal_router

router = APIRouter(prefix="/partner", tags=["partner"])
router.include_router(portal_router)
