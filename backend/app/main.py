from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.reason_codes import ensure_reason_catalog
from app.services.seed import seed_if_empty


def _ensure_reason_code_column() -> None:
    """Add reason_code to conflict_logs on databases created before it existed."""
    if "reason_code" in {c["name"] for c in inspect(engine).get_columns("conflict_logs")}:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE conflict_logs "
                "ADD COLUMN reason_code VARCHAR(40) NOT NULL DEFAULT 'UNCLASSIFIED'"
            )
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_reason_code_column()
    db = SessionLocal()
    try:
        ensure_reason_catalog(db)
        if settings.seed_on_empty:
            seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(title="SeatBond", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
