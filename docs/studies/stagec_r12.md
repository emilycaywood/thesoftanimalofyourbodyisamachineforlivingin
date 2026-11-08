# R12 / Stage C — every front body gets behaviours made for it (ADR-105)

Session R12, 2026-11-07/08. Simulation only; every part is unverified. The working body, catalogs, component values
and `verified` flags were not changed.

**Question.** Stage B (run `20261107-043030-evolve-c02e`, ADR-104) ranked bodies by R6c's and R7's 11 behaviours,
which were evolved for today's working body. Which body is best when each one has behaviours evolved for it?

**Method** (`docs/studies/stagec_r12.py`; ADR-105):

* One behaviour-diversity run per body (`map_elites_behaviour`, R7's run `4237` settings: 15 x 28, 24 s per seed,
  coverage at p 0.05 over 60 s, capped durations, variation within a movement, `variation_weight` 0.5, margin 0.2,
  seed 0), started from the stored candidate's body (`run_evolve candidate=...`, new) and seeded with R7's 11 safe
  generators. The working body got the same run, so it is compared like for like.
* Each body's safe cells (one elite per cell) played for **60 s on seeds 0-2** with the Stage B run's own R11c suite
  (friction 0.7-1.1, mass x0.95-1.05, torque-speed servos, margin 0.2), plus Stage B's screen (trot grid, walk, turn,
  lie_rise). The screens were all replayed from the play cache (0 new plays), so the bodies are bit for bit the ones
  Stage B judged.
* Ranking fixed before the results (ADR-105 point 5): behaviours that hold a minute on all three seeds, then share of
  minutes held, then range of quantity of motion held, then trot, then lie_rise.

| run | body | time |
|---|---|---|
| `20261108-000329-evolve-19d0` | working body | 45 min (alone on the CPU) |
| `20261107-205208-evolve-5222` | g020-008-r01 | 63 min |
| `20261107-205228-evolve-15de` | g012-009 | 125 min |
| `20261107-215523-evolve-883b` | g011-003 | 81 min |
| `20261107-225659-evolve-5994` | g009-000 | 67 min |
| `20261107-231639-evolve-74bd` | g007-002 | 84 min |

