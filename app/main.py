from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth_routes import router as auth_router
from app.api.routes import router
from app.core.config import settings
from app.core.database import (
    Base,
    SessionLocal,
    engine,
    migrate_sqlite_schema,
)
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.services.seed import seed_catalog

WORKSPACE_DIR = Path(__file__).resolve().parent / "static" / "workspace"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()

    with SessionLocal() as db:
        seed_catalog(db)

    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.include_router(auth_router)
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
    """Phase 8 / Job 12 — Human + AI Workspace UI."""
    index = WORKSPACE_DIR / "index.html"
    return FileResponse(index)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "env": settings.app_env,
        "workspace": "/workspace",
    }


@app.get("/health/ready")
def readiness():
    """Readiness probe — verifies DB connectivity."""
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
        db_error = None
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = str(exc)

    status_code = "ok" if db_ok else "not_ready"
    return {
        "status": status_code,
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
        "storage_backend": settings.storage_backend,
        "auth_enabled": settings.auth_enabled,
    }
