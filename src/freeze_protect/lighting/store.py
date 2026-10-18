from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .models import MAX_REVISION, DurableState


class LightStore:
    """One separately owned SQLite database, short synchronous durable commits."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise OSError("lighting database requires explicit provisioning")
        self.connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw",
            uri=True,
            check_same_thread=False,
            timeout=0.25,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS revision_fence (
                id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
                settings_revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS identities (
                kind TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                result TEXT NOT NULL, expires REAL NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, source TEXT NOT NULL,
                mode TEXT NOT NULL, desired_on INTEGER NOT NULL, reason TEXT NOT NULL);
        """)

    @classmethod
    def provision(cls, path: Path) -> None:
        """One-shot creation only. Existing databases are never replaced."""
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        store = cls(path)
        try:
            store.save(DurableState(), 0.0)
        finally:
            store.close()

    def load_revision(self) -> int:
        row = self.connection.execute(
            "SELECT revision FROM revision_fence WHERE id=1"
        ).fetchone()
        if row is None or type(row[0]) is not int or not 0 <= row[0] <= MAX_REVISION:
            raise ValueError("trustworthy revision fence unavailable")
        return int(row[0])

    def load_settings_revision(self) -> int:
        row = self.connection.execute(
            "SELECT settings_revision FROM revision_fence WHERE id=1"
        ).fetchone()
        if row is None or type(row[0]) is not int or not 0 <= row[0] <= MAX_REVISION:
            raise ValueError("trustworthy settings revision fence unavailable")
        return int(row[0])

    def load(self) -> DurableState:
        row = self.connection.execute("SELECT data FROM state WHERE id=1").fetchone()
        return DurableState.model_validate_json(row[0]) if row else DurableState()

    def lookup(self, kind: str, identity: str) -> tuple[str, dict[str, Any]] | None:
        row = self.connection.execute(
            "SELECT fingerprint,result FROM identities WHERE kind=? AND id=?",
            (kind, identity),
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save(
        self,
        state: DurableState,
        now: float,
        record: tuple[str, str, str, dict[str, Any]] | None = None,
        history: tuple[str, str, str, bool, str] | None = None,
    ) -> None:
        with self.connection:
            checkpoint = self.connection.execute(
                "SELECT revision,settings_revision FROM revision_fence WHERE id=1"
            ).fetchone()
            if checkpoint and (
                type(checkpoint[0]) is not int
                or checkpoint[0] > state.revision
                or type(checkpoint[1]) is not int
                or checkpoint[1] > state.settings.revision
            ):
                raise ValueError("revision fence rollback")
            self.connection.execute(
                "INSERT OR REPLACE INTO revision_fence VALUES (1,?,?)",
                (state.revision, state.settings.revision),
            )
            self.connection.execute("DELETE FROM identities WHERE expires < ?", (now,))
            if record:
                kind, identity, fingerprint, result = record
                count = self.connection.execute(
                    "SELECT COUNT(*) FROM identities"
                ).fetchone()[0]
                exists = self.lookup(kind, identity)
                if count >= 4096 and exists is None:
                    raise OverflowError("identity capacity")
                self.connection.execute(
                    "INSERT OR REPLACE INTO identities VALUES (?,?,?,?,?)",
                    (
                        kind,
                        identity,
                        fingerprint,
                        json.dumps(result),
                        now + (120 if kind == "event" else 86400),
                    ),
                )
            self.connection.execute(
                "INSERT OR REPLACE INTO state VALUES (1,?)", (state.model_dump_json(),)
            )
            if history:
                self.connection.execute(
                    "INSERT INTO history(at,source,mode,desired_on,reason) VALUES (?,?,?,?,?)",
                    history,
                )
                self.connection.execute(
                    "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 1000)"
                )

    def history(self, limit: int, offset: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id,at,source,mode,desired_on,reason FROM history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [
            dict(
                zip(
                    ("id", "at", "source", "mode", "desired_on", "reason"),
                    (*row[:4], bool(row[4]), row[5]),
                    strict=True,
                )
            )
            for row in rows
        ]

    def close(self) -> None:
        self.connection.close()
