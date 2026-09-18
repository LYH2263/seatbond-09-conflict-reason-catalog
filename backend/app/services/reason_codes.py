"""Conflict reason code catalog.

Every failed hold attempt writes a ConflictLog carrying a stable ``reason_code``
alongside the human-readable ``reason`` text. This module owns the canonical
code enum and the preset catalog rows (Chinese label, retry hint, enabled
flag). Codes whose business modules are not fully live yet (odd-pair split,
obstructed-view lock, cross-aisle) are still registered here so future writes
land on a real code; anything else falls back to UNCLASSIFIED.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ConflictReason


class ReasonCode(str, Enum):
    NO_CONTIGUOUS_BLOCK = "NO_CONTIGUOUS_BLOCK"  # 连续空座不足
    OVERLAP_EXISTING_HOLD = "OVERLAP_EXISTING_HOLD"  # 与既有持座重叠
    ODD_PAIR_SPLIT = "ODD_PAIR_SPLIT"  # 半对情侣（业务未全开，码已就绪）
    OBSTRUCTED_VIEW_LOCKED = "OBSTRUCTED_VIEW_LOCKED"  # 遮挡禁锁（业务未全开）
    CROSS_AISLE_ILLEGAL = "CROSS_AISLE_ILLEGAL"  # 跨过道非法（业务未全开）
    UNCLASSIFIED = "UNCLASSIFIED"  # 兜底：未归类


# Preset catalog rows. ``enabled`` is operator-togglable at runtime and is
# therefore only applied on first insert, never overwritten by re-syncs.
PRESET_REASONS: list[dict] = [
    {
        "code": ReasonCode.NO_CONTIGUOUS_BLOCK.value,
        "description_zh": "连续空座不足",
        "suggest_retry": True,
    },
    {
        "code": ReasonCode.OVERLAP_EXISTING_HOLD.value,
        "description_zh": "与既有持座重叠",
        "suggest_retry": True,
    },
    {
        "code": ReasonCode.ODD_PAIR_SPLIT.value,
        "description_zh": "半对情侣",
        "suggest_retry": True,
    },
    {
        "code": ReasonCode.OBSTRUCTED_VIEW_LOCKED.value,
        "description_zh": "遮挡禁锁",
        "suggest_retry": False,
    },
    {
        "code": ReasonCode.CROSS_AISLE_ILLEGAL.value,
        "description_zh": "跨过道非法",
        "suggest_retry": False,
    },
    {
        "code": ReasonCode.UNCLASSIFIED.value,
        "description_zh": "未归类",
        "suggest_retry": False,
    },
]


def ensure_reason_catalog(db: Session) -> None:
    """Insert missing preset reason codes; never clobber operator toggles."""
    existing = set(db.scalars(select(ConflictReason.code)).all())
    for preset in PRESET_REASONS:
        if preset["code"] not in existing:
            db.add(ConflictReason(enabled=True, builtin=True, **preset))
    db.commit()
