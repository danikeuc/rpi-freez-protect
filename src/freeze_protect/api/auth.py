from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, status


def build_admin_guard(admin_token: str | None) -> Callable[[str | None], None]:
    def require_admin(
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> None:
        _require_token(x_admin_token, admin_token, "administrator authentication")

    return require_admin


def build_display_guard(display_token: str | None) -> Callable[[str | None], None]:
    def require_display(
        x_display_token: Annotated[str | None, Header()] = None,
    ) -> None:
        _require_token(x_display_token, display_token, "display authentication")

    return require_display


def require_confirmation(received: str | None, expected: str) -> None:
    if received != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-Confirm-Command must equal {expected}",
        )


def _require_token(received: str | None, expected: str | None, label: str) -> None:
    if not expected or not received or not secrets.compare_digest(received, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{label} is required",
        )
