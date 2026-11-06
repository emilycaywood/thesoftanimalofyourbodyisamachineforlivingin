# Up to four STS3250 C002 servos: what they buy (ADR-100)

2026-11-06. Session R9 in `projects/robot-calf-final`, after R8. **Simulation only.** Each what-if is an in-memory
copy of the working body's spec (`docs/studies/servos_r9.py`, built on `joints_r8.py`). The project document,
belts, catalogs, other component values and `verified` flags were not changed. The only file change outside
`docs/` is the new library entry `sts3250_c002` (unverified), and it is on no body.

A swap changes two things on both sides of a pair of joints: the actuator's component and the servo case's mass
(74.5 g against 55 g, +39 g a pair). The case, mount and belt stay the same: the STS3250 has the STS3215's body.
Plays are as in R8:

* the trot primitive over a grid of cycle x stride (lift 0.6);
* the walk and the turn at their defaults;
* three seeds with the diversity preset's randomisation (friction 0.7-1.1, mass x0.95-1.05);
* every limit at margin 0.2, judged as everywhere else (torque-speed servos, derating 1, ADR-084).

"Within" below means within every limit on **all three** seeds. Data: `servos_r9.json` (every assignment),
`servos_r9_combos.json` and `servos_r9_quick.json` (with pulleys; quick grid 0.4-0.8 s x stride 0.5-2.0),
`belts_r9.json` (which catalog belts fit), `perform_r9*.json` (the behaviours). Tables: `servos_r9_table.py`,
`perform_r9_table.py`.

## The entry, and what depends on each null

`sts3250_c002` in `config/components/actuators.yaml` holds only the supplied 12 V values:

* 74.5 g; 45.22 x 24.72 x 35 mm;
* stall 4.9 N*m, rated 1.57 N*m, stall current 4.2 A;
* 0.133 s / 60 deg, i.e. 75.19 rpm, 451 deg/s (the spec, not the third-party 0.129 s, which is a remark in
  `notes`);
* gear ratio 1/345.

The operating range (6-12 V), the spline (25T, 5.9 mm) and the dual shaft have no field in the model: they are in
`notes`. Against the C018 the new servo has 1.67x the stall torque, 1.6x the rated torque and 1.67x the speed.

| null field | model uses | what depends on it |
|---|---|---|
| `armature_kgm2` | 0.005 kg*m^2 (default, the same the C018 gets) | the reflected inertia at the joint (x ratio^2), so the joint dynamics of every play; the comparison assumes equal rotor inertia. R1 found armature decides nothing on this body (ADR-086) |
| `idle_current_a` | 0.05 A (default) | the current figures below (+0.05 A per new servo); no limit is judged on current |
| `winding_resistance_ohm`, `r_thermal_k_per_w`, `c_thermal_j_per_k`, `max_temp_c` | 1.0 ohm, 5 K/W, 50 J/K, 80 degC (defaults) | only the rollout's temperature estimate for this servo; no constraint uses temperature, so no verdict here depends on them |
| `encoder_steps_per_rev` | none ("unknown") | nothing in simulation (the firmware export would) |
| `cost_usd` | 0 (default) | the BOM total |

A modelling choice matters more than any null: **the simulated position servo's gain is its stall torque over the
saturation angle** (`servo_saturation_deg`, `mjcf.py`). So the new servo is also simulated 1.67x **stiffer**: it
tracks harder and pushes harder into a belt for the same command. The real gain is set in the servo's firmware.

## On today's 2:1 belts: every assignment

Five pairs (hip ab/ad, stifle, hock, shoulder, carpus): the five single pairs and the ten combinations of two
pairs (four servos). Trot grid 0.5-1.2 s x stride 0.5-1.5.

