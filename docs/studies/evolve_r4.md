# Session R step 4: evolving the body with the vigour preset (ADR-091)

2026-11-04. Run `20261104-162051-evolve-d1b6` in `projects/robot-calf-final` (script `evolve_r4.py`, archive
read by `archive_r4.py`).

Settings:
* **Budget** (the researcher's): MAP-Elites 6 generations x 8 bodies, per-motion search 2 x 4.
* **Archive:** vigour_kept (10 cells) x worst_margin (8 cells), every evolvable gene, seed 0.
* **Starting body:** the project's (splay 12 / 10.5 deg, narrow blocks), with the hip ab/ad springs switched on
  (0.2 N/mm, free to go to 0) through `set_genes` (undoable).
* **Fitness node:** set to `vigour` with `set_node_params`.
* **Reference speeds**, measured on the starting body: walk 32.3 mm/s, trot 186.9 mm/s.
* **Interpretation:** `20261104-042426-interpret-ef3c`.
* Belts and joint ranges unchanged in every candidate.

**Wall clock 818 s** (estimate 1750 s, an upper bound), 7 workers.

## Candidates

| status | count |
|---|---|
| evaluated, new cell | 12 |
| evaluated, improved a cell | 6 |
| evaluated, not kept (a better body in its cell) | 17 |
| **infeasible** (not simulated) | **13** |

Why infeasible:
* 11: **the front legs are too short to reach the ground with the back level.** A longer rear leg (femur, tibia,
  a more upright cannon) or less hind splay raises the hips beyond what the front legs can reach.
* 2: **the hock belt fails its clearance check**: the hock servo would hit the stifle pulley and belt within the
  stifle's range.

No candidate failed to run, and none was rejected as unsafe.

## The best bodies

| body | fitness | vigour kept | worst margin | within limits on 3 seeds | hind / front hooves from centre (mm) |
|---|---|---|---|---|---|
| g005-000 (best) | +0.228 | 0.360 | -0.13 (walk) | trot, stand, step, fast play | 173 / 184 |
| g004-001 | +0.166 | 0.355 | -0.19 (walk) | trot, stand, step, fast play | 174 / 247 |
| g000-000 (the starting body) | +0.136 | 0.276 | -0.14 (walk) | trot, stand, fast play | 203 / 185 |
| g002-004 | +0.126 | 0.260 | -0.13 (walk) | trot, stand, step | 218 / 157 |

Per motion, kept / margin:

| body | walk | trot | stand | step | fast play |
|---|---|---|---|---|---|
| g005-000 | 0 / -0.13 | 0.24 / +0.69 | 0.85 / +0.77 | 0.27 / +0.16 | 0.44 / +0.16 |
| g004-001 | 0 / -0.19 | 0.29 / +0.12 | 0.84 / +0.75 | 0.28 / +0.08 | 0.36 / +0.16 |
| start | 0 / -0.14 | 0.14 / +0.36 | 0.87 / +0.84 | 0 / -0.04 | 0.37 / +0.71 |

What changed in the best body (g005-000), from the start:
* **Geometry:** axle spacing 550 -> 590 mm; femur 200 -> 183 mm; tibia 245 -> 266 mm; rear cannon 10 -> 3 deg
  (more upright); front cannon 245 -> 260 mm.
* **Width:** hind splay 12 -> 8.4 deg; hip block +12 mm per side.
* **Springs:** stifle 0.40 -> 0.19 N/mm; hock 0.20 -> 0.51 N/mm, but its free length went from 40 to 63 mm, so
  there is little more force at standing; **hip ab/ad 0.2 -> 0 and shoulder 0.2 -> 0**, which switches them off
  in effect.

g004-001 shows the same pattern: shoulder and hip ab/ad springs at 0, stifle softened, hind splay 8.9.
* Shoulder springs at 0 match step 2, where they gave 365 % of what the weight needs.
* The hip ab/ad springs went to 0 because a spring sized for standing does not help the walk on splayed legs
  (`width_r2c.md`, body F).

## Across the archive

* **No body is within every limit on every motion.** No body keeps the walk within limits on 3 seeds. The trot
  is within limits in 7 bodies (in step 3 it was within limits in neither body tested), the step in 9, the fast
  play in 9, the stand in 24.
* The walk's violations across bodies: joint speed 34, envelope 23, sustained torque 17, sustained belt 14,
  stall 6, belt peak 3, fall 1.
* **The search stayed near the starting body.** Hip block widening reached at most 18 mm per side, chest
  39 mm; `width_r2c.md` needed about 60-120 mm. Splay moved more (hind 2-22 deg).
* So **this archive's best (vigour 0.36) is below body E from step 3**. That body has blocks widened +60 / +52 mm,
  half splay and springs that just hold the weight. It reached vigour 0.517 and fitness +0.237 under the
  corrected formula, and its walk keeps 0.75 within limits on 3 seeds. At 6 x 8, with an initial spread of 0.15
  of each gene's range, MAP-Elites explores only near the starting body.

## History

| generation | best fitness | best of generation | coverage | elites | infeasible |
|---|---|---|---|---|---|
| 0 | 0.136 | 0.136 | 2.5 % | 2 | 4 |
| 1 | 0.136 | -0.089 | 6.3 % | 5 | 3 |
| 2 | 0.136 | 0.126 | 7.5 % | 6 | 1 |
| 3 | 0.136 | -0.082 | 11.3 % | 9 | 1 |
| 4 | 0.166 | 0.166 | 15.0 % | 12 | 3 |
| 5 | 0.228 | 0.228 | 15.0 % | 12 | 1 |
