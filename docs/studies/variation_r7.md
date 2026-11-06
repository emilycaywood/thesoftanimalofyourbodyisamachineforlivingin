# Movement that varies within a movement (ADR-098)

2026-11-05. Session R7 in `projects/robot-calf-final`, after R6c (`coverage_r6c.md`). Body, belts and component
values not changed.

## What changed

The `interpreted` controller can now vary a movement below the primitive (`calflab.control.variation`), as genes of
the behaviour generator (optimizer option **vary within**):

* **posture drift and small noise**: the trunk lowered (up to 15 mm) and the weight moved over the hooves
  (lateral and fore-aft), from poses solved on the body with every hoof planted; slow random drift plus a small
  faster noise, bounded. The head too, on a body with neck motors: **the feral calf has none**, so its head
  does not move;
* **cycle-to-cycle variation**: every cycle at its own tempo (up to about 28 % faster or slower) and amplitude
  (up to 25 % larger or smaller);
* **switches** up to 15 % of a cycle before an all-hooves-down window, and a **cross-fade** whose length varies
  (up to x / 2.2);
* durations stay capped (ADR-097);
* **coverage plays the extremes** of the state it checks: the weight to all four corners at full crouch with the
  noise at its fastest, the fastest and slowest cycles at the largest amplitude, the earliest switch, the shortest
  cross-fade in and the longest out.

