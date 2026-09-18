"""API tests for the conflict reason-code catalog and failure observability.

Runs against an in-memory SQLite database via dependency override, so no
Postgres is needed. TestClient is deliberately NOT used as a context manager:
the app lifespan (which targets the real database) stays out of the way.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.reason_codes import PRESET_REASONS, ReasonCode, ensure_reason_catalog
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    seed_if_empty(db)  # seeds catalog + halls/showtimes/holds + 2 conflict logs
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _first_showtime_id(client) -> int:
    shows = client.get("/api/showtimes").json()
    assert shows
    return shows[0]["id"]


def test_failed_hold_writes_log_with_reason_code(client):
    sid = _first_showtime_id(client)
    before = {c["id"] for c in client.get("/api/conflicts").json()}

    resp = client.post("/api/holds", json={"showtime_id": sid, "party_size": 12})
    assert resp.status_code == 409

    new_logs = [c for c in client.get("/api/conflicts").json() if c["id"] not in before]
    assert len(new_logs) == 1
    log = new_logs[0]
    assert log["reason_code"] == ReasonCode.NO_CONTIGUOUS_BLOCK.value
    assert log["reason"]  # 可读说明仍在
    assert log["party_size"] == 12


def test_seeded_conflict_logs_have_distinct_reason_codes(client):
    logs = client.get("/api/conflicts").json()
    seeded = [c for c in logs if c["reason_code"] in (
        ReasonCode.NO_CONTIGUOUS_BLOCK.value,
        ReasonCode.OVERLAP_EXISTING_HOLD.value,
    )]
    assert len(seeded) == 2
    codes = {c["reason_code"] for c in seeded}
    assert len(codes) == 2  # 空座不足与重叠必须落到不同的码


def test_filter_conflicts_by_reason_code(client):
    code_a = ReasonCode.NO_CONTIGUOUS_BLOCK.value
    code_b = ReasonCode.OVERLAP_EXISTING_HOLD.value

    filtered_a = client.get(f"/api/conflicts?reason_code={code_a}").json()
    assert filtered_a and all(c["reason_code"] == code_a for c in filtered_a)

    filtered_b = client.get(f"/api/conflicts?reason_code={code_b}").json()
    assert filtered_b and all(c["reason_code"] == code_b for c in filtered_b)

    assert {c["id"] for c in filtered_a}.isdisjoint({c["id"] for c in filtered_b})


def test_reason_catalog_presets_ready(client):
    catalog = {r["code"]: r for r in client.get("/api/conflict-reasons").json()}
    for preset in PRESET_REASONS:
        row = catalog[preset["code"]]
        assert row["description_zh"] == preset["description_zh"]
        assert row["suggest_retry"] == preset["suggest_retry"]
        assert row["enabled"] is True
    # 业务未全开的码也已就绪
    for future in (
        ReasonCode.ODD_PAIR_SPLIT,
        ReasonCode.OBSTRUCTED_VIEW_LOCKED,
        ReasonCode.CROSS_AISLE_ILLEGAL,
        ReasonCode.UNCLASSIFIED,
    ):
        assert future.value in catalog


def test_reason_toggle_keeps_logs_filterable(client):
    code = ReasonCode.NO_CONTIGUOUS_BLOCK.value

    resp = client.patch(f"/api/conflict-reasons/{code}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    catalog = {r["code"]: r for r in client.get("/api/conflict-reasons").json()}
    assert catalog[code]["enabled"] is False

    # 停用不隐藏历史日志：按码筛选仍可见
    filtered = client.get(f"/api/conflicts?reason_code={code}").json()
    assert filtered and all(c["reason_code"] == code for c in filtered)

    resp = client.patch(f"/api/conflict-reasons/{code}", json={"enabled": True})
    assert resp.json()["enabled"] is True


def test_toggle_unknown_reason_code_404(client):
    resp = client.patch("/api/conflict-reasons/NOPE", json={"enabled": False})
    assert resp.status_code == 404


def test_successful_hold_fields_intact(client):
    sid = _first_showtime_id(client)
    resp = client.post("/api/holds", json={"showtime_id": sid, "party_size": 2})
    assert resp.status_code == 200
    hold = resp.json()
    for field in ("order_code", "row", "start_col", "end_col", "party_size", "status"):
        assert field in hold
    assert hold["party_size"] == 2
    assert hold["end_col"] - hold["start_col"] + 1 == 2
    assert hold["status"] == "held"

    holds = client.get("/api/holds").json()
    assert any(h["order_code"] == hold["order_code"] for h in holds)