| new servos on | mass g | quickest trot within | fastest within | walk | turn |
|---|---|---|---|---|---|
| none (today) | 1304 | 1.2 s / 1.0, 76 mm/s | same | -0.13 x3 (joint speed) | -0.25 x3 (envelope) |
| hip ab/ad | 1343 | 1.2 s / 1.0 | 73 mm/s | -0.13 / **-0.92** / -0.10 (stifle belt) | -0.21 / -0.24 / -0.18 |
| stifle | 1343 | 1.2 s / 1.0 | 76 mm/s | -0.09 x3 | -0.20 / -0.22 / -0.19 |
| hock | 1343 | 1.2 s / 1.0 | 79 mm/s | -0.11 / -0.20 / -0.12 | -0.25 x3 |
| shoulder | 1343 | 1.2 s / 1.0 | 80 mm/s | -0.24 / -0.32 / -0.16 | -0.25 x3 |
| **carpus** | 1343 | **1.0 s / 1.0, 78 mm/s** | 1.2 s / 1.5, 102 mm/s | **+0.05 / +0.08 / +0.08** | +0.00 / -0.19 / +0.09 |
| hip ab/ad + stifle | 1382 | 1.2 s / 1.0 | 73 mm/s | -0.32 / -0.44 / -0.36 | -0.36 / -0.48 / -0.40 |
| hip ab/ad + hock | 1382 | 1.2 s / 1.0 | 76 mm/s | -0.09 / -0.40 / -0.09 | -0.24 / -0.36 / -0.24 |
| hip ab/ad + shoulder | 1382 | 1.2 s / 1.0 | 78 mm/s | -0.52 / -1.08 / -0.40 | -0.25 x3 |
| hip ab/ad + carpus | 1382 | 1.0 s / 1.5, 94 mm/s | 94 mm/s | -0.12 / -0.20 / -0.20 | -0.02 / -0.08 / +0.03 |
| stifle + hock | 1382 | 1.2 s / 1.0 | 80 mm/s | -0.09 / -0.20 / -0.09 | -0.17 / -0.17 / -0.15 |
| stifle + shoulder | 1382 | 1.2 s / 1.0 | 79 mm/s | -0.48 / -0.52 / -0.44 | -0.25 x3 |
| **stifle + carpus** | 1382 | 1.0 s / 1.0, 72 mm/s | 75 mm/s | **+0.08 x3** | **+0.09 / +0.04 / +0.10** |
| hock + shoulder | 1382 | 1.2 s / 1.0 | 83 mm/s | -0.40 / -0.48 / -0.20 | -0.25 x3 |
| hock + carpus | 1382 | 1.0 s / 1.0, 83 mm/s | 83 mm/s | -0.24 / -0.24 / -0.04 | -0.20 / -0.27 / -0.04 |
| shoulder + carpus | 1382 | 1.0 s / 1.0, 82 mm/s | 1.2 s / 1.5, 111 mm/s | -0.24 / -0.40 / -0.16 | +0.03 / -0.08 / +0.05 |

* **Only new carpi move the trot**: from 1.2 s to 1.0 s. A new servo anywhere else leaves the carpus at its speed
  limit and the trot where it was.
* **Below 1.0 s the carpus belt takes over.** With new carpi on today's 30T/60T pair, the carpus belt is over its
  sustained tension at every cycle of 0.8 s and shorter: 1.20-1.62x its margin-lowered limit. The new servo
  carries the same joint torque through the same small pulley and, simulated stiffer, peaks higher (72-86 N
  against 50-63 N). Below 0.6 s the old hocks are back on joint speed (1.10-1.15).
* **New carpi make the walk pass** (it was over on carpus joint speed). **Stifles + carpi** is the only
  assignment of the fifteen where the walk and the turn pass on all three seeds.
* **A new hip ab/ad, shoulder or stifle on its own costs the walk** (39 g more to carry and a stiffer joint). With
  new hip ab/ad, the stifle belt goes over its sustained tension in the walk on one seed (-0.92).
* Servos alone, at most four, on today's belts: **1.0 s at best. That does not beat R8's 0.6 s.**

