# R11: hardware chosen by the loads of behaviour (ADR-102)

Session R11, 2026-11-06. Project `projects/robot-calf-final`. The working body, component values, `verified`
flags and catalogs were not changed. Nothing installed.

## What was built

* Optimizer `map_elites_hardware` and preset `hardware` (`core/calflab/evolve/hardware.py`,
  `config/fitness/hardware.yaml`). The servo per joint pair and each belt drive (system, pulley pair, length:
  catalog ids) evolve with the geometry. C is derived; a body that fails a belt check or the servo budget (four
  STS3250 C002s) is rejected before any play and recorded as infeasible.
* Each body: a screen (quick trot grid 0.4-0.8 s x stride 0.5-2.0, walk, turn, `lie_rise`), then R6c's and R7's 11
  safe behaviours for 60 s if the best screen play's worst-seed margin is at least -0.25. Margin 0.2, three
  randomised seeds. Plays cached per body (`projects/robot-calf-final/.cache/hardware`).
* Archive: behaviour minutes held (of 33) x fastest trot within limits; Pareto front adding a hardware cost index.
  Per body: the binding limit per joint and how many plays each joint/limit stopped.
* Scripts: `hardware_r11.py` (estimate, seeds, trial, table through the lab), `store_r11.py` (plays as runs with
  compare links). All tables of the judged bodies: `hardware_r11_tables.md`.

## Runs

* `20261106-044751-evolve-dbf1`: one generation, what-ifs on, judging the working body, R9's best and R10's 1:1 45T
  body (8.5 min, 3 bodies fully played).
* `20261106-045624-evolve-59fd`: the trial, 3 generations x 7, catalog only (what-ifs off), seeded with the working
  body and R10's 40T/80T body (18.4 min; 21 bodies judged, 13 passed the screen, 235 draws rejected before a play).

## The reference bodies, through the new core path

The numbers agree with R9 and R10's scripts (20/33, 26/33, 28/33, 394 and 419 mm/s).

| body | minutes held | fastest trot within | walk | turn | lie_rise | cost index | stopped most by |
|---|---|---|---|---|---|---|---|
| working body (today) | **32**/33 | none in the quick grid | -0.13 | -0.25 | -3.00 | 0 | fl.carpus joint speed (8 plays), fl.shoulder sustained torque (4) |
| R10 40T/80T (catalog: new hocks + carpi, all three drives 40T/80T) | 28 | 63 mm/s (0.8 s / 1.0) | -0.24 | -0.20 | -2.80 | 1.58 | fl.carpus sustained belt tension (14), fl.shoulder torque (5) |
| R10 1:1 45T (**what-if**: new hocks + carpi) | 26 | **419** mm/s (0.5 s / 2.0) | -0.24 | -0.20 | -2.88 | 2.33 | fr.carpus belt (6), hl.hip_abd torque (3) |
| R9 best (**what-if**: new hip ab/ad + hocks, carpus 1:1 45T old servo) | 20 | 394 mm/s (0.5 s / 2.0) | **+0.21** | **+0.09** | -2.72 | 2.33 | fl.shoulder torque (6), fr.carpus torque (6) |

Costs: the three changed bodies each use four new STS3250 C002s (the budget) and 40T and 80T pulleys (two new
sizes); the what-ifs add 45T (a third size, not in a catalog). Mass 1382 g against 1304 g (servos only; pulley
masses are not entered). The new servos' current peaks at 2.0-3.7 A (sum, known servos only); the C018's current is
unknown. New servo cost unknown (no cost entered for the C002).

**Pareto front** (minutes, trot speed, cost): the working body, R10 40T/80T and R10 1:1 45T. R9's best is dominated by
R10's 1:1 45T body (fewer minutes, slower, same cost) but is the only body whose walk and turn hold.
**No body holds `lie_rise`** (front shoulders' sustained torque, -2.7 to -3.0).

## The trial

* Nothing new beat the seeds. The best new bodies: 15/33 minutes (carpus 40T/80T, old servos, geometry moved) and
  2/33 (four new servos, hock and carpus 40T/80T).
* **Why: the behaviours were evolved for today's geometry.** Geometry mutations put the stifle belts (sustained
  tension) and the hip ab/ad (sustained torque) over in R6c's and R7's behaviours, whatever the servos.
* 235 draws were rejected before any play (each recorded with its reason): the stifle range against the hock belt
  clearance (88), belt drives at the hock (72), stifle (52) and carpus (39), the servo case off its segment (43).
  Most come from geometry and belt length moving together.
* The quick grid (0.4-0.8 s) gives catalog bodies without a 1:1 carpus little trot speed: only R10's 40T/80T body
  trots within (0.8 s).

## Cost and budget

Measured: about 170 s wall per fully played body and about 15 s per body screened out, on 7 workers (the trial
averaged 53 s per body, since broken bodies fall early). Cached plays cost nothing. `estimate_evolve` now scales its
single-process probe by 2 for parallel workers (`PARALLEL_SLOWDOWN`); it gives an upper bound.

| run | bodies | wall time on 7 workers |
|---|---|---|
| 10 x 14 | 140 | 2-6.5 h |
| 20 x 14 | 280 | 4-13 h |
| 30 x 14 | 420 | 6-20 h |

The lower end is the trial's mix; the upper end is every body fully played without a fall.

## Stored runs

`R11 R10-40T80T <behaviour>: 60 s, seed N` (33 runs): R10's 40T/80T body. Its genome holds the servo and belt genes, all
in the catalog, so *Load* or *Simulate* from it gives that body. Compare links against today's body:
`store_r11.md`. R10's 1:1 45T body is already stored as `R10 what-if ...` runs (`compare_r10.md`).
