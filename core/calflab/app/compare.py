"""Group replays for the compare page: bodies x behaviours -> stored play runs (ADR-106).

``compare.html?set=r12`` shows one cell per body and switches every cell to the same behaviour at once. Everything the
page shows is decided here and sent as a *manifest*; the page only renders it (CLAUDE.md, golden rule 1):

* the bodies, each with a short line of numbers (behaviours held, trot mm/s, lie_rise, cost) from the study's judged
  data;
* the picker's three groups: screen plays every body can play, the shared behaviours (R6c's and R7's 11, which Stage
  B judged every body on), and each body's own Stage C safe cells, matched across bodies;
* per body x behaviour x seed: the stored run that replays it, a badge (within / near / over the margin) and the limit
  that stopped the play, if one did.

**Matching own behaviours.** Each Stage C run was seeded with R7's safe generators (``start_vectors``): candidate
``g000-<i>`` started from generator ``i mod n``, and every later candidate descends from its first parent. Two own
behaviours match when they come from the same R7 generator (the nearest archive cell among them if a body has several);
if none does, the same archive cell (quantity of motion x tempo regularity), or the nearest within
``max_cell_distance`` cells; otherwise the body shows "no matching behaviour".

**Plays** are runs of kind ``sim`` stored as ``docs/studies/store_r11cb.py`` stores them (rollout + scene, judged as the
R11c suite judges, ADR-104), found again by their ``cache_key`` = (set, body, Stage C run, play, seed). ``generate``
plays only the missing ones.

Units: margins are headroom over limits already lowered by the suite's margin (0 = exactly at margin 0.2), speeds mm/s.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

PLAY_VERSION = 1  # part of every cache key; bump when a stored play would no longer replay the same thing


class CompareSet(BaseModel):
    """Which runs a group of replays is read from."""

    key: str
    title: str
    stage_b_run: str = Field(description="The hardware run whose bodies, preset (suite, seeds, margin) and shared "
                                         "behaviours are used.")
    r7_run: str = Field(description="The behaviour run whose safe generators seeded every Stage C run.")
    stage_c_prefix: str = Field("R12 Stage C ", description="Stage C runs are titled <prefix><body>.")
    bodies: list[str] = Field(description="Body keys: 'working' or a Stage B candidate suffix, in cell order.")
    labels: dict[str, str] = Field(default_factory=dict, description="Display names (default: the key).")
    study: str | None = Field(None, description="Repo-relative JSON of the study's judgement (numbers per body).")
    screen: list[str] = Field(default_factory=lambda: ["lie_rise", "walk", "turn", "trot 0.4/2", "slowest trot"],
                              description="Screen plays by key; 'slowest trot' = the trot grid's longest cycle and "
                                          "shortest stride.")
    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2])
    near: float = Field(0.1, description="A play within this of the margin is 'near' (orange).")
    max_cell_distance: int = Field(2, description="Farthest archive cell (Chebyshev, in cells) an own behaviour may "
                                                  "be matched to when no behaviour shares its R7 generator.")
    evolved: dict[str, str] = Field(
        default_factory=dict,
        description="Screen plays evolved per body (ADR-107): label -> repo-relative JSON with "
                    "bodies.<body>.best.params (lie_rise primitive params) and search.settle_s. Each body plays its "
                    "own version, judged over the whole motion (calflab.evolve.lie_rise.play_seed).")
    title_prefix: str = "R12 compare"


SETS: dict[str, CompareSet] = {
    "r12": CompareSet(
        key="r12", title="R12 / Stage C bodies (ADR-105)",
        stage_b_run="20261107-043030-evolve-c02e", r7_run="20261105-232649-evolve-4237",
        bodies=["working", "g007-002", "g009-000", "g012-009", "g011-003", "g020-008-r01"],
        labels={"working": "working body"}, study="docs/studies/stagec_r12.json",
        evolved={"lie_rise (evolved)": "docs/studies/lierise_r13.json"}),
}


class CompareError(ValueError):
    """A set or one of its runs cannot be read."""


# ====================================================================== pure helpers (tested without a project)
def digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def play_key(set_key: str, body: str, body_run: str, play: str, seed: int) -> str:
    """The ``cache_key`` of a stored play."""
    return "compare-" + digest({"v": PLAY_VERSION, "set": set_key, "body": body, "run": body_run, "play": play,
                                "seed": int(seed)})


def slowest_trot(cycles_s: list[float], strides: list[float]) -> str:
    """The trot grid's slowest corner: longest cycle, shortest stride (the screen's key form)."""
    return f"trot {max(cycles_s):g}/{min(strides):g}"


def trot_label(key: str) -> str:
    c, _, s = key.removeprefix("trot ").partition("/")
    return f"trot {float(c):g} s / stride {float(s):.1f}"


def origin_index(cid: str, cands: dict[str, dict[str, Any]], n_starts: int) -> int | None:
    """Which start vector (R7 generator, by index) a diversity candidate descends from: its first parent, back to
    generation 0, where task ``i`` started from vector ``i mod n_starts`` (``diversity.MapElitesBehaviour``)."""
    if n_starts <= 0:
        return None
    seen: set[str] = set()
    c = cands.get(cid)
    while c is not None and c.get("parents") and c["id"] not in seen:
        seen.add(c["id"])
        c = cands.get(c["parents"][0])
    if c is None:
        return None
    tail = str(c["id"]).rsplit("-", 2)
    if len(tail) < 3 or not tail[-2].startswith("g") or int(tail[-2][1:]) != 0:
        return None  # an orphan after generation 0: no start vector to name
    return int(tail[-1]) % n_starts


def cell_distance(a: list[int] | tuple[int, ...], b: list[int] | tuple[int, ...]) -> int:
    return max(abs(int(x) - int(y)) for x, y in zip(a, b, strict=True))


def match_cell(origin: int | None, cell: list[int], cells: list[dict[str, Any]], max_d: int
               ) -> tuple[dict[str, Any] | None, str]:
    """A body's own behaviour for an item (``origin``, ``cell``). ``cells``: the body's safe cells with ``origin``,
    ``cell`` and ``candidate``. Returns (the cell or None, how it matched)."""
    def near(cs: list[dict[str, Any]]) -> dict[str, Any]:
        return min(cs, key=lambda c: (cell_distance(c["cell"], cell), c["candidate"]))

    same = [c for c in cells if origin is not None and c.get("origin") == origin]
    if same:
        c = near(same)
        return c, "same generator" if cell_distance(c["cell"], cell) == 0 else "same generator, other cell"
    if not cells:
        return None, "no matching behaviour"
    c = near(cells)
    d = cell_distance(c["cell"], cell)
    if d == 0:
        return c, "same cell"
    if d <= max_d:
        return c, f"nearest cell ({d} away)"
    return None, "no matching behaviour"


def badge(within: bool | None, margin: float | None, near: float) -> str | None:
    """'within' (green), 'near' (orange: within, but less than ``near`` above the margin), 'over' (red)."""
    if within is None:
        return None
    if not within:
        return "over"
    return "near" if margin is None or margin < near else "within"


def stopped_by(report: dict[str, Any], joints: dict[str, dict[str, Any]] | None) -> str | None:
    """The limit that stopped a play: the joint and limit used most beyond 1 (as ``hardware.summarise`` counts it),
    else the judge's first violation, else 'fell'. None for a play within limits."""
    from calflab.evolve.hardware import LIMIT_LABELS, LIMITS

    if report.get("within"):
        return None
    top: tuple[float, str, str] | None = None
    for j, u in (joints or {}).items():
        for lim in LIMITS:
            v = u.get(lim)
            if isinstance(v, int | float) and v > 1.0 and (top is None or v > top[0]):
                top = (float(v), j, lim)
    if top is not None:
        return f"{top[1]} {LIMIT_LABELS.get(top[2], top[2])}"
    viol = report.get("violations") or []
    if viol:
        return str(viol[0]).replace("_", " ")
    return "fell" if report.get("fell") else (str(report.get("closest") or "").replace("_", " ") or None)


