"""Session R10: the extra grid (11.1 V for the two leading bodies; the six-servo reference). Same columns as
``carpus_r10_table.py``.

Run:  python docs/studies/carpus_r10_extra_table.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> None:
    from carpus_r10_table import f, peaks, prim, trot_summary

    g = json.loads((HERE / "carpus_r10_grid_extra.json").read_text(encoding="utf-8"))
    print("| body | trots within | fastest within | walk | turn | lie_rise | belt peaks N (st / hk / cp) | new A peak / mean |")
    print("|---|---|---|---|---|---|---|---|")
    for name, e in g.items():
        t = trot_summary(e["seeds"])
        best = "none" if t["best"] is None else (f"{t['best'][0]} s / {t['best'][1]}, "
                                                 f"{min(t['best_speed']):.0f}-{max(t['best_speed']):.0f} mm/s")
        cols = [" / ".join(f(r["margin"]) for r in prim(e["seeds"], k)) for k in ("walk", "turn", "lie_rise")]
        pk = peaks(e["seeds"])
        b = " / ".join(f"{pk['belt_n'].get(j, 0):.0f}" for j in ("stifle", "hock", "carpus"))
        print(f"| {name} | {t['n_within']} | {best} | {' | '.join(cols)} | {b} | {pk['new_peak_a']:.2f} / "
              f"{pk['new_mean_a']:.2f} |")


if __name__ == "__main__":
    main()
