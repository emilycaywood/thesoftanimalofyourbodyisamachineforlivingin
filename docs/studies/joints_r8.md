# Faster joints: what binds, and what each lever buys (ADR-099)

2026-11-05. Session R8 in `projects/robot-calf-final`, after R7. Everything here is **simulation only**: the
body, belts, catalogs, component values and `verified` flags were not changed. Each what-if is an in-memory copy
of the working body's spec (`docs/studies/joints_r8.py`; data in `joints_r8.json` and `joints_r8_seeds.json`).

Plays: the trot primitive alone over cycle 0.6-1.2 s x stride 0.5-1.5 (lift 0.6, as `trot_r6c.py`), the walk and
the turn at their defaults; every limit at margin 0.2, judged as everywhere else (torque-speed servos, derating 1).

## Which limit binds at each joint today

Per joint, the share of its margin-lowered limit (1.0 = at the limit); bold = over.

| joint | trot 0.6 s, stride 1.0 | trot 1.2 s, stride 1.0 | walk | turn |
|---|---|---|---|---|
| front carpi | **speed 1.18-1.20** | speed 0.95 | **speed 1.12-1.13** | **speed 1.11-1.12** |
| hocks | **speed 1.14** | speed 0.65 | speed 0.91-0.92 | speed 0.87-0.91 |
| hip ab/ad | **torque 1.2** | 0.1 | torque 0.64 | torque 0.72-0.84 |
| shoulders | torque 0.20-0.28 | torque 0.40-0.52 | torque 0.80-0.84 | torque 0.56-0.84 |
| stifles | speed 0.61-0.67 | speed 0.35 | speed 0.52-0.53, belt 0.28-0.32 | belt 0.32-0.60 |

* **The carpi bind on speed first, everywhere**, as the handoff said: 135 deg/s at the joint (270 deg/s halved by
  the 2:1 belt), 108 after the margin.
* In a quick trot the **hocks** reach their speed limit too, and the **hip ab/ad** their sustained torque.
* The **stifles** have room in both speed and torque; the shoulders come close to sustained torque in the walk
  and turn.

## What each lever buys (seed 0)

"Quickest within" = the shortest cycle with any stride within every limit.

| what-if | quickest within | fastest within | 0.6-0.8 s within | walk | turn |
|---|---|---|---|---|---|
| now | 1.2 s | 77 mm/s | none | -0.13 joint speed | -0.25 envelope |
| carpus 1.5:1 (30T/45T) | 0.8 s | 79 mm/s | 0.8 s / 0.5 (36 mm/s) | -0.14 envelope | -0.25 envelope |
| carpus 1:1 (30T/30T) | none | none | none | +0.00 | -0.08 belt |
| all belts 1.5:1 | 0.8 s | 73 mm/s | 0.8 s / 0.5 (42 mm/s) | -0.76 belt | -0.28 servo torque |
| hip ab/ad behind 2:1 | 1.2 s | 78 mm/s | none | -0.56 servo torque | -0.25 envelope |
| hip springs x2 | 1.2 s | 77 mm/s | none | -0.14 joint speed | -0.25 envelope |
| mass x0.9 | 1.2 s | 80 mm/s | none | -0.13 joint speed | -0.25 envelope |
| carpus 1:1 + hip 2:1 | 1.0 s | 102 mm/s | none | -0.44 servo torque | -0.35 belt |
| all 1.5:1 + hip 2:1 + springs x2 + mass x0.9 | 0.8 s | 77 mm/s | 0.8 s / 0.5 (41 mm/s) | -0.88 belt | -0.24 envelope |
| carpus 1:1 45T/45T + hip 2:1 | 0.8 s | 102 mm/s | 0.8 s / 0.5, 1.0 (39, 63 mm/s) | -0.44 servo torque | -0.04 envelope |
| **carpus 1:1 45T/45T + hock 1.5:1** | **0.6 s** | **131 mm/s** | 0.6 s / 1.0; 0.8 s / 0.5, 1.0 | **+0.12** | **+0.05** |
| carpus 1:1 45T/45T + hock 1.5:1 + hip 2:1 | 0.6 s | 123 mm/s | 0.6 s / 0.5, 1.0; 0.8 s / 0.5, 1.0 | -0.12 servo torque | +0.06 |

