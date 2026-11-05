# Behaviours that stay safe for a minute: the coverage check (ADR-096)

2026-11-05. Session R6b in `projects/robot-calf-final`, after R6 (`perform_r6.md`) found that cells judged safe
over 24 s go over a limit within a minute (7 of 9 performances). Body, belts and component values not changed.

## The options, tried on the three R6 behaviours (`options_r6b.py`)

| option | calm | irregular | active | cost |
|---|---|---|---|---|
| (a) 60 s on three seeds (R6) | unsafe | unsafe | unsafe | 2.5x every play |
| (b) coverage (below) | unsafe | unsafe | unsafe | only candidates that pass their seeds |
| (c) steps left out, 60 s | **safe** | unsafe (already at 24 s) | **unsafe at 60 s** | as R5 |
| (b) + (c) | unsafe | unsafe | unsafe | |

(a) and (b) agree with what R6 saw. Leaving the steps out (c) is not enough on its own: the active behaviour
without steps still goes over at 60 s (fr.shoulder, in a turn-heavy minute).

**Coverage (b).** After a candidate has passed its seeds (24 s each), every state at least 5 % likely to be played
in a 60 s performance (`reach_probability`), and not played to its end on every seed, is forced into an extra play
on every seed: from the start if being first is most of its chance, otherwise after its likeliest predecessor among
likely states. The state is held for its 90th-percentile length, then the chain runs on for 6 s. Any limit over =
unsafe. The reach estimate matched R6: calm's `step_hr` 0.69 per minute, seen on 2 of 3 seeds.

A trial (3 x 14, 315 s against 180 s without coverage) found no safe candidate: of 3 that passed their seeds, two
failed only on their last forced state. **The researcher chose coverage with every state kept** (steps allowed
where they are safe in the chain), 20 x 28, seed 0, as R5.

## The run (`20261105-024409-evolve-7a63`, 2330 s on 7 workers; R5 took 1480 s)

* 560 candidates; 46 passed their seeds (R5: 30), 393 forced plays; **6 safe, in 6 cells** (R5: 30 in 16).
* Safe cells: quantity of motion 2.2-5.8 deg/s, regularity 0.26-0.76 (24 s descriptors). R5's calmest cells
  (1.3 deg/s) and most irregular (0.21) are gone: they relied on states that were never checked.
* What stops the rest: as R5, sustained servo torque (460), joint speed (260), sustained belt tension (247).
* **For the first time, a step and a trot are safe in context.** Two safe generators play `step_hl` (reach 0.6
  and 0.91 per minute); one plays the trot (reach 0.51). Each was forced in and judged on three seeds.

| cell | candidate | label | QoM, regularity (24 s) | margin | what it plays |
|---|---|---|---|---|---|
| (1,2) | `g013-014` | irregular | 2.45, 0.26 | +0.09 | shifts, stands, walks and turns, jumping between them |
| (1,4) | `g016-023` | calm | 2.16, 0.43 | +0.03 | shifts left-right with steps onto the left hind |
| (2,3) | `g002-021` | stepping | 3.38, 0.40 | +0.00 | walk / stand alternation, turns, a step |
| (2,6) | `g012-022` | trotting | 3.17, 0.70 | +0.03 | shifts and stands; sometimes a trot |
| (3,6) | `g006-024` | walking | 4.51, 0.61 | +0.03 | long walks broken by shifts |
| (3,7) | `g010-001` | active | 5.78, 0.76 | +0.01 | long walks and stands |

## Every safe cell played for a minute (`perform_r6.py`)

**15 of 18 minutes stay within every limit** (R6, before coverage: 2 of 9). None fell. The replays reproduce
the run's margins exactly.

| label | seed 0 | seed 1 | seed 2 | closest limit when within |
|---|---|---|---|---|
| calm | +0.03 | +0.03 | +0.03 | joint speed, hl.hock (105 of 135 deg/s) |
| irregular | +0.50 | +0.09 | +0.06 | joint speed / envelope, fl.carpus |
| stepping | **-0.64** | +0.12 | **-0.36** | joint speed, fl.carpus |
| trotting | +0.12 | +0.05 | +0.03 | joint speed, hl.hock / fl.carpus |
| walking | +0.04 | +0.04 | **-1.76** | joint speed, fr.carpus |
| active | +0.01 | +0.01 | +0.01 | joint speed, fl/fr.carpus |

Calm steps for 15-30 % of its minute within the limits; trotting trots for 19 % of seed 1's minute.

**The three that go over are all long holds.** Each failing episode was drawn longer than the length coverage
checked (its 90th percentile):

| performance | episode | drawn | typical | checked | limit |
|---|---|---|---|---|---|
| stepping, seed 0 | shift_hl at 45 s | 10.4 s | 5.0 s | 8.4 s | sustained torque, hr.hip_abd |
| stepping, seed 2 | turn at 27 s | 4.6 s | 2.0 s | 3.4 s | sustained torque, fl.shoulder |
| walking, seed 2 | shift_hl at 48 s | 3.6 s | 1.2 s | 2.0 s | sustained torque, fr.shoulder |

So coverage closes the gap of rare *states*. What is left is rare *lengths*: the controller draws durations from
a log-normal with no cap below 15 s. The fix is to cap each state's duration in the controller at the length
coverage checked, so a performance can never hold a state longer than was judged.

The 18 minutes are runs titled `R6 <label> ...` (Journal or Simulate > Runs).
