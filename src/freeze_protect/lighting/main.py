from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .api import create_app
from .executor import ExecutorClient


def run() -> None:
    socket_path = os.environ.get("LIGHT_EXECUTOR_SOCKET")
    executor = ExecutorClient(Path(socket_path)) if socket_path else None
    app = create_app(
        database_path=Path(
            os.environ.get("LIGHT_DB_PATH", "./data/independent-light.db")
        ),
        display_token=os.environ.get("LIGHT_DISPLAY_TOKEN"),
        settings_token=os.environ.get("LIGHT_SETTINGS_TOKEN"),
        camera_token=os.environ.get("LIGHT_CAMERA_TOKEN"),
        executor=executor,
        allowed_sources={
            s for s in os.environ.get("LIGHT_ALLOWED_SOURCES", "").split(",") if s
        },
    )
    uvicorn.run(app, host="127.0.0.1", port=8002)


if __name__ == "__main__":
    run()
