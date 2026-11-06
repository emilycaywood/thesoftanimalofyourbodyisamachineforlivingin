"""Fingerprints of feral-calf builds, for the R10 servo-gene change (ADR-101).

Written once with the code *before* the per-pair servo genes, so ``tests/test_genome.py`` and
``tests/test_feral_calf.py`` can prove that the bodies built through the new genes are bit-identical: the spec (with
the genome version, the new ``metadata.feral.servos`` and the catalog's folder left out), the MJCF and the masses.

Run:  python tests/data/make_servo_fingerprints.py [<project dir>]   (writes tests/data/servo_fingerprints_r10.json)
Re-running it after the change must give the same file (except the ``written`` stamp).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = HERE / "servo_fingerprints_r10.json"
#: candidates and the baked design of projects/robot-calf-final used (that folder is not in git: tests skip without it)
CANDIDATE_RUN = "20261105-232649-evolve-4237"
DESIGN = "calf1-v001"


def fingerprint(spec: Any) -> dict[str, str]:
    """sha256 of the spec, of its MJCF (seed 0) and of its mass breakdown. The spec leaves out the genome version,
    the new ``metadata.feral.servos`` and the belt catalog's folder."""
    from calflab.components import library
    from calflab.model.mass import mass_breakdown
    from calflab.sim import CompileOptions, compile_mjcf

    lib = library()
    dump = json.loads(spec.model_dump_json())
    dump.get("metadata", {}).pop("genome_version", None)  # 1 -> 2 is the change itself
    fer = dump.get("metadata", {}).get("feral") or {}
    fer.pop("servos", None)
    (fer.get("belt_catalog") or {}).pop("origin", None)  # the folder the catalog was read from (machine-specific)
    h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()  # noqa: E731
    return {
        "spec": h(json.dumps(dump, sort_keys=True)),
        "mjcf": h(compile_mjcf(spec, lib, CompileOptions(), 0).xml),
        "mass": h(json.dumps(mass_breakdown(spec, lib), sort_keys=True, default=str)),
        "total_mass_g": repr(spec.total_mass_g()),
    }


def v1_genome(values: dict[str, Any]) -> Any:
    from calflab.design import genome_definition
    from calflab.model.genome import Genome

    d = genome_definition("feral_calf")
    base = {g.id: g.default for g in d.genes if not g.id.startswith("servo_")}
    base["actuator"] = "sts3215_c018"
    return Genome(definition="feral_calf", version=1, values={**base, **values})


def builds(project: Path | None) -> dict[str, Any]:
    """name -> spec of every build the tests compare."""
    from calflab.design import build_design

    out: dict[str, Any] = {
        "default": build_design(v1_genome({}), [], "feral_calf", {}).spec,
        "v1_sts3250": build_design(v1_genome({"actuator": "sts3250_c002"}), [], "feral_calf", {}).spec,
    }
    if project is None or not (project / "project.calflab.json").is_file():
        return out
    from calflab.app.lab import Lab

    lab = Lab.open(project, create=False)
    try:
        out["project_document"] = lab.design().spec
        g, ov = lab.design_document(DESIGN)
        out["baked_design"] = lab.design(g, ov).spec
        cands = [json.loads(x) for x in (project / "runs" / CANDIDATE_RUN / "candidates.jsonl")
                 .read_text(encoding="utf-8").splitlines() if x]
        _c, g, ov = lab.candidate_body(cands[0]["id"])
        out["run_candidate"] = lab.design(g, ov).spec
        out["run_candidate_id"] = cands[0]["id"]
    finally:
        lab.close()
    return out


def main() -> None:
    import time

    from calflab.plugins import load_plugins

    load_plugins()
    project = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "projects" / "robot-calf-final"
    res: dict[str, Any] = {"written": time.strftime("%Y-%m-%d %H:%M"), "candidate_run": CANDIDATE_RUN,
                           "design": DESIGN}
    for name, spec in builds(project).items():
        res[name] = spec if isinstance(spec, str) else fingerprint(spec)
    OUT.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
