"""Strict bounded JSON decoding and scoped weather settings serialization."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import NoReturn

from fastapi import HTTPException, Request

from freeze_protect.application.weather_actions import (
    MAX_WIRE_REVISION,
    WeatherActionInput,
)
from freeze_protect.domain.weather import WeatherSettings


async def read_weather_json(request: Request, keys: set[str]) -> dict[str, object]:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4096:
            raise HTTPException(413, "weather request exceeds 4 KiB")
        body.extend(chunk)

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def reject_constant(_: str) -> NoReturn:
        raise ValueError("nonfinite JSON constant")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=reject_constant,
        )
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("invalid fields")
        return payload
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise HTTPException(422, "invalid weather request") from error


def action_input(payload: dict[str, object]) -> WeatherActionInput:
    try:
        return WeatherActionInput(**payload)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(422, "invalid weather action") from error


def settings_input(payload: dict[str, object]) -> WeatherSettings:
    values = dict(payload)
    revision = values.pop("expected_revision")
    if type(revision) is not int or not 0 <= revision <= MAX_WIRE_REVISION:
        raise HTTPException(422, "invalid weather revision")
    try:
        return WeatherSettings(revision=revision, **values)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(422, "invalid weather settings") from error


def settings_payload(settings: WeatherSettings) -> dict[str, object]:
    if settings.revision > MAX_WIRE_REVISION:
        raise HTTPException(503, "weather revision outside wire range")
    return asdict(settings)
