# Belted or direct carpus on g020-008-r01-mc (after R18; ADR-123, ADR-124)

2026-11-12. Script `docs/studies/carpus_r18.py` (stages `body`, `mass`, `clearance`, `statics`, `loads`, `replay`,
`suite`, `sheets`, `store`, `summary`; it reuses `mcmaster_r18.py`'s bodies, plays, judging, sheets and store). Data
`carpus_r18.json`, tables `carpus_r18_tables.md`, sheet `sheets_r18/g020_008_r01_mc_direct_*`. Compare page:
`compare.html?set=r18`, where the direct body sits beside the belted swap.

**Recommendation: keep the belted carpus on g020-008-r01-mc.**

- **The behaviours were written for the belted body, and the direct body keeps fewer of them:** 87 of R16's 107
  within every limit on all three seeds, against 103. Of the 52 full-search cells it keeps 47.
- **It gains none.** Every one of the 16 it loses fails on **sustained servo torque**:
  - 9 at the **front shoulder**;
  - 7 at the **hind hip ab/ad**, the C018 that has been the body's weak servo since R14.
- **The cause at the shoulder** is the C002 carpus servo (74.5 g) moving from 107.5 mm below the shoulder axis to
  340 mm.
  - The front leg's moment of inertia about the shoulder rises **49 %**, from 0.0132 to 0.0197 kg·m².
  - Its centre of mass moves from 214 to 314 mm below the axis.
  - The leg is 24 g lighter (the carpus axle goes), but that does not make up for it.
- **What the direct carpus gives:**
  - **USD 99.78** off the bill of materials (USD 301.36 → 201.58);
  - two fewer servo shaft adapters and two fewer axles, both still unchosen;
  - 48 g less in all;
  - slightly lower carpus loads (median peak −12 %).
  None of these is something that binds: the carpus belt binds nothing in the repertoire (highest peak 132 N, in the
  lying probe only; the sustained limit at the margin is 143.7 N).
- **The ground clearance at the carpus does not separate them.** Both put hardware about 20 mm below the carpus axis:
  - the belted driven pulley (pitch radius 21.5 mm);
  - the direct servo case (45.2 mm long, centred on the axis).
  Each becomes the leg's lowest point once the carpus folds past about 75°. Only the lying probe gets there.
- **The R11c suite does not separate them either:** both hold 1 of 33 minutes. The direct body holds fewer screen
  plays (10 against 12 of 23), and its fastest trot within limits is slower (435 against 546 mm/s).

A direct carpus would make sense if the behaviours were searched for it, for example with the swap's preset
`hardware_r18` and the carpus forced direct, as R18's r18-b was. On g020-008-r01-mc's own repertoire, the belt keeps
the servo's mass near the shoulder, and the shoulder is what binds.

**Read every result with these caveats:**

- **Breaking strength assumed:** 51 lbf per 1/8 in, 643 N for the 9 mm belt.
- **Allowable working tension:** Gates 17611-T, 179.6 N (ADR-120).
- *Within* means within every limit at margin 0.2, sustained belt tension included, as R18 judged.
- Masses are explicit_v2. Pulleys and belts count 0 g (none listed); the shaft adapters and axles are not modelled.
- The C002's idle current and rotor inertia (`armature_kgm2`, 0.005 kg·m² at the joint) are defaulted library
  values. The current figures count the six C002s only; the four C018s have no stall current.

## 1. The two bodies

| body | carpus | genes |
|---|---|---|
| `g020-008-r01-mc` | belted 1:1, 3MGT 45T/45T, 600 mm, C 232.5 mm; C002 on the upper leg 107.5 mm below the shoulder | R18 swap |
| `g020-008-r01-mc-direct` | direct: C002 on the carpus joint, outboard of the upper-leg tube, centred on the axis | the swap with `carpus_belt: false` only |

- Same lengths, servos and springs, and the same stifle and hock belts (3MGT 30T/45T, 450 / 414 mm).
- Both build at mass model explicit_v2 with the project's current catalog. Every check passes.
- The direct body's genes are in `mcmaster_r18.json` under `bodies`.

## 2. Mass and where it sits (tables section 1)

| | belted | direct |
|---|---|---|
| total | 2073.9 g | **2025.9 g** (−48: the two 24 g carpus axles) |
| front leg (upper + cannon) | 197.7 g | 173.7 g |
| front leg centre of mass from the shoulder axis | 213.5 mm | **314.4 mm** |
| front leg moment of inertia about the shoulder axis (standing) | 0.01324 kg·m² | **0.01968 kg·m²** (+49 %) |
| the same, carpus folded to 130° | 0.00779 | 0.01423 |
| reflected rotor inertia the simulator adds at the shoulder (defaulted) | 0.0050 | 0.0050 |
| whole-body centre of mass (x, z) | 30.5, 508.8 mm | 27.7, 494.7 mm |

- **Where the numbers come from:** the leg's numbers are taken from the simulator's compiled model, in the standing
  pose. The servo moves from the upper leg's top third to its lower end; nothing else moves.
- **Mass breakdown:** the trunk (1075.0 g) and the hind legs are unchanged. The difference by source is component
  −48 g. Headroom (300 g) and specified masses (150 g) are unchanged.

## 3. The carpus hardware's clearance (tables section 2)

**Method:**
- The carpus is swept through its range (−10 to 130°), with the upper leg at its standing angle.
- Each part's lowest point is compared with the leg's lowest collision point: the hoof, or the carpus tube once the
  cannon folds.

| part | standing | least | the leg's lowest point from |
|---|---|---|---|
| direct: servo case | 244.6 mm above the hoof | −19.5 mm at 130° | 75° |
| belted: driven pulley at the carpus (pitch diameter 43.0 mm) | 248.0 mm | −16.1 mm at 130° | 76° |
| belted: carpus servo on the upper leg | 470.1 mm | 206.0 mm | never |

- **In the plays:**
  - only R16's lying probe brings either part below the floor: the pulley to −14 mm at 82°, the case to −17.7 mm
    at 117°;
  - no other play comes within 50 mm.
  The parts are visual geoms, so the simulator never feels them.
- **The direct case against the front cannon:** a 2.0 mm gap through the whole range, all of it lateral. In the side
  view the case always overlaps the cannon near the joint; only the case's outboard placement separates them.

**Not checked (and not guessed):**
- **The servo's output-axis offset along its case** (not entered). The model centres the case on the carpus axis. A
  real STS3250's shaft is off-centre, so the case's lowest point moves by that offset, up or down depending on which
  way the case is turned. Turning its long end up the leg would raise it.
- **The lateral stack:** horn, any bearing or adapter, the cannon's fitting at the joint. The 2 mm gap is the
  generator's fixed constant, not a design.
- **The case against the chest block, the other leg and the trunk** in a turn or a lie.
- **The pulley's flanges:** the listed OD 45 mm would make the belted pulley 1 mm lower.

## 4. Statics and loads (tables sections 3-4)

**Holding torque, standing pose** (servo, N·m):

| | shoulder | carpus |
|---|---|---|
| belted | 0.038 | 0.303 (belt 14.1 N) |
| direct | 0.004 | 0.293 |

Both are a few % of the C002's 1.57 N·m rated torque. The direct shoulder's static torque is smaller because the leg's
centre of mass sits almost under the shoulder axis when standing.

**The three R18 load plays (seed 0).** All hold within limits on both bodies.

| play | body | margin | binds | shoulder servo peak / mean N·m | carpus servo peak / mean N·m | carpus speed use | known current peak / mean A |
|---|---|---|---|---|---|---|---|
| level stand | belted | 0.87 | fl.carpus envelope | 0.31 / 0.14 | 0.36 / 0.17 | 0.03 | 1.11 / 1.01 |
| level stand | direct | 0.90 | hl.stifle envelope | 0.28 / 0.10 | 0.34 / 0.16 | 0.03 | 1.03 / 0.93 |
| lowest stand | belted | 0.12 | fl.shoulder torque | 2.67 / 0.42 | 1.77 / 0.07 | 0.12 | 8.94 / 1.22 |
| lowest stand | direct | **0.08** | fl.shoulder torque | 2.69 / 0.37 | 1.73 / 0.07 | 0.11 | 8.99 / 1.13 |
| walk 256 mm/s | belted | 0.30 | hr.stifle speed | 1.02 / 0.26 | 1.12 / 0.29 | 0.33 | 3.10 / 1.55 |
| walk 256 mm/s | direct | 0.31 | hr.stifle speed | 1.02 / **0.35** | 0.94 / 0.27 | 0.33 | 2.99 / 1.65 |

- Envelope use stays below 0.6 for the shoulder and carpus in all three. No joint spends any time above 0.9 of its
  envelope.
- Per-servo current and the shoulder joint speed are in tables section 4.

**Over the whole repertoire** (all 321 plays per body, direct / belted, median with the 10th-90th percentile):

| quantity | median | 10th-90th percentile |
|---|---|---|
| shoulder servo mean torque | **1.13** | 0.79-1.39 |
| shoulder servo peak | 0.98 | |
| shoulder current, mean | 1.10 | |
| carpus servo mean torque | 0.95 | |
| carpus servo peak | 0.88 | |
| known whole-body current, mean | 1.01 | |

Joint speeds are unchanged. The sustained check counts time spent above 0.6 x rated (x 0.8 at the margin). A higher
*mean* at the shoulder is what fails it.

## 5. Behaviour: the R16 repertoire (tables section 5)

107 behaviours, seeds 0-2, 30 s, margin 0.2, judged exactly as R18 judged the swap. The swap's 321 plays were replayed
fresh; every judged field (holds, within, margin, violations, binding limit) equals R18's stored records.

| body | hold and within on all seeds | full-search cells |
|---|---|---|
| belted (swap) | **103** | 52 of 52 |
| direct | 87 | 47 of 52 |

- **Gained:** none.
- **Lost (16):** every one fails sustained servo torque on some seed; two also exceed joint speed.

| where it binds | lost behaviours |
|---|---|
| front shoulder | `full:stand|0|2` (the lowest stand, seed 1), `full:trot|6|2`, `full:walk|5|2`, `pilot:irregular|2|1`, `pilot:trot|2|0`, `probe_gaits:trot|3|1`, `probe_gaits:walk|3|3`, `probe_trot:trot|7|1`, `probe_trot:trot|8|1` |
| hind hip ab/ad | `full:pace|5|2`, `full:walk|6|2`, `pilot:trot|6|2`, `pilot:walk|5|2`, `probe_gaits:irregular|5|2`, `probe_gaits:trot|2|1`, `probe_trot:trot|2|0` |

- **The hip ab/ad losses:** the hip ab/ad's static load is slightly *lower* on the direct body (0.111 against
  0.115 N·m), so these losses are dynamic. With heavier-swinging front legs the controllers' gaits roll and sway
  differently. Several of them were already marginal on the swap (`probe_trot:trot|2|0` at margin 0.00).
