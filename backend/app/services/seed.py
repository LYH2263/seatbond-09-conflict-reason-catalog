from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.services.bond_engine import HoldSpan, SeatCell, find_bond_across_rows
from app.services.reason_codes import ConflictReason, ensure_reason_codes, resolve_code


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Hall.id).limit(1)):
        return
    # 目录先行：冲突日志的 reason_code 外键依赖原因码目录
    ensure_reason_codes(db)

    h1 = Hall(name="一号厅", rows=8, cols=12, aisle_cols="5,6")
    h2 = Hall(name="二号厅", rows=6, cols=10, aisle_cols="4,5")
    db.add_all([h1, h2])
    db.flush()
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    s1 = Showtime(hall_id=h1.id, film_title="星际旅人", start_at=now + timedelta(hours=2))
    s2 = Showtime(hall_id=h1.id, film_title="雾都夜曲", start_at=now + timedelta(hours=5))
    s3 = Showtime(hall_id=h2.id, film_title="山海经异", start_at=now + timedelta(hours=3))
    db.add_all([s1, s2, s3])
    db.flush()
    db.add_all(
        [
            SeatHold(showtime_id=s1.id, order_code="SB-1001", row=3, start_col=2, end_col=4, party_size=3),
            SeatHold(showtime_id=s1.id, order_code="SB-1002", row=5, start_col=7, end_col=9, party_size=3),
            SeatHold(showtime_id=s3.id, order_code="SB-1003", row=2, start_col=1, end_col=2, party_size=2),
        ]
    )
    db.flush()

    # 失败一：与既有持座重叠（候选撞上 s1 第3排 2-4 的持座）
    db.add(
        ConflictLog(
            showtime_id=s1.id,
            party_size=4,
            reason_code=resolve_code(db, ConflictReason.OVERLAP_EXISTING_HOLD),
            reason="与既有持座重叠：第3排 2-4",
        )
    )

    # 失败二：连续空座不足 —— 先用引擎验证 s2 空厅确实凑不出 7 连座
    # （一号厅过道 5,6 将每排断为 1-4 / 7-12 两段，最长仅 6 连座）
    aisles = {int(x) for x in h1.aisle_cols.split(",") if x.strip()}
    seats_by_row = {
        r: [SeatCell(row=r, col=c, is_aisle=c in aisles) for c in range(1, h1.cols + 1)]
        for r in range(1, h1.rows + 1)
    }
    party = 7
    assert find_bond_across_rows(seats_by_row, [], party) is None
    db.add(
        ConflictLog(
            showtime_id=s2.id,
            party_size=party,
            reason_code=resolve_code(db, ConflictReason.NO_CONTIGUOUS_SEATS),
            reason=f"连续空座不足：全厅无满足 {party} 人的连续空座",
        )
    )
    db.commit()