* **Less reduction at the carpi** is what the speed wall needs, but at 1:1 with today's 30T driver the servo
  carries twice the torque into the same small pulley and the **carpus belt** goes over its sustained tension. A
  larger pulley pair at 1:1 (45T/45T: 1.5x less belt tension per servo torque) removes that.
* The **hocks** are then the next speed limit in a quick trot; 1.5:1 there (30T/45T) clears it.
* **Belting the hip ab/ad** (2:1) helps only the shortest-stride quick trot and costs the walk: the walk's sway
  then needs more speed than half the servo's.
* **Stiffer hip springs** make the quick trot worse; **10 % lighter** changes little. Neither is a lever here.
* Mass x0.9 is optimistic: 14 parts still have no mass and would add to it.

## The combination, on three randomised seeds

Seeds 0, 1, 2 with the diversity preset's randomisation (friction 0.7-1.1, mass x0.95-1.05), margin 0.2:

| | trot 0.6 s / 0.5 | trot 0.6 s / 1.0 | trot 0.8 s / 1.0 | trot 1.2 s / 1.0 | walk | turn |
|---|---|---|---|---|---|---|
| now | -0.36 / -0.44 / -0.18 | -0.20 / -0.32 / -0.24 | -0.18 / -0.18 / -0.17 | +0.05 / +0.05 / +0.05 | -0.13 x3 | -0.25 x3 |
| **carpus 1:1 45T + hock 1.5:1** | -0.08 x3 (hip ab/ad torque) | **+0.16 x3, 130-137 mm/s** | +0.20 / +0.00 / +0.32 | +0.54 / +0.20 / +0.40 | **+0.16 / +0.12 / +0.18** | **+0.06 / +0.04 / +0.06** |
| + hip ab/ad 2:1 | +0.21 x3 | +0.16 x3 | +0.24 / +0.24 / +0.32 | +0.44 / +0.36 / +0.53 | +0.00 / -0.48 / -0.40 | +0.06 / +0.04 / +0.06 |

**Answer:** carpi at 1:1 on a 45T/45T pair and hocks at 1.5:1 (30T/45T) give a **0.6 s trot within every limit
at margin 0.2 on three seeds** (stride 1.0, 130-137 mm/s, against 77 mm/s at 1.2 s today), and make the walk and
the turn pass as well, which nothing else here did. The hip ab/ad is best left direct.

## What this rests on, and what is not checked

* **The pulleys are what-ifs.** Today's catalog has only 2:1 pairs (30T/60T). GT2 10 mm pulleys are listed
  commercially from 20T to 120T (ADR-088), including 30T and 45T for 10 mm belts. **Nothing was added to the
  catalog**: entries need your go-ahead, with sources, masses `null` and `verified: false`.
* **Belt length and centre distance not re-derived.** Other pulleys change the derived C for every catalog belt
  length (ADR-063): which belt fits each new pair, and whether the servo still sits on its segment, is unchecked.
  So is whether a 45T pulley (28.6 mm pitch diameter, against 19.1 for 30T) fits at the carpus.
* **Joint ranges:** a belted joint on a 360 deg servo spans at most 360 / ratio: carpus at 1:1 spans 140 deg
  (fine), hock at 1.5:1 at most 240 deg (its range is 110 deg: fine).
* **Torque at the joint drops** with the ratio (1:1 carpus: half; 1.5:1 hock: three quarters). It passed here
  in the trot, walk and turn; lying down and rising (`lie_rise`), which loads the carpi most, was not played.
* Pulley masses not modelled; the servo's figures are the library's, unverified, at 12 V (at 11.1 V the joints are
  about 7 % slower, ADR-086).
* Plays are of the primitives alone, not inside evolved sequences with coverage.
