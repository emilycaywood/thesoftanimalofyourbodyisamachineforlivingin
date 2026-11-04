# Behaviour diversity on the working body: the first full run (ADR-094)

2026-11-04. Run `20261104-181642-evolve-2650` in `projects/robot-calf-final`:
* optimizer `map_elites_behaviour`, preset `diversity`, 20 generations x 28, seed 0;
* scripts `diversity_trial.py`, read by `diversity_archive.py`;
* working body: the wide-block body (ADR-092);
* axes: quantity of motion 0-15 deg/s (10 cells) x tempo regularity 0-1 (10 cells);
* each candidate: 24 s on three seeds, friction 0.7-1.1 and mass x0.95-1.05, every limit at margin 0.2.

**Wall clock 1480 s** (estimate 32 min), 7 workers.

## What it found

* **560 candidates evaluated; 30 stayed within every limit on all three seeds (5 %).** They fill **16 of the 58
  cells** reached (the other 42 cells hold candidates just over a limit).
* Safe cells grew steadily: 3 after generation 0, 9 by 7, 16 by 15. Coverage rose to 58 % and was still
  rising, so a longer run would likely find more.
* **The safe region:** quantity of motion 1.3-6.9 deg/s, tempo regularity 0.21-0.80. Beyond about 7 deg/s,
  nothing is within the limits.
* **What stops the rest** (seed limits over, across all unsafe candidates): sustained servo torque 472, joint
  speed 275, sustained belt tension 245, envelope 70, stall 14. Sustained torque, the servos held near their
  rated torque, is what bounds vigorous movement on this body: the motors, as in session R's steps 1-2.
* **Which movements become safe in a sequence:**

| state | in safe candidates (of 30) | in unsafe ones (of 530) |
|---|---|---|
| weight shift (hl / hr) | 29 / 25 | 342 / 379 |
| stand | 28 | 441 |
| walk | 27 | 404 |
| turn | 25 | 375 |
| step (hl / hr) | 8 / 5 | 137 / 111 |
| trot | 1 | 156 |

  The steps appear in a few safe sequences, but only briefly. The trot appears in one safe sequence and is
  otherwise never safe. Neither had a setting within the limits on its own (ADR-093).

## The safe cells

| cell (QoM, regularity) | QoM deg/s | regularity | unpredictability | margin | what it plays |
|---|---|---|---|---|---|
| (0,4) | 1.37 | 0.46 | 0.05 | +0.71 | weight shifts left-right, long holds |
| (0,5) | 1.30 | 0.59 | 0.22 | +0.76 | the same, standing between |
| (1,4) | 2.68 | 0.42 | 0.43 | +0.21 | stand, walk, shifts, turns, mixed |
| (1,5) | 2.21 | 0.51 | 0.46 | +0.12 | stand, walk, turn, a right step |
| (1,6) | 2.78 | 0.63 | 0.46 | +0.00 | stand and short walks alternating |
| **(2,2)** | 3.93 | **0.21** | **0.74** | +0.08 | irregular: shifts, turns, stands, a left step |
| (2,3) | 4.26 | 0.37 | 0.77 | +0.05 | long walks broken by shifts |
| (2,4) | 3.73 | 0.45 | 0.19 | +0.22 | walk / stand, walk / stand |
| (2,5) | 3.11 | 0.54 | **0.78** | +0.03 | walk, stand, turn, shifts: jumps anywhere |
| (2,8) | 3.92 | **0.80** | 0.28 | +0.03 | shifts with a turn, the most rhythmic |
| (3,3) | 4.63 | 0.33 | 0.77 | +0.02 | step, stand, walk, shift |
| (3,4) | 4.68 | 0.45 | 0.61 | +0.03 | walk / stand, then a shift and a step |
| (3,5) | 5.37 | 0.50 | 0.67 | +0.02 | long walks, shifts |
| (3,6) | 5.65 | 0.62 | 0.70 | +0.00 | walk, stand, long turns |
| (4,4) | 6.34 | 0.41 | 0.53 | +0.03 | turns and walks, shifts, no standing |
| **(4,6)** | **6.86** | 0.67 | 0.68 | +0.00 | the most active: walk, stand, long turns, shifts |

Unpredictability (0-1, how hard the next movement is to guess) reaches 0.78 within the limits. The most
unpredictable safe sequences have low sharpness (about 1.4-3.0): they jump between any movements rather than
wander between neighbours. The calm cells are near-fixed alternations (0.05-0.22).

Every active safe cell (quantity of motion above about 3 deg/s) sits within 0.08 of the margin: the motors are
near their limit whenever the body does much.

Three of the most different safe cells, for playing as 60 s performances:
* **(0,5) calm** (`g011-020`): weight shifts left and right with standing between. Margin +0.76.
* **(2,2) irregular** (`g014-007`): regularity 0.21, unpredictability 0.74. Shift > stand > turn > shift > turn >
  stand > shift > stand > shift > step.
* **(4,6) active** (`g015-016`): 6.9 deg/s, trunk 50 mm/s. Walk > stand > turn > shift > turn.
