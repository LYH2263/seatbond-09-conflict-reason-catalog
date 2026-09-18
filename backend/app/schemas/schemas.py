from datetime import datetime
from pydantic import BaseModel, Field


class HallOut(BaseModel):
    id: int
    name: str
    rows: int
    cols: int
    aisle_cols: list[int]
    model_config = {"from_attributes": True}


class ShowtimeOut(BaseModel):
    id: int
    hall_id: int
    film_title: str
    start_at: datetime
    hall_name: str | None = None
    model_config = {"from_attributes": True}


class HoldOut(BaseModel):
    id: int
    showtime_id: int
    order_code: str
    row: int
    start_col: int
    end_col: int
    party_size: int
    status: str
    model_config = {"from_attributes": True}


class HoldRequest(BaseModel):
    showtime_id: int
    party_size: int = Field(ge=1, le=12)
    preferred_row: int | None = None


class ConflictOut(BaseModel):
    id: int
    showtime_id: int
    party_size: int
    reason_code: str
    reason: str
    reason_description: str | None = None
    retry_recommended: bool | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ReasonCodeOut(BaseModel):
    code: str
    description_zh: str
    retry_recommended: bool
    enabled: bool
    model_config = {"from_attributes": True}


class ReasonCodeUpdate(BaseModel):
    enabled: bool | None = None
    description_zh: str | None = None
    retry_recommended: bool | None = None


class SeatMapCell(BaseModel):
    row: int
    col: int
    is_aisle: bool
    occupied: bool
    heat: float


class SeatMapOut(BaseModel):
    showtime_id: int
    hall_name: str
    rows: int
    cols: int
    cells: list[SeatMapCell]
