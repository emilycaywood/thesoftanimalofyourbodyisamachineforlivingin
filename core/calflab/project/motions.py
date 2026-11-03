"""Motion library: reference-motion clips (from Blender or footage) stored in ``motions/``.

A clip is joint angles plus a root trajectory over time. Clips feed the Behave
timeline, the stochastic behaviors and the imitation term. A clip may carry
the researcher's affect tags (ADR-078): what *they* read in the movement. The
lab stores and filters by them; it never infers them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from calflab.project.store import Project, now_iso, read_json, slugify, write_json


class AffectTags(BaseModel):
    """The researcher's reading of a clip. Never set by the lab."""

    valence: float | None = Field(None, ge=-1.0, le=1.0)  # -1 unpleasant .. +1 pleasant
    arousal: float | None = Field(None, ge=0.0, le=1.0)  # 0 calm .. 1 agitated
    words: list[str] = Field(default_factory=list)  # free words: wary, curious, ...
    note: str = ""
    tagged: str = ""  # when (ISO time)

    def matches(self, words: list[str] | None = None, valence: tuple[float, float] | None = None,
                arousal: tuple[float, float] | None = None) -> bool:
        """All given conditions hold: every word is among the tags (case-insensitive), values inside the ranges."""
        mine = {w.strip().lower() for w in self.words}
        if words and not all(w.strip().lower() in mine for w in words):
            return False
        if valence is not None and (self.valence is None or not valence[0] <= self.valence <= valence[1]):
            return False
        return not (arousal is not None and (self.arousal is None or not arousal[0] <= self.arousal <= arousal[1]))


class MotionClip(BaseModel):
    """Angles in degrees relative to the standing pose; root in mm, quats (w, x, y, z)."""

    id: str = ""
    name: str
    fps: float = 30.0
    joints: dict[str, list[float]] = Field(default_factory=dict)
    root_pos: list[tuple[float, float, float]] = Field(default_factory=list)
    root_quat: list[tuple[float, float, float, float]] = Field(default_factory=list)
    source: str = "blender"
    created: str = Field(default_factory=now_iso)
    meta: dict[str, Any] = Field(default_factory=dict)
    affect: AffectTags | None = None

    @model_validator(mode="after")
    def _consistent(self) -> MotionClip:
        lengths = {len(v) for v in self.joints.values()}
        if self.root_pos:
            lengths.add(len(self.root_pos))
        if self.root_quat:
            lengths.add(len(self.root_quat))
        if len(lengths) > 1:
            raise ValueError(f"All channels of a clip need the same frame count, got {sorted(lengths)}")
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        return self

    @property
    def frames(self) -> int:
        if self.joints:
            return len(next(iter(self.joints.values())))
        return len(self.root_pos)

    @property
    def duration_s(self) -> float:
        return self.frames / self.fps if self.frames else 0.0


class MotionLibrary:
    def __init__(self, project: Project):
        self.project = project

    def save(self, clip: MotionClip) -> MotionClip:
        d = self.project.dir("motions")
        base = slugify(clip.id or clip.name, "clip")
        cid, n = base, 2
        while not clip.id and (d / f"{cid}.json").exists():
            cid = f"{base}-{n}"
            n += 1
        clip.id = cid
        write_json(d / f"{cid}.json", clip.model_dump(mode="json"))
        return clip

    def get(self, clip_id: str) -> MotionClip:
        p = self.project.dir("motions") / f"{slugify(clip_id)}.json"
        if not p.is_file():
            raise KeyError(f"No motion clip {clip_id!r}")
        return MotionClip.model_validate(read_json(p))

    def list(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.project.dir("motions").glob("*.json")):
            try:
                c = MotionClip.model_validate(read_json(p))
            except Exception:
                continue
            out.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "fps": c.fps,
                    "frames": c.frames,
                    "duration_s": round(c.duration_s, 3),
                    "joints": sorted(c.joints),
                    "source": c.source,
                    "created": c.created,
                    "affect": c.affect.model_dump(mode="json") if c.affect else None,
                }
            )
        return out
