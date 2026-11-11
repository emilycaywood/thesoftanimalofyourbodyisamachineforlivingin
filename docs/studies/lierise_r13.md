# R13: lying down and rising, diagnosed and evolved per body (ADR-107)

Project `projects/robot-calf-final`. Bodies of the R12 compare set, built as Stage C judged them (each Stage C run's
genome and overrides, the Stage B run's generator params and compile options). Judged with the R11c suite: seeds 0-2,
friction 0.7-1.1, mass x0.95-1.05, torque-speed servos, derating 1, **margin 0.2** (a margin here is headroom over limits
already lowered by 20 %; 0 = exactly at the margin). The working body, catalogs, component values and `verified` flags
were not changed. Script: `docs/studies/lierise_r13.py` (`diagnose`, `optimise`, `report`, `estimate`, `preset`,
`stage3`); data: `lierise_r13_diag.json`, `lierise_r13.json`.

## What the earlier numbers measured

Stage B and Stage C reported lie_rise from the hardware screen (`hardware.play_primitive_seed`). Two things made those
numbers something other than "lying down and rising":

1. **The play stops at 10 s.** The screen plays a primitive for at most `InterpretSettings.max_play_s` = 10 s; today's
   lie_rise lasts 11.5 s (five moves of 2 s and a 1.5 s hold), so the front rise was judged for its first 0.8 s.
2. **Lying down was counted as a fall on g020-008-r01 and g012-009.** The simulator calls a fall when the trunk is
   under 45 % of its standing height. These two bodies lie at 268-270 mm against a threshold of about 268 mm (they
   stand 596 mm tall); the play stopped 0.3 s after they lay down (t = 3.9 s), so only kneeling and lying down were
   judged. **Their -0.16 and -0.24 were the kneel's front-shoulder torque**, not the whole motion. Both bodies in fact
   lie down and stand up again upright on every seed. The working body (lying at 282 mm of 607) and g009-000 (275) were
   judged to 10.3 s and read -3.00, which is what every body reads over the whole motion.

So "lie_rise comes near only with C002 shoulders driven directly" (ADR-104) was an artifact of where the play was cut,
not of the shoulders. Here every play is judged over the whole motion plus 1 s of standing after it, and a fall is the
trunk tipping (up axis z < 0.4) or not standing again at the end; lying low is not a fall. The hardware screen itself
was not changed (it would change every stored Stage B / Stage C score).

## Stage 1: today's lie_rise, move by move

Per move, the joint and limit with the largest use on each seed (margin = 1 - use; sustained limits are counted in the
move that holds the middle of their 2 s window; -3.00 = above the lowered rated torque for the whole window).
Summary:

* **Every body is at -3.00 on every seed** over the whole motion.
* **Kneeling and lying down:** the front shoulders bind (sustained servo torque). Close on the bodies with C002
  shoulders (g020-008-r01 -0.12 to -0.24, g012-009 -0.16 to -0.24), far on the C018-shoulder bodies (working -1.8 to
  -2.2, g009-000 -2.0 to -2.3).
* **Lying (the hold) and rising behind:** the hind stifle binds on every body (servo torque, and on the belted stifles
  the belt's sustained tension, -1.6 to -3.0): lying on the folded hind legs at stifle and hock 75 deg loads them.
* **The reach:** front carpi (g020, g012) or front shoulders (working, g009), -1.5 to -2.2.
* **The front rise and the standing after it:** -3.00 everywhere; after the rise the hooves stand elsewhere than they
  started, and the front shoulders hold that stance.

### Stage 1 tables

| body | screen (cut at 10 s), seeds 0/1/2 | whole motion + 1 s, seeds 0/1/2 | binds (whole) |
|---|---|---|---|
| g020-008-r01 | -0.16 / -0.32 / -0.12 | -3.00 / -3.00 / -3.00 | servo_sustained |
| g012-009 | -0.24 / -0.24 / -0.16 | -3.00 / -3.00 / -3.00 | servo_sustained |
| g009-000 | -3.00 / -3.00 / -3.00 | -3.00 / -3.00 / -3.00 | servo_sustained |
| working | -3.00 / -3.00 / -3.00 | -3.00 / -3.00 / -3.00 | servo_sustained |

#### g020-008-r01

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.0 | fl.shoulder sustained torque -0.16 | fl.shoulder sustained torque -0.24 | fl.shoulder sustained torque -0.12 |
| lie | 2.0-4.0 | hl.stifle sustained belt -1.76 | hl.stifle sustained belt -1.80 | hl.stifle sustained belt -1.80 |
| hold | 4.0-5.5 | hl.stifle sustained torque -3.00 | hl.stifle sustained torque -3.00 | hl.stifle sustained torque -3.00 |
| rise hind | 5.5-7.5 | hl.stifle sustained belt -2.12 | hl.stifle sustained belt -2.40 | hl.stifle sustained belt -2.12 |
| reach | 7.5-9.5 | fl.carpus sustained torque -1.52 | hl.stifle sustained belt -1.57 | fl.carpus sustained torque -1.48 |
| rise front | 9.5-11.5 | hl.stifle sustained belt -3.00 | hl.stifle sustained torque -3.00 | fl.shoulder sustained torque -3.00 |
| standing after | 11.5-12.5 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 |

#### g012-009

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.0 | fl.shoulder sustained torque -0.24 | fl.shoulder sustained torque -0.24 | fl.shoulder sustained torque -0.16 |
| lie | 2.0-4.0 | hl.stifle sustained belt -1.76 | hl.stifle sustained belt -1.84 | hl.stifle sustained belt -1.84 |
| hold | 4.0-5.5 | hl.stifle sustained torque -3.00 | hl.stifle sustained torque -3.00 | hl.stifle sustained torque -3.00 |
| rise hind | 5.5-7.5 | hl.stifle sustained belt -2.32 | hl.stifle sustained belt -2.68 | hl.stifle sustained belt -2.24 |
| reach | 7.5-9.5 | fl.carpus sustained torque -1.64 | fl.carpus sustained torque -1.68 | fl.carpus sustained torque -1.60 |
| rise front | 9.5-11.5 | hl.stifle sustained belt -3.00 | hl.stifle sustained torque -3.00 | fl.shoulder sustained torque -3.00 |
| standing after | 11.5-12.5 | fl.shoulder sustained torque -3.00 | hl.stifle sustained belt -3.00 | fl.shoulder sustained torque -3.00 |

#### g009-000

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.0 | fl.shoulder sustained torque -2.25 | fl.shoulder sustained torque -2.33 | fl.shoulder sustained torque -2.00 |
| lie | 2.0-4.0 | fl.shoulder sustained torque -2.24 | fl.shoulder sustained torque -2.28 | fl.shoulder sustained torque -1.60 |
| hold | 4.0-5.5 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 |
| rise hind | 5.5-7.5 | fl.shoulder sustained torque -2.44 | fl.shoulder sustained torque -2.84 | fl.shoulder sustained torque -2.36 |
| reach | 7.5-9.5 | fl.shoulder sustained torque -2.08 | fl.shoulder sustained torque -2.16 | fl.shoulder sustained torque -2.16 |
| rise front | 9.5-11.5 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 |
| standing after | 11.5-12.5 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 | fl.shoulder sustained torque -3.00 |

#### working

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.0 | fl.shoulder sustained torque -1.96 | fl.shoulder sustained torque -2.21 | fl.shoulder sustained torque -1.76 |
| lie | 2.0-4.0 | fl.shoulder sustained torque -1.92 | fl.shoulder sustained torque -2.16 | hl.stifle sustained belt -1.64 |
| hold | 4.0-5.5 | hl.stifle sustained belt -3.00 | hl.stifle sustained belt -3.00 | hl.stifle sustained belt -3.00 |
| rise hind | 5.5-7.5 | fl.shoulder sustained torque -2.24 | fl.shoulder sustained torque -2.52 | fl.shoulder sustained torque -2.20 |
| reach | 7.5-9.5 | fl.shoulder sustained torque -1.97 | fl.shoulder sustained torque -2.01 | fl.shoulder sustained torque -1.93 |
| rise front | 9.5-11.5 | hl.stifle sustained belt -3.00 | hl.stifle sustained belt -3.00 | fl.shoulder sustained torque -3.00 |
| standing after | 11.5-12.5 | fl.shoulder sustained torque -3.00 | hl.stifle sustained belt -3.00 | fl.shoulder sustained torque -3.00 |

## Stage 2: the movement evolves per body

The lie_rise primitive's vector dims are now (ADR-107): kneel shoulder and carpus angles, reach shoulder and carpus
angles (inside the joint ranges less 2 deg), a time per move (kneel, lie, rise hind, reach, rise front; 0.8-6 s), the
hold, the order of rising (hind first, or front first: reach and push up from lying, sit on the folded hind legs, then
rise behind), a rock back before the front rise (hind stifles and hocks fold up to 20 deg further, held through the
reach), and pauses with the load on the hooves (after the first rise; after the reach). Today's motion is the default,
bit for bit. CMA-ES per body (popsize 12, 30 generations, sigma 0.25, seed 0) on the worst-seed margin over the three
seeds, today's motion first.

**A correction during the session.** The first Stage 2 run (commit a51e5eb) ranked a fall at a cost of 1 against
margins saturated at -3, so on the working body, g009-000 and g011-003 its "best" version somersaulted forward and
ended on its back with low loads (reported -0.28 / -0.48 / -0.88; not valid). Now a version that stands up again on
every seed always ranks above one that falls, the fall penalty is 10, and the trunk must get down to **0.5 of its
standing height** (today's lie reaches 0.45-0.47; graded penalty above it). The same check caught a version of the
lying-pose extension that "held" at +0.13 on g020-008-r01 by crouching (trunk at 0.59 of standing) instead of lying.
Both superseded results are kept in `lierise_r13.json` (`bodies_v1_superseded`, `bodies_lying_free`), labelled. The
18 compare plays of the first run are still in the registry (titles `R12 compare <body> lie_rise (evolved): seed N`,
run ids `20261110-192253-sim-502e` to `20261110-192352-sim-bbd3`); the page no longer uses them.

**Result: no body holds.** Every body's best version lies down to 0.45-0.46 of its standing height and stands up again
on all three seeds, from -3.00 to between -0.25 (g007-002) and -1.40 (g020-008-r01). The evolved versions are stored
as compare plays and play on `compare.html?set=r12` as **lie_rise (evolved)**; the stored runs reproduce these margins
on every seed.

What binds after the search:

* **g007-002** (-0.25, closest; C002 shoulders and hocks): the hind stifle's torque-speed envelope (C018 stifle) while
  rising behind; several other limits sit just over or at the margin: the hind hock belt in the hold (-0.08 to
  +0.04), the front carpi's speed in the kneel (-0.05) and envelope in the front rise (-0.07).
* **g012-009, g020-008-r01** (C002 shoulders, direct): the **hind hock belt's sustained tension** while lying and
  rising behind (-0.84 to -1.16), and the front carpi in the front rise on g020-008-r01 (-1.20 to -1.40).
* **working, g009-000, g011-003** (C018 shoulders): the **front shoulders' sustained torque** while kneeling, lying
  and rising behind (-0.56 to -1.36).

Since the bodies are unchanged, their Stage C behaviours and trot are unchanged.

### Stage 2 tables

| body | today (whole) worst | best worst-seed | holds 3/3 | stands up again | lowest trunk (share of standing) | plays (new) | wall min | best version |
|---|---|---|---|---|---|---|---|---|
| g020-008-r01 | -3.000 | -1.400 | no | yes | 269 mm (0.45) / 268 mm (0.45) / 269 mm (0.45) | 1057 (1057) | 16 | hind first; kneel -18/123, reach -46/108; moves 2.5/1.4/0.9/2.3/4.1 s; hold 0.0; rock 0 deg/1.3 s; pauses 1.7/0.5 s |
| g012-009 | -3.000 | -0.960 | no | yes | 271 mm (0.45) / 271 mm (0.45) / 271 mm (0.45) | 1003 (1003) | 19 | hind first; kneel -14/111, reach -38/109; moves 1.5/0.9/0.8/2.0/1.1 s; hold 0.0; rock 15 deg/0.4 s; pauses 1.4/1.2 s |
| g009-000 | -3.000 | -1.360 | no | yes | 273 mm (0.46) / 272 mm (0.45) / 273 mm (0.46) | 1007 (1007) | 24 | hind first; kneel -31/90, reach -42/104; moves 2.9/2.3/2.7/1.2/3.9 s; hold 0.0; rock 2 deg/0.4 s; pauses 1.8/0.4 s |
| working | -3.000 | -1.200 | no | yes | 277 mm (0.46) / 277 mm (0.46) / 278 mm (0.46) | 955 (955) | 15 | hind first; kneel -39/126, reach -44/110; moves 1.6/1.0/0.8/0.9/2.5 s; hold 0.1; rock 9 deg/0.8 s; pauses 0.0/0.0 s |
| g007-002 | -3.000 | -0.251 | no | yes | 282 mm (0.46) / 282 mm (0.46) / 282 mm (0.46) | 1019 (1019) | 18 | hind first; kneel -21/125, reach -43/110; moves 1.8/2.8/0.9/2.7/2.0 s; hold 1.0; rock 8 deg/0.3 s; pauses 1.4/0.0 s |
| g011-003 | -3.000 | -1.320 | no | yes | 271 mm (0.45) / 271 mm (0.45) / 271 mm (0.45) | 1033 (1033) | 13 | hind first; kneel -27/85, reach -58/110; moves 1.7/1.5/0.8/1.3/0.8 s; hold 0.0; rock 4 deg/1.1 s; pauses 0.5/0.2 s |

#### g020-008-r01: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.5 | fl.shoulder sustained torque -0.36 | fl.shoulder sustained torque -0.40 | fl.shoulder sustained torque -0.28 |
| lie | 2.5-3.9 | hl.hock sustained belt -1.16 | hl.hock sustained belt -1.16 | hl.hock sustained belt -1.04 |
| hold | 3.9-3.9 | hl.hock sustained belt -1.12 | hl.hock sustained belt -1.16 | hl.hock sustained belt -1.04 |
| rise hind | 3.9-4.7 | hl.hock sustained belt -1.08 | hl.hock sustained belt -1.12 | hl.hock sustained belt -1.04 |
| pause | 4.7-6.4 | hl.stifle sustained belt -0.19 | hl.stifle sustained belt -0.31 | hl.stifle sustained belt -0.19 |
| rock back | 6.4-7.7 | hl.stifle envelope +0.90 | hl.stifle envelope +0.89 | hl.stifle envelope +0.90 |
| reach | 7.7-10.0 | fl.shoulder envelope +0.81 | fl.shoulder envelope +0.81 | fl.shoulder envelope +0.83 |
| pause on hooves | 10.0-10.6 | fl.shoulder sustained torque +0.20 | fl.shoulder sustained torque +0.12 | fl.shoulder sustained torque +0.20 |
| rise front | 10.6-14.7 | fl.carpus sustained torque -1.20 | fl.carpus sustained torque -1.40 | fl.carpus sustained torque -1.24 |
| standing after | 14.7-15.7 | fl.carpus envelope +0.94 | fl.carpus envelope +0.94 | fl.carpus envelope +0.94 |

#### g012-009: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.5 | fl.shoulder sustained torque -0.12 | hl.stifle sustained belt -0.19 | hl.stifle sustained belt -0.07 |
| lie | 1.5-2.4 | hl.hock sustained belt -0.88 | hl.hock sustained belt -0.96 | hl.hock sustained belt -0.84 |
| hold | 2.4-2.5 | hl.hock sustained belt -0.88 | hl.hock sustained belt -0.96 | hl.hock sustained belt -0.84 |
| rise hind | 2.5-3.3 | hl.hock sustained belt -0.88 | hl.hock sustained belt -0.96 | hl.hock sustained belt -0.84 |
| pause | 3.3-4.7 | hl.stifle sustained belt -0.47 | hl.stifle sustained belt -0.51 | hl.stifle sustained belt -0.43 |
| rock back | 4.7-5.1 | hl.stifle envelope +0.59 | hl.stifle envelope +0.59 | hl.stifle envelope +0.58 |
| reach | 5.1-7.0 | fl.shoulder envelope +0.81 | fl.shoulder envelope +0.81 | fl.shoulder envelope +0.83 |
| pause on hooves | 7.0-8.2 | fl.shoulder sustained torque -0.44 | fl.shoulder sustained torque -0.48 | fl.shoulder sustained torque -0.48 |
| rise front | 8.2-9.3 | fl.shoulder sustained torque -0.64 | fl.shoulder sustained torque -0.80 | fl.shoulder sustained torque -0.72 |
| standing after | 9.3-10.3 | fl.shoulder sustained torque -0.64 | fl.shoulder sustained torque -0.80 | fl.shoulder sustained torque -0.72 |

#### g009-000: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.9 | fl.carpus sustained belt -0.48 | fl.carpus sustained belt -0.56 | fl.carpus sustained belt -0.48 |
| lie | 2.9-5.2 | fl.shoulder sustained torque -1.12 | fl.shoulder sustained torque -1.24 | fl.shoulder sustained torque -1.12 |
| hold | 5.2-5.2 | - | - | - |
| rise hind | 5.2-7.9 | fl.shoulder sustained torque -1.24 | fl.shoulder sustained torque -1.36 | fl.shoulder sustained torque -1.20 |
| pause | 7.9-9.7 | fl.shoulder sustained torque -0.03 | hl.stifle sustained belt -0.74 | fl.shoulder sustained torque +0.01 |
| rock back | 9.7-10.1 | hl.stifle envelope +0.90 | hl.stifle envelope +0.89 | hl.stifle envelope +0.90 |
| reach | 10.1-11.3 | fl.shoulder sustained torque +0.76 | fl.shoulder sustained torque +0.72 | fl.shoulder sustained torque +0.76 |
| pause on hooves | 11.3-11.7 | fl.carpus sustained belt +0.40 | fl.carpus sustained belt +0.40 | fl.carpus sustained belt +0.40 |
| rise front | 11.7-15.6 | fl.carpus sustained belt -0.60 | fl.carpus sustained belt -0.80 | fl.carpus sustained belt -0.64 |
| standing after | 15.6-16.6 | hl.hip_abd envelope +0.96 | hl.hip_abd envelope +0.96 | hl.hip_abd envelope +0.96 |

#### working: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.6 | fl.shoulder sustained torque -0.56 | fl.shoulder sustained torque -0.60 | fl.shoulder sustained torque -0.16 |
| lie | 1.6-2.6 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.76 | fl.shoulder sustained torque -0.56 |
| hold | 2.6-2.7 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.76 | fl.shoulder sustained torque -0.68 |
| rise hind | 2.7-3.5 | fl.shoulder sustained torque -1.04 | fl.shoulder sustained torque -1.20 | fl.shoulder sustained torque -0.88 |
| pause | 3.5-3.6 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.84 | fl.shoulder sustained torque -0.52 |
| rock back | 3.6-4.4 | fl.shoulder sustained torque -0.64 | fl.shoulder sustained torque -0.80 | fl.shoulder sustained torque -0.48 |
| reach | 4.4-5.2 | fl.carpus sustained belt -0.04 | fl.shoulder sustained torque -0.04 | fl.carpus sustained belt -0.04 |
| pause on hooves | 5.2-5.3 | fl.carpus sustained belt -0.08 | fl.carpus sustained belt -0.08 | fl.carpus sustained belt -0.08 |
| rise front | 5.3-7.8 | fl.carpus sustained belt -0.40 | fl.carpus sustained belt -0.48 | fl.carpus sustained belt -0.40 |
| standing after | 7.8-8.8 | hl.hip_abd envelope +0.93 | hl.hip_abd envelope +0.93 | hl.hip_abd envelope +0.93 |

#### g007-002: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.8 | fl.carpus joint speed -0.04 | fl.carpus joint speed -0.05 | fl.carpus joint speed -0.05 |
| lie | 1.8-4.6 | hl.hip_abd sustained torque +0.40 | hl.hip_abd sustained torque +0.32 | fl.carpus sustained belt +0.60 |
| hold | 4.6-5.5 | hl.hock sustained belt -0.04 | hl.hock sustained belt -0.08 | hl.hock sustained belt +0.04 |
| rise hind | 5.5-6.4 | hl.stifle envelope -0.25 | hl.stifle envelope -0.25 | hl.stifle envelope -0.25 |
| pause | 6.4-7.8 | hl.hock sustained belt -0.04 | hl.hock sustained belt -0.08 | hl.hock sustained belt +0.04 |
| rock back | 7.8-8.1 | hl.stifle joint speed +0.71 | hl.stifle joint speed +0.71 | hl.stifle envelope +0.71 |
| reach | 8.1-10.8 | fl.carpus sustained belt +0.00 | fl.carpus sustained torque -0.04 | fl.carpus sustained belt +0.00 |
| pause on hooves | 10.8-10.9 | fl.carpus sustained belt +0.00 | fl.carpus sustained torque -0.04 | fl.carpus sustained belt +0.00 |
| rise front | 10.9-12.8 | fl.carpus envelope -0.04 | fl.carpus envelope -0.07 | fl.carpus envelope -0.04 |
| standing after | 12.8-13.8 | hl.hip_abd envelope +0.92 | hl.hip_abd envelope +0.92 | hl.hip_abd envelope +0.92 |

#### g011-003: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.7 | fl.shoulder sustained torque -1.28 | fl.shoulder sustained torque -1.32 | fl.shoulder sustained torque -0.76 |
| lie | 1.7-3.2 | fl.shoulder sustained torque -0.84 | fl.shoulder sustained torque -0.88 | fl.shoulder sustained torque -0.36 |
| hold | 3.2-3.2 | - | - | - |
| rise hind | 3.2-4.0 | hl.hock sustained belt -0.48 | hl.hock sustained belt -0.68 | hl.stifle envelope -0.20 |
| pause | 4.0-4.5 | fl.shoulder sustained torque -0.08 | fl.shoulder sustained torque -0.04 | fl.shoulder sustained torque +0.00 |
| rock back | 4.5-5.6 | hl.hock sustained belt +0.28 | hl.hock sustained belt +0.24 | hl.hock sustained belt +0.28 |
| reach | 5.6-6.8 | fl.carpus sustained belt +0.24 | fl.carpus sustained belt +0.28 | fl.carpus sustained belt +0.28 |
| pause on hooves | 6.8-7.0 | fl.shoulder sustained torque +0.17 | fl.carpus sustained belt +0.28 | fl.carpus sustained belt +0.28 |
| rise front | 7.0-7.9 | fl.carpus envelope +0.01 | fl.carpus envelope -0.04 | fl.carpus envelope -0.00 |
| standing after | 7.9-8.9 | fl.shoulder envelope +0.71 | fl.shoulder envelope +0.71 | fl.shoulder envelope +0.74 |

## Extension: the lying pose searched too

Not asked for: Stage 2 left the hind belts binding *in the lying pose*, which is not among the primitive's dims. With
`--lying` the search also sets the lying stifle, hock, shoulder and carpus (inside the joint ranges less 2 deg),
warm-started from each body's Stage 2 best, with the same lying-depth requirement. It helps exactly the hind-limited
bodies: **g012-009 -0.96 -> -0.44** (hock less folded, 62 deg, the trunk at 0.48), **g020-008-r01 -1.40 -> -0.84**. On
the shoulder-limited bodies and g007-002 it found nothing better than the Stage 2 version. Still no body holds.

### Extension tables

| body | today (whole) worst | best worst-seed | holds 3/3 | stands up again | lowest trunk (share of standing) | plays (new) | wall min | best version |
|---|---|---|---|---|---|---|---|---|
| g020-008-r01 | -3.000 | -0.840 | no | yes | 269 mm (0.45) / 269 mm (0.45) / 269 mm (0.45) | 1072 (1066) | 16 | hind first; kneel -19/97, reach -48/110; moves 1.5/0.8/0.8/2.6/3.3 s; hold 0.0; rock 4 deg/0.6 s; pauses 1.8/1.1 s; lying stifle/hock 78/77, shoulder/carpus -46/109 |
| g012-009 | -3.000 | -0.440 | no | yes | 289 mm (0.48) / 289 mm (0.48) / 289 mm (0.48) | 1030 (1024) | 189 | hind first; kneel -7/108, reach -30/85; moves 1.1/1.9/0.8/1.2/1.1 s; hold 0.1; rock 12 deg/0.3 s; pauses 1.7/0.0 s; lying stifle/hock 75/62, shoulder/carpus -36/104 |
| g009-000 | -3.000 | -1.360 | no | yes | 273 mm (0.46) / 272 mm (0.45) / 273 mm (0.46) | 1056 (1050) | 18 | hind first; kneel -31/90, reach -42/104; moves 2.9/2.3/2.7/1.2/3.9 s; hold 0.0; rock 2 deg/0.4 s; pauses 1.8/0.4 s; lying stifle/hock 75/75, shoulder/carpus -40/125 |
| working | -3.000 | -1.200 | no | yes | 277 mm (0.46) / 277 mm (0.46) / 278 mm (0.46) | 998 (992) | 16 | hind first; kneel -39/126, reach -44/110; moves 1.6/1.0/0.8/0.9/2.5 s; hold 0.1; rock 9 deg/0.8 s; pauses 0.0/0.0 s; lying stifle/hock 75/75, shoulder/carpus -40/125 |
| g007-002 | -3.000 | -0.251 | no | yes | 282 mm (0.46) / 282 mm (0.46) / 282 mm (0.46) | 992 (986) | 13 | hind first; kneel -21/125, reach -43/110; moves 1.8/2.8/0.9/2.7/2.0 s; hold 1.0; rock 8 deg/0.3 s; pauses 1.4/0.0 s; lying stifle/hock 75/75, shoulder/carpus -40/125 |
| g011-003 | -3.000 | -1.320 | no | yes | 271 mm (0.45) / 271 mm (0.45) / 271 mm (0.45) | 1068 (1062) | 15 | hind first; kneel -27/85, reach -58/110; moves 1.7/1.5/0.8/1.3/0.8 s; hold 0.0; rock 4 deg/1.1 s; pauses 0.5/0.2 s; lying stifle/hock 75/75, shoulder/carpus -40/125 |

#### g020-008-r01: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.5 | fl.carpus sustained torque -0.24 | hl.stifle sustained belt -0.40 | hl.stifle sustained belt -0.36 |
| lie | 1.5-2.3 | hl.hock sustained belt -0.64 | hl.hock sustained belt -0.64 | hl.hock sustained belt -0.52 |
| hold | 2.3-2.3 | hl.hock sustained belt -0.60 | hl.hock sustained belt -0.64 | hl.hock sustained belt -0.52 |
| rise hind | 2.3-3.1 | hl.hock sustained belt -0.60 | hl.hock sustained belt -0.64 | hl.hock sustained belt -0.52 |
| pause | 3.1-4.9 | hl.stifle sustained belt +0.05 | hl.stifle sustained belt -0.07 | hl.stifle sustained belt +0.01 |
| rock back | 4.9-5.5 | hl.stifle envelope +0.90 | hl.stifle stall +0.89 | hl.stifle stall +0.91 |
| reach | 5.5-8.2 | fl.shoulder envelope +0.83 | fl.shoulder envelope +0.83 | fl.shoulder envelope +0.85 |
| pause on hooves | 8.2-9.2 | hl.stifle sustained belt -0.08 | hl.stifle sustained belt -0.16 | hl.stifle sustained belt +0.00 |
| rise front | 9.2-12.5 | fl.carpus sustained torque -0.64 | fl.carpus sustained torque -0.84 | fl.carpus sustained torque -0.72 |
| standing after | 12.5-13.5 | fl.shoulder envelope +0.92 | fl.shoulder envelope +0.92 | fl.shoulder envelope +0.92 |

#### g012-009: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.1 | fl.shoulder sustained torque -0.20 | fl.shoulder sustained torque -0.44 | fl.shoulder sustained torque +0.08 |
| lie | 1.1-3.0 | fl.carpus sustained torque -0.40 | fl.shoulder sustained torque -0.44 | fl.carpus sustained torque -0.40 |
| hold | 3.0-3.1 | fl.carpus sustained torque -0.40 | fl.carpus sustained torque -0.40 | fl.carpus sustained torque -0.40 |
| rise hind | 3.1-4.0 | fl.carpus sustained torque -0.40 | fl.carpus sustained torque -0.40 | fl.carpus sustained torque -0.40 |
| pause | 4.0-5.6 | fl.shoulder sustained torque -0.16 | hl.stifle sustained belt -0.36 | fl.shoulder sustained torque -0.16 |
| rock back | 5.6-5.9 | hl.stifle envelope +0.58 | hl.stifle envelope +0.59 | hl.stifle envelope +0.58 |
| reach | 5.9-7.1 | fl.carpus sustained torque -0.28 | fl.shoulder sustained torque -0.44 | fl.carpus sustained torque -0.32 |
| pause on hooves | 7.1-7.1 | - | - | - |
| rise front | 7.1-8.3 | fl.carpus sustained torque -0.28 | fl.shoulder sustained torque -0.40 | fl.carpus sustained torque -0.32 |
| standing after | 8.3-9.3 | fl.carpus sustained torque +0.08 | fl.shoulder sustained torque +0.00 | fl.shoulder sustained torque +0.08 |

#### g009-000: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-2.9 | fl.carpus sustained belt -0.48 | fl.carpus sustained belt -0.56 | fl.carpus sustained belt -0.48 |
| lie | 2.9-5.2 | fl.shoulder sustained torque -1.12 | fl.shoulder sustained torque -1.24 | fl.shoulder sustained torque -1.12 |
| hold | 5.2-5.2 | - | - | - |
| rise hind | 5.2-7.9 | fl.shoulder sustained torque -1.24 | fl.shoulder sustained torque -1.36 | fl.shoulder sustained torque -1.20 |
| pause | 7.9-9.7 | fl.shoulder sustained torque -0.03 | hl.stifle sustained belt -0.74 | fl.shoulder sustained torque +0.01 |
| rock back | 9.7-10.1 | hl.stifle envelope +0.90 | hl.stifle envelope +0.89 | hl.stifle envelope +0.90 |
| reach | 10.1-11.3 | fl.shoulder sustained torque +0.76 | fl.shoulder sustained torque +0.72 | fl.shoulder sustained torque +0.76 |
| pause on hooves | 11.3-11.7 | fl.carpus sustained belt +0.40 | fl.carpus sustained belt +0.40 | fl.carpus sustained belt +0.40 |
| rise front | 11.7-15.6 | fl.carpus sustained belt -0.60 | fl.carpus sustained belt -0.80 | fl.carpus sustained belt -0.64 |
| standing after | 15.6-16.6 | hl.hip_abd envelope +0.96 | hl.hip_abd envelope +0.96 | hl.hip_abd envelope +0.96 |

#### working: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.6 | fl.shoulder sustained torque -0.56 | fl.shoulder sustained torque -0.60 | fl.shoulder sustained torque -0.16 |
| lie | 1.6-2.6 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.76 | fl.shoulder sustained torque -0.56 |
| hold | 2.6-2.7 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.76 | fl.shoulder sustained torque -0.68 |
| rise hind | 2.7-3.5 | fl.shoulder sustained torque -1.04 | fl.shoulder sustained torque -1.20 | fl.shoulder sustained torque -0.88 |
| pause | 3.5-3.6 | fl.shoulder sustained torque -0.68 | fl.shoulder sustained torque -0.84 | fl.shoulder sustained torque -0.52 |
| rock back | 3.6-4.4 | fl.shoulder sustained torque -0.64 | fl.shoulder sustained torque -0.80 | fl.shoulder sustained torque -0.48 |
| reach | 4.4-5.2 | fl.carpus sustained belt -0.04 | fl.shoulder sustained torque -0.04 | fl.carpus sustained belt -0.04 |
| pause on hooves | 5.2-5.3 | fl.carpus sustained belt -0.08 | fl.carpus sustained belt -0.08 | fl.carpus sustained belt -0.08 |
| rise front | 5.3-7.8 | fl.carpus sustained belt -0.40 | fl.carpus sustained belt -0.48 | fl.carpus sustained belt -0.40 |
| standing after | 7.8-8.8 | hl.hip_abd envelope +0.93 | hl.hip_abd envelope +0.93 | hl.hip_abd envelope +0.93 |

#### g007-002: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.8 | fl.carpus joint speed -0.04 | fl.carpus joint speed -0.05 | fl.carpus joint speed -0.05 |
| lie | 1.8-4.6 | hl.hip_abd sustained torque +0.40 | hl.hip_abd sustained torque +0.32 | fl.carpus sustained belt +0.60 |
| hold | 4.6-5.5 | hl.hock sustained belt -0.04 | hl.hock sustained belt -0.08 | hl.hock sustained belt +0.04 |
| rise hind | 5.5-6.4 | hl.stifle envelope -0.25 | hl.stifle envelope -0.25 | hl.stifle envelope -0.25 |
| pause | 6.4-7.8 | hl.hock sustained belt -0.04 | hl.hock sustained belt -0.08 | hl.hock sustained belt +0.04 |
| rock back | 7.8-8.1 | hl.stifle joint speed +0.71 | hl.stifle joint speed +0.71 | hl.stifle envelope +0.71 |
| reach | 8.1-10.8 | fl.carpus sustained belt +0.00 | fl.carpus sustained torque -0.04 | fl.carpus sustained belt +0.00 |
| pause on hooves | 10.8-10.9 | fl.carpus sustained belt +0.00 | fl.carpus sustained torque -0.04 | fl.carpus sustained belt +0.00 |
| rise front | 10.9-12.8 | fl.carpus envelope -0.04 | fl.carpus envelope -0.07 | fl.carpus envelope -0.04 |
| standing after | 12.8-13.8 | hl.hip_abd envelope +0.92 | hl.hip_abd envelope +0.92 | hl.hip_abd envelope +0.92 |

#### g011-003: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-1.7 | fl.shoulder sustained torque -1.28 | fl.shoulder sustained torque -1.32 | fl.shoulder sustained torque -0.76 |
| lie | 1.7-3.2 | fl.shoulder sustained torque -0.84 | fl.shoulder sustained torque -0.88 | fl.shoulder sustained torque -0.36 |
| hold | 3.2-3.2 | - | - | - |
| rise hind | 3.2-4.0 | hl.hock sustained belt -0.48 | hl.hock sustained belt -0.68 | hl.stifle envelope -0.20 |
| pause | 4.0-4.5 | fl.shoulder sustained torque -0.08 | fl.shoulder sustained torque -0.04 | fl.shoulder sustained torque +0.00 |
| rock back | 4.5-5.6 | hl.hock sustained belt +0.28 | hl.hock sustained belt +0.24 | hl.hock sustained belt +0.28 |
| reach | 5.6-6.8 | fl.carpus sustained belt +0.24 | fl.carpus sustained belt +0.28 | fl.carpus sustained belt +0.28 |
| pause on hooves | 6.8-7.0 | fl.shoulder sustained torque +0.17 | fl.carpus sustained belt +0.28 | fl.carpus sustained belt +0.28 |
| rise front | 7.0-7.9 | fl.carpus envelope +0.01 | fl.carpus envelope -0.04 | fl.carpus envelope -0.00 |
| standing after | 7.9-8.9 | fl.shoulder envelope +0.71 | fl.shoulder envelope +0.71 | fl.shoulder envelope +0.74 |

## Stage 3: a body search with lie_rise as a constraint (built, not run)

`map_elites_hardware` has a `lie_rise_gate` (ADR-107): before the screen, each body's lie_rise is optimised as above
(plays one after another inside the body's task, cached per body), and a body whose best version does not hold on all
three seeds plays nothing else and does not pass. A body that passes is judged as Stage B judged it (trot grid, walk,
turn, the 11 shared behaviours for 60 s on three seeds). Preset `config/fitness/hardware_r13.yaml` (written by
`lierise_r13.py preset --lying --budget=S`): hardware_r11c's space and judging (lengths +-10 %, single listed pulleys,
springs incl. the shoulder springs' rate, preload and anchors, the shoulder drive, at most six C002), seeded with
g012-009, g020-008-r01 and g009-000; the gate searches the 15 dims plus the lying pose, warm-started from those three
bodies' best versions. The old lie_rise screen play is dropped from the screen (the gate replaces it).

Cost (`lierise_r13.py estimate`; 7.5 CPU-s per play as measured here, batches of 14 on 7 workers = 2 waves; an upper
bound: cached plays cost nothing):

| gate budget | plays per body | CPU min per body | wall per generation of 14 | + judging if all pass | 10 generations | 20 generations |
|---|---|---|---|---|---|---|
| S (8 x 8) | 204 | 26 | 0.8 h | +32 min | 8-14 h | 17-28 h |
| M (12 x 15) | 552 | 69 | 2.3 h | +32 min | 23-28 h | 46-57 h |
| L (12 x 30, as Stage 2) | 1092 | 136 | 4.5 h | +32 min | 46-51 h | 91-102 h |

Start it with `python docs/studies/lierise_r13.py projects/robot-calf-final preset --lying --budget=<S|M|L>`, then
`... stage3 --generations=<N> --batch=14`. The researcher chooses the budget.

Caveats: settle 1 s, lying depth 0.5 and the fall test (tipped, or not standing again at 85 % height) are my choices
(PROVISIONAL). Every search used one CMA-ES seed per body; the lying-pose search started from the Stage 2 best, so its
"nothing better" on four bodies is one run, not a proof. The excess term (0.1 x mean excess per move) only shapes the
search where the margin saturates; it is 0 for any version within limits.

## Superseded: the lying pose without a depth requirement (g020-008-r01 only)

| body | today (whole) worst | best worst-seed | holds 3/3 | stands up again | lowest trunk (share of standing) | plays (new) | wall min | best version |
|---|---|---|---|---|---|---|---|---|
| g020-008-r01 | -3.000 | +0.127 | yes | yes | 352 mm / 352 mm / 352 mm | 1086 (1080) | 13 | hind first; kneel -13/125, reach -58/107; moves 0.9/1.4/1.2/1.4/1.0 s; hold 0.0; rock 1 deg/0.7 s; pauses 1.3/0.5 s; lying stifle/hock 38/72, shoulder/carpus -28/122 |

### g020-008-r01: best version, per move

| move | t (s) | seed 0 | seed 1 | seed 2 |
|---|---|---|---|---|
| kneel | 0.0-0.9 | fl.shoulder stall +0.15 | fl.shoulder envelope +0.13 | fl.shoulder stall +0.17 |
| lie | 0.9-2.3 | fl.shoulder sustained torque +0.64 | fl.shoulder sustained torque +0.40 | hl.hock joint speed +0.69 |
| hold | 2.3-2.3 | fl.shoulder stall +0.82 | fl.shoulder sustained torque +0.72 | hl.hip_abd envelope +0.82 |
| rise hind | 2.3-3.5 | hl.hock joint speed +0.61 | hl.hock joint speed +0.61 | hl.hock joint speed +0.61 |
| pause | 3.5-4.8 | hl.stifle envelope +0.92 | hl.stifle envelope +0.91 | hl.stifle envelope +0.92 |
| rock back | 4.8-5.5 | hl.hock sustained belt +0.88 | hl.stifle stall +0.92 | hl.stifle envelope +0.93 |
| reach | 5.5-7.0 | fl.carpus sustained torque +0.28 | fl.carpus sustained torque +0.24 | fl.carpus sustained torque +0.24 |
| pause on hooves | 7.0-7.5 | fl.carpus sustained torque +0.28 | fl.carpus sustained torque +0.24 | fl.carpus sustained torque +0.24 |
| rise front | 7.5-8.5 | fl.carpus sustained torque +0.28 | fl.carpus sustained torque +0.24 | fl.carpus sustained torque +0.24 |
| standing after | 8.5-9.5 | fl.carpus sustained torque +0.28 | fl.carpus sustained torque +0.24 | fl.carpus sustained torque +0.24 |
