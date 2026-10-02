from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.services.seed import seed_catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
