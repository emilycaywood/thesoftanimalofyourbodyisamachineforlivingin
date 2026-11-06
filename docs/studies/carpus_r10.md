# Session R10: servos per joint pair, and the carpus drive for a faster body (ADR-101)

In simulation only. The working body, belts, catalogs, component values and `verified` flags are unchanged;
nothing was added to the pulley catalog.

## Part 1: the genome (summary; details in ADR-101)

* `feral_calf` genes v2: `servo_hip_abd`, `servo_stifle`, `servo_hock`, `servo_shoulder`, `servo_carpus` replace
  `actuator`. The migration copies `actuator` into each with `setdefault`. An open v1 document (unversioned
  params) builds with its own servo and is written as v2 at its next save.
* Bit-identical to the code before the change (spec, MJCF, masses): the default body, a v1 genome on the STS3250, and
  the `robot-calf-final` document, baked design `calf1-v001` and run candidate `...-4237-g000-000`.
* R9's in-memory swap and the genes give the same MJCF. The R9 best body built through the genes replays R9's 33
  minutes exactly (R6c calm -1.00 / -1.04 / -1.00, ...).
* Mass tab: *Servos by joint* (servo, mass, belt ratio, speed and stall / rated torque at the joint).

## Part 2: the carpus drive

**Bodies.** Each keeps R9's stifle and hock belts (catalog 40T/80T on 444 / 400 mm belts) and has at most four STS3250
C002s. Carpus drives:
* 1:1 on 45T/45T (R8's what-if);
* 1.5:1 on 30T/45T (what-if);
* 2:1 on today's 30T/60T;
* 2:1 on the catalog's 40T/80T, 640 mm, C 259.7.

New-servo pairs, as asked:
* hip ab/ad + hocks (R9's best; old carpus);
* hocks + carpi;
* hip ab/ad + carpi.

Once the first grid showed `lie_rise` bound by the front shoulders, these were added:
* shoulders + hocks;
* shoulders + hip ab/ad;
* shoulders + carpi.

That makes 24 bodies, plus today's.

**Plays.**
* The quick trot grid (cycle 0.4-0.8 s x stride 0.5-2.0, lift 0.6), the walk, the turn and `lie_rise`, on three
  randomised seeds at margin 0.2 (`carpus_r10.py grid`, `carpus_r10_grid.json`).
* R6c's and R7's 11 safe behaviours for 60 s on three seeds, on a shortlist of 7 bodies (`carpus_r10.py perform`,
  `carpus_r10_perform/`).
* Tables: `carpus_r10_table.py` -> `carpus_r10_tables.md`; 11.1 V and the six-servo reference:
  `carpus_r10_extra_table.py` -> `carpus_r10_extra_tables.md`.

### Results at 12 V

| body | trots within (of 20) | fastest within, 3 seeds | walk | turn | lie_rise | 60 s held (of 33) |
|---|---|---|---|---|---|---|
| today | 0 | none (1.2 s in R9's wider grid) | -0.13 x3 | -0.25 x3 | -3.00 x3 | 32 (R9) |
| **R9's best: new hip ab/ad + hocks, old carpus 1:1 45T** | 12 | 0.5 s / 2.0, 394-404 mm/s | **+0.21-0.23** | **+0.09-0.12** | -2.72 to -2.96 | 20 |
| same, old carpus 1.5:1 30T/45T | 1 | 0.8 s / 1.0, 74 mm/s | +0.03-0.04 | -0.17 to -0.20 | -2.7 to -3.0 | 18 |
| same, old carpus 2:1 30T/60T | 0 | none | -0.09 | -0.15 | -2.7 to -3.0 | - |
| same, old carpus 2:1 40T/80T | 0 | none | -0.09 | -0.15 | -2.6 to -2.9 | 21 |
| **new hocks + carpi, 1:1 45T** | **13** | **0.5 s / 2.0, 418-425 mm/s** | -0.24 / -0.24 / +0.00 | -0.19 / -0.24 / +0.00 | -2.9 to -3.0 | **26** |
| new hocks + carpi, 1.5:1 | 0 | none | -0.24 / -0.24 / -0.04 | -0.20 / -0.24 / +0.01 | -2.9 to -3.0 | 25 |
| **new hocks + carpi, 2:1 40T/80T** | 2 | 0.8 s / 1.0, 63-71 mm/s | -0.24 / -0.24 / -0.04 | -0.20 / -0.24 / -0.04 | -2.8 to -3.0 | **28** |
| new hip ab/ad + carpi, any drive | 0-1 | 0.8 s at best | -0.04 to -0.24 | -0.03 to +0.01 | -2.8 to -3.0 | - |
| new shoulders + hocks, 1:1 45T | 12 | 0.5 s / 2.0, 412-416 mm/s | -0.28 to -0.48 | -0.01 to -0.19 | -1.92 to -1.96 | 19 |
| new shoulders + hip ab/ad or carpi | 0-2 | 0.8 s at best | -0.07 to -0.40 | -0.25 to +0.05 | -1.2 to -2.0 | - |

Full tables (every body, every seed, belt peaks and current) are in `carpus_r10_tables.md`.

**No carpus drive keeps the calm behaviours within limits while the trot stays fast, with at most four new servos.
No body keeps `lie_rise` within limits.**

* **The fast trot needs a 1:1 carpus.** Every 1.5:1 and 2:1 carpus, on either servo, loses the 0.4-0.6 s trots: the
  carpus is back on joint speed (old servo: 135 deg/s at 2:1; new: 226 deg/s at 2:1, 301 at 1.5:1). It also needs
  new hocks. Without them no body gets below 0.8 s.
* **The calm behaviours need carpus torque at the joint without belt tension.**
  * With the old servo at 1:1 they go over on the carpus servo's sustained torque (R9).
  * With the new servo at 1:1 or 1.5:1 they go over on the carpus **belt**, above its 44 N allowable working tension
    for half of a 2 s window. The 45T driver, or the 30T on 1.5:1, gives up the 2:1 belt's leverage.
  * The old servo on a 2:1 carpus keeps them (calm +0.17 to +0.42, as today), but there is no fast trot.
  * **The new servo on the catalog's 40T/80T (2:1, larger driver)** keeps them on 2 of 3 seeds (+0.23 to +0.40) and
    holds **28 of 33 minutes, the most of any body**. Every minute that goes over does so on the **old front
    shoulder** (sustained torque), not the carpus. But it trots at 0.8 s at best (63-71 mm/s): the carpus is back on
    joint speed. It needs no new pulley size.
* **The walk and the turn need new hip ab/ad servos** (old ones: sustained torque, -0.24). Hip ab/ad + hocks + carpi
  is six new servos. As an out-of-budget reference, that body on 1:1 trots at 0.5 s / 2.0 (402-409 mm/s) and walks
  (+0.12 to +0.20), but its turn still goes over (-0.04 to -0.24, front shoulder).
* **`lie_rise` binds on the old front shoulders' sustained torque** on every body. Today it also binds on the stifle
  belt (-3.00). New shoulders halve the overrun (-1.2 to -2.0) and nothing gets within. Lying down and rising is a
  long hold at a deep angle. It needs more than a servo swap: a different shoulder drive (a belt), springs, or a
  different way down. It was not studied further.

### The best body within four new servos: new hocks + new carpi, carpi 1:1 45T

This is my pick on R10's criterion (behaviours held, trot speed). It is not a body that does everything.

* 26 of 33 minutes hold (R9's best: 20; today: 32). Where they hold, the headroom is larger than R9's: lively
  +0.36-0.54, walking +0.20-0.45, trotting +0.08-0.28, trot-shift +0.16-0.20, all now within.
* The fastest trot within every limit is 0.5 s / 2.0 at 418-425 mm/s, 13 of 20 trots within.
* What it loses: R6c calm and R7 calm on all seeds (carpus belt, sustained), R7 walking seed 0, and **the walk and
  the turn** (old hip ab/ad, two seeds of three, -0.19 to -0.24).
* R9's best body is the alternative when the walk and turn matter more than the behaviours: 20 of 33, walk and turn
  within with margin.
* For calm behaviours over speed, the same servos with the carpi on the catalog's 40T/80T hold 28 of 33,
  calm on 2 seeds of 3, and need no new pulley size. Their trot is 0.8 s. The choice between a fast trot and calm
  stance is the carpus ratio; it is the researcher's.

**Belt peaks**, within-limit plays, highest over all of them:
* stifle 70 N, hock 61 N, carpus 76 N;
* R9's best: 79 / 67 / 51 N.

Every belt's allowable working tension is 44 N (sustained) and its breaking strength 860 N; it is judged at 172 N,
the 0.2 fraction. The peaks are short. Sustained tension is what binds the calm behaviours.

**The new servos' current** (hocks + carpi), within-limit plays:
* peak sum 1.93 A, mean sum 0.96 A;
* per servo: hock 0.71 A, carpus 0.98 A peak.

R9's best (hip ab/ad + hocks): 2.11 / 1.03 A, hip ab/ad 1.39 A peak. The C018s' current is still unknown (no stall
current entered), so the packs' load is not known.

### At 11.1 V

* **New hocks + carpi 1:1:**
  * 8 trots within (12 V: 13), the fastest 0.5 s / 1.5 at 314 mm/s;
  * walk +0.00 / -0.16 / -0.16 and turn -0.20 to -0.44: worse.
* **R9's best:**
  * 7 trots within, 0.5 s / 1.5 at 300 mm/s;
  * walk +0.15-0.16, turn +0.01 / -0.01 / +0.03 (as R9 found).
* `lie_rise`: -2.96 to -3.00 on both.

The behaviours were not re-run at 11.1 V.

## Stored plays and side-by-side links

Runs in `projects/robot-calf-final`:
* `R10 what-if (new: hock+carpus | carpus 1:1 45T | stifle 40T-80T | hock 40T-80T 400) <label> ...` (33 minutes);
* `R10 play: new carpi and hocks, ...` (trot 0.5 s / 2.0, walk, turn, `lie_rise`, seed 0);
* `R10 play: today, turn` and `R10 play: today, lie_rise`.

Their stored genome carries the servo and catalog belt genes. The 45T carpus is not in any catalog and is
in-memory only. Links, today on the left: `compare_r10.md` (`compare_r10.py`; port 8020).

**Restart the lab on 8020 before opening them.** The running server has the v1 gene file: replaying works, but
Load or Simulate from an R10 run would refuse its v2 genome.

## What this rests on

* The STS3250 C002's and STS3215 C018's figures are unverified (ADR-100). The simulated servo's stiffness follows
  its stall torque.
* 45T and 30T/45T pairs are what-ifs: ratio and driver diameter changed in memory. Their belt lengths, derived C,
  fit and pulley masses are not checked. The 40T/80T pairs are real catalog entries with real belt checks, masses
  null.
* The belt's 44 N allowable working tension is the catalog's value for GT2 10 mm generic. A wider or stronger belt
  system would move the calm behaviours' limit on a new 1:1 carpus. That is a catalog question for the researcher.