def _num(v: float | None, fmt: str, none: str = "-") -> str:
    return none if v is None else format(v, fmt)


def body_line(numbers: dict[str, Any]) -> str:
    """'23 held · trot - · lie_rise -1.44 · cost 1.58' (trot '-' = no trot within limits); with an evolved lie_rise
    (ADR-107) its worst-seed margin over the whole motion follows: 'lie_rise -1.44 (evolved, whole: -0.40)'."""
    held = numbers.get("held")
    trot = numbers.get("trot_mm_s")
    ev = numbers.get("lie_rise_evolved")
    evolved = "" if ev is None else f" (evolved, whole: {ev:+.2f})"
    return (f"{'?' if held is None else held} held · trot {_num(trot or None, '.0f')} mm/s · "
            f"lie_rise {_num(numbers.get('lie_rise'), '+.2f')}{evolved} · cost {_num(numbers.get('cost'), '.2f')}")


def evolved_versions(spec: CompareSet) -> dict[str, dict[str, Any]]:
    """Per evolved label: ``{"settle_s": s, "bodies": {body: {"params", "worst", "held"}}}`` from its JSON (missing
    file or body = not evolved yet)."""
    from calflab.paths import repo_root

    out: dict[str, dict[str, Any]] = {}
    for label, rel in spec.evolved.items():
        f = repo_root() / rel
        data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        bodies = {b: {"params": v["best"]["params"], "worst": v["best"].get("worst"), "held": v["best"].get("held")}
                  for b, v in (data.get("bodies") or {}).items() if (v.get("best") or {}).get("params")}
        first: dict[str, Any] = next(iter((data.get("bodies") or {}).values()), {})
        out[label] = {"settle_s": float((first.get("search") or {}).get("settle_s", 1.0)), "bodies": bodies}
    return out


