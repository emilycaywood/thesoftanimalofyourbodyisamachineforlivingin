# R14: the candidate bodies at their real weight (ADR-108)

Script: `docs/studies/mass_r14.py` (breakdown / judge / report / preset / estimate / search). Data:
`mass_r14.json`; full tables (every behaviour, every lie_rise seed): `mass_r14_tables.md`.

## What changed in the model

Gene `mass_model` (Form > Body). `as_entered` is ADR-068's counting, used for every body evolved or judged so far.
`explicit_v1` adds the researcher's masses of 2026-11-11:

| item | mass | where | source |
|---|---|---|---|
| pulley axle (`pulley_axle`, kind part) | 24 g x each belt-driven joint (6; 8 with belted shoulders) | joint axis | researcher's measurement |
| servo horn (`servo_horn`, kind part) | 14 g x 10 | servo output | researcher's measurement |
| servos | library: STS3215 C018 55 g, STS3250 C002 74.5 g (both entered, nothing stopped) | as before | library |
| leg tubes (`cf_leg_tube_16x12`) | pi/4 x (16^2 - 12^2) x length x 1.65 g/cm3 = 0.1451 g/mm, per segment | along each segment | researcher's request |
| batteries | 270 g for both packs (unchanged: ADR-068 already had 2 x 135 g) | as before | researcher |
| headroom (PROVISIONAL) | 300 g | trunk's centre of mass | researcher; not a part |

## 1. Mass

| body | as simulated g | explicit_v1 g | of it real parts g | leg tubes g | servos g | CoM x / z mm |
|---|---|---|---|---|---|---|
| working | 1304 | **2005** | 1705 | 248 -> 366 | 550 | 16/536 -> 13/522 |
| g007-002 | 1383 | **2085** | 1785 | 250 -> 368 | 628 | 18/532 -> 16/520 |
| g009-000 | 1380 | **2080** | 1780 | 246 -> 362 | 628 | 18/521 -> 15/510 |
| g012-009 | 1421 | **2122** | 1822 | 248 -> 365 | 667 | 28/526 -> 24/514 |
| g020-008-r01 | 1419 | **2120** | 1820 | 247 -> 363 | 667 | 28/521 -> 24/510 |

Every body gains 700-702 g: axles +144, horns +140, tubes +116 to +118, headroom +300. Batteries, servos, head and
rails are unchanged. Still 0 g and listed as missing: bearings, clamp collars, tube plugs, both blocks,
electronics, skin, hoof pads, belts, pulleys and springs.

## 2. Re-judged with the R11c suite (seeds 0-2, margin 0.2)

Control: the same script at `as_entered` reproduces R12's Stage C judging and R13's lie_rise margins exactly
(every behaviour's held count and worst margin, the trots, both lie_rise versions). The changes below are the mass
alone.

| body | own behaviours held 3/3 | minutes | fastest trot held (trot plays held) | walk | turn | lie_rise evolved | lie_rise, lying pose | what binds now (plays stopped) |
|---|---|---|---|---|---|---|---|---|
| working | 11 -> **1** of 12 | 35 -> **11**/36 | none (0) | -0.13 -> -0.84 | -0.25 -> -1.16 | -1.20 -> -3.00 | -1.20 -> -3.00 | hr hip ab/ad torque (15), shoulders' torque (18) |
| g007-002 | 23 -> **4** of 25 | 72 -> **25**/75 | none (0) | -0.32 -> -0.60 | -0.25 -> -0.48 | -0.25 -> -2.80 | -0.25 -> -2.80 | hr hip ab/ad torque (15), fl carpus belt (14), fr carpus speed (11) |
| g009-000 | 16 -> **0** of 17 | 50 -> **9**/51 | 394 -> 394 mm/s (7 -> 4) | -0.12 -> -0.88 | -0.08 -> -1.08 | -1.36 -> -3.00 | -1.36 -> -3.00 | shoulders' torque (36), fl carpus belt (8) |
| g012-009 | 14 -> **0** of 16 | 44 -> **11**/48 | 414 -> 414 mm/s (16 -> 8) | -0.48 -> -0.72 | -0.08 -> -0.96 | -0.96 -> -3.00 | -0.44 -> -3.00 | hr stifle torque (11), fl carpus torque (10), hl hip ab/ad torque (8) |
| g020-008-r01 | 8 -> **0** of 11 | 29 -> **0**/33 | 530 -> 543 mm/s (16 -> 12) | -0.52 -> -0.72 | -0.08 -> -0.84 | -1.40 -> -3.00 | -0.84 -> -3.00 | fr carpus torque (18), hr hip ab/ad torque (12) |

**What still holds.** g007-002 keeps 4 of its 25 behaviours (g000-009, g006-024, g002-010, g012-026; margins
+0.03 to +0.87) and the working body 1 (g001-012, +0.34). No body holds walk, turn or lying down and rising (every
lie_rise seed at -2.3 to -3.0, bound by sustained servo torque). The trot holds where it did, with fewer grid
points: g020-008-r01 still trots at 543 mm/s, g012-009 at 414 and g009-000 at 394.

**What binds.** Sustained servo torque (more than 25 % of a play above the rated torque less the margin) on the
joints that carry the weight: the C018 hip ab/ad servos (every body except g009-000), the shoulders (C018 on working
and g009-000), and the carpi (torque on the C002 bodies, belt tension on g007-002 and g009-000). Joint speed is still the closest limit
in the plays that hold.

## 3. The next search

Presets `hardware_r11c` and `hardware_r13` are now version 2 with `mass_model: explicit_v1`; runs made with version
1 carry their own copy and reload as they were. `config/fitness/hardware_r14.yaml` (version 1) is hardware_r11c v2
seeded with the three bodies that hold best at the new weight, ranked by own behaviours held, then minutes, then
trot: **g007-002** (4, 25 min), **working** (1, 11 min), **g012-009** (0, 11 min, trots at 414 mm/s), each with
its shoulder spring switched, its shoulder belted and its carpus spring on (11 seed bodies).

Estimate from measured rates (an upper bound; heavier bodies that fail the screen play nothing else):

| preset | per generation of 15 | 5 generations | 10 generations | 20 generations |
|---|---|---|---|---|
| hardware_r14 (= hardware_r11c v2 + seeds) | 34 min | 2.8 h | 5.7 h | 11.3 h |
| hardware_r13 v2 (lie_rise gate S) | 54 min | 4.5 h | 8.9 h | 17.9 h |

Caveat: the Stage B judging plays R6c's and R7's 11 shared behaviours, evolved for the light working body; at
explicit_v1 they will hold less, so minutes held mostly measure which body carries the weight. Stage C behaviours
for a new front body would need their own diversity run (R12's method), about 45-125 min per body.

Not started: the researcher chooses the budget.
