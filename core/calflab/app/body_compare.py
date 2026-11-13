"""The compare page's manifest for the same behaviours on several bodies (R18, ADR-119).

``compare.html?set=r18`` shows one cell per body (the baseline g020-008-r01, its closest McMaster swap and the
reformulated bodies); the picker sets every cell to the same R16 behaviour. The page renders this manifest only
(CLAUDE.md, golden rule 1): names, numbers and badges are decided here.

Read from the study's JSON (``docs/studies/mcmaster_r18.json``):

* ``replay[body]``: one record per behaviour and seed (holds, within, within excluding sustained belt tension,
  margins, binding, belt statistics), written by ``mcmaster_r18.py replay``;
* ``store[body][behaviour key]``: the seed-0 ``sim`` run of that play (``mcmaster_r18.py store``); the baseline's
  are R16's own runs (``diversity_r16.json`` shown);
* ``labels[body]``: the cell's title line.

* ``measured[body][behaviour key]``: what that stored seed-0 run actually plays, measured the way R16 labels a
  behaviour (``measure_run``; ``mcmaster_r18.py measure``). The behaviour names are R16's, from g020-008-r01 over
  three seeds; on another body (or on seed 0 alone) the same controller can play another gait, so each cell says
  what its own run plays and flags a run that differs from its label (ADR-125).

Badges: green = holds and within every limit at the margin on every seed, sustained belt tension included (the
McMaster belts' allowable working tension is Gates' published figure, ADR-120; their breaking strength is assumed);
red = over a limit or unsafe on a seed (the limit named). Units: N, mm/s, deg/s.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from calflab.paths import repo_root


class BodyCompareSet(BaseModel):
    key: str
    title: str
    study: str
    #: the behaviours' names, groups and numbers
    behaviours: str
    note: str = ""
    #: only these bodies of the study, in this order; empty = every replayed body (in the study's order)
    bodies: list[str] = []


BODY_SETS: dict[str, BodyCompareSet] = {
    "r18": BodyCompareSet(key="r18", title="R18 / g020-008-r01 on McMaster-Carr belt parts",
                          study="docs/studies/mcmaster_r18.json", behaviours="docs/studies/diversity_r16.json",
                          note="within every limit incl. sustained belt tension (Gates 17611-T allowable); breaking "
                               "strength assumed"),
    "carpus": BodyCompareSet(key="carpus", title="g020-008-r01-mc: belted carpus vs direct carpus (ADR-123)",
                             study="docs/studies/mcmaster_r18.json", behaviours="docs/studies/diversity_r16.json",
                             bodies=["g020-008-r01-mc", "g020-008-r01-mc-direct"],
                             note="within every limit incl. sustained belt tension (Gates 17611-T allowable); "
                                  "breaking strength assumed"),
}


def _read(rel: str) -> dict[str, Any]:
    f = repo_root() / rel
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}


def judged(records: list[dict[str, Any]]) -> dict[str, Any]:
    """One behaviour on one body over its seeds: badge, text, worst margin (excluding sustained belt tension), the
    binding limit of the worst seed, and the largest belt peak / mean (N) over the seeds."""
    if not records:
        return {"badge": "empty", "text": "not replayed", "margin": None, "limit": None}
    ok = all(r["holds"] and r["within"] for r in records)
    ms = [r["margin"] for r in records if r.get("margin") is not None]
    worst = min(records, key=lambda r: r["margin"] if r.get("margin") is not None else 9.0)
    b = worst.get("binding") or {}
    limit = f"{b.get('joint')} {b.get('limit')}" if b.get("joint") else None
    peaks = [v["belt_peak_n"] for r in records for v in (r.get("belts") or {}).values()]
    means = [v["belt_mean_n"] for r in records for v in (r.get("belts") or {}).values()]
    belt = f"belt peak {max(peaks):.0f} N, mean {max(means):.0f} N" if peaks else ""
    if ok:
        text = f"holds and within limits on all {len(records)} seeds"
    elif all(r["holds"] for r in records):
        bad = sorted({v for r in records for v in r["violations"]})
        text = "holds, but over " + (", ".join(bad) or "a limit")
    else:
        text = "does not hold on " + ", ".join(str(r["seed"]) for r in records if not r["holds"])
    return {"badge": "within" if ok else "over", "text": f"{text}; {belt}".strip("; "),
            "margin": min(ms) if ms else None, "limit": None if ok else limit}


#: how a class reads in a sentence ("seed 0 plays a trot")
CLASS_WORDS: dict[str, str] = {
    "walk": "a walk", "trot": "a trot", "pace": "a pace", "bound": "a bound", "irregular": "irregular steps",
    "stand": "a stand", "crouch": "a crouch", "kneel": "a kneel", "down": "lying down",
}


def measure_run(rollout: Any, spec: Any, task: dict[str, Any] | None = None) -> dict[str, Any]:
    """What one recorded play does, measured as R16 labels a behaviour (``calflab.fitness.outcomes.measure_free``
    with the behaviour's own task settings): its class, forward speed (mm/s, + ahead) and turn rate (deg/s, + left)."""
    from calflab.fitness.outcomes import FreeTask, measure_free

    o = measure_free(rollout, spec, FreeTask.model_validate(task or {}))
    return {"class": o.get("d_class"), "speed": o.get("d_speed_mm_s"), "turn": o.get("d_turn_deg_s")}


def plays_as(measured: dict[str, Any] | None, label: dict[str, Any] | None) -> dict[str, Any] | None:
    """A cell's own run against the behaviour's label (R16's descriptor): the sentence the page shows and whether the
    class agrees. None when the run has not been measured."""
    if not measured or not measured.get("class"):
        return None
    cls = str(measured["class"])
    speed, turn = float(measured.get("speed") or 0.0), float(measured.get("turn") or 0.0)
    still = cls in ("stand", "crouch", "kneel", "down") and abs(speed) < 25.0  # a pose: its drift is not a speed
    what = CLASS_WORDS.get(cls, cls) + ("" if still else f", {speed:.0f} mm/s")
    what += f", turning {turn:+.0f} deg/s" if abs(turn) >= 1.0 else ""
    lc = (label or {}).get("class")
    agrees = lc is None or cls == lc
    text = f"seed 0 plays {what}" + ("" if agrees else f": not {CLASS_WORDS.get(str(lc), lc)} as labelled")
    return {"text": text, "agrees": agrees, "class": cls, "speed": speed, "turn": turn}


def body_order(data: dict[str, Any]) -> list[str]:
    """The cells' order: the study's ``order`` first (bodies that have been replayed), then any other replayed body in
    the order it was added (``carpus_r18.py`` puts the direct-carpus body beside the belted swap, ADR-123)."""
    replay = data.get("replay") or {}
    first = [n for n in (data.get("order") or []) if n in replay]
    return first + [n for n in replay if n not in first]


def body_manifest(lab: Any, set_key: str) -> dict[str, Any]:
    from calflab.app.diversity_compare import GROUP_TITLES, _n, name

    spec = BODY_SETS[set_key]
    data = _read(spec.study)
    shown = _read(spec.behaviours).get("shown") or []
    replay: dict[str, list[dict[str, Any]]] = data.get("replay") or {}
    store: dict[str, dict[str, str]] = data.get("store") or {}
    labels: dict[str, str] = data.get("labels") or {}
    measured: dict[str, dict[str, dict[str, Any]]] = data.get("measured") or {}
    names = body_order(data)
    if spec.bodies:
        names = [n for n in spec.bodies if n in names]
    bodies = [{"key": n, "label": n, "line": labels.get(n, ""), "stage_c_run": None} for n in names]
    by_group: dict[str, list[dict[str, Any]]] = {}
    for rec in shown:
        by_group.setdefault(rec.get("group") or "probe", []).append(rec)
    groups = []
    stored = missing = differ = 0
    for g in ["stand", "walk", "trot", "pace", "bound", "irregular", "probe"] + sorted(
            x for x in by_group if x not in ("stand", "walk", "trot", "pace", "bound", "irregular", "probe")):
        if g not in by_group:
            continue
        items = []
        for rec in sorted(by_group[g], key=lambda r: (float((r.get("descriptor") or {}).get("speed") or 0.0),
                                                      float((r.get("descriptor") or {}).get("turn") or 0.0))):
            d, o = rec.get("descriptor") or {}, rec.get("outcome") or {}
            title = rec.get("title") or name(d, o)
            cells = []
            for n in names:
                run = (store.get(n) or {}).get(rec["key"])
                j = judged([r for r in replay.get(n, []) if r["key"] == rec["key"]])
                ms = (measured.get(n) or {}).get(rec["key"])
                pa = plays_as(ms if ms and ms.get("run") == run else None, d)  # only for the run the cell plays
                differ += bool(pa and not pa["agrees"])
                stored += bool(run)
                missing += not run
                cells.append({"body": n, "play": rec["key"], "playing": f"{title} on {n}: {j['text']}",
                              "match": None, "empty": not run, "message": None if run else "not stored yet",
                              "seeds": [{"seed": 0, "run": run, "badge": j["badge"], "margin": j["margin"],
                                         "limit": j["limit"], "text": j["text"], "plays": pa,
                                         "href": f"/?replay={run}" if run else None}]})
            items.append({"key": rec["key"], "label": f"{title} ({_n(d.get('speed'), '.0f')} mm/s)", "kind": "elite",
                          "cells": cells})
        groups.append({"key": g, "title": GROUP_TITLES.get(g, g), "items": items})
    return {"set": spec.key, "title": spec.title, "seeds": [0], "near": 0.0, "bodies": bodies, "groups": groups,
            "stored": stored, "missing": missing, "per_cell": False, "differ": differ,
            "hint": (f"the same {len(shown)} R16 behaviours on {len(names)} bodies; replays are seed 0, the badge is "
                     f"over seeds 0-2; {spec.note}; behaviour names are R16's (g020-008-r01, three seeds): under "
                     f"each cell, what its own seed-0 run plays ({differ} cells differ from their label)" if names else
                     "nothing replayed yet: python docs/studies/mcmaster_r18.py <project> replay")}
