"""The compare page's manifest for behaviours searched by outcome (R15, ADR-110, ADR-111).

``compare.html?set=r15`` shows one cell per body; each cell has its own behaviour menu (stand, suckle, trot, lie) and
the top picker sets every cell at once. The page renders this manifest only (CLAUDE.md, golden rule 1): which run
each cell replays, the text under its title and its badge are decided here.

Read from the study's JSON (``docs/studies/outcomes_r15.json``): ``pilot.<body>.<behaviour>.best`` (the version
judged on three seeds; the worst seed is described) and ``stored.<body>.<behaviour>`` (its seed-0 replay, a ``sim``
run). Badges: green = holds on every judging seed; orange = within every limit but a gate fails; red = over a limit.
Units: forces N, speeds mm/s, lengths mm, effort = mean |torque| / rated torque.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from calflab.paths import repo_root


class OutcomeCompareSet(BaseModel):
    key: str
    title: str
    study: str = Field(description="Repo-relative JSON with pilot.<body>.<behaviour> and stored.<body>.<behaviour>.")
    bodies: list[str]
    labels: dict[str, str] = Field(default_factory=dict)
    behaviours: list[str] = Field(default_factory=lambda: ["stand", "suckle", "trot", "lie"])


OUTCOME_SETS: dict[str, OutcomeCompareSet] = {
    "r15": OutcomeCompareSet(
        key="r15", title="R15 / behaviours by outcome, bodies judged at real weight",
        study="docs/studies/outcomes_r15.json",
        bodies=["working", "g007-002", "g009-000", "g012-009", "g020-008-r01"],
        labels={"working": "working body"}),
}

BEHAVIOUR_LABELS = {"stand": "Stand", "suckle": "Suckle (10 s press)", "trot": "Trot (a minute)", "lie": "Lie down"}


def _n(v: Any, fmt: str) -> str:
    return "-" if v is None else format(float(v), fmt)


def describe(behaviour: str, o: dict[str, Any]) -> str:
    """One line of the numbers that matter for a behaviour's outcome record (``calflab.fitness.outcomes``)."""
    if behaviour == "stand":
        return (f"effort mean {_n(o.get('effort_mean'), '.2f')} / worst {_n(o.get('effort_max'), '.2f')} "
                f"({o.get('worst', '-')}), height {_n(o.get('height'), '.2f')}, drift {_n(o.get('drift_mm'), '.1f')} mm")
    if behaviour == "suckle":
        return (f"presses {_n(o.get('push_p20_n'), '.2f')} N (20th pct), mean {_n(o.get('push_mean_n'), '.2f')} N, "
                f"hooves creep {_n(o.get('slip_max_mm'), '.0f')} mm, effort worst {_n(o.get('effort_max'), '.2f')}")
    if behaviour == "trot":
        ff = (o.get("footfall") or {}).get("label") or "-"
        return (f"{_n(o.get('speed_min_mm_s'), '.0f')} mm/s (slowest 5 s), footfall {ff}, "
                f"drift {_n(o.get('drift_mm_s'), '.1f')} mm/s")
    if behaviour == "lie":
        return (f"down to {_n(o.get('lying_min'), '.2f')} of standing for {_n(o.get('lying_held_s'), '.1f')} s, "
                f"descent {_n(o.get('descent_peak_mm_s'), '.0f')} mm/s, impact {_n(o.get('impact_peak_bw'), '.2f')} bw, "
                f"rises {'yes' if o.get('risen') else 'no'}")
    return ""


def worst_seed(best: dict[str, Any]) -> dict[str, Any] | None:
    seeds = best.get("seeds") or []
    return min(seeds, key=lambda s: float(s.get("rank", 0.0))) if seeds else None


def judgement(best: dict[str, Any]) -> tuple[str, str, str | None]:
    """(badge, text, limit) for a judged best version: holds, a failed gate, or over a limit."""
    w = worst_seed(best) or {}
    o = w.get("outcome") or {}
    if best.get("holds"):
        return "within", "holds on every seed", None
    b = w.get("binding") or {}
    limit = f"{b.get('joint')} {b.get('limit')} ({_n(b.get('use'), '.2f')})" if b else None
    if not best.get("within", w.get("within", True)):
        return "over", "over a limit", limit
    failed = [k for k, v in (o.get("gates") or {}).items() if not v]
    return "near", "fails " + (", ".join(failed) or "a gate"), None


def outcome_manifest(lab: Any, set_key: str) -> dict[str, Any]:
    spec = OUTCOME_SETS[set_key]
    f = repo_root() / spec.study
    data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    pilot, stored, mass = data.get("pilot") or {}, data.get("stored") or {}, data.get("mass_g") or {}
    bodies = []
    for b in spec.bodies:
        held = [beh for beh in spec.behaviours if ((pilot.get(b) or {}).get(beh) or {}).get("best", {}).get("holds")]
        searched = sum(1 for beh in spec.behaviours if beh in (pilot.get(b) or {}))
        parts = [f"{mass[b]:.0f} g" if b in mass else None,
                 f"holds {len(held)}/{searched}" + (f" ({', '.join(held)})" if held else "") if searched else
                 "not searched yet"]
        bodies.append({"key": b, "label": spec.labels.get(b, b), "line": " · ".join(p for p in parts if p),
                       "stage_c_run": None})
    items = []
    stored_n = missing = 0
    for beh in spec.behaviours:
        cells: list[dict[str, Any]] = []
        for b in spec.bodies:
            r = (pilot.get(b) or {}).get(beh)
            run = (stored.get(b) or {}).get(beh)
            if r is None or run is None:
                missing += 1
                cells.append({"body": b, "play": None, "playing": None, "match": None, "empty": True,
                              "message": "not searched yet" if r is None else "not stored yet", "seeds": []})
                continue
            stored_n += 1
            best = r.get("best") or {}
            w = worst_seed(best) or {}
            badge, text, limit = judgement(best)
            cells.append({"body": b, "play": beh, "playing": describe(beh, w.get("outcome") or {}) + " (worst seed)",
                          "match": None, "empty": False, "message": None,
                          "seeds": [{"seed": 0, "run": run, "badge": badge, "margin": w.get("margin"),
                                     "limit": limit, "text": text, "href": f"/?replay={run}"}]})
        items.append({"key": beh, "label": BEHAVIOUR_LABELS.get(beh, beh), "kind": "outcome", "cells": cells})
    return {"set": spec.key, "title": spec.title, "seeds": [0], "near": 0.0, "bodies": bodies,
            "groups": [{"key": "outcome", "title": "Behaviours by outcome", "items": items}],
            "stored": stored_n, "missing": missing, "per_cell": True,
            "hint": ("each cell's menu picks its own behaviour; replays are seed 0, the text is the worst of three "
                     "seeds; the suckling block is not drawn"
                     + (f" · {missing} not searched or stored yet: docs/studies/outcomes_r15.py" if missing else ""))}
