"""Event-sourced command log (ADR-009).

``commands.jsonl`` is append-only. Each line is one operation:

    {"op": "do",    "record": {...}}     a command was executed
    {"op": "amend", "id": ..., "after": {...}, "params": {...}}   coalesced follow-up
    {"op": "undo",  "id": ...}
    {"op": "redo",  "id": ...}

Replaying the file reconstructs the undo stack. Commands undone and then
superseded by a new command stay in the file (marked discarded on replay), so
the log is also a faithful record of how a design was reached.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from calflab.project.store import now_iso

LOG_FILE = "commands.jsonl"


class CommandRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    time: str = Field(default_factory=now_iso)
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    title: str = ""
    client: str = "unknown"
    before: dict[str, Any] = Field(default_factory=dict)  # top-level state key -> old value
    after: dict[str, Any] = Field(default_factory=dict)  # top-level state key -> new value
    coalesce: str | None = None
    discarded: bool = False


class CommandLog:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.records: list[CommandRecord] = []  # live undo stack (no discarded records)
        self.cursor = 0  # number of applied records
        self.total = 0  # all "do" operations ever logged
        self._lock = threading.Lock()
        if path is not None and path.is_file():
            self._replay()
            for r in self.records:  # never coalesce into a previous session's command
                r.coalesce = None

    # ------------------------------------------------------------------ persistence
    def _replay(self) -> None:
        assert self.path is not None
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    op = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn last line after a crash
                kind = op.get("op")
                if kind == "do":
                    del self.records[self.cursor :]
                    self.records.append(CommandRecord.model_validate(op["record"]))
                    self.cursor = len(self.records)
                    self.total += 1
                elif kind == "amend" and self.records and self.cursor:
                    rec = self.records[self.cursor - 1]
                    if rec.id == op.get("id"):
                        rec.after = op["after"]
                        rec.params = op.get("params", rec.params)
                elif kind == "undo" and self.cursor > 0:
                    self.cursor -= 1
                elif kind == "redo" and self.cursor < len(self.records):
                    self.cursor += 1

    def _write(self, op: dict[str, Any]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(op, default=str) + "\n")

    # ------------------------------------------------------------------ operations
    def push(self, record: CommandRecord) -> CommandRecord:
        """Log an executed command. Coalesces with the previous record when both
        carry the same ``coalesce`` key (e.g. a slider drag = one undo step)."""
        with self._lock:
            if (
                record.coalesce
                and self.cursor > 0
                and self.cursor == len(self.records)
                and self.records[-1].coalesce == record.coalesce
                and self.records[-1].client == record.client
            ):
                last = self.records[-1]
                for key, value in record.before.items():
                    last.before.setdefault(key, value)
                last.after.update(record.after)
                last.params = record.params
                last.time = record.time
                self._write({"op": "amend", "id": last.id, "after": last.after, "params": last.params})
                return last
            del self.records[self.cursor :]
            self.records.append(record)
            self.cursor = len(self.records)
            self.total += 1
            self._write({"op": "do", "record": record.model_dump(mode="json")})
            return record

    def break_coalescing(self) -> None:
        """End the current coalescing run (e.g. on mouse-up)."""
        with self._lock:
            if self.records and self.cursor == len(self.records):
                self.records[-1].coalesce = None

    def undo(self) -> CommandRecord | None:
        with self._lock:
            if self.cursor == 0:
                return None
            self.cursor -= 1
            rec = self.records[self.cursor]
            rec.coalesce = None
            self._write({"op": "undo", "id": rec.id})
            return rec

    def redo(self) -> CommandRecord | None:
        with self._lock:
            if self.cursor >= len(self.records):
                return None
            rec = self.records[self.cursor]
            self.cursor += 1
            self._write({"op": "redo", "id": rec.id})
            return rec

    # ------------------------------------------------------------------ queries
    @property
    def can_undo(self) -> bool:
        return self.cursor > 0

    @property
    def can_redo(self) -> bool:
        return self.cursor < len(self.records)

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        out = []
        start = max(0, len(self.records) - limit)
        for i, r in enumerate(self.records[start:], start=start):
            out.append(
                {
                    "id": r.id,
                    "time": r.time,
                    "command": r.command,
                    "title": r.title or r.command,
                    "client": r.client,
                    "applied": i < self.cursor,
                }
            )
        return out
