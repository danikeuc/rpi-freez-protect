from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from freeze_protect.api.app import create_app


def _development_mode(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


app = create_app(
    Path(os.environ.get("FREEZE_PROTECT_DB_PATH", "./data/freeze-protect.db")),
    os.environ.get("FREEZE_PROTECT_ADMIN_TOKEN"),
    _development_mode(os.environ.get("FREEZE_PROTECT_DEVELOPMENT_MODE")),
)


def run() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
