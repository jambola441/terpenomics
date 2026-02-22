from fastapi import APIRouter
from .customers import router as customers_router
from .products import router as products_router
from .purchases import router as purchases_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(customers_router)
router.include_router(products_router)
router.include_router(purchases_router)
