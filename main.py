# main.py
from fastapi import FastAPI, Response

from database import create_db_and_tables
from routes_me import router as me_router
from routes.admin import router as admin_router
from routes.customer import router as customer_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Dispensary MVP API")
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
    # DEV ONLY: creates tables from models
    create_db_and_tables()


@app.get("/health")
def health():
    return Response(content='{"ok": true}', media_type="application/json")
