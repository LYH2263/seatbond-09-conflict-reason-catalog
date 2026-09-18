"""冲突原因码目录：失败落码、按码筛选、目录启停、成功主路径不受影响。"""

from sqlalchemy import select

from app.models.models import ConflictLog, ReasonCode, Showtime
from app.services.reason_codes import ConflictReason


SEED_CODES = {
    ConflictReason.NO_CONTIGUOUS_SEATS.value,
    ConflictReason.OVERLAP_EXISTING_HOLD.value,
}
PRESET_CODES = {
    "NO_CONTIGUOUS_SEATS",
    "OVERLAP_EXISTING_HOLD",
    "COUPLE_PAIR_SPLIT",
    "OBSTRUCTED_VIEW",
    "AISLE_CROSSING",
    "UNCLASSIFIED",
}


def test_catalog_preset_and_flags(client):
    rows = client.get("/api/reason-codes").json()
    codes = {r["code"] for r in rows}
    assert PRESET_CODES <= codes
    by = {r["code"]: r for r in rows}
    # 后几项业务尚未全开，目录与枚举也要先就绪且默认启用
    for c in ("COUPLE_PAIR_SPLIT", "OBSTRUCTED_VIEW", "AISLE_CROSSING", "UNCLASSIFIED"):
        assert by[c]["enabled"] is True
        assert by[c]["description_zh"]
    # 遮挡、跨过道属硬性不可锁，不建议重试；空座不足可改人数重试
    assert by["NO_CONTIGUOUS_SEATS"]["retry_recommended"] is True
    assert by["OBSTRUCTED_VIEW"]["retry_recommended"] is False
    assert by["AISLE_CROSSING"]["retry_recommended"] is False


def test_seed_two_failures_have_distinct_codes(client):
    """种子分别制造空座不足与重叠，两条日志 reason_code 必须不同。"""

    rows = client.get("/api/reason-codes").json()  # warm：确认目录就绪
    assert rows

    logs = client.get("/api/conflicts").json()
    seeded = [c for c in logs if c["reason_code"] in SEED_CODES]
    codes = {c["reason_code"] for c in seeded}
    assert SEED_CODES <= codes
    no_seats = next(c for c in seeded if c["reason_code"] == "NO_CONTIGUOUS_SEATS")
    overlap = next(c for c in seeded if c["reason_code"] == "OVERLAP_EXISTING_HOLD")
    assert no_seats["reason_code"] != overlap["reason_code"]
    # 可读说明始终随码返回
    assert no_seats["reason_description"] and overlap["reason_description"]
    assert no_seats["retry_recommended"] is True
    for c in seeded:
        assert c["reason"]  # 人读说明仍保留


def test_failed_hold_writes_stable_reason_code(client, db):
    # s3：二号厅 10 列、过道 4/5，最长连段仅 5 座（6-10），7 人必失败
    s3 = db.scalar(select(Showtime).where(Showtime.film_title == "山海经异"))
    before = len(client.get("/api/conflicts").json())

    res = client.post("/api/holds", json={"showtime_id": s3.id, "party_size": 7})
    assert res.status_code == 409

    logs = client.get("/api/conflicts").json()
    assert len(logs) == before + 1
    entry = logs[0]
    assert entry["showtime_id"] == s3.id
    assert entry["party_size"] == 7
    assert entry["reason_code"] == ConflictReason.NO_CONTIGUOUS_SEATS.value
    assert entry["reason_description"]  # 目录说明联查可见


def test_log_conflict_always_carries_code(client, db):
    """重叠分支虽在并发下才触发，落码工具同样必须写入稳定码与外键。"""

    s2 = db.scalar(select(Showtime).where(Showtime.film_title == "雾都夜曲"))
    from app.api.router import _log_conflict

    _log_conflict(db, s2.id, 2, ConflictReason.OVERLAP_EXISTING_HOLD, "与既有持座重叠：第1排 1-3")
    db.commit()
    row = db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).first()
    assert row.reason_code == ConflictReason.OVERLAP_EXISTING_HOLD.value
    assert db.get(ReasonCode, row.reason_code) is not None


def test_filter_conflicts_by_code(client):
    for code in SEED_CODES:
        rows = client.get(f"/api/conflicts?reason_code={code}").json()
        assert rows, f"按 {code} 筛选应至少命中种子日志"
        assert all(r["reason_code"] == code for r in rows)

    only_no_seats = client.get("/api/conflicts?reason_code=NO_CONTIGUOUS_SEATS").json()
    only_overlap = client.get("/api/conflicts?reason_code=OVERLAP_EXISTING_HOLD").json()
    assert {r["id"] for r in only_no_seats}.isdisjoint({r["id"] for r in only_overlap})


def test_disable_code_hides_from_active_but_history_still_filterable(client):
    code = "NO_CONTIGUOUS_SEATS"

    active = {r["code"] for r in client.get("/api/reason-codes?active_only=true").json()}
    assert code in active

    res = client.patch(f"/api/reason-codes/{code}", json={"enabled": False})
    assert res.status_code == 200 and res.json()["enabled"] is False

    # 停用后：启用目录里消失
    active = {r["code"] for r in client.get("/api/reason-codes?active_only=true").json()}
    assert code not in active
    # 全量目录仍在，且历史冲突按码筛选依旧可见
    assert code in {r["code"] for r in client.get("/api/reason-codes").json()}
    rows = client.get(f"/api/conflicts?reason_code={code}").json()
    assert rows and all(r["reason_code"] == code for r in rows)

    # 未知码 404
    assert client.patch("/api/reason-codes/NOPE", json={"enabled": True}).status_code == 404

    # 重新启用后恢复可见
    client.patch(f"/api/reason-codes/{code}", json={"enabled": True})
    active = {r["code"] for r in client.get("/api/reason-codes?active_only=true").json()}
    assert code in active


def test_update_retry_recommendation(client):
    res = client.patch("/api/reason-codes/OBSTRUCTED_VIEW", json={"retry_recommended": True})
    assert res.status_code == 200 and res.json()["retry_recommended"] is True
    client.patch("/api/reason-codes/OBSTRUCTED_VIEW", json={"retry_recommended": False})


def test_successful_hold_path_unaffected(client, db):
    # s2：一号厅空场次，3 人应成功落在第 1 排 1-3
    s2 = db.scalar(select(Showtime).where(Showtime.film_title == "雾都夜曲"))
    before_conflicts = len(client.get("/api/conflicts").json())

    res = client.post("/api/holds", json={"showtime_id": s2.id, "party_size": 3})
    assert res.status_code == 200
    hold = res.json()
    assert hold["order_code"].startswith("SB-")
    assert hold["showtime_id"] == s2.id
    assert hold["party_size"] == 3
    assert hold["row"] >= 1 and hold["start_col"] <= hold["end_col"]
    assert hold["status"] == "held"

    # 成功主路径不产生冲突日志，且持座可在订单接口查到
    assert len(client.get("/api/conflicts").json()) == before_conflicts
    orders = client.get("/api/holds").json()
    assert any(o["id"] == hold["id"] and o["order_code"] == hold["order_code"] for o in orders)
