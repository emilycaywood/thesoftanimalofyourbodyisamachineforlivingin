"""Store every play the group compare page needs for a set (ADR-106), reusing the ones already stored.

The plays (screen plays, the shared R6c/R7 behaviours, each body's own Stage C behaviours, seeds 0-2) are listed by
``calflab.app.compare.todo`` and stored as runs of kind ``sim`` by ``calflab.app.compare.generate``; the page
``compare.html?set=<set>`` then finds them through ``/api/compare/<set>``. The project document is never changed.

Run:  python docs/studies/compare_r12.py <project dir> [--set=r12] [--workers=7] [--seeds=0,1,2] [--limit=N] [--dry]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> None:
    from calflab.app import compare
    from calflab.app.lab import Lab
    from calflab.plugins import load_plugins

    proj = Path(sys.argv[1])
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in sys.argv[2:] if a.startswith("--"))
    key = opts.get("set") or "r12"
    seeds = [int(s) for s in opts["seeds"].split(",")] if opts.get("seeds") else None
    load_plugins()
    lab = Lab.open(proj, create=False)
    try:
        before = compare.manifest(lab, key)
        print(f"set {key}: {before['stored']} plays stored, {before['missing']} cell-seeds missing", flush=True)
        if "dry" in opts:
            jobs = compare.todo(lab, key, seeds)
            kinds: dict[str, int] = {}
            for j in jobs:
                kinds[j["play"].split(":")[0]] = kinds.get(j["play"].split(":")[0], 0) + 1
            print(f"{len(jobs)} plays to play: {kinds}")
            return
        t0 = time.perf_counter()

        def report(done: int, total: int, msg: str) -> None:
            el = time.perf_counter() - t0
            eta = el / done * (total - done) if done else 0.0
            print(f"[{done}/{total}] {el:.0f} s (eta {eta:.0f} s) {msg}", flush=True)

        out = compare.generate(lab, key, workers=int(opts.get("workers") or 7), seeds=seeds, report=report,
                               limit=int(opts["limit"]) if opts.get("limit") else None)
        after = compare.manifest(lab, key)
        print(f"played {out['played']} of {out['planned']} in {out['wall_s']:.0f} s ({out['wall_s'] / 60:.1f} min); "
              f"failed {len(out['failed'])}; now {after['stored']} stored, {after['missing']} missing", flush=True)
        for f in out["failed"]:
            print("FAILED", f)
    finally:
        lab.close()


if __name__ == "__main__":
    main()
