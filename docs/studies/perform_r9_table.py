"""Table for ``servos_r9.md``: R6c's and R7's safe behaviours, 60 s on three seeds, on today's body (from
``perform_r7.json`` and ``coverage_r6c.md``'s runs) and on what-if bodies (``perform_r9.py`` JSON files).

Per behaviour and body: the margin per seed (bold = over), the closest limit where it went over, the quantity of
motion (deg/s) and trunk speed (mm/s) over the minute.

Run:  python docs/studies/perform_r9_table.py <perform_r9 json> [...]
"""
from __future__ import annotations

import json
import sys
from typing import Any


def rows(path: str) -> dict[str, dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if isinstance(d, list):  # perform_r6.py's format (today's body)
        d = {"case": "now", **{r["candidate"]: r for r in d}}
    out = {}
    for k, v in d.items():
        if k == "case":
            continue
        seeds = sorted(v["seeds"], key=lambda s: s["seed"])
        out[v["label"]] = {
            "margins": [s["report"]["margin"] for s in seeds], "within": [s["report"]["within"] for s in seeds],
            "over": sorted({s["report"]["closest_detail"].split(":")[0] + " " + str(s["report"]["closest"])
                            for s in seeds if not s["report"]["within"]}),
            "qom": [s["movement"]["quantity_of_motion_deg_s"] for s in seeds],
            "speed": [s["movement"]["trunk_speed_mm_s"] for s in seeds],
            "runs": [s.get("run") for s in seeds]}
    return out


def main() -> None:
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        case = d["case"] if isinstance(d, dict) else f"now ({path})"
        r = rows(path)
        n = sum(sum(x["within"]) for x in r.values())
        print(f"\n{case}: {n} of {3 * len(r)} minutes hold\n")
        print("| behaviour | seed 0 | seed 1 | seed 2 | over at | QoM deg/s | trunk mm/s |\n|---|---|---|---|---|---|---|")
        for label, x in r.items():
            m = " | ".join(f"{v:+.2f}" if ok else f"**{v:+.2f}**" for v, ok in zip(x["margins"], x["within"], strict=True))
            print(f"| {label} | {m} | {', '.join(x['over']) or '-'} | {min(x['qom']):.1f}-{max(x['qom']):.1f} | "
                  f"{min(x['speed']):.0f}-{max(x['speed']):.0f} |")


if __name__ == "__main__":
    main()
