# Three evolved behaviours played for a minute (ADR-095)

2026-11-04. From run `20261104-181642-evolve-2650` (ADR-094, `diversity_r5.md`) in `projects/robot-calf-final`,
three safe cells played for 60 s on the run's three seeds (friction 0.7-1.1, mass x0.95-1.05), every limit at
margin 0.2, falls reported. Script `perform_r6.py`; about 3 min of physics in all. Body, belts and component values
not changed.

**The replay reproduces the run.** The run's own 24 s task, re-run, gave the stored margins on every seed to the
fourth decimal, and the same controller parameters. The first 24 s of each 60 s performance has the same margin as
the 24 s evaluation: a minute starts exactly where the run's evaluation did.

## The nine performances

| behaviour | seed | 60 s margin | within? | closest limit over the minute | first 24 s | stored as run |
|---|---|---|---|---|---|---|
| calm (0,5) `g011-020` | 0 | +0.76 | yes | joint speed, hl.hock (26 of 135 deg/s) | +0.76 | `20261105-001129-sim-31a7` |
| | 1 | -3.00 | no | sustained servo torque, fl.shoulder (100 % of a 2 s window) | +0.76 | `20261105-001143-sim-b3be` |
| | 2 | -1.24 | no | sustained servo torque, fl.shoulder | +0.77 | `20261105-001158-sim-0f67` |
| irregular (2,2) `g014-007` | 0 | -0.04 | no | sustained servo torque, hr.hip_abd | +0.30 | `20261105-001229-sim-011e` |
| | 1 | -0.16 | no | sustained belt tension, fr.carpus | +0.09 | `20261105-001244-sim-75f4` |
| | 2 | +0.08 | yes | sustained belt tension, fr.carpus (23 % of a window) | +0.08 | `20261105-001258-sim-c447` |
| active (4,6) `g015-016` | 0 | -0.40 | no | sustained servo torque, fr.shoulder | +0.02 | `20261105-001332-sim-8412` |
| | 1 | -0.84 | no | sustained servo torque, fr.shoulder | +0.00 | `20261105-001347-sim-ac0f` |
| | 2 | -3.00 | no | sustained servo torque, fr.shoulder (100 % of a window) | +0.03 | `20261105-001401-sim-7852` |

No performance fell. **Two of nine stay within every limit for the minute** (calm seed 0, irregular seed 2).

## 60 s does not stay within what 24 s did

Every seed was within the limits over its first 24 s, as in the run. Seven of nine go over later. In each, the
trouble starts in a **step**:

* calm: `step_hr` at 47 s (seed 1) and 55 s (seed 2) takes **fl.shoulder** over sustained torque. In seed 1 the
  following weight shift stays over for its whole 8 s (-3.0): the body does not come back from the step.
* irregular: a `step_hl` at 21-27 s takes the **fr.carpus belt** over (seed 1); seed 0 goes over at the hr hip
  ab/ad in a stand at 58 s after four steps.
* active: `step_hl` (seeds 0, 1) and a weight shift just before one (seed 2) take **fr.shoulder** over.

Neither step had a setting within the limits on its own (ADR-093). In 24 s they came up rarely: the calm cell's
evaluation never played one; in a minute it plays one on two seeds of three. **A 24 s evaluation on three seeds
under-samples a sequence's rare states**, so a cell judged safe can hold a movement that is not.

The closest limit when within: joint speed at the hocks and carpi (the cap of 0.76 of the servo's speed), and
sustained belt tension at the fr.carpus for the irregular cell.

## Do the behaviours keep their character over a minute?

| behaviour | 24 s (mean of seeds): QoM, regularity | 60 s per seed: QoM, regularity | trunk mm/s |
|---|---|---|---|
| calm | 1.30, 0.59 | 1.71-2.23, 0.56-0.62 | 20-25 |
| irregular | 3.93, 0.21 | 3.55-4.33, 0.16-0.20 | 31-40 |
| active | 6.86, 0.67 | 6.12-7.11, 0.42-0.62 | 50-52 |

The calm one moves one cell up (the steps); the active one is less rhythmic over a minute. What each plays
(share of the minute):
* calm: almost only weight shifts left-right, 11-12 of them, 4-6 s each; a stand on one seed, a step at the end on
  two.
* irregular: shifts 37-56 %, steps 9-37 %, turns 6-20 %, walk 2-23 %, stands 4-8 %; 19-21 episodes, no pattern.
* active: turning 44-66 % of the minute, shifts 19-39 %, steps 8 %, walks 2-6 %.

Whether any of this looks organic is for the researcher to judge in the viewport: Journal (or Simulate) > Runs,
rows titled `R6 ...`.
