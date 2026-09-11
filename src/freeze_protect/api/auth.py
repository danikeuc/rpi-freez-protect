from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, status


def build_admin_guard(admin_token: str | None) -> Callable[[str | None], None]:
    """Build a dependency that rejects missing or mismatched local admin tokens."""

    def require_admin(
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> None:
        if not admin_token or not x_admin_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="administrator authentication is required",
            )
        if not secrets.compare_digest(x_admin_token, admin_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="administrator authentication is required",
            )

    return require_admin


def require_confirmation(received: str | None, expected: str) -> None:
    if received != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-Confirm-Command must equal {expected}",
        )