- **Where each body binds** (worst seed per behaviour):
  - the swap: hind stifle and hock joint speed (42 behaviours; 28 on the direct body);
  - the direct body: front shoulder torque 21 (7 on the swap), hip ab/ad torque 19 (13).
- **Margins:** the direct margin is better on 144 of 321 plays, worse on the rest.

Per-behaviour holds / within / margin / binding limit for both bodies, with shoulder and carpus peaks, carpus speed
and envelope use and the hardware's floor clearance, are in tables section 5.

## 6. Behaviour: the R11c suite (tables section 6)

Screen + 11 suite behaviours, 60 s, seeds 0-2. Scored as `mcmaster_r18.py confirm` does: preset `hardware_r18`, its
controllers, cache and baseline, and run `20261112-214157-evolve-3baa`'s compile settings (the torque-only servo
model, the same as the repertoire's).

| body | fitness (3 seeds) | suite minutes held | fastest trot within | screen held |
|---|---|---|---|---|
| belted | −0.810 | 1 / 33 | 546 mm/s | 12 / 23 |
| direct | −0.803 | 1 / 33 | 435 mm/s | 10 / 23 |

- Neither body plays the R11c suite: every suite behaviour fails sustained servo torque. The one minute each holds
  is `R7-ambling` on one seed.