## With pulleys

Two kinds of pulley change were combined with the swaps:

* **Catalog pairs.** The project catalog already has two larger 2:1 pairs, 36T/72T and 40T/80T: no new pulley.
  Each is built through the belt genes, so C, the servo's place and every belt check are real (`belts_r9.py`). All
  three pairs fit with 14 stocked lengths at the carpus, and 5-7 at the hock. The belt length used is the one
  whose C is nearest today's:
  * carpus 40T/80T on 640 mm: C 259.7 (today 274.8);
  * hock 40T/80T on 400 mm: C 139.4 (today 154.7);
  * stifle 40T/80T on 444 mm: C 161.5 (today 176.7).

  A 40T/80T hock on 444 mm together with a 40T/80T stifle is **rejected**: the stifle belt comes within 2.3 mm of
  the hock servo at 80 deg of flexion.
* **R8's what-ifs, not in the catalog.** Carpus 1:1 on 45T/45T and hock 1.5:1 on 30T/45T; only on joints that
  keep the old servo, as asked.

| body | quickest trot within | fastest trot within | trots within | walk | turn |
|---|---|---|---|---|---|
| R8: carpus 1:1 45T + hock 1.5:1, old servos | 0.4 s / 0.5, 162 mm/s (+0.00) | **0.5 s / 1.0, 208 mm/s** (+0.03) | 7 | +0.16 / +0.12 / +0.18 | +0.06 / +0.04 / +0.06 |
| new carpi, carpus 40T/80T (**no new pulley**) | 0.8 s / 1.0, 46-56 mm/s | 1.2 s / 1.5, 102 mm/s | 7 | +0.08 x3 | +0.00 / -0.15 / +0.04 |
| new hocks + carpi, carpus 40T/80T (no new pulley) | 0.8 s / 1.0, 62-70 mm/s | 1.0 s / 1.0, 83 mm/s | 6 | -0.24 / -0.28 / -0.04 | -0.23 / -0.32 / -0.04 |
| new stifles + carpi, carpus 40T/80T (no new pulley) | 0.8 s / 0.5, 20 mm/s | 1.2 s / 1.0, 75 mm/s | 5 | +0.08 x3 | +0.08 / +0.04 / +0.10 |
| new stifles + R8's pulleys | 0.4 s / 0.5, 156 mm/s | 0.5 s / 1.0, 209 mm/s | 7 | **+0.26 / +0.25 / +0.25** | +0.10 / +0.04 / +0.11 |
| new hip ab/ad + R8's pulleys | 0.5 s / 1.0 | 206 mm/s; **0.6 s / 0.5 within (+0.20)** | 8 | +0.25 / **-0.84** / +0.27 | +0.08 / -0.20 / +0.11 |
| new hocks + carpus 1:1 45T | 0.45 s / 1.0, 246 mm/s | 0.5 s / 1.5, 306 mm/s | 7 | -0.12 / -0.16 / +0.00 | -0.16 / -0.24 / -0.08 |
| new hocks + shoulders + carpus 1:1 45T | 0.45 s / 1.0 | **0.5 s / 2.0, 414 mm/s** (+0.04) | 8 | -0.36 / -0.48 / -0.24 | -0.15 / -0.16 / -0.02 |
| new hip ab/ad + hocks + carpus 1:1 45T | 0.4 s / 0.5 | 0.5 s / 1.5, 299 mm/s | 9 | -0.04 / -0.40 / +0.04 (stifle belt) | -0.32 / -0.40 / -0.36 |
| ... + stifle 40T/80T | 0.4 s / 0.5 | 0.5 s / 1.5, 299 mm/s | 9 | +0.21 / +0.21 / +0.23 | +0.10 / +0.08 / +0.11 |
| **... + stifle 40T/80T + hock 40T/80T** | **0.4 s / 1.0, 283-286 mm/s** (+0.02) | **0.5 s / 2.0, 394 mm/s** (+0.05) | **12** | **+0.21 / +0.21 / +0.23** | **+0.11 / +0.09 / +0.12** |

