from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.services.reason_codes import ReasonCode, ensure_reason_catalog


def seed_if_empty(db: Session) -> None:
    ensure_reason_catalog(db)
    if db.scalar(select(Hall.id).limit(1)):
        return
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
    # 两类失败样本：空座不足与持座重叠，reason_code 必须不同
    db.add_all(
        [
            ConflictLog(
                showtime_id=s2.id,
                party_size=8,
                reason="无足够连续空座（人数 8）",
                reason_code=ReasonCode.NO_CONTIGUOUS_BLOCK.value,
            ),
            ConflictLog(
                showtime_id=s1.id,
                party_size=4,
                reason="与既有持座重叠：第3排 2-4",
                reason_code=ReasonCode.OVERLAP_EXISTING_HOLD.value,
            ),
        ]
    )
    db.commit()
