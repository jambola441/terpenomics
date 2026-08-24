from fastapi import APIRouter
from .orders import router as orders_router
from .portal import router as portal_router

router = APIRouter(prefix="/customer", tags=["customer-portal"])
# orders first: its literal /orders/bitpay/ipn path must win over portal's
# /{customer_id}/... parameterized paths
router.include_router(orders_router)
router.include_router(portal_router)
