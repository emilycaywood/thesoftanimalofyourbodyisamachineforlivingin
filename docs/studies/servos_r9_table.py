"""Tables for ``servos_r9.md`` from the JSON written by ``servos_r9.py`` (ADR-100).

Per case, over the seeds it was played on: the quickest trot within every limit on every seed (shortest cycle,
then the stride with the highest slowest-seed speed), the fastest trot within on every seed, the walk and turn
margins, the highest belt tension of any play (N, and of the trots within), and the new servos' current.

Run:  python docs/studies/servos_r9_table.py <servos_r9.json> [case ...]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any


def summary(name: str, v: dict[str, Any]) -> dict[str, Any]:
    seeds = sorted(v["seeds"])
    by: dict[tuple[str, float, float], list[dict[str, Any]]] = defaultdict(list)
    for sd in seeds:
        for r in v["seeds"][sd]["rows"]:
            p = r["params"]
            by[(r["primitive"], p.get("cycle_s", 0.0), p.get("stride", 0.0))].append(r)
    trots = {k: rs for k, rs in by.items() if k[0] == "trot" and len(rs) == len(seeds)}
    ok = {k: rs for k, rs in trots.items() if all(r["within"] for r in rs)}
    quick = min(ok, key=lambda k: (k[1], -min(r["speed_mm_s"] for r in ok[k]))) if ok else None
    fast = max(ok, key=lambda k: min(r["speed_mm_s"] for r in ok[k])) if ok else None

    def m(prim: str) -> list[dict[str, Any]]:
        return next((rs for k, rs in by.items() if k[0] == prim), [])

    def worst(rs: list[dict[str, Any]]) -> str:
        w = min(rs, key=lambda r: r["margin"])
        return w["worst"][0][0] if w["worst"] else ""

    allrows = [r for rs in by.values() for r in rs]
    okrows = [r for rs in ok.values() for r in rs]

    def belt_peak(rows: list[dict[str, Any]]) -> tuple[float, str]:
        best = (0.0, "")
        for r in rows:
            for j, b in r["belts"].items():
                if b["peak_n"] > best[0]:
                    best = (b["peak_n"], j)
        return best

    cur = [r["current"]["new_total_peak_a"] for r in allrows if r["current"]["new_total_peak_a"] is not None]
    cur_ok = [r["current"]["new_total_peak_a"] for r in okrows if r["current"]["new_total_peak_a"] is not None]
    mean_ok = [r["current"]["new_total_mean_a"] for r in okrows if r["current"]["new_total_mean_a"] is not None]
    return {
        "name": name, "mass_g": v["mass_g"], "seeds": len(seeds),
        "quick": quick, "quick_speeds": [r["speed_mm_s"] for r in ok[quick]] if quick else None,
        "quick_margins": [r["margin"] for r in ok[quick]] if quick else None,
        "fast": fast, "fast_speed": min(r["speed_mm_s"] for r in ok[fast]) if fast else None,
        "n_ok": len(ok), "ok": sorted(ok),
        "walk": [r["margin"] for r in m("walk")], "walk_worst": worst(m("walk")) if m("walk") else "",
        "turn": [r["margin"] for r in m("turn")], "turn_worst": worst(m("turn")) if m("turn") else "",
        "belt_peak": belt_peak(allrows), "belt_peak_ok": belt_peak(okrows),
        "current_peak_a": max(cur) if cur else None, "current_peak_ok_a": max(cur_ok) if cur_ok else None,
        "current_mean_ok_a": max(mean_ok) if mean_ok else None,
    }


def fmt(s: dict[str, Any]) -> str:
    q = f"{s['quick'][1]:g} s / {s['quick'][2]:g} ({min(s['quick_speeds']):.0f}-{max(s['quick_speeds']):.0f} mm/s, " \
        f"{min(s['quick_margins']):+.2f})" if s["quick"] else "none"
    f = f"{s['fast'][1]:g} s / {s['fast'][2]:g}, {s['fast_speed']:.0f} mm/s" if s["fast"] else "none"
    w = " / ".join(f"{x:+.2f}" for x in s["walk"]) + (f" {s['walk_worst']}" if min(s["walk"] or [1]) < 0 else "")
    t = " / ".join(f"{x:+.2f}" for x in s["turn"]) + (f" {s['turn_worst']}" if min(s["turn"] or [1]) < 0 else "")
    b = f"{s['belt_peak'][0]:.0f} ({s['belt_peak'][1]})"
    bo = f"{s['belt_peak_ok'][0]:.0f} ({s['belt_peak_ok'][1]})" if s["belt_peak_ok"][1] else "-"
    c = "-" if s["current_peak_a"] is None else f"{s['current_peak_a']:.1f}"
    co = "-" if s["current_peak_ok_a"] is None else f"{s['current_peak_ok_a']:.1f} / {s['current_mean_ok_a']:.1f}"
    return (f"| {s['name']} | {s['mass_g']:.0f} | {q} | {f} | {s['n_ok']} | {w} | {t} | {b} | {bo} | {c} | {co} |")


HEADER = ("| case | mass g | quickest trot within (3 seeds) | fastest within | trots within | walk | turn | "
          "belt peak N (any play) | belt peak N (trots within) | new servos A peak (any) | A peak / mean (trots within) |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|")


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
    names = sys.argv[2:] or list(d)
    print(HEADER)
    for n in names:
        if d[n]["seeds"]:
            print(fmt(summary(n, d[n])))


if __name__ == "__main__":
    main()
