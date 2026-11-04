# Session R step 3: the vigour preset, two bodies, and what a run costs (ADR-090)

2026-11-04. `vigour_r3.py` on a scratch copy of `robot-calf-final` (7 local workers). The fitness formula was
corrected after this run (shortfall below 0, not below 0.2). The fitness column is recomputed from the
recorded vigour and margin; the searches and plays themselves do not depend on it.

## The preset (`config/fitness/vigour.yaml`)

A body plays five motions, each searched for that body (CMA-ES 4 x 2 + the starting setting, seed 0, cached),
then the best settings within the limits are checked on three seeds with friction 0.7-1.1 and mass x0.95-1.05:

| motion | primitive | starts from | kept = |
|---|---|---|---|
| walk | walk | defaults | speed / 32.8 mm/s (default walk on today's body) |
| trot | trot | defaults | speed / 186.1 mm/s (default trot on today's body) |
| stand | weight_shift | the interpretation's setting | calf features matched (exp(-d^2), weighted) |
| step | step | the interpretation's setting | the same |
| other (fast play) | trot | the interpretation's setting | the same |

Margin = headroom over every limit lowered by 0.2 (0 = exactly at margin 0.2). Fitness = mean kept - how far
the worst motion's margin is below 0 (at most 1). Archive axes: vigour kept x worst margin.

## Two bodies

| body | vigour kept | worst margin | fitness | motions within limits on 3 seeds | plays | wall |
|---|---|---|---|---|---|---|
| today (splay 12 / 10.5, narrow blocks) | 0.315 | -0.44 (trot) | -0.125 | stand, step, fast play | 54 | 64 s |
| E: half splay, blocks +60 / +52 mm, hip springs, springs holding the weight | 0.517 | -0.28 (trot) | +0.237 | walk, stand, step, fast play | 59 | 84 s |

Per motion (kept, margin of the worst seed or of the best search play):

| motion | today | E |
|---|---|---|
| walk | 0 (no setting within: -0.14, torque, speed, envelope) | **0.75** (+0.10; cycle 3.1 s, stride 1.09, sway 0.08) |
| trot | 0 (-0.44, torque) | 0 (-0.28, torque, speed, envelope) |
| stand | 0.87 (+0.84) | 0.86 (+0.85) |
| step | 0.34 (+0.16) | **0.59** (+0.28) |
| fast play (trot) | 0.36 (+0.71) | 0.39 (+0.73) |

With the wide blocks, the walk keeps three quarters of its speed within every limit on three seeds. The trot is
still over sustained torque on both bodies at this small budget. The fast play keeps about 0.4 of the calf's
features on both.

## Cost (Estimate cost, the upper bound: every search play uncached, every verification run to the end)

| budget (generations x batch, inner iterations x popsize) | plays max | CPU | wall, 7 workers |
|---|---|---|---|
| 3 x 8, 2 x 4 | 2 160 | 0.8 h | 0.2 h |
| 6 x 8, 2 x 4 | 4 320 | 1.1 h | 0.3 h |
| 10 x 16, 2 x 4 | 14 400 | 3.7 h | 0.7 h |
| 6 x 8, 4 x 6 | 8 160 | 2.1 h | 0.5 h |

Measured: a body took 54-59 plays (bound 90) and 64-84 s of one core. So 6 x 8 at 2 x 4 is about 6 rounds x
2 bodies per worker x 80 s = 16 min, matching the estimate.

## Raw output

```
today: fitness (as run) -0.325, vigour 0.315, worst margin -0.44, feasible 3/5; plays 54, 64 s
   walk   kept 0.00 margin -0.14 searched 9 within 0  viol servo_sustained, joint_speed, envelope
   trot   kept 0.00 margin -0.44 searched 9 within 0  viol servo_sustained
   stand  kept 0.87 margin +0.84 searched 9 within 8 verified 1
   step   kept 0.34 margin +0.16 searched 9 within 4 verified 1
   other  kept 0.36 margin +0.71 searched 9 within 1 verified 1
E: fitness (as run) 0.037, vigour 0.517, worst margin -0.28, feasible 4/5; plays 59, 84 s
   walk   kept 0.75 margin +0.10 searched 9 within 1 verified 1  cycle_s 3.13 stride 1.09 lift 0.50 sway 0.08
   trot   kept 0.00 margin -0.28 searched 9 within 0  viol servo_sustained, joint_speed, envelope
   stand  kept 0.86 margin +0.85 searched 9 within 8 verified 1
   step   kept 0.59 margin +0.28 searched 9 within 3 verified 2
   other  kept 0.39 margin +0.73 searched 9 within 3 verified 1
```
