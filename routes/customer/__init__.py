from fastapi import APIRouter
from .partners import router as partners_router
from .portal import router as portal_router

router = APIRouter(prefix="/customer", tags=["customer-portal"])
router.include_router(partners_router)
router.include_router(portal_router)
