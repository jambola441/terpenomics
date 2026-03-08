from fastapi import APIRouter
from .portal import router as portal_router

router = APIRouter(prefix="/customer", tags=["customer-portal"])
router.include_router(portal_router)