Two runs shared the CPU at a time (7 workers each). Judging took 14 min on 14 workers. Runs are titled
`R12 Stage C <body>` in Journal > Runs, so they can be replayed. A trial run, `20261107-204744-evolve-e7dd` ("R12
trial", 1 x 4), is also in the project.

## Result

| rank | body | safe cells | behaviours held 3/3 | held 3/3 with margin >= +0.1 | minutes | median margin of held | QoM held deg/s | trot mm/s | lie_rise | walk | turn | cost | Stage B minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | g007-002 | 25 | **23** | 6 | 72/75 | +0.03 | 0.5-11.9 | none | -1.44 | -0.32 | -0.25 | 1.58 | 33/33 |
| 2 | g009-000 | 17 | 16 | **15** | 50/51 | +0.35 | 1.1-11.9 | 394 | -3.00 | -0.12 | -0.08 | 1.83 | 32/33 |
| 3 | g012-009 | 16 | 14 | 14 | 44/48 | **+0.44** | 0.5-11.7 | 414 | -0.24 | -0.48 | -0.08 | 2.37 | 33/33 |
| 4 | g011-003 | 12 | 11 | 10 | 35/36 | +0.30 | 0.7-11.9 | 410 | -3.00 | -0.03 | -0.04 | 2.08 | 32/33 |
| 5 | working | 12 | 11 | 3 | 35/36 | +0.03 | 1.2-12.0 | none | -3.00 | -0.13 | -0.25 | 0.00 | 32/33 |
| 6 | g020-008-r01 | 11 | 8 | 6 | 29/33 | +0.32 | 1.7-11.7 | **530** | **-0.16** | -0.52 | -0.08 | 2.12 | 33/33 |

Margins are headroom over the limits already lowered by 0.2 (0 = exactly at margin 0.2). "With margin >= +0.1" was
added after the results (a post-hoc reading): it counts the behaviours that still hold if every limit were 10 % lower
again. Every body is on the Pareto front over (behaviours held, trot, lie_rise, -cost), so the front does not choose.
Full per-behaviour tables: `stagec_r12_tables.md`; data: `stagec_r12.json`.

**What it says.**

1. **Stage B's winner is last when bodies get their own behaviours.** g020-008-r01 keeps the fastest trot and the
   best lie_rise, but its own run found the fewest safe cells (11), and 3 of them go over in a minute (sustained servo
   torque at the hip ab/ad, which stays on the C018, and at its C002 carpi on 1:1 80T/80T). Its 33/33 in Stage B came
   from the working body's 11 behaviours, which happen to suit it.
2. **By the rule fixed beforehand, g007-002 wins** (23 behaviours that hold a minute, 72 of 75 minutes, the widest
   range from a near-still shifting stand at 0.5 deg/s to a trot-walk at 11.9). It is the body nearest the working
   body in hardware (C002 on hocks and shoulders only; carpi on the C018 at 40T/80T; no quick trot), and like the
   working body it is **bounded by carpus joint speed**: almost every one of its behaviours sits at the
   margin-capped speed, with headroom +0.00 to +0.03. With 10 % less headroom it keeps 6 behaviours; the working body
   3.
3. **The bodies with C002 carpi (g009-000, g012-009, g011-003) hold their behaviours with room to spare**
   (median +0.30 to +0.44). Asked for a little more headroom they keep almost all of them: g009-000 15 of 16, g012-009
   14 of 14. They also trot at 394-414 mm/s. What stops them is the front-left carpus belt (sustained tension, 8 plays,
   g009-000 and g011-003), the hip ab/ad torque and the front shoulders' torque.
4. **lie_rise** is unchanged by new behaviours (it is a screen play): only g020-008-r01 (-0.16) and g012-009 (-0.24)
   come near. No body holds it.
5. One diversity run per body, seed 0: the counts of safe cells carry run-to-run noise that was not measured
   (R7-type runs differ by a few cells between seeds). Differences of 1-3 behaviours (g009-000 against g012-009,
   g011-003 against the working body) are within that; 23 against 11 is not, and neither is the collapse at +0.1.

**Reading.** If "most behaviours, at margin 0.2 exactly" is the criterion, g007-002 wins, and the working body is about
as good as anything with old carpi. If the criterion is behaviours that keep holding when the model is a little wrong
(parts are unverified, the servos' thermal and current values are defaults), **g009-000 is first** (15 robust
behaviours, 394 mm/s trot, 4 new servos, cost 1.83) and **g012-009 second** (14, 414 mm/s, lie_rise -0.24, 6 new
servos, cost 2.37). I recommend reading the result the second way for a body that is going to be built, and keeping
the pre-registered ranking as the formal answer of this session: the choice is Emily's.

## The bodies (from Stage B, ADR-104)

| body | hardware | lengths |
|---|---|---|
| g007-002 | C002 on hocks + shoulders; stifle 40T/80T 444; hock 40T/60T 400; carpus 40T/80T 640; shoulder direct; stifle spring lower anchor moved | rear cannon 232, upper leg 344 |
| g009-000 | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 48T/80T 640; springs at hip ab/ad, stifle, hock, shoulder | within 10 % of today |
| g012-009 | C002 on hocks + shoulders + carpi; stifle 40T/60T 444; hock 40T/80T 450; carpus 80T/80T 640; springs at all five sites (carpus added) | within 10 % of today |
| g011-003 | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 45T/80T 640; +carpus spring, no shoulder spring | rear cannon 226, front cannon 247 |
| g020-008-r01 | C002 on hocks + shoulders + carpi; stifle and hock 40T/60T; carpus 80T/80T 640 | within 2.5 % of today |

Belt loads from each body's own behaviours (peak / largest mean, N): g009-000 stifle 108/22, hock 64/18, carpus 70/20;
g012-009 95/25, 67/17, 66/12; g007-002 113/24, 88/20, 84/15; working body 149/29, 76/18, 100/19. All under the
breaking check (172 N, R9); the means are what the sustained-tension limit judges.

## Sheets

`docs/studies/sheets_r12/C1_g007_002`, `C2_g009_000`, `C3_g012_009` (`_geometry.csv` for Rhino/Grasshopper,
`_parts.json`). The geometry is identical to their `sheets_r11c/B20_*` files (checked); the parts lists add a
`stage_c` block: rank, the behaviour run, each behaviour's ref (`<run>:<candidate>`) and minutes, the screen, what
stopped the plays, belt loads and spring peaks from the body's own behaviours.

## Caveats

* Simulation only; every pulley and the C002 are `verified: false`; pulley masses are not used (ADR-103).
* One run per body; noise in safe-cell counts unmeasured.
* "Stopped by" counts include the screen plays (the trot grid and lie_rise), as `hardware.summarise` reports them.
* Variation within movements stays small, as in R7 (variation amount about 0.08).
* The trot objective is still the grid's ceiling for g020-008-r01 (ADR-104).
