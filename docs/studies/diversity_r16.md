# R16: what g020-008-r01 can do (a diversity search on one body, and probes)

Session R16, 2026-11-11, ADR-112. **The body is fixed:** g020-008-r01 at mass_model explicit_v2 (2074 g), built as
`outcomes_r15.py` builds it. Its genome, the catalogs, the library entries and the `verified` flags were not changed,
and no hardware was added. Code: `calflab.control.outcome` (version 2), `calflab.fitness.outcomes` (`free`),
`calflab.evolve.qd` (MAP-Elites) and `calflab.app.diversity_compare` (`compare.html?set=r16`). Script:
`docs/studies/diversity_r16.py`. Tables: `diversity_r16_tables.md`. Data: `diversity_r16.json`.

## 1. The search

**Question.** R15 found one best version of four prescribed behaviours. Here the question is the other way round:
what *different* things can this body do while staying within the limits? Novel and unexpected behaviour counts for
more than a higher score.

**Controller.** `outcome_motion` version 2. With every new number at its default, it plays version 1 exactly: R15's
stored trot gives the same 551.1 mm/s and margin 0.1945 (checked). Each widening is cheap: a few numbers, no new
sensing.

| added | why |
|---|---|
| `stride` (−1 to 2) and `turn` up to ±1.5 (it was ±1) | Turning on the spot needs the two sides to sweep in opposite directions; walking backward needs a negative stride. Version 1 could only curve. |
| left/right offset per joint group (`side_*`), reached over `side_s` from `side_from_s` | Weight shifts (Stage C's `shift_hl` / `shift_hr`), standing or walking askew, folding the legs to one side to lie down (calves lie sternally with their legs to one side). Seven numbers instead of a full per-side keyframe (fifteen). |
| a pause at keyframes 1 and 2 (`p*_hold_s`) | Pauses and transitions: kneel, wait, then fold. |
| the rhythm can start late (`gait_from_s`) and run in bouts (`bout_s`, `pause_s`) | Behaviour that changes within a play: stand then walk, or step, stop and step again. |

**What a play is judged on** (the `free` outcome). No task is given. The limits are the R11c suite at margin 0.2:
servo torque-speed envelope, sustained torque, stall, belt tension, joint ranges and speeds, on seeds 0–2 (friction
0.7–1.1, mass ×0.95–1.05). Safety gates come from R15's lying gates: tilt ≤ 30°, peak trunk descent ≤ 300 mm/s,
non-hoof floor force ≤ 2 body weights. **Inside a cell the least servo effort wins**: −(mean + worst)/2 of each servo's
mean |torque| / rated torque, as R15's stand.

**Behaviour descriptors.** These are three things a person watching would call different:

1. **What the body does** (a class; `fitness.outcomes.classify`):
   - Posture classes come first. *down* means the trunk is held for 1 s at ≤ 0.5 of standing height. *kneel* means
     the floor carries ≥ 0.1 body weight through non-hoof parts for 1 s. *crouch* and *stand* are a still trunk held
     below / above 0.85.
   - Otherwise the class is R15's footfall label: *walk*, *trot*, *pace* or *bound*. Unlabelled stepping is
     *irregular*.
   - Footfall alone would put lying, kneeling and standing in one cell, and posture alone would merge every gait.
2. **Forward speed** (mm/s, + ahead, over 3–16 s): backward / in place (±15) / creeping (≤ 100) / slow (≤ 250) /
   medium (≤ 400) / brisk (≤ 550) / fast.
3. **Turn rate** (deg/s, + left): right fast (< −10) / right (< −2.5) / straight / left / left fast. Turning is a
   different behaviour, and turning on the spot is one of the open questions.

That gives 9 × 7 × 5 = 315 cells. Trunk pitch and head force were left out. Pitch mostly follows the class and the
speed. Head force needs the suckling block, which is not in a free scene; suckling is already settled in R15.

**The search** (`calflab.evolve.qd`):
- MAP-Elites over 52 dims scaled 0..1, in seven blocks: three keyframes, the rise, the side offset, the rhythm and
  the reflexes.
- Each new candidate is a mutated elite. One of three operators is chosen: nudge a quarter of the dims (σ 0.08); a
  line step towards another elite; or copy one whole block from another elite (for example one body's posture with
  another's rhythm).
- Batches of 28 on 14 workers.
- Each candidate plays 16 s on seed 0. Only if it is safe and within every limit does it play seeds 1 and 2.
- A candidate enters the archive only when it holds on all three seeds. Its class is the majority over the seeds;
  speed and turn are the medians.
- At the end, every elite is played again at **30 s** on seeds 0–2.
- Deterministic for a seed; plays are cached.

**Starting points only** (19): R15's four versions on this body; R13's evolved lie_rise; and the primitives the
R7 / Stage C generators play (stand, weight shift left and right, the feral walk, the walk turned on the spot, and the
trot at five R11c grid corners).

## 2. Pilot: coverage, which cells fill, what binds

**40 batches, 1139 candidates, 2062 plays, 24 min** (search) + 1.7 min (judging), 14 workers.

**32 of 315 cells (10 %)**: 11 trot, 8 irregular, 8 walk, 4 pace, 1 stand. The coverage curve was still rising
(4 → 13 → 19 → 32: 19 cells at batch 20, 32 at batch 37, and none new in the last three batches).
**29 hold at 30 s, 14 of them in the same cell.**

| class | cells | tried (seed 0) | held on 3 seeds | most common reasons it failed (seed 0) |
|---|---|---|---|---|
| trot | 11 | 390 | 159 | hr / hl hip ab/ad sustained torque 72; hl / hr hock belt 60; fr shoulder torque 16 |
| irregular | 8 | 358 | 104 | fl / fr shoulder torque 73; hip ab/ad torque 67; stifle belt 42 |
| walk | 8 | 229 | 83 | fl shoulder torque 24; hip ab/ad torque 35; stifle belt 27 |
| pace | 4 | 73 | 15 | shoulder torque 26; hip ab/ad torque 15; stifle belt 8 |
| stand | 1 | 64 | 46 | fl shoulder torque 10 |
| bound | 0 | 5 | 0 | hip ab/ad torque, shoulder torque, stifle belt |
| down | 0 | 11 | 0 | descent too fast 10, landing 9, tipped 8; shoulder and hl stifle torque |
| kneel | 0 | 6 | 0 | tipped, too fast, hard landing (all 6); fl shoulder torque |
| crouch | 0 | 0 | – | (never reached as a still pose) |

**Where the limits bind.**

- **Stepping gaits.** The binding limit depends on the gait:
  - Trots: sustained torque at the **hind hip ab/ad (C018)** (the R15 weak point) and the **hind hock belt**.
  - Walks, paces and irregular gaits: the **front shoulders' sustained torque** and the hind stifle belt.
  - Elites near their speed limit bind on **stifle and hock joint speed** (0.85–0.93 of the limit).
- **Posture changes.** Every attempt to go down or kneel failed on safety first: it came down too fast, landed too
  hard or tipped. Behind those are the front shoulders' and hind stifles' sustained torque (section 3c explains why).

**What the archive holds.** All of these are distinct, and none was a starting point:

- **Walks** (four beats) from 82 to 371 mm/s, plus walks turning right and left.
- **Paces** at 170 and 278 mm/s (lateral pairs, lag > 0.32). They hold at 30 s and stay in their cells.
- **Trots** from 49 to 554 mm/s.
- **Turning trots and walks.** A trot turns right at about 8 deg/s while hardly moving forward (−8 mm/s at 30 s), and
  a walk turns right at 4 deg/s at 4 mm/s. In effect both turn on the spot.
- **Irregular steppers**: four-beat patterns that are neither walk nor trot by the lag rule, some curving.

The judging at 30 s shows something the 16 s search hides:

- **Half the elites leave their cell over 30 s.** Most often a curving gait slows or straightens, a walk reads as a
  trot on one seed, or the reverse.
- Class agreement between seeds is often 2 of 3. The lag thresholds (0.18 and 0.32) cut through a continuum.

The compare page shows these in orange.

## 3. Probes on the open questions

### a. Is there a trot faster or more economical than the warm start?

**Yes, both, a little.** The trot probe searched the rhythm, the reflexes and one posture: 15 batches, 677 plays,
7.5 min, with 50 mm/s speed bins. Every straight trot at ≥ 300 mm/s was then judged **exactly as R15 judges a trot**
(60 s, every gate, seeds 0–2):

| trot | holds (60 s) | slowest 5 s | effort mean / worst (30 s) | binds | margin |
|---|---|---|---|---|---|
| R15 (warm start, 0.4 s, stride 2) | yes | 543 mm/s | – (about 0.25 at 16 s) | hl.hip_abd sustained torque 0.83 | 0.17 |
| **probe, 550–600 bin** | **yes** | **578 mm/s** | 0.214 / 0.268 | hl.stifle speed 0.86 | 0.15 |
| probe, 500–550 bin | yes | 515 mm/s | 0.199 / 0.266 | hr.stifle speed 0.80 | 0.20 |
| probe, 400–450 bin | yes | 413 mm/s | 0.190 / 0.261 | hr.hock speed 0.69 | 0.31 |
| pilot, fast | yes | 553 mm/s | 0.206 / 0.303 | hl.stifle speed 0.92 | 0.08 |
| probe, 600–650 bin | **no** (60 s: drifts off heading) | 395 mm/s | 0.218 / 0.265 | hr.hock speed 0.93 | 0.06 |

- **About 6 % faster.** A trot at 578 mm/s holds for a minute, against 544, at a slightly lower effort (about 0.24
  against R15's about 0.25, (mean + worst)/2). The R15 figure was measured at 16 s and the new one at 30 s, so the
  comparison is approximate.
- **What stops it going faster is joint speed** at the stifle and hock (0.86–0.93 of the limit), no longer the
  hip ab/ad's sustained torque. A 605 mm/s trot holds for 30 s but curves off heading within a minute; a heading
  reflex might rescue it.
- **Cheaper per metre:** slower trots cost less effort per second (0.13–0.19 at 50–300 mm/s), but per metre the fast
  ones are the most economical.

### b. Is there a gait other than a trot that holds?

**Yes:**

- **The walk** holds within every limit at 82–416 mm/s. A 416 mm/s walk holds at 30 s and stays in its cell.
- **The pace** holds at 170, 278, 369 and 441 mm/s.
- **Turning on the spot** holds slowly: a trot turning right at about 8 deg/s and a walk turning right at about
  4 deg/s, both within 10 mm/s of standing still at 30 s.

**The bound does not:** 7 tries in all, none within limits. It binds on the hind hip ab/ad and the front shoulders.
The pronk, rotary-gallop phases, backward trot and backward walk starts did not become elites either. They failed on
the same limits or became other gaits.

The gait probe searched only the rhythm and reflexes from 15 gait starting points (15 batches, 949 plays, 9 min). It
found 15 cells, the same kinds as the pilot. None was new, so in this pilot the full search's posture blocks were not
what limited the gaits.

Only **right-turning** gaits stayed on the spot. The left-turning cells drift forward over 30 s. This is an open-loop
asymmetry that the search did not equalise; the earlier trots veer too (handoff, "The default trot veers").

### c. Is there any lying down within the limits? If not, why not?

**No.** The lying probe used R15's lie outcome and gates with the wider controller: three keyframes, pauses and a
left/right offset, 32 dims. It started from R15's version, R13's three and five new ones: front first, hind first,
folded to one side, hips out, and slow with pauses. CMA-ES ran 20 generations of 12 (258 plays, 2.4 min).

- **Nothing improved on R15's version.** Every version reaches 0.42–0.45 of standing height. Several pass every
  outcome gate (*front first, slow with pauses*: 11 s down, descent 202 mm/s, impact 1.37 body weights), but all are
  over a sustained limit: **hl.stifle** or **hl.hip_abd** torque at use 4 (saturated).

**Why** (`lie_grid`): the front kneels and lies (carpus 125°, shoulder −45°) and the hind stifle and hock fold to
each pair of a 5 × 5 grid (20–78°). Measured in the last 2 s:

| hind fold | trunk down to | floor under the body | hind hooves | front hooves | hl.stifle mean effort |
|---|---|---|---|---|---|
| stifle 20, hock 20 | 0.62 | 0.53 bw | 0.47 bw | 0 | 0.60 of rated |
| stifle 55, hock 55 | 0.50 | 0.49 bw | 0.51 bw | 0 | 0.73 |
| stifle 78, hock 20 | 0.32 | 0.53 bw | 0.47 bw | 0 | 0.62 |
| stifle 78, hock 78 | 0.42 | 0.45 bw | 0.55 bw | 0 | 0.61 |

- **In every fold the hind hooves still carry about half the body's weight**, and the floor carries the other half
  through the chest and front legs. The hind quarters never rest on the floor. The hind legs, folded within their
  PROVISIONAL ranges (stifle and hock −30..80°, hip ab/ad ±25°), hold the hip block up. Each hind stifle then holds
  0.6–1.1 of its rated torque for as long as the body lies. The sustained limit allows 60 % for at most a quarter of
  any 2 s window.
- Folding further only moves the load onto the **hip ab/ad (C018)**, which binds in nine of the grid's poses.
- So it is not how the body goes down. Front first, hind first, slow, pauses and one-sided all fail on the same
  thing: **lying needs the hind end to rest on the floor**, and this body cannot get it there.
- What could change that is hardware or geometry, so it is your decision; nothing was changed:
  - wider hind joint ranges, so the legs fold flat (the ranges are PROVISIONAL);
  - a hip ab/ad range that tucks the legs to the side;
  - a C002 at the stifle (R13's suggestion);
  - or a stifle spring that carries the folded leg.

## 4. Show me

- The elites are stored as runs titled `R16 g020-008-r01 <cell> [<source>]: seed 0`: the pilot archive, the trot
  probe's trots, the gait probe's non-trot elites and the lying probe's best. Journal > Runs.
- **`compare.html?set=r16`** shows six views of the body. Each view has a menu of every stored behaviour, grouped by
  class.
- Each label says what the behaviour is ("trots forward", "walks forward, turning right", "trots on the spot, turning
  right"), then speed, turn, trunk height, footfall and lag, effort, and margin.
- The badge reflects the 30 s judging:
  - green: holds on every seed and stays in its cell;
  - orange: holds but changes cell, or the seeds disagree on the class;
  - red: over a limit or unsafe, with the limit named.

## 5. The full search: three budgets (estimated after the pilot; M was run, section 6)

From the pilot: 34.7 s per batch of 28 on 14 workers, 1.81 plays per candidate, 3.2 s per elite judged at 30 s.

| budget | batches | candidates | wall |
|---|---|---|---|
| S | 200 | 5 600 | about 2.0 h |
| M | 500 | 14 000 | about 4.9 h |
| L | 1 200 | 33 600 | about 11.6 h |

What a larger budget is likely to buy:

- The coverage curve had flattened to about one cell per two batches, so S would probably reach 50–70 cells and M
  80–100.
- Almost all of these would be **more locomotion**: gaits × speed × turn, especially left turns and backward gaits.
- Posture classes (down, kneel, crouch) will stay empty at any budget: section 3c shows the limit is physical, not
  search effort.

**Before spending M or L**, I recommend two cheap changes:

- **judge cells at 30 s inside the search** (more plays per accepted elite, but no cell drift);
- **seed the posture blocks from a dedicated emitter** that keeps the rhythm off, for crouches, askew stands and
  weight shifts.

Run with:

```bash
python docs/studies/diversity_r16.py projects/robot-calf-final pilot --iters=200
```

(use a new seed with `--seed=1`).

## 6. The full search (budget M, chosen by Emily; ADR-113)

**Run:** 500 batches of 28, seed 1, `full` in the JSON, 24 909 plays, 4 h 22 min on 14 workers, after a first
attempt was stopped at batch 100 (see the third bullet below).

**Two changes before it,** as recommended in section 5:

* **Confirmation.** A candidate that would fill or improve a cell is played again for 30 s on seeds 0-2. It enters
  only if it holds there and stays in its cell (`QDSettings.confirm`).
* **A posture emitter.** Half of each batch switches the rhythm off and nudges only the keyframes, side offsets and
  pauses, harder (σ 0.15, 40 % of those dims; `p_posture`).

**A third change found during the run.** The first attempt held 321 still stands by batch 100, and they all landed in
one cell. A body standing still has no speed or turn, so every still pose (leaning, nose down, raised, askew) competed
for "stand, in place, straight". I stopped it after about an hour (kept as `full_stopped`; every play stays in the
cache) and restarted with **still poses binned by trunk pitch** (bins at ±1, ±3, ±6°, + nose down) **and mean trunk
height** (bins at 0.6, 0.75, 0.95, 1.02 of standing) instead (`Grid.still_by_posture`). The pilot's grid is
unchanged.

**Result: 52 of 315 cells; all 52 hold for 30 s on every seed and stay in their cell** (the pilot managed 14 of 32).
The full table is in `diversity_r16_tables.md`.

| class | cells | new kinds compared with the pilot |
|---|---|---|
| stand | 13 | still poses from **nose up 6° and lowered to 0.93** through level, to **nose down 7°**, and raised to 1.03 of standing; effort 0.08-0.18 (the cheapest, nose down and raised, 0.076 / 0.124) |
| trot | 12 | **trotting in place** (straight, turning left, turning right); **backward** trot (−18 mm/s) and backward turning left; up to 573 mm/s forward |
| walk | 10 | **walking in place**, **walking backward** (−38 mm/s), and a **556 mm/s walk** (four beats, as fast as the fastest trot, margin 0.07) |
| irregular | 9 | stepping **backward** (−75 mm/s, nose down 6°), **stepping in place**, turning on the spot to the left, a 521 mm/s irregular gait |
| pace | 6 | **pacing in place**, pacing while turning right, a **497 mm/s pace** |
| bound | 2 | **the first bounds that hold**: 33 and 130 mm/s, front pair and hind pair each together (margin 0.20-0.24) |
| down / kneel / crouch | 0 | 1 029 tries: all fail on descent speed, landing or tipping first, then front shoulder, hind stifle and hip ab/ad torque |

**What this adds to the probes (section 3):**

* **Other gaits:** a bound does hold, but only slowly (≤ 130 mm/s). The pilot's 7 tries were too few. The walk
  reaches 556 mm/s and the pace 497.
* **Turning on the spot** now holds to the left as well (a trot at 2.9 deg/s in place, an irregular gait at
  3.3 deg/s). The fast on-the-spot turns of the pilot (8 deg/s right) were among the elites that drifted at 30 s;
  with confirmation, every turn on the spot that holds is slow (2.5-3.5 deg/s).
* **Lowered stands are as far down as this body goes** (0.93-0.95 of standing height). They cost about twice the
  effort of a level stand (0.16-0.18) and bind on the front shoulder, the same limit that stops kneeling.
* Still no posture below 0.9 holds. That agrees with section 3c: lowering the trunk loads the hind stifle and the
  front shoulders past their sustained limits.

**Coverage curve** (cells after every 25 batches): 6, 18, 21, 25, 28, 28, 32, 35, 35, 41, 42, 43, 44, 44, 45, 45,
48, 50, 52, 52, 52. The last 75 batches added no new cell, so budget L would most likely add only a handful.

## 7. What this rests on

- **Library values, unverified:** the C018 and C002 torque-speed figures and rated torques (effort, sustained
  limits).
- **PROVISIONAL:** joint ranges, the 300 g headroom, every gate threshold, and the class thresholds:
  - lag 0.18 / 0.32;
  - 0.5 / 0.85 of height;
  - 0.1 bw kneel.
- The bins are my choice. Effort is mean |torque| / rated, not current or heat (the C018's stall current is unknown).
- **Seed 0 is replayed**; the text describes the worst of three seeds.
- The suckling block is not in these plays.
