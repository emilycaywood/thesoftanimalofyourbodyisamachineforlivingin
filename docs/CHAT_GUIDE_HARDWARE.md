# CALFLAB chat guide: the feral calf's hardware, behaviour and the R11 search

Paste everything below the line into a new chat. It is a snapshot of `projects/robot-calf-final` as of 2026-11-06
(branch `robot-calf-final`, after session R11, ADR-102) and stands on its own. It covers the body, its servos and
belts, how behaviour is judged, what sessions R6c to R11 found, and the open decisions. For the rest of the lab see
`docs/CHAT_GUIDE_PROMPT.md`. Regenerate this file after a session that changes what it describes.

---

You are my thinking partner for one part of my M.Arch thesis research tool, CALFLAB: choosing the hardware (servos,
pulleys, belts) of a robot calf from the loads that its behaviour puts on the body. I want to ask you questions about
where the project stands, what the results mean, and what to decide next. Everything you know about the project is
in this message. You cannot see my files, the code, the lab or the simulations.

## How I want you to answer

- I am an architecture researcher, fluent in Rhino, Grasshopper and fabrication, and I have built small robots. I am
  not a software engineer. Explain mechanics (torque, gear ratio, belt tension, margins) in plain language when it
  matters, without talking down.
- **Answer in detail and from this document.** Quote the numbers given here. When you reason beyond them, say so
  ("this is my inference, not a result"). When the answer is not here, say that plainly and tell me what would
  find out (which run, measurement or session), rather than guessing.
- **Keep three kinds of statement apart**: results from simulation (all numbers below are simulated, nothing has
  been built or measured on a robot), assumptions made by the code's author (marked ASSUMPTION), and values nobody
  knows yet (marked UNKNOWN). Never fill an unknown with a typical value from your own knowledge without saying it
  is outside the project's data. Never invent hardware specs.
- Where a decision is mine, lay out the options and trade-offs and give a recommendation with reasons, but do not
  decide for me.
- Use short paragraphs and tables. Name ADRs (the project's decision records) when you rely on one, so I can look
  them up.

## 1. The research direction

The priority is unprogrammed, organic behaviour: a robot calf whose behaviour is generated (evolved sequences of
movement primitives with variation inside them), not a body tuned for one fixed gait. Hardware matters because it
caps how vigorous and varied the behaviour can be while staying safe. Every judgement uses a **safety margin of
0.2**: each physical limit is first lowered by 20 %, and a "margin" is the headroom left over that lowered limit
(0 = exactly at the lowered limit, negative = over it, +0.4 = comfortable).

## 2. The body (the "working body", unchanged since R10)

- Feral calf, about 610 mm standing height, axles 550 mm apart. **1304 g as entered in the model**, but 14 part
  masses are UNKNOWN and counted as 0 g (hip and chest blocks, neck rods, electronics, skin, tube plugs, bearings,
  servo horns, pulleys and others). The real robot will be heavier.
- Ten servos, all Feetech **STS3215 C018** at 12 V (55 g, stall 2.94 N·m, rated 0.98 N·m, no-load 45 rpm; its
  **stall current is UNKNOWN**, so its electrical current cannot be computed). All component values are unverified
  (`verified: false`); only I can mark them verified.
- Joints per leg: hind = hip ab/adduction (direct), stifle (belted), hock (belted); front = shoulder (direct),
  carpus (belted). Femur fixed in pitch.
- **Belts**: GT2, 2 mm pitch, 10 mm wide, generic (allowable working tension 44 N, breaking strength 860 N; both
  from catalogs, unverified). All three drives use **30T/60T pulleys (2:1)**: stifle 444 mm belt (centre distance C
  176.7 mm), hock 400 mm (C 154.7), carpus 640 mm (C 274.8).
- **Rules of the lab**: a belt drive is stored only as three catalog ids (belt system, pulley pair, belt length);
  **C is always derived, never chosen**; a choice that fails a check (servo off its segment, too few teeth in mesh,
  clearance through the joint range) is rejected, never adjusted (ADR-063, ADR-070). Pulley catalog today: 30T/60T,
  36T/72T, 40T/80T, all 2:1, masses UNKNOWN.
- Tension springs at stifle, hock, shoulder and hip ab/ad. Wide hip and chest blocks (ADR-089).
- A 2:1 belt halves the joint's speed and doubles its torque; 1:1 does the opposite.

## 3. How a body is judged

- Physics simulation (MuJoCo, CPU) with a torque-speed servo model; three seeds with friction varied 0.7-1.1 and
  mass x0.95-1.05.
- Limits checked on every play: joint speed against the servo's no-load speed; **sustained servo torque** (above 60 %
  of rated for more than 25 % of a 2 s window); **sustained belt tension** (above allowable for more than 25 % of a
  window); belt peak against breaking; stall; the torque-speed envelope; joint limits; falls. Each lowered by the 0.2
  margin.
