"""The compare page's manifest for what one body can do (R16, ADR-112).

``compare.html?set=r16`` shows a grid of views of the same body (g020-008-r01); every cell has a menu of all the
distinct elites the diversity search and the probes stored, grouped by what the body does. Each cell starts on a
different behaviour (``default_cells``); the top picker sets every cell at once. The page renders this manifest only
(CLAUDE.md, golden rule 1): the behaviour's name, its numbers and its badge are decided here.

Read from the study's JSON (``docs/studies/diversity_r16.json``): ``shown`` (one record per stored elite, written by
``diversity_r16.py store``): key, group, source, descriptor, the judged worst seed's outcome, holds / within /
same_cell, binding, margin and the seed-0 run. Badges: green = holds on every judging seed and stays in its cell;
orange = within every limit and safe, but it changes cell over the judging length (or the seeds disagree on the
class); red = over a limit or unsafe at the judging length (the binding limit named).
Units: mm/s, deg/s, trunk height as a share of standing, effort = mean |torque| / rated torque.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from calflab.paths import repo_root


class DiversityCompareSet(BaseModel):
    key: str
    title: str
    study: str = Field(description="Repo-relative JSON with shown[] (diversity_r16.py store).")
    body: str
    views: int = 6
    #: groups in this order; a group not listed goes last
    groups: list[str] = Field(default_factory=lambda: ["down", "kneel", "crouch", "stand", "walk", "trot", "pace",
                                                       "bound", "irregular", "probe"])


DIVERSITY_SETS: dict[str, DiversityCompareSet] = {
    "r16": DiversityCompareSet(key="r16", title="R16 / what g020-008-r01 can do (diversity search)",
                               study="docs/studies/diversity_r16.json", body="g020-008-r01"),
}

GROUP_TITLES = {"down": "Down (trunk at half height or lower)", "kneel": "Kneeling (resting on more than hooves)",
                "crouch": "Crouched, still", "stand": "Standing, still", "walk": "Walking (four beats)",
                "trot": "Trotting (diagonal pairs)", "pace": "Pacing (lateral pairs)", "bound": "Bounding",
                "irregular": "Irregular stepping", "probe": "Probes (open questions)"}
VERBS = {"down": "goes down", "kneel": "kneels", "crouch": "crouches", "stand": "stands", "walk": "walks",
         "trot": "trots", "pace": "paces", "bound": "bounds", "irregular": "steps irregularly"}


def _n(v: Any, fmt: str) -> str:
    return "-" if v is None else format(float(v), fmt)


def name(d: dict[str, Any], o: dict[str, Any]) -> str:
    """What the behaviour is, in words, from its descriptor (class, speed mm/s, turn deg/s) and outcome."""
    cls = str(d.get("class") or "-")
    sp, tu = float(d.get("speed") or 0.0), float(d.get("turn") or 0.0)
    verb = VERBS.get(cls, cls)
    moving = cls in ("walk", "trot", "pace", "bound", "irregular")
    if moving:
        if abs(sp) < 15.0 and abs(tu) >= 2.5:
            where = f"on the spot, turning {'left' if tu > 0 else 'right'}"
        elif abs(sp) < 15.0:
            where = "in place"
        else:
            where = ("backward" if sp < 0 else "forward") + (
                f", turning {'left' if tu > 0 else 'right'}" if abs(tu) >= 2.5 else "")
        return f"{verb} {where}"
    extra = []
    if abs(sp) >= 15.0:
        extra.append("drifting " + ("back" if sp < 0 else "forward"))
    if abs(tu) >= 2.5:
        extra.append(f"turning {'left' if tu > 0 else 'right'}")
    if cls in ("down", "kneel") and (o.get("height_mean") or 0) >= 0.85:
        extra.append("and gets up again")
    return verb + (" (" + ", ".join(extra) + ")" if extra else "")


def numbers(d: dict[str, Any], o: dict[str, Any], margin: Any) -> str:
    ff = o.get("gait") or "-"
    lag = o.get("diagonal_lag")
    return (f"{_n(d.get('speed'), '.0f')} mm/s, turn {_n(d.get('turn'), '+.1f')} deg/s, trunk {_n(o.get('height_mean'), '.2f')}"
            f" (lowest {_n(o.get('height_low'), '.2f')}), footfall {ff}" + (f" lag {lag:.2f}" if lag is not None else "")
            + f", effort {_n(o.get('effort_mean'), '.2f')}/{_n(o.get('effort_max'), '.2f')} ({o.get('worst') or '-'})"
            + f", margin {_n(margin, '.2f')}")


def badge(rec: dict[str, Any]) -> tuple[str, str, str | None]:
    b = rec.get("binding") or {}
    limit = f"{b.get('joint')} {b.get('limit')} ({_n(b.get('use'), '.2f')})" if b else None
    if rec.get("holds") and rec.get("same_cell", True) and float(rec.get("agree", 1.0)) >= 1.0:
        return "within", f"holds on every seed ({rec.get('judged_s', '-')} s)", None
    if rec.get("holds"):
        why = "changes cell over the judging length" if not rec.get("same_cell", True) else "seeds disagree on the class"
        return "near", f"holds, but {why}", None
    if not rec.get("within", True):
        return "over", "over a limit at the judging length", limit
    failed = [k for k, v in ((rec.get("outcome") or {}).get("gates") or {}).items() if not v]
    return "over", "unsafe: " + (", ".join(failed) or "a gate"), None


def diversity_manifest(lab: Any, set_key: str) -> dict[str, Any]:
    spec = DIVERSITY_SETS[set_key]
    f = repo_root() / spec.study
    data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    shown: list[dict[str, Any]] = data.get("shown") or []
    mass = data.get("mass_g")
    views = [{"key": f"v{i + 1}", "label": spec.body, "line": f"view {i + 1}" + (f" · {mass:.0f} g" if mass else ""),
              "stage_c_run": None} for i in range(spec.views)]
    by_group: dict[str, list[dict[str, Any]]] = {}
    for rec in shown:
        by_group.setdefault(rec.get("group") or "probe", []).append(rec)
    order = [g for g in spec.groups if g in by_group] + sorted(g for g in by_group if g not in spec.groups)
    groups: list[dict[str, Any]] = []
    for g in order:
        items: list[dict[str, Any]] = []
        for rec in sorted(by_group[g], key=lambda r: (float((r.get("descriptor") or {}).get("speed") or 0.0),
                                                      float((r.get("descriptor") or {}).get("turn") or 0.0))):
            d, o = rec.get("descriptor") or {}, rec.get("outcome") or {}
            title = rec.get("title") or name(d, o)
            bd, text, limit = badge(rec)
            playing = f"{title}: {numbers(d, o, rec.get('margin'))} · {rec.get('source', '')}"
            cell = {"play": rec["key"], "playing": playing, "match": None, "empty": not rec.get("run"),
                    "message": None if rec.get("run") else "not stored yet",
                    "seeds": [{"seed": 0, "run": rec.get("run"), "badge": bd, "margin": rec.get("margin"),
                               "limit": limit, "text": text,
                               "href": f"/?replay={rec['run']}" if rec.get("run") else None}]}
            items.append({"key": rec["key"], "label": f"{title} ({_n(d.get('speed'), '.0f')} mm/s)", "kind": "elite",
                          "cells": [{**cell, "body": v["key"]} for v in views]})
        groups.append({"key": g, "title": GROUP_TITLES.get(g, g), "items": items})
    # each view starts on a different group's showpiece: one that holds (green), the fastest of those
    def showpiece(items: list[dict[str, Any]]) -> str:
        def k(it: dict[str, Any]) -> tuple[bool, float]:
            s = it["cells"][0]["seeds"][0]
            d = by_key[it["key"]].get("descriptor") or {}
            return s["badge"] == "within", abs(float(d.get("speed") or 0.0))
        return max(items, key=k)["key"]

    by_key = {r["key"]: r for r in shown}
    firsts = [showpiece(grp["items"]) for grp in groups if grp["items"]]
    rest = [it["key"] for grp in groups for it in grp["items"] if it["key"] not in firsts]
    default_cells = (firsts + rest)[: spec.views]
    n = len(shown)
    return {"set": spec.key, "title": spec.title, "seeds": [0], "near": 0.0, "bodies": views, "groups": groups,
            "stored": sum(1 for r in shown if r.get("run")), "missing": sum(1 for r in shown if not r.get("run")),
            "per_cell": True, "default_cells": default_cells,
            "hint": (f"{n} distinct behaviours of one body; each cell's menu picks its own; replays are seed 0, the "
                     "text is the worst of three judging seeds" if n else
                     "nothing stored yet: python docs/studies/diversity_r16.py <project> store")}
