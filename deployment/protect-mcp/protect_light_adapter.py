"""Read-only Protect MCP source; Pi remains the sole lighting policy authority."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import signal
import ssl
import stat
import threading
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PAGE_LIMIT = 100
MAX_AGE = 60
POLL_SECONDS = 5
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def timestamp(value: object) -> float:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("UTC required")
    return parsed.timestamp()


def iso(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


class Admission:
    """No backlog on start/reconnect; consume IDs before any delivery attempt."""

    def __init__(self, camera: str) -> None:
        if not IDENTIFIER.fullmatch(camera):
            raise ValueError("camera")
        self.camera = camera
        self.boundary = 0.0
        self.last: tuple[float, float] | None = None
        self.seen: dict[str, float] = {}

    def disconnect(self) -> None:
        self.last = None

    def select(self, payload: object, wall: float, mono: float) -> list[dict[str, str]]:
        try:
            if not math.isfinite(wall) or not math.isfinite(mono):
                raise ValueError("clock")
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise ValueError("MCP unsuccessful")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("invalid MCP data envelope")  # noqa: TRY004
            items = data.get("detections")
            count = data.get("count")
            if (
                not isinstance(items, list)
                or type(count) is not int
                or count != len(items)
                or len(items) >= PAGE_LIMIT
            ):
                raise ValueError("partial or saturated page")
            old = self.last
            self.last = (wall, mono)
            # Large scheduling/transport gaps form a new admission boundary.
            if (
                old is None
                or mono <= old[1]
                or mono - old[1] > 20
                or abs((wall - old[0]) - (mono - old[1])) > 2
            ):
                self.boundary = max(self.boundary, wall)
                return []
            self.seen = {
                key: expiry for key, expiry in self.seen.items() if expiry > mono
            }
            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                identity = item.get("id")
                kinds = item.get("smart_detect_types")
                if (
                    item.get("camera") != self.camera
                    or item.get("type") != "smartDetectZone"
                    or not isinstance(kinds, list)
                    or "person" not in kinds
                    or not isinstance(identity, str)
                    or not IDENTIFIER.fullmatch(identity)
                ):
                    continue
                try:
                    occurred = timestamp(item.get("start"))
                except (ValueError, OverflowError):
                    continue
                if (
                    identity in self.seen
                    or not self.boundary < occurred <= wall
                    or wall - occurred > MAX_AGE
                ):
                    continue
                if len(self.seen) >= 2000:
                    raise ValueError("identity capacity")
                self.seen[identity] = mono + 120
                result.append(
                    {
                        "event_id": identity,
                        "source_id": self.camera,
                        "occurred_at": iso(occurred),
                    }
                )
            return sorted(result, key=lambda item: item["occurred_at"])
        except Exception:
            self.disconnect()
            raise


def private_read(path: Path) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("private file unavailable") from None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > 8192
        ):
            raise ValueError("private file required")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            return stream.read(8193)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Config:
    camera_id: str
    launcher: str
    mode: str = "observe"
    endpoint: str = ""
    token_file: str = ""
    ca_file: str = ""

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Config:
        config = cls(**raw)
        if (
            not isinstance(config.camera_id, str)
            or not IDENTIFIER.fullmatch(config.camera_id)
            or not isinstance(config.launcher, str)
            or not Path(config.launcher).is_absolute()
            or config.mode not in {"observe", "forward"}
        ):
            raise ValueError("configuration")
        if config.mode == "observe":
            if config.endpoint or config.token_file or config.ca_file:
                raise ValueError("observe has no destination or credentials")
        else:
            url = urlsplit(config.endpoint)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path != "/api/v1/lights/events/unifi"
                or not Path(config.token_file).is_absolute()
            ):
                raise ValueError("verified HTTPS event endpoint required")
        return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect rejected")


@contextmanager
def delivery_deadline(seconds: float = 8):
    # Dedicated Linux main process: no abandoned HTTP threads after a timeout.
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("delivery requires main thread")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("timer already owned")

    def expired(signum, frame):
        raise TimeoutError("delivery deadline")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Sink:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.token = private_read(Path(config.token_file)).strip()
        if not re.fullmatch(r"[!-~]{32,512}", self.token):
            raise ValueError("invalid token")
        context = ssl.create_default_context(cafile=config.ca_file or None)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
        )

    def send(self, event: dict[str, str]) -> str:
        if not 0 <= time.time() - timestamp(event["occurred_at"]) <= MAX_AGE:
            return "expired"
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(event).encode(),
            method="POST",
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        with delivery_deadline(), self.opener.open(request, timeout=5) as response:
            body = response.read(16385)
            if response.status != 200 or len(body) > 16384:
                raise ValueError("invalid receipt")
            receipt = json.loads(body)
        if (
            not isinstance(receipt, dict)
            or type(receipt.get("accepted")) is not bool
            or type(receipt.get("duplicate")) is not bool
            or not isinstance(receipt.get("status"), dict)
        ):
            raise ValueError("unconfirmed receipt")
        return (
            "duplicate"
            if receipt["duplicate"]
            else "accepted"
            if receipt["accepted"]
            else "inhibited"
        )


def unpack(reply: Any) -> object:
    if reply.is_error:
        raise ValueError("MCP tool error")
    structured = reply.structured_content
    if isinstance(structured, dict):
        if len(json.dumps(structured)) > 131072:
            raise ValueError("MCP envelope too large")
        return structured
    texts = [part.text for part in reply.content if part.type == "text"]
    if len(texts) != 1 or len(texts[0]) > 131072:
        raise ValueError("MCP envelope")
    return json.loads(texts[0])


def report(state: str, **counts: int | str) -> None:
    # Never log payloads, credentials, exception text or camera imagery.
    print(json.dumps({"time": iso(time.time()), "state": state, **counts}), flush=True)


async def _poll(session: Any, gate: Admission, sink: Sink | None) -> None:
    wall = time.time()
    async with asyncio.timeout(15):
        reply = await session.call_tool(
            "protect_execute",
            {
                "tool": "protect_list_smart_detections",
                "arguments": {
                    "camera_id": gate.camera,
                    "detection_type": "person",
                    "start": iso(wall - MAX_AGE),
                    "end": iso(wall),
                    "limit": PAGE_LIMIT,
                    "min_confidence": 0,
                    "compact": True,
                },
            },
        )
    selected = gate.select(unpack(reply), time.time(), time.monotonic())
    results: dict[str, int] = {}
    for event in selected:
        if sink is None:
            outcome = "observed"
        else:
            # One attempt only. Timeout/ambiguous response disarms the whole batch.
            outcome = sink.send(event)
        results[outcome] = results.get(outcome, 0) + 1
    report(
        "observing" if sink is None else "forwarding", fresh=len(selected), **results
    )


async def poll(session: Any, gate: Admission, sink: Sink | None) -> None:
    try:
        await _poll(session, gate, sink)
    except BaseException:
        gate.disconnect()
        raise


async def run(config: Config, once: bool = False) -> None:
    # Imported only by the VM entry point; Pi never needs the MCP SDK.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    gate = Admission(config.camera_id)
    sink = Sink(config) if config.mode == "forward" else None
    delay = 5
    while True:
        try:
            with open(os.devnull, "w") as errors:  # noqa: ASYNC230 - local null device
                async with (
                    stdio_client(
                        StdioServerParameters(command=config.launcher), errlog=errors
                    ) as (read, write),
                    ClientSession(read, write) as session,
                ):
                    async with asyncio.timeout(20):
                        await session.initialize()
                    gate.disconnect()
                    delay = 5
                    while True:
                        await poll(session, gate, sink)
                        if once:
                            return
                        await asyncio.sleep(POLL_SECONDS)
        except Exception:  # noqa: BLE001 - redact SDK exception groups at process boundary
            gate.disconnect()
            report("unavailable", retry_seconds=delay)
            if once:
                raise RuntimeError("observation unavailable") from None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        config = Config.parse(json.loads(private_read(args.config)))
        asyncio.run(run(config, args.once))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001 - never expose configuration secrets
        report("stopped_configuration_or_runtime_error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
