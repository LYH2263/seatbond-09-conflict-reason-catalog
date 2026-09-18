from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ConflictLog, Hall, ReasonCode, SeatHold, Showtime
from app.schemas.schemas import (
    ConflictOut,
    HallOut,
    HoldOut,
    HoldRequest,
    ReasonCodeOut,
    ReasonCodeUpdate,
    SeatMapCell,
    SeatMapOut,
    ShowtimeOut,
)
from app.services.bond_engine import (
    HoldSpan,
    SeatCell,
    conflicts_with,
    find_bond_across_rows,
    find_contiguous_block,
)
from app.services.reason_codes import ConflictReason, ensure_reason_codes, resolve_code

api_router = APIRouter()


def _aisles(hall: Hall) -> list[int]:
    if not hall.aisle_cols.strip():
        return []
    return [int(x) for x in hall.aisle_cols.split(",") if x.strip()]


def _hall_out(h: Hall) -> HallOut:
    return HallOut(id=h.id, name=h.name, rows=h.rows, cols=h.cols, aisle_cols=_aisles(h))


def _log_conflict(
    db: Session,
    showtime_id: int,
    party_size: int,
    reason: ConflictReason,
    detail: str,
) -> ConflictLog:
    """写入一条带稳定 reason_code 的冲突日志，返回未提交对象。"""

    code = resolve_code(db, reason)
    entry = ConflictLog(
        showtime_id=showtime_id,
        party_size=party_size,
        reason_code=code,
        reason=detail,
    )
    db.add(entry)
    return entry


def _conflict_out(db: Session, log: ConflictLog) -> ConflictOut:
    rc = db.get(ReasonCode, log.reason_code)
    return ConflictOut(
        id=log.id,
        showtime_id=log.showtime_id,
        party_size=log.party_size,
        reason_code=log.reason_code,
        reason=log.reason,
        reason_description=rc.description_zh if rc else None,
        retry_recommended=rc.retry_recommended if rc else None,
        created_at=log.created_at,
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/halls", response_model=list[HallOut])
def list_halls(db: Session = Depends(get_db)):
    return [_hall_out(h) for h in db.scalars(select(Hall).order_by(Hall.id)).all()]


@api_router.get("/showtimes", response_model=list[ShowtimeOut])
def list_showtimes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Showtime).order_by(Showtime.start_at)).all()
    out = []
    for s in rows:
        hall = db.get(Hall, s.hall_id)
        out.append(
            ShowtimeOut(
                id=s.id,
                hall_id=s.hall_id,
                film_title=s.film_title,
                start_at=s.start_at,
                hall_name=hall.name if hall else None,
            )
        )
    return out


@api_router.get("/seatmap/{showtime_id}", response_model=SeatMapOut)
def seatmap(showtime_id: int, db: Session = Depends(get_db)):
    st = db.get(Showtime, showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    holds = db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()
    occupied: set[tuple[int, int]] = set()
    for h in holds:
        for c in range(h.start_col, h.end_col + 1):
            occupied.add((h.row, c))
    cells: list[SeatMapCell] = []
    total = hall.rows * hall.cols
    for r in range(1, hall.rows + 1):
        for c in range(1, hall.cols + 1):
            occ = (r, c) in occupied
            cells.append(
                SeatMapCell(
                    row=r,
                    col=c,
                    is_aisle=c in aisles,
                    occupied=occ,
                    heat=1.0 if occ else (0.15 if c in aisles else 0.0),
                )
            )
    return SeatMapOut(
        showtime_id=showtime_id,
        hall_name=hall.name,
        rows=hall.rows,
        cols=hall.cols,
        cells=cells,
    )


@api_router.get("/holds", response_model=list[HoldOut])
def list_holds(db: Session = Depends(get_db)):
    return db.scalars(select(SeatHold).order_by(SeatHold.id.desc())).all()


@api_router.get("/reason-codes", response_model=list[ReasonCodeOut])
def list_reason_codes(active_only: bool = False, db: Session = Depends(get_db)):
    """原因码目录；active_only=true 时仅返回启用码（供筛选下拉）。"""

    stmt = select(ReasonCode).order_by(ReasonCode.code)
    if active_only:
        stmt = stmt.where(ReasonCode.enabled.is_(True))
    return db.scalars(stmt).all()


@api_router.patch("/reason-codes/{code}", response_model=ReasonCodeOut)
def update_reason_code(code: str, body: ReasonCodeUpdate, db: Session = Depends(get_db)):
    """启用/停用原因码，亦可维护说明与重试建议。"""

    rc = db.get(ReasonCode, code)
    if rc is None:
        raise HTTPException(404, f"原因码不存在：{code}")
    if body.enabled is not None:
        rc.enabled = body.enabled
    if body.description_zh is not None:
        rc.description_zh = body.description_zh
    if body.retry_recommended is not None:
        rc.retry_recommended = body.retry_recommended
    db.commit()
    db.refresh(rc)
    return rc


@api_router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(reason_code: str | None = None, db: Session = Depends(get_db)):
    """冲突日志；可按稳定原因码筛选，停用码的历史日志仍可查出。"""

    stmt = select(ConflictLog).order_by(ConflictLog.id.desc())
    if reason_code:
        stmt = stmt.where(ConflictLog.reason_code == reason_code)
    logs = db.scalars(stmt).all()
    return [_conflict_out(db, log) for log in logs]


@api_router.post("/holds", response_model=HoldOut)
def create_hold(body: HoldRequest, db: Session = Depends(get_db)):
    st = db.get(Showtime, body.showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    existing = db.scalars(select(SeatHold).where(SeatHold.showtime_id == body.showtime_id)).all()
    holds = [HoldSpan(row=h.row, start_col=h.start_col, end_col=h.end_col) for h in existing]
    seats_by_row: dict[int, list[SeatCell]] = {}
    for r in range(1, hall.rows + 1):
        seats_by_row[r] = [
            SeatCell(row=r, col=c, is_aisle=c in aisles) for c in range(1, hall.cols + 1)
        ]

    block = None
    if body.preferred_row:
        block = find_contiguous_block(
            seats_by_row.get(body.preferred_row, []), holds, body.preferred_row, body.party_size
        )
    if block is None:
        block = find_bond_across_rows(seats_by_row, holds, body.party_size)
    if block is None:
        _log_conflict(
            db,
            body.showtime_id,
            body.party_size,
            ConflictReason.NO_CONTIGUOUS_SEATS,
            f"连续空座不足：全厅无满足 {body.party_size} 人的连续空座",
        )
        db.commit()
        raise HTTPException(409, "无足够连续空座")

    # 兜底校验：并发写入等情况下候选块可能与既有持座重叠
    hits = conflicts_with(holds, block)
    if hits:
        hit = hits[0]
        _log_conflict(
            db,
            body.showtime_id,
            body.party_size,
            ConflictReason.OVERLAP_EXISTING_HOLD,
            f"与既有持座重叠：第{hit.row}排 {hit.start_col}-{hit.end_col}",
        )
        db.commit()
        raise HTTPException(409, "与既有持座冲突")

    code = f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}"
    hold = SeatHold(
        showtime_id=body.showtime_id,
        order_code=code,
        row=block.row,
        start_col=block.start_col,
        end_col=block.end_col,
        party_size=body.party_size,
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return hold