def evolved_play(label: str, params: dict[str, Any]) -> str:
    """A cell's play name for a body's evolved version (changes when the version does)."""
    return f"evolved:{label}:{digest(params)[:12]}"


def item_key(origin: int | None, cell: list[int]) -> str:
    return f"own:{'x' if origin is None else origin}:{cell[0]}-{cell[1]}"


# ====================================================================== the plan (reads the runs)
_PLAN_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}


def compare_set(key: str) -> CompareSet:
    if key not in SETS:
        from calflab.app.diversity_compare import DIVERSITY_SETS
        from calflab.app.outcome_compare import OUTCOME_SETS

        known = ", ".join(sorted([*SETS, *OUTCOME_SETS, *DIVERSITY_SETS]))
        raise CompareError(f"No compare set {key!r}; known: {known}")
    return SETS[key]


def stage_c_runs(lab: Any, spec: CompareSet) -> dict[str, str]:
    """The latest finished Stage C run per body (titled ``<prefix><body>``)."""
    out: dict[str, str] = {}
    for r in lab.registry.list_runs("evolve", 100000):
        title = str(r.get("title") or "")
        if not title.startswith(spec.stage_c_prefix) or r.get("status") != "done":
            continue
        body = title[len(spec.stage_c_prefix):]
        if body in spec.bodies and (body not in out or r["id"] > out[body]):
            out[body] = r["id"]
    return out


def _study(spec: CompareSet) -> dict[str, Any]:
    from calflab.paths import repo_root

    if not spec.study:
        return {}
    f = repo_root() / spec.study
    if not f.is_file():
        return {}
    return (json.loads(f.read_text(encoding="utf-8")) or {}).get("bodies") or {}