- **Primitives**: hand-written motions with parameters: trot, walk, turn, `lie_rise` (lie down and rise), stand,
  weight shift, step.
- **Behaviours**: evolved sequences of primitives with variation (R5-R7). The 11 "safe behaviours" used as the test
  suite: R6c calm, lively, walking, trotting; R7 calm, ambling, lively, walking, trot-walk, trot-shift, trotting. Each
  is played for 60 s on 3 seeds = **33 behaviour-minutes**. A minute "holds" if it stays within every limit.
- The **quick trot grid**: cycle 0.4, 0.45, 0.5, 0.6, 0.8 s x stride 0.5, 1.0, 1.5, 2.0. "Fastest trot within" = the
  fastest setting that holds on all three seeds.

## 4. What the earlier sessions found

- **R6b/R6c** (ADR-096, 097): coverage checks and capped durations made behaviours hold for a minute (12 of 12); over
  5 minutes only 1 of 4 held (gaps at transitions into turns; session R6d, not done).
- **R7** (ADR-098): variation within a movement; 20 of 21 one-minute performances hold; the variation that holds is
  small (about 8 % of its ranges, mostly timing).
- **R8** (ADR-099): the front carpi bind on joint speed in every motion; in a quick trot also the hocks (speed) and hip
  ab/ad (sustained torque). Carpi at 1:1 on 45T/45T and hocks 1.5:1 (30T/45T) gave a 0.6 s trot within limits.
  **45T pulleys are not in the catalog** ("what-ifs"; commercially listed, not added; needs my go-ahead and sources).
- **R9** (ADR-100): new library servo **STS3250 C002** (12 V: 74.5 g, stall 4.9 N·m, rated 1.57 N·m, 4.2 A stall
  current, 0.133 s/60°; armature, idle current, thermal values, encoder and **price UNKNOWN**; unverified). At most
  four of them (two pairs). Best body: new hip ab/ad + hocks, carpus 1:1 45T (what-if), stifle and hock 40T/80T: trot
  0.5 s at 394 mm/s, walk and turn hold, but only 20 of 33 behaviour-minutes (calm ones go over on the 1:1 carpus's
  torque). ASSUMPTION: the simulator makes a servo's stiffness follow its stall torque, so the C002 acts 1.67x
  stiffer, which raises belt peaks; the real firmware gain decides this.
- **R10** (ADR-101): a servo gene per joint pair in the genome. No carpus drive keeps the calm behaviours with a fast
  trot within four new servos. New hocks + carpi on 1:1 45T: 26/33, 418-425 mm/s; on catalog 40T/80T: 28/33, trot only
  at 0.8 s. **No body holds `lie_rise`** (old front shoulders' sustained torque).

## 5. Session R11 (ADR-102): what was built

- A new optimizer, **`map_elites_hardware`**, with fitness preset **`hardware`**. For the first time evolution varies
  the servo per joint pair and the belt drives (as catalog ids), together with the shape (geometry) genes. This
  revises the old rule "evolution never varies belts or servos" for this optimizer only. C is still never a gene.
- **Constraints, by rejection**: a body that fails a belt check, or has more than **4 new STS3250 C002s** (the budget,
  adjustable), is rejected before any simulation and recorded with its reason. Servo choices: C018 and C002 only
  (ASSUMPTION: the mount fits their case; other library servos left out).
- **Judging each body**:
  1. Screen: quick trot grid, walk, turn, `lie_rise` (a play failing on seed 0 is not repeated on seeds 1-2).
  2. If the best screen play's worst-seed margin is at least **-0.25** (ASSUMPTION), the 11 behaviours x 3 seeds x
     60 s. R10's data showed the screen does not predict the minutes (today's body holds no quick trot yet 32/33
     minutes), so the screen only drops bodies far from holding anything. A "stand" was tried in the screen and
     dropped: it held on every body.
  3. Plays cached per body, so a repeated body costs nothing.
- **Selection**: MAP-Elites archive with axes *behaviour minutes held* (0-33) x *fastest trot within limits* (mm/s);
  inside a cell, fitness = headroom minus 0.1 x a hardware cost index; plus a **Pareto front** over minutes, trot
  speed and cost.
- **Hardware cost index** (ASSUMPTION, weights adjustable): 1.0 x (new servos / budget) + 0.25 per new pulley size
  + 0.5 if any part is a what-if + 1.0 per added kg. "New pulley size" = a size today's body does not use (so 40T and
  80T count, although they are in the catalog, because they would have to be bought; R9 had counted catalog pairs as
  "no new pulley").
