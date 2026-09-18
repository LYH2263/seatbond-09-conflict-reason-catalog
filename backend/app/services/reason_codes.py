"""冲突原因码目录。

稳定的 ``reason_code`` 随每条锁座失败日志落库，目录维护代码、中文说明、
是否建议重试与是否启用。即使部分业务模块（半对情侣 / 遮挡 / 跨过道）尚未
全开，枚举与目录也已就绪，待对应规则接入后即可直接落到码上；任何未匹配
规则的失败统一落到 ``UNCLASSIFIED``。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ReasonCode


class ConflictReason(str, Enum):
    """锁座失败原因码（稳定标识，勿随意调整取值）。"""

    NO_CONTIGUOUS_SEATS = "NO_CONTIGUOUS_SEATS"
    OVERLAP_EXISTING_HOLD = "OVERLAP_EXISTING_HOLD"
    COUPLE_PAIR_SPLIT = "COUPLE_PAIR_SPLIT"
    OBSTRUCTED_VIEW = "OBSTRUCTED_VIEW"
    AISLE_CROSSING = "AISLE_CROSSING"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass(frozen=True)
class ReasonSpec:
    code: ConflictReason
    description_zh: str
    retry_recommended: bool
    enabled: bool = True


# 预置目录：code -> 规范定义
REASON_CODE_CATALOG: dict[ConflictReason, ReasonSpec] = {
    ConflictReason.NO_CONTIGUOUS_SEATS: ReasonSpec(
        ConflictReason.NO_CONTIGUOUS_SEATS,
        "连续空座不足：厅内无满足人数的连续空座",
        retry_recommended=True,
    ),
    ConflictReason.OVERLAP_EXISTING_HOLD: ReasonSpec(
        ConflictReason.OVERLAP_EXISTING_HOLD,
        "与既有持座重叠：候选座位已被占用",
        retry_recommended=True,
    ),
    ConflictReason.COUPLE_PAIR_SPLIT: ReasonSpec(
        ConflictReason.COUPLE_PAIR_SPLIT,
        "半对情侣：双人座被拆散，无法成对安排",
        retry_recommended=True,
    ),
    ConflictReason.OBSTRUCTED_VIEW: ReasonSpec(
        ConflictReason.OBSTRUCTED_VIEW,
        "遮挡禁锁：座位视线被遮挡，禁止锁定",
        retry_recommended=False,
    ),
    ConflictReason.AISLE_CROSSING: ReasonSpec(
        ConflictReason.AISLE_CROSSING,
        "跨过道非法：连座不允许跨过过道列",
        retry_recommended=False,
    ),
    ConflictReason.UNCLASSIFIED: ReasonSpec(
        ConflictReason.UNCLASSIFIED,
        "未归类：暂未匹配到明确原因码的失败",
        retry_recommended=False,
    ),
}


def ensure_reason_codes(db: Session) -> None:
    """将预置目录同步入库：补齐缺失码、更新说明/重试建议，启停状态以库内为准。

    已存在记录的 ``enabled`` 不会被覆盖，运营在面板上的停用会被保留。
    """

    existing = {rc.code: rc for rc in db.scalars(select(ReasonCode)).all()}
    changed = False
    for reason, spec in REASON_CODE_CATALOG.items():
        rc = existing.get(reason.value)
        if rc is None:
            db.add(
                ReasonCode(
                    code=reason.value,
                    description_zh=spec.description_zh,
                    retry_recommended=spec.retry_recommended,
                    enabled=spec.enabled,
                )
            )
            changed = True
            continue
        if rc.description_zh != spec.description_zh or rc.retry_recommended != spec.retry_recommended:
            rc.description_zh = spec.description_zh
            rc.retry_recommended = spec.retry_recommended
            changed = True
    if changed:
        db.flush()


def resolve_code(db: Session, reason: ConflictReason) -> str:
    """返回可落库的原因码；目录中缺失时先补齐，兜底返回未归类码。"""

    code = reason.value if isinstance(reason, ConflictReason) else str(reason)
    row = db.scalar(select(ReasonCode).where(ReasonCode.code == code))
    if row is None:
        spec = REASON_CODE_CATALOG.get(reason if isinstance(reason, ConflictReason) else ConflictReason.UNCLASSIFIED)
        if spec is None:
            spec = REASON_CODE_CATALOG[ConflictReason.UNCLASSIFIED]
            code = spec.code.value
        db.add(
            ReasonCode(
                code=code,
                description_zh=spec.description_zh,
                retry_recommended=spec.retry_recommended,
                enabled=spec.enabled,
            )
        )
        db.flush()
    return code
