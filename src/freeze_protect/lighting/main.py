from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from .api import create_app
from .executor import ExecutorClient
from .store import LightStore


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Independent lighting service")
    parser.add_argument("--provision-new-db", action="store_true")
    args = parser.parse_args(argv)
    database_path = Path(os.environ.get("LIGHT_DB_PATH", "./data/independent-light.db"))
    if args.provision_new_db:
        LightStore.provision(database_path)
        return
    socket_path = os.environ.get("LIGHT_EXECUTOR_SOCKET")
    executor = ExecutorClient(Path(socket_path)) if socket_path else None
    app = create_app(
        database_path=database_path,
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
