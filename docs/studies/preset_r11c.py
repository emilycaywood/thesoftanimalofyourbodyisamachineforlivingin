"""Write config/fitness/hardware_r11c.yaml from hardware.yaml (session R11c, ADR-103): the R11 judging unchanged, the
R11c space (production block), a servo budget of six STS3250 C002, the cost index's servo term over a fixed 4, spring
sites in the cost, and the Stage A seed bodies (geometry fixed).

Run:  python docs/studies/preset_r11c.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

NEW = "sts3250_c002"
R10_BELTS = {"belt_stifle_pulleys": "40T-80T", "belt_stifle_length": "GT2-2mm-444-C",
             "belt_hock_pulleys": "40T-80T", "belt_hock_length": "GT2-2mm-400-C"}
BODIES = [
    ("R10 1:1 45T", "new hocks + carpi; carpus 45T/45T (now listed: GT2-45T-10) 640; stifle and hock 40T/80T",
     {"servo_hock": NEW, "servo_carpus": NEW, "belt_carpus_pulleys": "GT2-45T-10+GT2-45T-10",
      "belt_carpus_length": "GT2-2mm-640-C", **R10_BELTS}),
    ("R10 40T/80T", "new hocks + carpi; carpus, stifle and hock 40T/80T",
     {"servo_hock": NEW, "servo_carpus": NEW, "belt_carpus_pulleys": "40T-80T", "belt_carpus_length": "GT2-2mm-640-C",
      **R10_BELTS}),
    ("hips+hocks+carpi C002", "six new: hip ab/ad, hocks, carpi; belts as R10 40T/80T",
     {"servo_hip_abd": NEW, "servo_hock": NEW, "servo_carpus": NEW, "belt_carpus_pulleys": "40T-80T",
      "belt_carpus_length": "GT2-2mm-640-C", **R10_BELTS}),
    ("hocks+carpi+shoulders C002", "six new: hocks, carpi, shoulders; belts as R10 40T/80T",
     {"servo_hock": NEW, "servo_carpus": NEW, "servo_shoulder": NEW, "belt_carpus_pulleys": "40T-80T",
      "belt_carpus_length": "GT2-2mm-640-C", **R10_BELTS}),
]


def main() -> None:
    src = Path("config/fitness/hardware.yaml")
    d = yaml.safe_load(src.read_text(encoding="utf-8"))
    d["name"] = "hardware_r11c"
    d["version"] = 1
    d["description"] = ("R11c (ADR-103): R11's judging (ADR-102) over a bounded production space: segment lengths "
                        "+-10% on 2 mm steps with ratios +-5%, driver and driven pulleys chosen separately from listed "
                        "pulleys, belt lengths feasible by construction, springs and the shoulder drive as genes, at "
                        "most six STS3250 C002. Fitness within a cell = headroom minus 0.1 x a hardware cost index.")
    hw = d["evaluation"]["hardware"]
    hw["servo_budget"] = {NEW: 6}
    hw["servo_denominator"] = 4
    hw["drives"] = ["stifle", "hock", "carpus", "shoulder"]
    hw["cost_weights"] = {"servos": 1.0, "pulley_sizes": 0.25, "what_if": 0.5, "mass_kg": 1.0, "spring_sites": 0.25}
    hw["production"] = {
        "geometry": {"genes": ["femur_length", "tibia_length", "rear_cannon_length", "upper_leg_length",
                               "front_cannon_length"], "rel": 0.10, "step_mm": 2.0,
                     "ratios": [["tibia_length", "femur_length"], ["rear_cannon_length", "tibia_length"],
                                ["front_cannon_length", "upper_leg_length"]], "ratio_tolerance": 0.05},
        "springs": {"sites": ["hip_abd", "stifle", "hock", "shoulder", "carpus"], "switch": True,
                    "k_factors": [0.5, 0.75, 1.0, 1.5, 2.0], "preload_factors": [0.5, 1.0, 1.5],
                    "along_steps_mm": [-15.0, 0.0, 15.0], "normal_steps_mm": [-10.0, 0.0, 10.0],
                    "clearance_mm": 3.0, "sweep_step_deg": 5.0, "fitting_mm": 28.0, "lever_mm": 30.0},
        "pulleys": "singles", "feasible_lengths": True, "shoulder_drive": True, "stop_rejected_fraction": 0.5,
    }
    seeds = []
    for label, note, vals in [("today's body", "the working body", {})] + BODIES:
        if vals:
            seeds.append({"label": label, "note": note, "values": dict(vals)})
        seeds.append({"label": f"{label} + carpus spring", "note": note + "; carpus springs on (gene defaults)",
                      "values": {**vals, "spring_carpus": True}})
        seeds.append({"label": f"{label} + belted shoulder", "note": note + "; shoulder belted (gene defaults: "
                      "30T/60T, 394 mm)", "values": {**vals, "shoulder_belt": True}})
    hw["seeds_bodies"] = seeds
    head = ("# Fitness preset R11c (ADR-103): written by docs/studies/preset_r11c.py from hardware.yaml. Use with the\n"
            "# optimizer map_elites_hardware. Bump `version` whenever you change it.\n")
    Path("config/fitness/hardware_r11c.yaml").write_bytes(
        (head + yaml.safe_dump(d, sort_keys=False, width=118, allow_unicode=True)).encode("utf-8"))
    print(len(seeds), "seed bodies")


if __name__ == "__main__":
    main()
