from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_REVISION = 2**53 - 1
Identifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
]
Revision = Annotated[int, Field(strict=True, ge=0, le=MAX_REVISION)]
Mode = Literal["AUTO", "MANUAL_ON", "MANUAL_OFF"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Action(StrictModel):
    request_id: Identifier
    expected_revision: Revision
    action: Literal["timed_on", "off", "manual_on", "manual_off", "auto"]


class Event(StrictModel):
    event_id: Identifier
    source_id: Identifier
    occurred_at: Annotated[str, Field(min_length=20, max_length=40)]

    @field_validator("occurred_at")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            raise ValueError("UTC timestamp required")
        return value

    @property
    def timestamp(self) -> float:
        return datetime.fromisoformat(self.occurred_at).timestamp()


class SettingsUpdate(StrictModel):
    request_id: Identifier
    expected_revision: Revision
    hold_seconds: Annotated[int, Field(strict=True, ge=60, le=7200, multiple_of=60)]
    manual_seconds: Annotated[int, Field(strict=True, ge=60, le=7200, multiple_of=60)]


class Settings(StrictModel):
    revision: Revision = 0
    hold_seconds: Annotated[int, Field(strict=True, ge=60, le=7200, multiple_of=60)] = (
        300
    )
    manual_seconds: Annotated[
        int, Field(strict=True, ge=60, le=7200, multiple_of=60)
    ] = 3600


class Status(StrictModel):
    capability: Literal["independent_light_v1"] = "independent_light_v1"
    revision: Revision
    mode: Mode
    desired_on: bool
    gpio_on: bool | None
    health: Literal["OK", "FAULT", "UNAVAILABLE"]
    reason: str
    remaining_seconds: int
    manual_remaining_seconds: int
    observed_at: str


class EventResult(StrictModel):
    accepted: bool
    duplicate: bool
    status: Status


class DurableState(StrictModel):
    revision: Revision = 0
    mode: Mode = "AUTO"
    manual_until: float = 0.0
    boundary: float = 0.0
    saved_at: float = 0.0
    fault: bool = False
    settings: Settings = Field(default_factory=Settings)
