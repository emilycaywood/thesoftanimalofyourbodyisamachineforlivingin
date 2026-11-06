"""Session R10: compare.html links, today's body (left) against the R10 body (right), for the 33 behaviour minutes
(R6c / R7 runs on today's body, ``R10 what-if`` runs) and the primitive plays (``R9 play`` / ``R10 play`` runs).

Run:  python docs/studies/compare_r10.py [<port>]   (prints a markdown table)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1] / "projects" / "robot-calf-final"


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8020"
    con = sqlite3.connect(f"file:{PROJECT / 'index.sqlite'}?mode=ro", uri=True)
    runs = dict(con.execute("select id, title from runs"))
    today: dict[tuple[str, int], str] = {}
    for rid, title in runs.items():
        m = re.match(r"(R6c|R7) (\S+) \(.*\) \S+: 60 s, seed (\d)", title or "")
        if m:
            today[(f"{m.group(1)}-{m.group(2)}", int(m.group(3)))] = rid
    stored = json.loads((HERE / "carpus_r10_stored.json").read_text(encoding="utf-8"))
    url = f"http://localhost:{port}/compare.html"
    print("| behaviour | seed | today | R10 body | link |")
    print("|---|---|---|---|---|")
    for k, v in stored.items():
        if k == "case":
            continue
        for s in sorted(v["seeds"], key=lambda s: s["seed"]):
            a = today.get((v["label"], s["seed"]))
            if a is None:
                continue
            la, lb = quote(f"today {v['label']} s{s['seed']}"), quote(f"R10 {v['label']} s{s['seed']}")
            print(f"| {v['label']} | {s['seed']} | {a} | {s['run']} ({s['report']['margin']:+.2f}) | "
                  f"[compare]({url}?a={a}&b={s['run']}&la={la}&lb={lb}) |")
    plays = {t: r for r, t in runs.items() if (t or "").startswith(("R9 play: old servos", "R10 play:"))}

    def find(prefix: str) -> str | None:
        return next((r for t, r in plays.items() if t.startswith(prefix)), None)

    pairs = [("trot, same 0.5 s / 2.0", "R9 play: old servos, the same quick trot",
              "R10 play: new carpi and hocks, fastest trot"),
             ("trot, each body's fastest within", "R9 play: old servos, fastest trot",
              "R10 play: new carpi and hocks, fastest trot"),
             ("walk", "R9 play: old servos, walk", "R10 play: new carpi and hocks, walk"),
             ("turn", "R10 play: today, turn", "R10 play: new carpi and hocks, turn"),
             ("lie_rise", "R10 play: today, lie_rise", "R10 play: new carpi and hocks, lie_rise")]
    print()
    print("| play (seed 0) | today | R10 body | link |")
    print("|---|---|---|---|")
    for label, pa, pb in pairs:
        a, b = find(pa), find(pb)
        if a and b:
            print(f"| {label} | {a} | {b} | [compare]({url}?a={a}&b={b}&la=today&lb=R10) |")


if __name__ == "__main__":
    main()
