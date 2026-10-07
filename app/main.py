from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.core.database import (
    Base,
    SessionLocal,
    engine,
    migrate_sqlite_schema,
)
from app.services.seed import seed_catalog

WORKSPACE_DIR = Path(__file__).resolve().parent / "static" / "workspace"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()

    with SessionLocal() as db:
        seed_catalog(db)

    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)

if WORKSPACE_DIR.exists():
    app.mount(
        "/workspace/assets",
        StaticFiles(directory=str(WORKSPACE_DIR)),
        name="workspace_assets",
    )


@app.get("/workspace")
@app.get("/workspace/")
def human_ai_workspace():
    """Phase 8 — Human + AI Workspace UI."""
    index = WORKSPACE_DIR / "index.html"
    return FileResponse(index)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0", "workspace": "/workspace"}
