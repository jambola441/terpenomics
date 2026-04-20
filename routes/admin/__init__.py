from fastapi import APIRouter
from .customers import router as customers_router
from .dispensaries import router as dispensaries_router
from .lab_reports import router as lab_reports_router
from .listings import router as listings_router
from .products import router as products_router
from .purchases import router as purchases_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(customers_router)
router.include_router(dispensaries_router)
router.include_router(lab_reports_router)
router.include_router(listings_router)
router.include_router(products_router)
router.include_router(purchases_router)
