# main.py
from fastapi import FastAPI, Response

from database import create_db_and_tables
from routes_me import router as me_router
from routes.admin import router as admin_router
from routes.customer import router as customer_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(title="Dispensary MVP API")
# The portal's browse endpoints return large JSON documents (a busy category
# runs to megabytes uncompressed). Nothing in front of the app compresses for
# us, so do it here.
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # Allow cookies and authorization headers to be included in cross-origin requests
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me_router)
app.include_router(admin_router)
app.include_router(customer_router)


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.get("/health")
def health():
    return Response(content='{"ok": true}', media_type="application/json")