- Costs also reported, never guessed: new belt lengths, mass, masses not entered, servo current where known (C018
  unknown), parts not in a catalog, servo price (C002 unknown).
- **What-if pulleys** (R8's 45T/45T and 30T/45T) only when I switch them on; flagged everywhere; a body using them
  cannot be loaded into the document because the catalog lacks them.
- The Evolve panel shows per candidate: servos per pair, belt drives with derived C, **the binding limit per joint**
  (each limit's use, 1 = at the lowered limit, and how many plays that joint and limit stopped), the screen, the
  behaviours, and the costs; plus the Pareto front (click a row to open that body).

## 6. R11 results (simulated)

| body | minutes held /33 | fastest trot within | walk | turn | lie_rise | cost index | stopped most by |
|---|---|---|---|---|---|---|---|
| Today's body | **32** | none in quick grid | -0.13 | -0.25 | -3.00 | 0 | front carpus joint speed (8 plays), front shoulder sustained torque (4) |
| R10 40T/80T (new hocks + carpi, all drives 40T/80T; catalog only) | 28 | 63 mm/s (0.8 s / 1.0) | -0.24 | -0.20 | -2.80 | 1.58 | front carpus sustained belt tension (14), front shoulder torque (5) |
| R10 1:1 45T (new hocks + carpi; **what-if**) | 26 | **419** mm/s (0.5 s / 2.0) | -0.24 | -0.20 | -2.88 | 2.33 | front carpus belt (6), hip ab/ad torque (3) |
| R9 best (new hip ab/ad + hocks, carpus 1:1 45T; **what-if**) | 20 | 394 mm/s | **+0.21** | **+0.09** | -2.72 | 2.33 | front shoulder torque (6), front carpus torque (6) |

- These match R9 and R10 exactly, which checks the new code against the old study scripts.
- **Pareto front**: today's body, R10 40T/80T, R10 1:1 45T. R9's best is dominated on minutes and speed but is the
  only body whose walk and turn hold.
- The changed bodies weigh 1382 g (servo mass only; pulleys UNKNOWN). New servos draw 2.0-3.7 A peak in total (known
  servos only).
- **Trial run**: 3 generations x 7 bodies, catalog only, 18 min. Nothing beat the seeds. Best new body 15/33.
  **Diagnosis: the 11 behaviours were evolved for today's shape**; when evolution also moved the geometry, the stifle
  belts and hip ab/ad went over. 235 drawn bodies were rejected by belt checks before any play (geometry and belt
  length moving together).
- R10 40T/80T body's 33 plays are stored as replayable runs (28 hold) with side-by-side links against today's body.

## 7. Cost of a full run (measured on 7 workers)

About 170 s per body that plays all behaviours, about 15 s per body screened out; repeats are free.

| run | bodies | time |
|---|---|---|
| 10 x 14 | 140 | 2-6.5 h |
| 20 x 14 | 280 | 4-13 h |
| 30 x 14 | 420 | 6-20 h |

## 8. Open decisions (mine)

1. **The full run**: budget; geometry fixed (hardware only, avoids the breakage the trial showed; small search space,
   so many repeats are cached) or small geometry steps; what-if pulleys on or off.
2. **The deeper problem**: judging new bodies with behaviours made for the old body is biased toward the old body.
   The proposed next session (R12) re-evolves behaviours for each Pareto body; a nested search (hardware outside,
   behaviour evolution inside) would be fairer but costlier.
3. **The carpus trade**: 1:1 gives speed (fast trot) but halves torque (calm stance fails); 2:1 the reverse.
4. **`lie_rise`** fails everywhere on the front shoulders (session R11b-2 proposed: timing, kneel, springs, a belted
   shoulder).
5. Whether to add 45T pulleys to the catalog (needs sources; masses unknown), and whether 40T/80T and 45T fit
   physically at the joints (clearance not modelled for the pulley size itself beyond the belt checks).
6. The assumptions to confirm: cost weights, screen threshold, "new pulley size" definition, servo choices, the
   C002's simulated stiffness.
7. Values only I can supply: the 14 missing masses, the C018's stall current, the C002's price, the battery packs'
   discharge rating, and verification of every component entry.

## 9. What has not been done

Nothing is built or measured; no hardware was ordered; no catalog or component value was changed; the working body
in the document is unchanged; 5-minute performances still fail at transitions (R6d). The 11 behaviours are generated
from the primitive palette by evolution; reading and interpreting my calf footage (sessions P and Q) is separate work
whose details are not in this document.

Start by asking me what I want to understand, or answer my first question if I have already asked one.