87 genes on the eight-state palette (R6c: 53). Old runs replay bit for bit (checked on R6c's trotting cell).

## First run: no safe cell (`20261105-221840-evolve-02e3`, 40 x 28, 2780 s)

Your budget, from random generators as R6c. 1120 candidates; 29 passed their three seeds; **none survived the
forced plays** (sustained servo torque 21, joint speed 8, belt 7). Three findings (`rejudge_r7.py`, `vary_r6c_r7.py`):

1. The forced plays put *every* state into its extremes, not only the one checked: stricter than any
   performance. Changed (only the checked state plays its extremes). Re-judged, the 29 were still unsafe.
2. The same 29 without their variation genes are unsafe too: the search had not found sequences that hold. With
   34 more genes mutated alongside, offspring of near-safe parents land further away.
3. **Nothing rewarded variation**, so evolution had no reason to grow it. Added a fitness term (weight 0.5, the
   unpredictability's).

R6c's four safe generators with every variation gene at 10 % of its range all stay safe with coverage at the
extremes; at 30 % all four go over on their seeds.

## Second run: seeded from R6c (`20261105-232649-evolve-4237`, 15 x 28, 2355 s)

Starts from R6c's four safe generators with 10 % variation; variation in the fitness (weight 0.5).

* 420 candidates, 60 passed their seeds, 652 forced plays, **11 safe in 7 cells** (R6c: 4).
* Quantity of motion 2.1-10.0 deg/s (R6c 2.1-10.0); three new cells: (2,5) ambling, (5,7), (5,8).
* **The variation that holds is small**: variation amount 0.07-0.10 of 1, where it started. Within margin 0.2 and
  coverage at the extremes, evolution did not raise it. That is about +-2.5 % tempo and amplitude per cycle, cross-fades
  varying by about +-8 %, and a posture drift of a fraction of a millimetre: invisible as posture.

| cell | candidate | label | QoM, regularity (24 s) | margin | plays |
|---|---|---|---|---|---|
| (1,5) | `g000-000` | calm | 2.06, 0.56 | +0.08 | R6c calm + variation |
| (2,5) | `g009-004` | ambling | 3.72, 0.54 | +0.01 | shifts, stand, walk |
| (4,6) | `g000-001` | lively | 7.16, 0.68 | +0.02 | R6c lively + variation |
| (4,7) | `g008-000` | walking | 6.72, 0.76 | +0.08 | shifts, stand, trot, walk |
| (5,7) | `g006-013` | trot-walk | 8.37, 0.76 | +0.00 | shifts, stand, trot, walk |
| (5,8) | `g001-015` | trot-shift | 8.06, 0.85 | +0.12 | shifts, stand, trot |
| (6,8) | `g000-003` | trotting | 9.96, 0.88 | +0.01 | R6c trotting + variation |

## Played for a minute: 20 of 21 hold

Every safe cell on all three seeds (`perform_r6.py --tag=R7`; the 24 s margins reproduce exactly). One goes over:
**walking, seed 0**, at 50 s in an 8.7 s `step_hr`, a state 1.4 % likely in a minute (under coverage's 5 %), so never
checked. That is the rare-state gap of R6c, not a variation extreme.

## Movement features against R6c (`compare_r7.py`)

Means over the minute barely move: quantity of motion, tempo regularity, jerk, expressive range and the posture
spread (trunk height, roll and pitch while standing or shifting) are within a few percent of R6c's for the same
sequences.

What changes is **how alike two plays of the same state are**. *Repeat dissimilarity*: the RMS difference of the
joint angles over the first 2 s of two episodes of one state, over the movement's own RMS; 0 = an exact repeat.

| same sequence | R6c (seeds 0 / 1 / 2) | R7 | per state, R6c -> R7 |
|---|---|---|---|
| calm | 0.08 / 0.06 / 0.09 | 0.92 / 0.79 / 0.23 | walk 0.007 -> 0.38; shift 0.11-0.19 -> 0.31-1.19 |
| lively | 0.02 / 0.19 / 0.03 | 0.96 / 1.35 / 0.80 | trot 0.007-0.011 -> 0.46-1.20; walk 0.03 -> 0.47-1.46 |
| trotting | 0.10 / 0.06 / 0.12 | 0.39 / 0.31 / 0.48 | trot 0.025-0.075 -> 0.12-0.22 |

In R6c a walk or a trot repeated itself almost exactly (0.007-0.03). In R7 the repeats differ by about as much as
the movement itself, mostly in **timing**: a few percent of tempo per cycle moves the phase, so two walks drift
apart within a couple of seconds. The variation is felt as timing more than as posture.

## Five minutes (seed 0): the R6d gap, neither better nor worse

| label | R7 300 s | R6c 300 s | where it goes over |
|---|---|---|---|
| lively | **+0.025** | +0.03 | - |
| trot-walk | **+0.004** | (new) | - |
| trot-shift | **+0.121** | (new) | - |
| calm | -0.36 | -1.32 | 228 s, walk / stand / walk / turn |
| trotting | -1.24 | -1.16 | 120 s, trot, stand, then shifts |
| ambling | -0.32 | (new) | 240 s, a walk into a trot |
| walking | -2.52 | (new) | 50 s, the rare step |

3 of 7 hold (R6c 1 of 4). Like for like, the outcome is the same: lively holds in both, calm and trotting go over
in both, in transitions and rare states as in R6c. None of the failures is at a variation extreme. **The variation
neither closes nor widens R6d's gap**; covering transitions (R6d) is still what 5 minutes need.

## Watch them side by side

Start the lab (`.\calflab.ps1 lab --project projects/robot-calf-final --port 8020`), then open a row. Each side is
the lab replaying one run (switch either side to Simulate or Journal for a larger viewport). For "same sequence"
rows both play the **same states in the same order** (the variation draws from its own random stream); only the
movement within them differs.

| R7 | seed | left side | R7 margin | repeat dissimilarity (R7 vs R6c) | link |
|---|---|---|---|---|---|
| calm | 0 | same sequence | +0.428 | 0.921 vs 0.083 | [open](http://localhost:8020/compare.html?a=20261105-060126-sim-92ff&b=20261106-000700-sim-4321&la=R6c+calm+s0&lb=R7+calm+s0) |
| calm | 1 | same sequence | +0.160 | 0.786 vs 0.057 | [open](http://localhost:8020/compare.html?a=20261105-060139-sim-d170&b=20261106-000714-sim-abbd&la=R6c+calm+s1&lb=R7+calm+s1) |
| calm | 2 | same sequence | +0.162 | 0.23 vs 0.094 | [open](http://localhost:8020/compare.html?a=20261105-060152-sim-4681&b=20261106-000727-sim-6f10&la=R6c+calm+s2&lb=R7+calm+s2) |
| lively | 0 | same sequence | +0.026 | 0.96 vs 0.019 | [open](http://localhost:8020/compare.html?a=20261105-060222-sim-f788&b=20261106-000758-sim-c2be&la=R6c+lively+s0&lb=R7+lively+s0) |
| lively | 1 | same sequence | +0.025 | 1.351 vs 0.187 | [open](http://localhost:8020/compare.html?a=20261105-060235-sim-e99f&b=20261106-000811-sim-6c60&la=R6c+lively+s1&lb=R7+lively+s1) |
| lively | 2 | same sequence | +0.027 | 0.797 vs 0.026 | [open](http://localhost:8020/compare.html?a=20261105-060248-sim-9ee5&b=20261106-000825-sim-a3e4&la=R6c+lively+s2&lb=R7+lively+s2) |
| trotting | 0 | same sequence | +0.017 | 0.388 vs 0.1 | [open](http://localhost:8020/compare.html?a=20261105-060413-sim-3bbd&b=20261106-000952-sim-058e&la=R6c+trotting+s0&lb=R7+trotting+s0) |
| trotting | 1 | same sequence | +0.017 | 0.314 vs 0.062 | [open](http://localhost:8020/compare.html?a=20261105-060426-sim-bf75&b=20261106-001005-sim-195e&la=R6c+trotting+s1&lb=R7+trotting+s1) |
| trotting | 2 | same sequence | +0.039 | 0.475 vs 0.117 | [open](http://localhost:8020/compare.html?a=20261105-060439-sim-0b66&b=20261106-001019-sim-d7ea&la=R6c+trotting+s2&lb=R7+trotting+s2) |
| walking | 0 | R6c walking | -2.520 | 0.177 vs 0.027 | [open](http://localhost:8020/compare.html?a=20261105-060317-sim-e6ea&b=20261106-000855-sim-abe9&la=R6c+walking+s0&lb=R7+walking+s0) |
| walking | 1 | R6c walking | +0.299 | 0.506 vs 0.289 | [open](http://localhost:8020/compare.html?a=20261105-060331-sim-2d64&b=20261106-000908-sim-c9e2&la=R6c+walking+s1&lb=R7+walking+s1) |
| walking | 2 | R6c walking | +0.287 | 0.27 vs 0.025 | [open](http://localhost:8020/compare.html?a=20261105-060344-sim-e33a&b=20261106-000922-sim-285f&la=R6c+walking+s2&lb=R7+walking+s2) |
| trot-walk | 0 | R6c walking | +0.004 | 1.122 vs 0.027 | [open](http://localhost:8020/compare.html?a=20261105-060317-sim-e6ea&b=20261106-001049-sim-df6a&la=R6c+walking+s0&lb=R7+trot-walk+s0) |
| trot-walk | 1 | R6c walking | +0.004 | 0.693 vs 0.289 | [open](http://localhost:8020/compare.html?a=20261105-060331-sim-2d64&b=20261106-001103-sim-b188&la=R6c+walking+s1&lb=R7+trot-walk+s1) |
| trot-walk | 2 | R6c walking | +0.004 | 0.839 vs 0.025 | [open](http://localhost:8020/compare.html?a=20261105-060344-sim-e33a&b=20261106-001116-sim-db3d&la=R6c+walking+s2&lb=R7+trot-walk+s2) |
| trot-shift | 0 | R6c trotting | +0.178 | 0.174 vs 0.1 | [open](http://localhost:8020/compare.html?a=20261105-060413-sim-3bbd&b=20261106-001146-sim-0e1e&la=R6c+trotting+s0&lb=R7+trot-shift+s0) |
| trot-shift | 1 | R6c trotting | +0.176 | 0.439 vs 0.062 | [open](http://localhost:8020/compare.html?a=20261105-060426-sim-bf75&b=20261106-001159-sim-2ff5&la=R6c+trotting+s1&lb=R7+trot-shift+s1) |
| trot-shift | 2 | R6c trotting | +0.127 | 0.39 vs 0.117 | [open](http://localhost:8020/compare.html?a=20261105-060439-sim-0b66&b=20261106-001213-sim-c8b8&la=R6c+trotting+s2&lb=R7+trot-shift+s2) |
| ambling | 0 | R6c calm | +0.029 | 0.358 vs 0.083 | [open](http://localhost:8020/compare.html?a=20261105-060126-sim-92ff&b=20261106-001243-sim-fc58&la=R6c+calm+s0&lb=R7+ambling+s0) |
| ambling | 1 | R6c calm | +0.029 | 0.389 vs 0.057 | [open](http://localhost:8020/compare.html?a=20261105-060139-sim-d170&b=20261106-001256-sim-aaea&la=R6c+calm+s1&lb=R7+ambling+s1) |
| ambling | 2 | R6c calm | +0.030 | 0.159 vs 0.094 | [open](http://localhost:8020/compare.html?a=20261105-060152-sim-4681&b=20261106-001310-sim-5890&la=R6c+calm+s2&lb=R7+ambling+s2) |

The 5-minute plays are runs `R7 <label> ... 300 s, seed 0` (Journal or Simulate > Runs).

## Not done

* **Clips from your footage as states** (optional): not added. The interpretation's feasible versions are
  quasi-static sways (ADR-084), which the weight drift now covers in kind.
* Larger variation within margin 0.2: the search held it at about 8 % of the ranges. A run that keeps the
  sequence genes fixed and evolves only the variation genes would show how far each R6c behaviour can vary.
