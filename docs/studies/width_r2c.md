# Session R, between steps 2 and 3: wide hooves from wider blocks, and hip springs (ADR-089)

2026-11-04. The researcher wants the legs splayed for stability and chose "wide hips plus springs". Two new
genes widen the hip and chest blocks per side (`hip_block_widen`, `chest_block_widen`); a new hip ab/ad tension
spring per hind leg (`spring_hip_abd`, off by default) pulls the leg in against the weight. This study plays them
in physics on the project's body (`robot-calf-final`, 1304 g as entered), in memory only.

Method: `width_r2c.py` (all bodies, all motions) and `width_r2c_trot.py` (the trot's per-joint torques).
Torque-speed servos, derating 1, seed 0, judged at margin 0.2, as in `sensitivity_r1.md` and `load_r2.md`. The
interpreted trot and step use the parameters interpreted on today's body. "GC springs" = every enabled spring's
rate scaled so that at standing its torque equals what the weight puts on its joint (`static_spring_report`).
"Hoof half-width" = the distance of a hoof from the centre line, standing.

## Results (worst margin; negative = over a limit)

| body | hooves from centre, hind / front (mm) | walk | trot | interp. trot | interp. step |
|---|---|---|---|---|---|
| A today: splay 12 / 10.5 deg, narrow blocks | 203 / 185 | -2.48 (hip ab/ad torque) | -1.20 (hip ab/ad torque, belt) | +0.71 | +0.28 |
| B straight legs, narrow blocks (step 2) | 83 / 80 | -0.13 (speed) | -0.16 (belt) | -0.47 | +0.27 |
| C straight legs, blocks +120 / +105 mm per side | 203 / 185 | **-0.13 (speed only)** | -1.80 (belt, torque) | **+0.73** | -2.04 (torque) |
| D = C + GC springs | 203 / 185 | **-0.14 (speed only)** | -1.22 (belt, torque) | -0.23 (torque) | **+0.28** |
| E splay 6 / 5.25, blocks +60 / +52, hip springs, GC springs | 203 / 185 | **-0.13 (speed)** | -1.24 (torque, belt) | **+0.73** | **+0.28** |
| F today's splay, hip springs, GC springs | 203 / 185 | -1.56 (torque) | -0.68 (torque, belt) | +0.72 | +0.27 |
| G straight legs, blocks +60 / +53, GC springs | 143 / 132 | -0.14 (speed) | -0.52 (belt, stall) | -0.20 | +0.27 |

Walk, constraint by constraint (A -> C): sustained torque -2.48 -> +0.28, sustained belt -0.07 -> +0.28,
envelope -0.25 -> +0.10; joint speed -0.12 -> -0.13 is the only one left (the carpus folding fast).

## The trot on wide blocks

`width_r2c_trot.py`, the trot as it is (its parameters were set on the narrow body). Mean |torque| at the joint
(N*m):

| body | stifle | hock | shoulder | carpus | hip ab/ad | trunk roll rms / max (deg) |
|---|---|---|---|---|---|---|
| B narrow, straight | 0.35-0.38 | 0.21-0.23 | 0.14-0.17 | 0.19-0.21 | 0.06-0.07 | 0.86 / 2.55 |
| C wide, straight | 0.73-0.75 | 0.35 | 0.42-0.45 | 0.29-0.31 | 0.29-0.31 | 1.19 / 2.21 |
| C, trot roll gain 0 | 0.72-0.75 | 0.34-0.36 | 0.41-0.47 | 0.28-0.32 | 0.14-0.18 | 1.21 / 2.23 |

On wide blocks the trot's load moves into the stifles (twice as much) and shoulders (three times). A trot
stands on one diagonal pair. The line between the two hooves passes through the middle of the body, and the
centre of mass is ahead of or behind that point (head, batteries). The wider the hooves, the farther the line
swings to the side of the centre of mass, so the body tips toward the lifted pair until those legs land. The
legs in stance work harder to hold it. The trot's own roll feedback is not the cause (roll gain 0 changes
little). This is the gait, not the body: the trot's timing and stride were set for the narrow body, and step 4
tunes them per body.

## What it says

* **Wide blocks do what splay did for stability without loading the hip ab/ad servos.** With the hooves at
  today's width, the walk loses every torque, belt and envelope failure. Only joint speed is left, and that is
  set by the gait.
* **Hip springs alone do not rescue full splay** (F: walk -1.56). Splay 12 deg puts too much weight on the hip
  ab/ad, and a spring sized for standing does not follow the walk.
* **Half splay + half widening + hip springs (E)** is as good as straight legs on wide blocks for the walk and
  both interpreted motions. If you want some visible splay, this is the way to have it.
* **GC springs matter for the read motions.** The interpreted step goes from -2.04 to +0.28 on wide blocks once
  the springs hold just the weight.
* **The trot needs to be re-tuned for each body.** That is step 4's inner loop. The walk needs a slower carpus
  fold (also a gait parameter).

## Raw output (`width_r2c.py`)

```
A today:  walk -2.48 (servo_sust -2.48 belt -0.07 speed -0.12 env -0.25)  trot -1.2 (servo -1.20 belt -0.96)
          interp trot +0.71  interp step +0.28
B:        walk -0.13 (servo -0.04 speed -0.13)  trot -0.16 (servo -0.04 belt -0.16 speed -0.04)
          interp trot -0.47 (servo -0.47 belt -0.08)  interp step +0.27
C:        walk -0.13 (servo +0.28 belt +0.28 speed -0.13 env +0.10)  trot -1.8 (servo -1.00 belt -1.80 env -0.02)
          interp trot +0.73  interp step -2.04 (servo -2.04)
D:        walk -0.14 (speed -0.14)  trot -1.22 (servo -0.96 belt -1.22 env -0.07)  interp trot -0.23  interp step +0.28
          springs k: stifle 0.20, hock 0.13, shoulder 0.020 N/mm
E:        walk -0.13 (servo +0.16 speed -0.13 env -0.09)  trot -1.24 (servo -1.24 belt -0.92)
          interp trot +0.73  interp step +0.28; springs k: stifle 0.20, hock 0.13, shoulder 0.022, hip ab/ad 0.18 N/mm
F:        walk -1.56 (servo -1.56 speed -0.13 env -0.25)  trot -0.68 (servo -0.68 belt -0.54)
          interp trot +0.72  interp step +0.27; hip ab/ad k 0.34 N/mm
G:        walk -0.14 (speed -0.14)  trot -0.52 (servo -0.32 stall -0.23 belt -0.52 speed -0.07 env -0.23)
          interp trot -0.20  interp step +0.27
```
