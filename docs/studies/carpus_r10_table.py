"""Tables for session R10's carpus study (``carpus_r10.py``): per body, the fastest trot within every limit on all
three seeds, walk / turn / lie_rise margins, the behaviours that hold for 60 s, belt peaks and the new servos' current.

Run:  python docs/studies/carpus_r10_table.py [<grid json>] [<perform dir>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def trot_summary(seeds: dict[str, Any]) -> dict[str, Any]:
    """The trots within limits on every seed, the fastest of them (by its slowest seed), and per-seed margins."""
    by: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for s in seeds.values():
        for r in s["rows"]:
            if r["primitive"] == "trot":
                by.setdefault((r["params"]["cycle_s"], r["params"]["stride"]), []).append(r)
    ok = {k: v for k, v in by.items() if len(v) == len(seeds) and all(r["within"] for r in v)}
    best = max(ok, key=lambda k: min(r["speed_mm_s"] for r in ok[k]), default=None)
    return {"n_within": len(ok), "n": len(by), "best": best,
            "best_speed": None if best is None else [r["speed_mm_s"] for r in ok[best]],
            "best_margin": None if best is None else [r["margin"] for r in ok[best]]}


def prim(seeds: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [next(r for r in seeds[s]["rows"] if r["primitive"] == key) for s in sorted(seeds)]


def peaks(seeds: dict[str, Any]) -> dict[str, Any]:
    """Over the plays within limits: the highest belt tension per belted joint (N) and the new servos' current (A)."""
    belt: dict[str, float] = {}
    brk: dict[str, Any] = {}
    cur_peak, cur_mean, per = 0.0, 0.0, {}
    for s in seeds.values():
        for r in s["rows"]:
            if not r["within"]:
                continue
            for j, b in r["belts"].items():
                key = j.split(".")[-1]
                belt[key] = max(belt.get(key, 0.0), b["peak_n"])
                brk[key] = b.get("breaking_n")
            c = r["current"]
            if c.get("new_total_peak_a") is not None:
                cur_peak = max(cur_peak, c["new_total_peak_a"])
                cur_mean = max(cur_mean, c["new_total_mean_a"])
            for j, v in c["per_servo"].items():
                key = j.split(".")[-1]
                per[key] = max(per.get(key, 0.0), v["peak_a"])
    return {"belt_n": belt, "breaking_n": brk, "new_peak_a": cur_peak, "new_mean_a": cur_mean, "per_servo_peak_a": per}


def perform_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = {}
    held = total = 0
    for k, v in d.items():
        if k == "case":
            continue
        ms = sorted(v["seeds"], key=lambda s: s["seed"])
        rows[v["label"]] = [(s["report"]["margin"], s["report"]["closest"], s["report"]["within"]) for s in ms]
        held += sum(1 for s in ms if s["report"]["within"])
        total += len(ms)
    return {"held": held, "total": total, "rows": rows}


def f(v: float | None, p: int = 2) -> str:
    return "-" if v is None else f"{v:+.{p}f}"


def main() -> None:
    from carpus_r10 import cases, safe_name

    grid = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "carpus_r10_grid.json"
    pdir = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "carpus_r10_perform"
    g = json.loads(grid.read_text(encoding="utf-8"))
    suffix = ""
    if "_11.1V" in grid.name:
        suffix = " @11.1V"
    print("| body | trots within (of 20) | fastest within, 3 seeds | walk | turn | lie_rise | 60 s held |")
    print("|---|---|---|---|---|---|---|")
    for label, c in cases().items():
        e = g.get(c + suffix)
        if not e or len(e["seeds"]) < 3:
            continue
        t = trot_summary(e["seeds"])
        best = "none" if t["best"] is None else (f"{t['best'][0]} s / {t['best'][1]}, "
                                                 f"{min(t['best_speed']):.0f}-{max(t['best_speed']):.0f} mm/s")
        w = " / ".join(f(r["margin"]) for r in prim(e["seeds"], "walk"))
        tu = " / ".join(f(r["margin"]) for r in prim(e["seeds"], "turn"))
        lr = prim(e["seeds"], "lie_rise")
        lrs = " / ".join(f(r["margin"]) for r in lr)
        if not all(r["within"] for r in lr):
            lrs += f" ({lr[0]['worst'][0][0] if lr[0]['worst'] else '?'})"
        p = perform_summary(pdir / f"{safe_name(c)}.json")
        ps = "-" if p is None else f"{p['held']} / {p['total']}"
        print(f"| {label} | {t['n_within']} | {best} | {w} | {tu} | {lrs} | {ps} |")
    print()
    print("| body | belt peaks within limits, N (stifle / hock / carpus) | new servos' current, A (peak sum / mean sum) |")
    print("|---|---|---|")
    for label, c in cases().items():
        e = g.get(c + suffix)
        if not e or len(e["seeds"]) < 3:
            continue
        pk = peaks(e["seeds"])
        b = " / ".join(f"{pk['belt_n'].get(j, 0):.0f}" for j in ("stifle", "hock", "carpus"))
        print(f"| {label} | {b} | {pk['new_peak_a']:.2f} / {pk['new_mean_a']:.2f} |")
    print()
    for label, c in cases().items():
        p = perform_summary(pdir / f"{safe_name(c)}.json")
        if p is None:
            continue
        print(f"### {label}: {p['held']} / {p['total']} held")
        for b, ms in p["rows"].items():
            print(f"* {b}: " + " / ".join(f"{m:+.2f}{'' if w else ' (' + str(cl) + ')'}" for m, cl, w in ms))


if __name__ == "__main__":
    main()
