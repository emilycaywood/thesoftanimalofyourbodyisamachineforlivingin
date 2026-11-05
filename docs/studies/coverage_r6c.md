# Durations no longer than what was checked (ADR-097)

2026-11-05. Session R6c in `projects/robot-calf-final`, after R6b (`coverage_r6b.md`): coverage made 15 of 18
one-minute performances hold, and the 3 that went over held a state longer than coverage had checked it. Body,
belts and component values not changed.

## The change

Optimizer option `cap_durations` (with `coverage`): every state's duration in the `interpreted` controller is
capped at the length coverage checks, its 90th percentile (`checked_duration`, 1.67 x its typical length). A
longer draw is held at the cap. With the cap, coverage forces **every** likely state at exactly that length, even
one the seeds already played: a typical-length episode says nothing about the full cap. (R6b skipped such states,
and walking's failing shift was one.)

What it removes from the duration spread (log-normal, sd 0.4):
* 1 draw in 10 is held at the cap;
* the longest hold drops from about 2.5 x typical (1 draw in 100) to 1.67 x;
* the ratio of a long to a short hold (99th to 1st percentile) drops from 6.5 to 4.2;
* the mean duration drops 3.5 %.

On the six R6b cells (`options_r6b.py --tries=b_coverage_capped`): calm, irregular, stepping, trotting and active
pass; **walking is caught** (a forced step_hr after a turn, seed 2). Each passing candidate needs 18-21 forced
plays, about 3 min on one core.

## The run (`20261105-053201-evolve-e4c8`, 20 x 28, seed 0, 1715 s)

A first start stopped after 9 generations when the Claude session ended (`20261105-044708-evolve-e577`, marked
cancelled); this is the full re-run.

* 560 candidates; 20 passed their seeds, 202 forced plays; **4 safe, in 4 cells** (R5 16, R6b 6).
* **The safe cells reach further:** quantity of motion 2.1-10.0 deg/s, trunk up to 71 mm/s (R5's ceiling was
  6.9 deg/s, R6b's 5.8). Three of the four trot.
* What stops the rest: sustained servo torque (495), joint speed (346), sustained belt tension (283).

| cell | candidate | label | QoM, regularity (24 s) | margin | what it plays |
|---|---|---|---|---|---|
| (1,5) | `g002-016` | calm | 2.07, 0.54 | +0.16 | stand, shifts onto the left hind, short walks and turns, a step |
| (4,6) | `g018-025` | lively | 7.22, 0.67 | +0.02 | walks, trots, shifts and stands mixed |
| (4,7) | `g013-008` | walking | 6.93, 0.75 | +0.02 | walk / stand alternation, sometimes trot bouts |
| (6,8) | `g012-026` | trotting | 9.98, 0.88 | +0.05 | trot bouts broken by shifts and stands |

## Played for a minute: 12 of 12 hold

Every safe cell on all three seeds stays within every limit for 60 s (R6: 2 of 9, R6b: 15 of 18). None fell, and
the 24 s margins reproduce exactly. The closest limit is joint speed at a front carpus (89-106 of 135 deg/s), the
commanded-speed cap; calm has the most headroom (+0.17 to +0.38).

| label | seed 0 | seed 1 | seed 2 | QoM over the minute |
|---|---|---|---|---|
| calm | +0.38 | +0.17 | +0.17 | 2.2-2.6 |
| lively | +0.03 | +0.02 | +0.03 | 6.0-7.4 |
| walking | +0.02 | +0.02 | +0.02 | 6.5-8.5 |
| trotting | +0.05 | +0.05 | +0.05 | 9.4-12.0 |

## Played for five minutes (seed 0): 1 of 4 holds

The 60 s bound of `SimSettings` is the Simulate panel's slider range; the study script sets 300 s after
validation (no core change).

| label | 300 s margin | goes over at | episode | where | why it was not checked |
|---|---|---|---|---|---|
| lively | **+0.03** | - | - | - | - |
| calm | -1.32 | 233 s, 258 s | a turn after a walk; the stand after it | fl.shoulder | the turn was checked after a stand |
| walking | -0.64 | 285 s | a turn after a trot, the shift after it | hl.hip_abd | the turn was checked after a shift |
| trotting | -1.16 | 262 s | an 11 s turn | hr.hip_abd, then fl.shoulder | turning is 3 % likely in a minute, under the 5 % threshold |

None of these is a long hold: the cap works. What remains is the reach of the check itself:
* **Transitions:** coverage forces each state along one path. Coming out of a gait leaves the hooves spread
  (session Q), so the same turn can be within the limits after a stand and over them after a walk or trot.
* **Length:** the check covers states likely in 60 s. A 5-minute performance reaches states that a minute
  rarely does. `performance_s` can be set to 300 s; that is what it is for.

Next (R6d): cover the likely *transitions* (pairs), with `performance_s` at the performance's real length.

The plays are runs titled `R6c <label> ...` (Journal or Simulate > Runs): 12 of 60 s, 4 of 300 s.