def body_numbers(judged: dict[str, Any] | None) -> dict[str, Any]:
    """Behaviours held a minute on every seed, trot within limits (mm/s), lie_rise worst margin, cost index."""
    if not judged:
        return {"held": None, "trot_mm_s": None, "lie_rise": None, "cost": None}
    s = judged.get("summary") or {}
    held = sum(1 for r in s.get("performances") or [] if r.get("held") == r.get("of"))
    return {"held": held, "trot_mm_s": s.get("trot_speed_mm_s"),
            "lie_rise": ((s.get("screen") or {}).get("lie_rise") or {}).get("worst_margin"),
            "cost": (s.get("costs") or {}).get("cost_index")}


def plan(lab: Any, spec: CompareSet) -> dict[str, Any]:
    """Bodies, groups and items, and per item and body the play (or none) - everything but the stored runs.
    Cached per set and Stage C runs."""
    from calflab.evolve.hardware import HardwareSettings

    runs = stage_c_runs(lab, spec)
    evolved = evolved_versions(spec)
    sig = digest({"spec": spec.model_dump(), "runs": runs, "evolved": evolved})
    hit = _PLAN_CACHE.get(spec.key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    try:
        brun = lab.registry.get_run(spec.stage_b_run)
        r7 = lab.registry.get_run(spec.r7_run)
    except KeyError as exc:
        raise CompareError(str(exc)) from exc
    hw = HardwareSettings.model_validate(brun.fitness["preset"]["evaluation"]["hardware"])
    study = _study(spec)

    # R7's safe generators, in the order Stage C was seeded with them (stagec_r12.r7_safe), named by their shared label
    r7_safe = [c for c in lab.registry.list_candidates(r7.id) if (c.get("metrics") or {}).get("within_limits")]
    shared_by_ref = {p.ref.split(":", 1)[1]: p.label for p in hw.performances if p.ref.startswith(r7.id + ":")}
    gen_names = [shared_by_ref.get(c["id"].split(r7.id + "-")[-1], "R7 " + c["id"].split(r7.id + "-")[-1])
                 for c in r7_safe]

    bodies: list[dict[str, Any]] = []
    cells_by_body: dict[str, list[dict[str, Any]]] = {}
    for body in spec.bodies:
        rid = runs.get(body)
        nums = body_numbers(study.get(body))
        for ev in evolved.values():
            if body in ev["bodies"]:
                nums["lie_rise_evolved"] = ev["bodies"][body]["worst"]
        row = {"key": body, "label": spec.labels.get(body, body), "stage_c_run": rid, "numbers": nums,
               "line": body_line(nums), "candidate": (study.get(body) or {}).get("candidate")}
        bodies.append(row)
        if rid is None:
            cells_by_body[body] = []
            continue
        run = lab.registry.get_run(rid)
        n_starts = len((run.inputs.get("params") or {}).get("start_vectors") or [])
        cands = {c["id"]: c for c in lab.registry.list_candidates(rid)}
        arch = json.loads((lab.registry.run_dir(rid) / "archive.json").read_text(encoding="utf-8"))
        safe = []
        for cell in arch["archive"]["cells"]:
            if not cell.get("within_limits"):
                continue
            c = cands[cell["candidate"]]
            o = origin_index(c["id"], cands, n_starts)
            d = c.get("descriptors") or {}
            short = "-".join(c["id"].rsplit("-", 2)[-2:])
            safe.append({"candidate": c["id"], "short": short, "cell": list(c["cell"]), "origin": o,
                         "origin_name": None if o is None or o >= len(gen_names) else gen_names[o],
                         "qom": d.get("quantity_of_motion"), "regularity": d.get("tempo_regularity"),
                         "controller": c["controller"]})
        cells_by_body[body] = safe

    groups: list[dict[str, Any]] = []
    # ---- screen plays
    slow = slowest_trot(hw.trot_cycles_s, hw.trot_strides)
    screen_items = []
    for k in spec.screen:
        key = slow if k == "slowest trot" else k
        label = (f"slowest trot ({trot_label(key).removeprefix('trot ')})" if k == "slowest trot"
                 else trot_label(key) if key.startswith("trot ") else key)
        screen_items.append({"key": f"screen:{key}", "label": label, "kind": "screen", "play": key,
                             "cells": [{"body": b["key"], "play": f"screen:{key}", "playing": label,
                                        "match": None} for b in bodies]})
    for label, ev in evolved.items():  # each body its own version (ADR-107)
        cells = []
        for b in bodies:
            got = ev["bodies"].get(b["key"])
            if got is None:
                cells.append({"body": b["key"], "play": None, "playing": None, "match": "not evolved yet"})
                continue
            cells.append({"body": b["key"], "play": evolved_play(label, got["params"]), "match": None,
                          "playing": f"{label}: this body's version (worst-seed margin {got['worst']:+.2f}, whole "
                                     f"motion)"})
        screen_items.append({"key": f"screen:{label}", "label": label, "kind": "screen", "play": label,
                             "cells": cells})
    groups.append({"key": "screen", "title": "Screen plays (every body)", "items": screen_items})
    # ---- shared behaviours
    shared_items = [{"key": f"shared:{p.label}", "label": p.label, "kind": "shared", "ref": p.ref,
                     "cells": [{"body": b["key"], "play": f"shared:{p.label}", "playing": p.label, "match": None}
                               for b in bodies]} for p in hw.performances]
    groups.append({"key": "shared", "title": "Shared behaviours (R6c, R7; Stage B)", "items": shared_items})
    # ---- own behaviours: one item per distinct (R7 generator, archive cell) among the bodies' safe cells
    seen: dict[str, dict[str, Any]] = {}
    for body in spec.bodies:
        for c in cells_by_body[body]:
            seen.setdefault(item_key(c["origin"], c["cell"]), c)
    own_items = []
    for key, ref in sorted(seen.items(), key=lambda kv: (kv[1]["cell"][0], kv[1]["cell"][1],
                                                         -1 if kv[1]["origin"] is None else kv[1]["origin"])):
        x, y = ref["cell"]
        origin = ref["origin_name"] or "an unseeded start"
        label = f"from {origin} · cell {x},{y}"
        cells = []
        for b in bodies:
            got, how = match_cell(ref["origin"], ref["cell"], cells_by_body[b["key"]], spec.max_cell_distance)
            if got is None:
                cells.append({"body": b["key"], "play": None, "playing": None, "match": how})
            else:
                playing = (f"{got['short']} q{got['qom']:.1f} r{got['regularity']:.2f} "
                           f"(from {got['origin_name'] or 'an unseeded start'}; {how})")
                cells.append({"body": b["key"], "play": f"own:{got['candidate']}", "playing": playing, "match": how})
        own_items.append({"key": key, "label": label, "kind": "own", "origin": ref["origin_name"], "cell": [x, y],
                          "qom": ref["qom"], "cells": cells})
    groups.append({"key": "own", "title": "Own behaviours (Stage C), matched across bodies", "items": own_items})

    out = {"set": spec.key, "title": spec.title, "seeds": list(spec.seeds), "bodies": bodies, "groups": groups,
           "stage_c_runs": runs, "_cells": cells_by_body, "_hw": hw}
    _PLAN_CACHE[spec.key] = (sig, out)
    return out


def manifest(lab: Any, set_key: str) -> dict[str, Any]:
    """The compare page's manifest: plan + per cell and seed the stored run, badge and stopping limit. Sets of
    behaviours searched by outcome (R15) are read by ``calflab.app.outcome_compare``."""
    from calflab.app.diversity_compare import DIVERSITY_SETS, diversity_manifest
    from calflab.app.outcome_compare import OUTCOME_SETS, outcome_manifest

    if set_key in OUTCOME_SETS:
        return outcome_manifest(lab, set_key)
    if set_key in DIVERSITY_SETS:  # one body, many behaviours (R16, ADR-112)
        return diversity_manifest(lab, set_key)
    spec = compare_set(set_key)
    p = plan(lab, spec)
    runs = p["stage_c_runs"]
    stored = missing = 0
    groups = []
    for g in p["groups"]:
        items = []
        for it in g["items"]:
            cells = []
            for c in it["cells"]:
                seeds = []
                if c["play"] is not None and runs.get(c["body"]):
                    for seed in spec.seeds:
                        rec = lab.registry.find_run_by_key(play_key(spec.key, c["body"], runs[c["body"]], c["play"],
                                                                    seed))
                        if rec is None:
                            missing += 1
                            seeds.append({"seed": seed, "run": None, "badge": None, "margin": None, "limit": None,
                                          "text": "not played yet"})
                            continue
                        stored += 1
                        m = rec.metrics or {}
                        b = badge(m.get("within_limits"), m.get("safety_margin"), spec.near)
                        mg = m.get("safety_margin")
                        text = {"within": "within", "near": "near the margin", "over": "over"}.get(b or "", "")
                        if mg is not None:
                            text += f" {mg:+.2f}"
                        seeds.append({"seed": seed, "run": rec.id, "badge": b, "margin": mg,
                                      "limit": m.get("stopped_by"), "text": text, "href": f"/?replay={rec.id}"})
                cells.append({**c, "empty": c["play"] is None,
                              "message": (c.get("match") or "no matching behaviour") if c["play"] is None else None,
                              "seeds": seeds})
            items.append({**{k: v for k, v in it.items() if k != "cells"}, "cells": cells})
        groups.append({**g, "items": items})
    return {"set": spec.key, "title": spec.title, "seeds": list(spec.seeds), "near": spec.near,
            "bodies": p["bodies"], "groups": groups, "stored": stored, "missing": missing,
            "hint": (f"{missing} plays not stored yet: python docs/studies/compare_r12.py <project> --set={spec.key}"
                     if missing else "")}


# ====================================================================== generating the missing plays
def _generator_params(lab: Any, brun: Any) -> dict[str, Any]:
    """The design params the Stage B run built its bodies with (as ``stagec_r12.judge``), belt catalog inlined."""
    from calflab.design import genome_definition
    from calflab.evolve.hardware import catalog_with_what_ifs

    gdef = genome_definition("feral_calf")
    bg = lab.variant_graph(gdef.complete(brun.genome["values"]))
    for role, key in (("model", "compile"), ("design", "generator_params")):
        bg.role(role).params = {k: v for k, v in brun.inputs[key].items() if k != "belt_catalog"}
    gp = lab.job_generator_params(bg)
    gp["belt_catalog"] = catalog_with_what_ifs(gp["belt_catalog"], False)
    return gp


def todo(lab: Any, set_key: str, seeds: list[int] | None = None) -> list[dict[str, Any]]:
    """Every play of the set that has no stored run yet, with its worker payload."""
    from calflab.design import genome_definition
    from calflab.evolve.hardware import screen_plays

    spec = compare_set(set_key)
    p = plan(lab, spec)
    runs = p["stage_c_runs"]
    hw = p["_hw"]
    brun = lab.registry.get_run(spec.stage_b_run)
    preset = lab.prepare_hardware(brun.fitness["preset"])
    perfs = {x["label"]: x for x in preset["evaluation"]["hardware"]["performances"]}
    screens = {x["key"]: x for x in screen_plays(hw)}
    own = {f"own:{c['candidate']}": c for cs in p["_cells"].values() for c in cs}
    evolved = evolved_versions(spec)
    gp = _generator_params(lab, brun)
    gdef = genome_definition("feral_calf")
    bodies: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    wanted: set[tuple[str, str]] = set()
    for g in p["groups"]:
        for it in g["items"]:
            for c in it["cells"]:
                if c["play"] is not None and runs.get(c["body"]):
                    wanted.add((c["body"], c["play"]))
    for body, play in sorted(wanted):
        if body not in bodies:
            run = lab.registry.get_run(runs[body])
            bodies[body] = {"genome": {"definition": gdef.name, "version": gdef.version,
                                       "values": gdef.complete(run.genome["values"])},
                            "overrides": run.overrides, "generator": "feral_calf", "generator_params": gp,
                            "compile": brun.inputs["compile"], "evaluation": brun.fitness["preset"]["evaluation"]}
        kind, _, name = play.partition(":")
        if kind == "screen":
            item = {"kind": "screen", "label": name, **screens[name]}
        elif kind == "shared":
            item = {"kind": "performance", "label": name, "controller": perfs[name]["controller"]}
        elif kind == "evolved":
            label = name.rsplit(":", 1)[0]
            ev = evolved[label]
            item = {"kind": "lie_rise", "label": label, "params": ev["bodies"][body]["params"],
                    "settle_s": ev["settle_s"]}
        else:
            c = own[play]
            item = {"kind": "performance", "label": f"{c['short']} q{c['qom']:.1f}", "controller": c["controller"],
                    "candidate": c["candidate"]}
        for seed in seeds if seeds is not None else spec.seeds:
            key = play_key(spec.key, body, runs[body], play, seed)
            if lab.registry.find_run_by_key(key) is not None:
                continue
            out.append({"key": key, "body": body, "body_run": runs[body], "play": play, "seed": seed,
                        "payload": {**bodies[body], "item": item, "seed": seed, "seconds": hw.performance_s,
                                    "margin": hw.margin}})
    return out


def play_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker: one play (a screen primitive or a performance) on one seed, judged as the R11c suite judges it; the
    rollout is saved to a temporary file for the main process to move into the run folder."""
    from calflab.evolve.hardware import _build, compile_options, judge_play
    from calflab.fitness.preset import EvaluationSettings
    from calflab.plugins import load_plugins, registry
    from calflab.sim import CompileOptions, SimSettings, compile_mjcf, run_rollout

    load_plugins()
    seed, margin, item = int(payload["seed"]), float(payload["margin"]), payload["item"]
    if item["kind"] == "lie_rise":  # a body's own evolved version, judged over the whole motion (ADR-107)
        from calflab.evolve.lie_rise import play_seed

        t = time.perf_counter()
        path = Path(tempfile.mkdtemp(prefix="calflab-compare-")) / "rollout.npz"
        rec = play_seed(payload, item["params"], seed, margin, float(item["settle_s"]), rollout_path=str(path))
        return {"report": rec, "rollout": str(path), "compile": rec.pop("compile"), "controller": rec["controller"],
                "wall_s": round(time.perf_counter() - t, 1)}
    design, lib = _build(payload)
    ev = EvaluationSettings.model_validate(payload["evaluation"])
    copts = compile_options(payload.get("compile", {}), ev)
    t = time.perf_counter()
    cm = compile_mjcf(design.spec, lib, CompileOptions.model_validate(copts), seed)
    if item["kind"] == "screen":
        from calflab.behave.interpret import InterpretSettings

        prim = registry.get("motion_primitive", item["primitive"])(item["params"])  # type: ignore[call-arg]
        s = InterpretSettings(margin=margin, seed=seed)
        key, params = prim.controller(design.spec, lib)  # type: ignore[attr-defined]
        off, per = float(prim.warmup_s()), float(prim.period_s())  # type: ignore[attr-defined]
        length = per if prim.one_shot else s.cycles * per  # type: ignore[attr-defined]
        t0, t1 = off, off + min(max(length, s.min_play_s), s.max_play_s)
        ctrl = {"key": key, "params": params}
        duration = round(t1 + 0.3, 3)
    else:
        ctrl = item["controller"]
        t0, t1, duration = 0.0, float(payload["seconds"]), float(payload["seconds"])
    settings = SimSettings(duration_s=duration, control_hz=50.0, record_hz=50.0, settle_s=0.4, start_pose="stand",
                           stop_on_fall=False, seed=seed)
    ro = run_rollout(cm, registry.get("controller", ctrl["key"])(ctrl["params"]), settings, lib)  # type: ignore[arg-type]
    rec = judge_play(ro, design.spec, lib, margin, t0, t1)
    path = Path(tempfile.mkdtemp(prefix="calflab-compare-")) / "rollout.npz"
    ro.save(path)
    return {"report": rec, "rollout": str(path), "compile": copts, "controller": ctrl,
            "wall_s": round(time.perf_counter() - t, 1)}


def store_play(lab: Any, spec: CompareSet, job: dict[str, Any], result: dict[str, Any], scene: dict[str, Any]) -> str:
    """Store one finished play as a run of kind ``sim`` (as ``store_r11cb.py``), keyed for ``manifest``."""
    from calflab.project.registry import RunRecord

    rep = result["report"]
    sim_id = lab.registry.new_run_id("sim")
    rdir = lab.registry.run_dir(sim_id)
    rdir.mkdir(parents=True, exist_ok=True)
    shutil.move(result["rollout"], rdir / "rollout.npz")
    shutil.rmtree(Path(result["rollout"]).parent, ignore_errors=True)
    (rdir / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    label = spec.labels.get(job["body"], job["body"])
    item = job["payload"]["item"]
    lab.registry.save_run(RunRecord(
        id=sim_id, kind="sim", title=f"{spec.title_prefix} {label} {item['label']}: seed {job['seed']}",
        duration_s=result["wall_s"], seed=job["seed"], backend="local", cache_key=job["key"],
        inputs={"compare": {"set": spec.key, "body": job["body"], "body_run": job["body_run"], "play": job["play"],
                            "seed": job["seed"], "candidate": item.get("candidate")},
                "compile": result["compile"], "margin": job["payload"]["margin"],
                "report": {k: v for k, v in rep.items() if k != "joints"}, "joints": rep["joints"]},
        genome=job["payload"]["genome"], overrides=job["payload"]["overrides"], controller=result["controller"],
        metrics={"within_limits": rep["within"], "safety_margin": rep["margin"], "closest": rep["closest"],
                 "fell": rep["fell"], "stopped_by": stopped_by(rep, rep.get("joints"))},
        artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
        parent=job["body_run"], tags=["compare", spec.key, job["body"], item["label"]]))
    return sim_id


def generate(lab: Any, set_key: str, workers: int = 7, seeds: list[int] | None = None,
             report: Callable[[int, int, str], None] | None = None,
             cancelled: Callable[[], bool] | None = None, limit: int | None = None) -> dict[str, Any]:
    """Play every missing play of a set and store it; existing ones are reused. ``report(done, total, message)``.
    Returns counts and the wall time (s)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from calflab.app.scene import build_scene
    from calflab.evolve.hardware import _build

    spec = compare_set(set_key)
    jobs = todo(lab, set_key, seeds)
    if limit is not None:
        jobs = jobs[:limit]
    t0 = time.perf_counter()
    scenes: dict[str, dict[str, Any]] = {}
    for j in jobs:
        if j["body"] not in scenes:
            design, _lib = _build(j["payload"])
            scenes[j["body"]] = build_scene(design, lab.state.layers, lab.state.settings)
    done, failed = 0, []
    if report:
        report(0, len(jobs), f"{len(jobs)} plays to play")
    if jobs:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(play_task, j["payload"]): j for j in jobs}
            for f in as_completed(futs):
                j = futs[f]
                if cancelled and cancelled():
                    for other in futs:
                        other.cancel()
                    break
                try:
                    sid = store_play(lab, spec, j, f.result(), scenes[j["body"]])
                    msg = f"{j['body']} {j['play']} seed {j['seed']}: run {sid}"
                except Exception as exc:  # one failing play must not lose the others
                    failed.append({"body": j["body"], "play": j["play"], "seed": j["seed"], "error": str(exc)})
                    msg = f"{j['body']} {j['play']} seed {j['seed']}: FAILED {exc}"
                    log.warning(msg)
                done += 1
                if report:
                    report(done, len(jobs), msg)
    return {"played": done - len(failed), "failed": failed, "wall_s": round(time.perf_counter() - t0, 1),
            "planned": len(jobs)}