- **What stops the suite:**
  - on the swap: hip ab/ad (C018), stifle and carpus;
  - on the direct body: stifle, carpus and hip ab/ad.
- R18's seed-0 judgement of the swap was 0/11.
- The suite's controllers were written for older bodies, so it does not discriminate here.
- **Screen:**
  - the direct body holds one short-cycle trot the swap does not (0.4/0.5);
  - it loses three long-stride trots (0.4/2, 0.45/2, 0.5/2).

## 7. Hardware difference (tables section 7)

| | belted | direct |
|---|---|---|
| 45T pulleys 3764N141 | 8 | 4 |
| 600 mm belts 7947K815 | 2 | 0 |
| bill of materials (belts + pulleys, USD, as read 2026-11-12) | 301.36 | **201.58** |
| open: servo shaft adapters / 1/4 in axles | 6 / 6 | 4 / 4 |

- **Production sheet** (`sheets_r18/g020_008_r01_mc_direct_geometry.csv`, `_parts.json`):
  - the four carpus pulley rows and the derived carpus C are gone;
  - the carpus servo moves from (301.2, ±179.1, 496.6) to (357.9, ±188.8, 271.0) mm, standing pose, on the carpus
    axis.
- **The direct carpus needs a horn-to-cannon fitting at the joint** (not modelled, not listed): the spline horn must
  carry the cannon. That replaces the adapter and axle, but it is still a part to choose.

## 8. What is not modelled or not known

- The servo's output-axis offset; the lateral stack at the carpus; the horn-to-cannon fitting.
- Pulley and belt masses; the adapters and axles (the belted body's cost in mass is therefore understated).
- Contact of the servo case or pulleys with the ground: they are visual geoms.
- The C002's rotor inertia and idle current (defaulted); the C018's stall current (unknown).
- Behaviours searched for the direct body: none were. The comparison is on the swap's own repertoire.