**R8 was better than R8 reported.** Its grid stopped at 0.6 s. Its pulley-only body trots within every limit at
0.5 s / stride 1.0 (208 mm/s) and at 0.4 s / 0.5 (162 mm/s, margin +0.00), against "0.6 s, 130-137 mm/s". Its
0.6 s / 0.5 trot is still over on hip ab/ad sustained torque (-0.08). The comparison below is against the re-run.

## The best assignment

**New STS3250s on the hip ab/ad and the hocks (four).** Carpi at 1:1 on 45T/45T with the old servo (R8's what-if).
Stifles and hocks on the catalog's 40T/80T pair, belts 444 mm (C 161.5) and 400 mm (C 139.4); every belt check
passes. The one check that stays "unknown" (hock servo against the stifle belt: the servo's output-axis offset is
not entered) is unknown on today's body too.

* Mass 1382 g as entered (1304 today; pulley masses are still null).
* **12 trots of the grid within every limit on all three seeds**, R8's body 7:
  * quickest: 0.4 s / 1.0 at 283-286 mm/s (+0.02);
  * fastest: 0.5 s / 2.0 at **394 mm/s** (+0.05).
  * The 0.6 s / 0.5 trot R8 left over on hip ab/ad sustained torque is within (+0.04).
* Walk +0.21 / +0.21 / +0.23 and turn +0.11 / +0.09 / +0.12, both more headroom than R8's body.
* **Against R8 (re-run): 1.9x the trot speed within every limit** (394 against 208 mm/s), with more trots, walk and
  turn margin.
* What binds now: joint speed again, at the old servos. Carpi 0.95-0.97, stifles up to 1.11 at 0.4 s / 2.0; then
  the new hocks (1.00-1.05).

| joint | servo, drive | trot 0.5 s / 2.0 | trot 0.4 s / 1.0 | walk | turn |
|---|---|---|---|---|---|
| front carpi | C018, 1:1 45T/45T | speed 0.91-0.93 | speed 0.95 | < 0.9 | < 0.9 |
| hocks | STS3250, 2:1 40T/80T | speed 0.91-0.92 | speed 0.91 | < 0.9 | < 0.9 |
| stifles | C018, 2:1 40T/80T | < 0.9 | speed 0.98 | < 0.9 | < 0.9 |
| hip ab/ad | STS3250, direct | < 0.9 | < 0.9 | < 0.9 | < 0.9 |
| shoulders | C018, direct | < 0.9 | < 0.9 | < 0.9 | < 0.9 |

(Share of the margin-lowered limit, the largest over the three seeds; "< 0.9" = nothing at 0.9 or above.)

**Does it need new pulleys?** Yes, but fewer than R8: **one size**, 45T for 10 mm GT2 belts, a pair per carpus
(four pulleys). R8's 30T/45T hock pair is not needed: the new hock servos make up the hock's speed at 2:1. The two
40T/80T pairs are already in the catalog. Without any new pulley, the best is a 0.8 s trot at 46-70 mm/s (new
carpi on 40T/80T). That is a quicker cycle than today but not faster travel, and neither it nor anything else
without new pulleys beats R8. The fastest trot within limits of all (0.5 s / 2.0, 414 mm/s) puts the new servos
on the hocks and shoulders, but its walk and turn go over.

## Belt tension and battery current

* **Peak belt tension** of the final body: 79 N (hind stifle) in any play within limits, 109 N in any play at
  all (a trot that goes over elsewhere), against 860 N breaking. Breaking is judged at 0.25 x 0.8 = 172 N, so
  the peaks are at 46 % and 64 % of the check. Sustained tension (allowable
  44 N x 0.8 = 35.2 N for more than 25 % of a 2 s window) is the belt limit that binds, wherever a belt binds.
* At stall the new servo puts 513 N into a 30T driver (the C018: 308 N): 60 % of the breaking strength. A 40T
  driver gives 385 N, a 45T 342 N. Today's servo can already exceed the 0.25 breaking check at stall. Stall itself
  is rejected by the safety policy, so no accepted play reaches these numbers.
* With the new servos the highest belt peaks are on the stifle: up to 138-158 N when the stifle or the hock servo
  is new and the stifle stays on 30T/60T (today: 107 N). The stifle on 40T/80T brings the final body back to 109 N.
* **Battery current:** in the final body's plays within limits, the four new servos together draw at most 2.1 A
  at peak (in the turn) and 0.8-1.0 A on average. The highest peak of any play is 3.0 A, in a trot that goes over a
  limit. Each value includes the defaulted 0.05 A idle current per servo. At stall, four would draw 16.8 A. **The
  six C018s' share is unknown** (no stall current entered), so the packs' total is unknown.
* The two 3S 2200 mAh packs in parallel have **no discharge rating in the library** (only their mass, in
  `config/feral_calf.yaml`), so no limit can be checked. If the researcher enters it, the per-servo currents are
  in the JSON.

## At 11.1 V (ADR-086)

The library's figures are at 12 V. ADR-086's assumption: stall and rated torque, no-load speed and stall current
scale linearly with voltage (x 0.925), so torque per amp is unchanged. The 11.1 V plays used the quick grid
(0.4-0.8 s), so for the slower bodies the 11.1 V column shows the best within 0.8 s, not their 1.0-1.2 s trots.

| body | fastest trot within, 12 V | 11.1 V | walk at 11.1 V | turn at 11.1 V |
|---|---|---|---|---|
| R8's pulley-only body | 0.5 s / 1.0, 208 mm/s | 0.6 s / 1.0, 131 mm/s | +0.11 / +0.05 / +0.11 | **-0.05 / -0.32 / -0.04** |
| new carpi, today's belts | 1.2 s / 1.5, 102 mm/s | 0.8 s / 0.5, 36 mm/s | -0.00 x3 (joint speed) | -0.23 / -0.23 / -0.03 |
| new stifles + carpi, carpus 40T/80T | 1.2 s / 1.0, 75 mm/s | 0.8 s / 0.5, 20 mm/s | -0.00 / -0.01 / -0.00 | +0.00 / +0.00 / +0.02 |
| new hocks + carpus 1:1 45T | 0.5 s / 1.5, 306 mm/s | 0.5 s / 1.5, 307 mm/s | -0.04 / -0.20 / -0.08 | -0.31 / -0.35 / -0.24 |
| **best body** | 0.5 s / 2.0, 394 mm/s | **0.5 s / 1.5, 300 mm/s** (+0.02) | **+0.15 / +0.15 / +0.16** | +0.01 / **-0.01** / +0.03 |

At the packs' voltage every body loses its fastest trots. The best body keeps a 0.5 s trot at 300 mm/s and the
walk, but its turn goes just over on one seed (envelope, -0.01). R8's body loses the turn on all three seeds and
its trot falls to 131 mm/s. Full packs (12.6 V) would be above the 12 V figures.

## R6c's and R7's safe behaviours on the best body (60 s, three seeds)

The four R6c cells and seven R7 cells, played exactly as `perform_r6.py` plays them: the candidate's stored
controller, the run's compile settings and randomisation, every limit at 0.2. The script reproduces today's
results exactly (R7 calm, seed 0: +0.428 both times).

| behaviour | today | best body | where it goes over |
|---|---|---|---|
| R6c calm | +0.38 / +0.17 / +0.17 | **-1.00 / -1.04 / -1.00** | front carpus, sustained torque |
| R6c lively | +0.03 / +0.02 / +0.03 | +0.43 / +0.12 / +0.43 | - |
| R6c walking | +0.02 x3 | +0.43 / **-0.40** / +0.43 | front shoulder, sustained torque |
| R6c trotting | +0.05 x3 | +0.00 / +0.00 / +0.00 | - |
| R7 calm | +0.43 / +0.16 / +0.16 | **-1.00 / -1.12 / -1.04** | front carpus, sustained torque |
| R7 ambling | +0.03 x3 | +0.42 / +0.39 / +0.39 | - |
| R7 lively | +0.03 / +0.02 / +0.03 | +0.43 / **-0.04** / +0.43 | front shoulder |
| R7 walking | **-2.52** / +0.30 / +0.29 | **-0.64** / +0.00 / +0.04 | front carpus |
| R7 trot-walk | +0.00 x3 | +0.35 / **-0.04** / +0.35 | front carpus |
| R7 trot-shift | +0.18 / +0.18 / +0.13 | **-0.08 x3** | front shoulder |
| R7 trotting | +0.02 / +0.02 / +0.04 | +0.04 / +0.00 / +0.04 | - |

**20 of 33 minutes hold on the best body, against 32 of 33 today.** Nothing fell.

* The behaviours move exactly as before: the same quantity of motion (2.2-12 deg/s) and trunk speed. They were
  evolved under today's joint speeds, and a faster body does not make them faster.
* **Where they hold, the headroom is new**: lively, walking, ambling and trot-walk go from +0.00-0.03 to about
  +0.35-0.43, because the carpus is no longer at its speed limit. There is room for more vigorous behaviour.
* **Where they fail, the front end is too weak to stand.** At 1:1 the old carpus servo has half the torque at the
  joint (0.98 N*m rated, against 1.96 at 2:1). The calm behaviours stand and shift their weight for most of a
  minute; in their worst 2 s window the carpus is above 48 % of rated for half the time (the limit is a quarter). The shoulders then carry more in
  shifts and trot-shift.
* The body that keeps the carpus at 2:1 does not do better: new stifles and carpi on 40T/80T, no new pulley,
  `perform_r9_nopulley.json`, report only. **18 of 33 hold.** The heavier, stiffer carpi move the load onto the old
  front shoulders, which go over in calm, lively, walking, trot-shift and trotting.
* **Newly possible:** a 0.4-0.5 s trot up to 394 mm/s, and a walk and turn with margin to spare. **Not yet:** a
  repertoire that uses it. R6c's and R7's behaviours would have to be evolved again on such a body (coverage and
  capped durations as in R6c, variation as in R7). The calm states need the carpus torque that a 1:1 carpus gives
  away.

The 33 minutes on the best body are runs titled `R9 what-if (new: hip_abd+hock | ...) <label> ...` (Journal >
Runs). The 33 on the same body without the hock 40T/80T pair are `R9 what-if (new: hip_abd+hock | carpus 1:1 45T |
stifle 40T-80T) ...`; their front end is the same, and so are the results within 0.1. Their stored genome builds
the working body: Simulate or Load from them gives today's servos and belts.

## What this rests on, and what is not checked

* **The STS3250's figures are the researcher's, unverified**, at 12 V. So are the C018's (whose stall current is
  missing). The simulated servo's stiffness follows its stall torque (above).
* **45T pulleys are what-ifs** (R8's `d1` x 1.5 and ratio 1; not in the catalog, nothing added). The catalog pairs
  (36T/72T, 40T/80T) are real catalog entries with real belt checks, but their **masses are null** (0 g).
* Whether a 45T pulley (28.6 mm pitch diameter) or an 80T one (50.9 mm) fits at its joint, clear of the leg and the
  other belt, is not checked beyond the catalog's checks.
* `lie_rise` was not played. It loads the carpi most, and the calm behaviours already show the 1:1 carpus short of
  torque.
* The primitives are played alone, plus the 60 s performances; nothing was evolved on the new body.
* Pulley masses, skin and 14 other parts have no mass yet; ADR-086 found the step verdicts sensitive to mass.
