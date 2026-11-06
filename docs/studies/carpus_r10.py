"""Session R10 (ADR-101): which carpus drive keeps the calm behaviours and ``lie_rise`` within limits while the trot
stays fast. In memory only (the working body is unchanged); bodies are built through the per-pair servo genes.

Every body keeps R9's best stifle and hock belts (catalog 40T/80T, 444 and 400 mm) and has at most four STS3250
C002s. Carpus drives (old or new carpus servo):
* ``carpus 1:1 45T``: R8's what-if, a 45T/45T pair (not in the catalog);
* ``carpus 1.5:1``: R8's what-if, a 30T/45T pair (not in the catalog);
* today's 30T/60T (2:1, catalog);
* ``carpus 40T-80T``: the catalog's 40T/80T (2:1) on a 640 mm belt.
New-servo pairs: hip ab/ad + hocks (R9's best, old carpus), hocks + carpi, or hip ab/ad + carpi; and, once the first
grid showed ``lie_rise`` binding on the old front shoulders, shoulders + hocks, shoulders + hip ab/ad, shoulders + carpi.

Stage ``grid``: ``servos_r9.py --grid=r10`` (the quick trot grid, walk, turn and ``lie_rise`` on three seeds, margin
0.2). Stage ``perform``: ``perform_r9.py --store=0`` (R6c's and R7's safe behaviours, 60 s, three seeds), one output
file per body in ``carpus_r10_perform/``. ``--volt=11.1`` runs the same at 11.1 V (grid only).

Run:  python docs/studies/carpus_r10.py <project dir> grid|perform [--cases=a;b] [--volt=11.1] [--workers=7]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BELTS = "stifle 40T-80T | hock 40T-80T 400"
DRIVES = {"1:1 45T": "carpus 1:1 45T", "1.5:1 30T/45T": "carpus 1.5:1", "2:1 30T/60T (today)": "",
          "2:1 40T/80T": "carpus 40T-80T"}
SERVOS = {"old carpus": "new: hip_abd+hock", "new carpus, new hocks": "new: hock+carpus",
          "new carpus, new hip ab/ad": "new: hip_abd+carpus",
          # added after the first grid: lie_rise binds on the old front shoulders' sustained torque on every body
          "new shoulders, new hocks": "new: hock+shoulder", "new shoulders, new hip ab/ad": "new: hip_abd+shoulder",
          "new shoulders, new carpus": "new: shoulder+carpus"}
#: R6c's and R7's safe behaviours (as R9 played them)
PICKS = ["20261105-053201-evolve-e4c8:g002-016=R6c-calm", "20261105-053201-evolve-e4c8:g018-025=R6c-lively",
         "20261105-053201-evolve-e4c8:g013-008=R6c-walking", "20261105-053201-evolve-e4c8:g012-026=R6c-trotting",
         "20261105-232649-evolve-4237:g000-000=R7-calm", "20261105-232649-evolve-4237:g009-004=R7-ambling",
         "20261105-232649-evolve-4237:g000-001=R7-lively", "20261105-232649-evolve-4237:g008-000=R7-walking",
         "20261105-232649-evolve-4237:g006-013=R7-trot-walk", "20261105-232649-evolve-4237:g001-015=R7-trot-shift",
         "20261105-232649-evolve-4237:g000-003=R7-trotting"]


def cases() -> dict[str, str]:
    """label -> case name (``servos_r9.parse_case``); ``today`` is the working body."""
    out = {"today": "now"}
    for s_label, servos in SERVOS.items():
        for d_label, drive in DRIVES.items():
            out[f"{s_label}, carpus {d_label}"] = " | ".join(p for p in (servos, drive, BELTS) if p)
    return out


def safe_name(case: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in case).strip("_")


def main() -> None:
    proj, stage = sys.argv[1], sys.argv[2]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[3:] if a.startswith("--"))
    names = list(cases().values())
    if "cases" in opts:
        names = [c.strip() for c in opts["cases"].split(";")]
    py = sys.executable
    workers = opts.get("workers", "7")
    if stage == "grid":
        volt = opts.get("volt")
        run = [f"{c} @{volt}V" for c in names] if volt else names
        out = HERE / (f"carpus_r10_grid_{volt}V.json" if volt else "carpus_r10_grid.json")
        subprocess.run([py, str(HERE / "servos_r9.py"), proj, str(out), "--cases=" + ";".join(run), "--grid=r10",
                        f"--workers={workers}", "--append=1"], check=True)
    elif stage == "perform":
        d = HERE / "carpus_r10_perform"
        d.mkdir(exist_ok=True)
        for c in names:
            out = d / f"{safe_name(c)}.json"
            if out.exists() and "redo" not in opts:
                continue
            subprocess.run([py, str(HERE / "perform_r9.py"), proj, str(out), c, "--store=0", f"--workers={workers}",
                            *PICKS], check=True)
    else:
        raise SystemExit(f"unknown stage {stage!r}")
    print(json.dumps(cases(), indent=1))


if __name__ == "__main__":
    main()
