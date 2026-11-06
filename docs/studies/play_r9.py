"""Session R9 (ADR-100): store primitive plays on what-if bodies as runs of kind ``sim`` so they replay in the lab
and can be compared side by side (``compare.html?a=<run>&b=<run>``).

Each play is judged as in ``servos_r9.py`` (margin 0.2, the diversity preset's randomisation, the given seed) and
recorded with its verdict. The stored scene is the what-if spec's; the stored genome builds the working body.

Run:  python docs/studies/play_r9.py <project dir> <seed> "<case>=<primitive>:<k:v,k:v>=<label>" ...
e.g.  python docs/studies/play_r9.py projects/robot-calf-final 0 "now=trot:cycle_s:1.2,stride:1.0,lift:0.6=today, fastest trot"
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> None:
    import calflab.behave.physics as phys
    import numpy as np
    from calflab.app.lab import Lab
    from calflab.app.scene import build_scene
    from calflab.behave.interpret import InterpretSettings, judge, play_primitive
    from calflab.behave.study import randomization
    from calflab.plugins import load_plugins, registry
    from calflab.project.registry import RunRecord
    from servos_r9 import MARGIN, lib_at, parse_case, what_if

    load_plugins()
    proj, seed = Path(sys.argv[1]), int(sys.argv[2])
    strip = phys.compile_params
    rand = randomization(True, (0.7, 1.1), (0.95, 1.05))
    phys.compile_params = lambda d: {**strip(d), "randomization": rand}  # type: ignore[assignment]
    lab = Lab.open(proj, create=False)
    g = lab.state.graph
    design = lab.design()
    generator = g.role("design").type.split(":", 1)[1]
    gen_params = lab.job_generator_params(g)
    overrides = [o for o in lab.state.overrides if o.enabled]
    doc = dict(g.role("model").params)
    for item in sys.argv[3:]:
        case_name, rest = item.split("=", 1)
        prim_part, label = rest.rsplit("=", 1)
        key, _, prm = prim_part.partition(":")
        case = parse_case(case_name)
        lib = lib_at(case.get("volt"))
        spec = what_if(design, overrides, generator, gen_params, case, lib)
        given = {k: float(v) for k, v in (kv.split(":") for kv in prm.split(",") if kv)} if prm else {}
        prim = registry.get("motion_primitive", key)(given)  # type: ignore[call-arg]
        t = time.perf_counter()
        ro, t0, t1, (ckey, cparams) = play_primitive(prim, spec, lib, doc, InterpretSettings(margin=MARGIN, seed=seed))
        j = judge(ro, spec, lib, MARGIN)
        trunk = ro.body_ids.index(spec.root.id) if spec.root.id in ro.body_ids else 0
        mm = (ro.t >= t0) & (ro.t < t1)
        dist = float(np.linalg.norm(ro.body_pos[mm, trunk, :2][-1] - ro.body_pos[mm, trunk, :2][0])) * 1000.0
        speed = dist / max(1e-6, float(ro.t[mm][-1] - ro.t[mm][0]))
        sim_id = lab.registry.new_run_id("sim")
        rdir = lab.registry.run_dir(sim_id)
        rdir.mkdir(parents=True, exist_ok=True)
        ro.save(rdir / "rollout.npz")
        scene = build_scene(dataclasses.replace(design, spec=spec), lab.state.layers, lab.state.settings)
        (rdir / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
        title = f"R9 play: {label} ({case_name}; {key} {prm or ''}), seed {seed}"
        lab.registry.save_run(RunRecord(
            id=sim_id, kind="sim", title=title, duration_s=time.perf_counter() - t, seed=seed, backend="local",
            inputs={"what_if": {"case": case_name, **case, "note": "in-memory spec change; the genome and overrides "
                                "stored here build the working body, not this one (ADR-100)"},
                    "primitive": {"key": key, "params": prim.params.model_dump(mode="json")}, "margin": MARGIN,
                    "judged": j, "speed_mm_s": round(speed, 1)},
            genome=dict(design.genome.model_dump(mode="json")), overrides=[o.model_dump(mode="json") for o in overrides],
            controller={"key": ckey, "params": cparams},
            metrics={"within_limits": j["within_limits"], "safety_margin": j["margin"], "fell": j["fell"],
                     "speed_mm_s": round(speed, 1)},
            artifacts={"rollout": f"runs/{sim_id}/rollout.npz", "scene": f"runs/{sim_id}/scene.json"},
            tags=["R9", "what-if", "play"]))
        print(f"{sim_id}  {label}: within {j['within_limits']} margin {j['margin']:+.2f} {speed:.0f} mm/s", flush=True)
    lab.close()


if __name__ == "__main__":
    main()
