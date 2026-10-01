"""Research journal: Markdown entries with live links and captures.

Entries are ``journal/<date>-<slug>.md`` with a small YAML front matter. Links
to research objects use the ``calflab://`` scheme, e.g.
``[the trot run](calflab://run/20261001-101500-sim-ab12)`` or
``calflab://design/calf-v003``; clients resolve them to the live object.

Captures (viewport images/video) are stored in ``assets/captures/`` next to a
JSON sidecar recording full provenance (state revision, design, run, camera).
"""

from __future__ import annotations

import base64
import contextlib
import re
import uuid
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from calflab.project.store import Project, now_iso, slugify, write_json, write_text_atomic

LINK_RE = re.compile(r"calflab://(run|design|candidate|capture)/([A-Za-z0-9_\-]+)")


class JournalEntry(BaseModel):
    id: str  # file stem
    title: str
    created: str = Field(default_factory=now_iso)
    modified: str = Field(default_factory=now_iso)
    tags: list[str] = Field(default_factory=list)
    body: str = ""

    def links(self) -> list[dict[str, str]]:
        return [{"kind": k, "id": i} for k, i in LINK_RE.findall(self.body)]


def _parse(path: Path) -> JournalEntry:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            meta = yaml.safe_load(text[4:end]) or {}
            body = text[end + 5 :]
    return JournalEntry(
        id=path.stem,
        title=str(meta.get("title", path.stem)),
        created=str(meta.get("created", "")),
        modified=str(meta.get("modified", "")),
        tags=list(meta.get("tags", [])),
        body=body.lstrip("\n"),
    )


class Journal:
    def __init__(self, project: Project):
        self.project = project

    @property
    def dir(self) -> Path:
        return self.project.dir("journal")

    def list(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.dir.glob("*.md"), reverse=True):
            e = _parse(p)
            out.append({"id": e.id, "title": e.title, "created": e.created, "modified": e.modified,
                        "tags": e.tags, "excerpt": e.body[:160], "links": e.links()})
        return out

    def get(self, entry_id: str) -> JournalEntry:
        p = self.dir / f"{slugify(entry_id)}.md"
        if not p.is_file():
            raise KeyError(f"No journal entry {entry_id!r}")
        return _parse(p)

    def save(self, title: str, body: str, entry_id: str | None = None, tags: list[str] | None = None) -> JournalEntry:
        created = now_iso()
        if entry_id:
            with contextlib.suppress(KeyError):
                created = self.get(entry_id).created or created
            eid = slugify(entry_id)
        else:
            eid = f"{created[:10]}-{slugify(title, 'entry')}"
            n = 2
            while (self.dir / f"{eid}.md").exists():
                eid = f"{created[:10]}-{slugify(title, 'entry')}-{n}"
                n += 1
        entry = JournalEntry(id=eid, title=title, created=created, modified=now_iso(), tags=tags or [], body=body)
        front = yaml.safe_dump(
            {"title": entry.title, "created": entry.created, "modified": entry.modified, "tags": entry.tags},
            sort_keys=False,
        )
        write_text_atomic(self.dir / f"{eid}.md", f"---\n{front}---\n\n{body}")
        return entry

    def delete(self, entry_id: str) -> None:
        p = self.dir / f"{slugify(entry_id)}.md"
        if p.is_file():
            p.unlink()

    # ------------------------------------------------------------------ captures
    def add_capture(self, data_url: str, provenance: dict[str, Any], kind: str = "image") -> dict[str, Any]:
        """Store a viewport capture sent as a data URL; returns its record."""
        header, _, b64 = data_url.partition(",")
        ext = "png"
        if "image/jpeg" in header:
            ext = "jpg"
        elif "video/webm" in header:
            ext = "webm"
        cid = f"{now_iso()[:19].replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:4]}"
        d = self.project.dir("assets") / "captures"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{cid}.{ext}"
        path.write_bytes(base64.b64decode(b64))
        record = {
            "id": cid,
            "kind": kind,
            "path": self.project.rel(path),
            "created": now_iso(),
            "provenance": provenance,
        }
        write_json(d / f"{cid}.json", record)
        return record

    def captures(self) -> list[dict[str, Any]]:
        import json

        d = self.project.dir("assets") / "captures"
        out = []
        for p in sorted(d.glob("*.json"), reverse=True):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out
