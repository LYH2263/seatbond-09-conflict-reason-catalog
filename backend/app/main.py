from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.reason_codes import ensure_reason_codes
from app.services.seed import seed_if_empty


def _upgrade_schema() -> None:
    """轻量幂等 DDL：给旧库的 conflict_logs 补 reason_code 列（新建库无需此步）。

    需在目录同步之后执行：旧日志回填为 UNCLASSIFIED，该目录行此时已存在，
    满足外键引用。
    """

    inspector = inspect(engine)
    if "conflict_logs" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("conflict_logs")}
    if "reason_code" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE conflict_logs "
                "ADD COLUMN reason_code VARCHAR(48) DEFAULT 'UNCLASSIFIED'"
            )
        )
        conn.execute(text("UPDATE conflict_logs SET reason_code = 'UNCLASSIFIED' WHERE reason_code IS NULL"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 先同步原因码目录，保证失败写入总能落到码上（旧库回填也依赖该父行）
        ensure_reason_codes(db)
        db.commit()
        _upgrade_schema()
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
