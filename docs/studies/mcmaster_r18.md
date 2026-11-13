# R18 — g020-008-r01 on McMaster-Carr timing belt parts only (1/4 in bore pulleys)

Session R18, 2026-11-12. ADR-115 to ADR-120. Script `docs/studies/mcmaster_r18.py` (stages `fits`, `swap`, `mass`,
`loads`, `replay`, `preset`, `search`, `confirm`, `sheets`, `store`, `summary`), catalog script `catalog_r18.py`, data
`mcmaster_r18.json`, tables `mcmaster_r18_tables.md`, every fitting choice in `mcmaster_r18_fits_<drive>.csv`,
production sheets in `sheets_r18/`. Compare page: `compare.html?set=r18`.

**Read every result with these caveats:**

- **Breaking strength assumed.** The McMaster belts' breaking strength is the researcher's assumption of
  2026-11-12: 51 lbf per 1/8 in of width (71.4 N/mm), so 429 N for 6 mm and 643 N for 9 mm. McMaster does not
  publish it.
- **Allowable working tension from Gates 17611-T (ADR-120, entered during the session).** Gates' recommended working
  tension per inch, proportioned with width: 179.6 N for the 9 mm 3MGT belt, 26.2 N for the 6 mm 2MGT belt. It is
  GT2-generation data; McMaster lists the belts as GT2 / GT3 / GT4 compatible, so it is likely conservative for GT3.
  It is a recommended working tension, not a full drive-design rating.
- **Two kinds of "within limits":**
  - *within* means within every limit at margin 0.2, sustained belt tension included;
  - *within\** excludes sustained belt tension. Sections 4-5 were first judged that way, before the allowable existed;
    the swap was then re-judged with it.

## Why

The working body's belt hardware cannot be sourced:

- GT2-80T-10 has one listing, marked sold out;
- GT2-40T-10's only read listing is sold out;
- the 640 and 444 mm belts have one unconfirmed listing each.

From now on every pulley and belt comes from McMaster-Carr: GT pulleys with a finished 1/4 in bore (set screw), and
closed neoprene GT belts (fiberglass cord, nylon-coated teeth). No cut-to-length belts.

## 1. The catalog (ADR-115)

| system | pitch / width | pulleys (1/4 in bore) | closed lengths | breaking strength | allowable working tension (Gates) | Gates ultimate per span (comparison only) |
|---|---|---|---|---|---|---|
| `MM-2MGT-6` | 2 mm / 6 mm | 60T 3764N118, 72T 3764N119 | 46 (50-582 teeth, 7947K711-K764) | 429 N (**assumed**) | 26.2 N (111 x 6 / 25.4) | 517 N (5 338 / 2 x 6 / 25.4 x 0.82) |
| `MM-3MGT-9` | 3 mm / 9 mm | 16-45T, 3764N125-N141 (16 sizes) | 42 (33-687 teeth, 7947K765-K828) | 643 N (**assumed**) | 179.6 N (507 x 9 / 25.4) | 1 560 N (9 786 / 2 x 9 / 25.4 x 0.90) |

Gates' ultimate strength is "not appropriate for use in belt drive design" (its note 3) and is not entered. The
breaking check uses the researcher's assumption, which is well below Gates' figure for 9 mm (643 against 1 560 N)
and about equal to it for 6 mm (429 against 517 N).

- **What the part pages list:** all 18 pulley pages were read in the built-in browser. Each lists the pitch
  diameter (it agrees with teeth x pitch / pi), flanges, hub diameter, OD, inside / outside / overall width and a
  set-screw mount. No page lists a weight or a set-screw size: those stay unentered.
- **Belt pages:** three were read (the swap's belts). They list a price and the Gates number, and no weight.
- **Mass:** no pulley or belt mass is entered, so each counts 0 g, as every pulley has since ADR-068.
- **Earlier entries:** every system, pair, pulley, length source and length is kept and marked `not_sourceable`
  with its evidence.
- **Offered from now on:**
  - `set_belt_drive`, the Belts panel and a search with `sourceable_only` offer only McMaster parts;
  - a McMaster system also checks that both pulleys and the length come from McMaster (check `vendor`).
- **Stored bodies:** they build exactly as before.
- **New projects:** the default rule chooses 3MGT 30T/45T on `MM-3MGT-9`.
- **Mounting (open, not modelled):** each belted servo needs a spline-horn-to-1/4 in shaft adapter, and each belted
  joint a 1/4 in axle. They are listed as open items with no mass or size.

## 2. What fits each drive of g020-008-r01 (ADR-116)

A fit passes every belt check:

- pitch, pulley width and vendor;
- the length is offered;
- the belt goes round both pulleys;
- pulley gap: C > (D1 + D2) / 2 + 3 mm;
- at least 6 teeth in mesh;
- the servo case lies on its segment;
- at the hock, the hock servo clears the stifle belt through the stifle's range.

"Unknown" checks (the servo's output-axis offset is not entered) do not fail.

| drive | now | McMaster choices that fit | pulley pairs | ratios | C range |
|---|---|---|---|---|---|
| stifle (femur 198 mm) | 40T/60T 2 mm, 1.5:1, C 171.9 | 7 371 | 260 | 0.36-2.81 | 28-238 mm |
| hock (tibia 239 mm) | 40T/60T 2 mm, 1.5:1, C 149.9 | 5 125 | 260 | 0.36-2.81 | 28-161 mm |
| carpus (upper leg 340 mm) | 80T/80T 2 mm, 1:1, C 240.0 | 8 408 | 260 | 0.36-2.81 | 28-312 mm |

- **Most choices are 3MGT.** The 2MGT system has only 60T and 72T at 1/4 in, so 1:1, 1.2:1 and 0.83:1.
- **Why choices fail:** most failures are the servo case not fitting its segment. At the hock, many fail the
  stifle-belt clearance.
- The full lists are in the CSVs and the per-pair counts in tables section 1. The shoulder is direct on this body.

## 3. The closest swap g020-008-r01-mc (ADR-116)

Each drive moves to the fitting choice with:

1. the ratio nearest the current one;
2. then the most belt margin per N*m of servo torque (driver pitch radius x the assumed breaking strength);
3. then C nearest the current C.

| drive | now | swap | belt | C mm (was) | gap mm | teeth in mesh | parts |
|---|---|---|---|---|---|---|---|
| stifle | 40T/60T 2 mm, 444 mm | 3MGT 30T/45T, 1.5:1 | 450 mm, 150 T | 168.6 (171.9) | 132.8 | 14.6 | 7947K795, 3764N134 / N141 |
| hock | 40T/60T 2 mm, 400 mm | 3MGT 30T/45T, 1.5:1 | 414 mm, 138 T | 150.6 (149.9) | 114.8 | 14.5 | 7947K792, 3764N134 / N141 |
| carpus | 80T/80T 2 mm, 640 mm | 3MGT 45T/45T, 1:1 | 600 mm, 200 T | 232.5 (240.0) | 189.5 | 22.5 | 7947K815, 3764N141 x 2 |

- **Every check passes.** The hock's stifle-belt clearance stays "unknown" as on the baseline: it clears for some
  output-axis positions only.
- **Mass:** 2073.9 g, the same as the baseline (no pulley or belt mass is entered).
- **Bill of materials:** **USD 301.36**, complete for the drives. That is 6 belts and 12 pulleys:
  - 3764N134 x 4;
  - 3764N141 x 8;
  - one pair each of 7947K795, K792 and K815.
- **Open and unpriced:** 6 shaft adapters and 6 axles.

## 4. Statics and loads (baseline vs swap; judged before ADR-120)

**Belt tension per unit of servo torque:**

- stifle and hock fall by 11 % (30T 3MGT driver, pitch radius 14.3 mm, against 12.7 mm for 40T 2 mm);
- the carpus rises by 18 % (45T 3MGT driver, 21.5 mm, against 25.5 mm for 80T 2 mm);
- the assumed breaking strength is 643 N against 860 N, so every peak is a larger fraction of it.

| play (seed 0) | within* | stifle peak / mean N | hock | carpus | largest peak as a share of breaking (assumed) |
|---|---|---|---|---|---|
| standing (statics) | - | 4 / - (5) | 3 / - (3) | 14 / - (12) | 0.02 (0.01) |
| level stand | yes (yes) | 9 / 1 (10 / 2) | 8 / 7 (9 / 8) | 17 / 8 (14 / 7) | 0.03 (0.02) |
| lowest stand (0.93) | yes (yes) | 75 / 20 (84 / 23) | 91 / 3 (101 / 4) | 82 / 3 (70 / 3) | 0.14 (0.12) |
| walk 256 mm/s | yes (yes) | 45 / 9 (50 / 10) | 45 / 16 (50 / 18) | 52 / 13 (44 / 11) | 0.08 (0.06) |

Swap first, baseline in brackets. The breaking check allows 25 % x 0.8 = 20 % of breaking strength (129 N on 9 mm).

## 5. The R16 repertoire replayed (107 behaviours, seeds 0-2, 30 s, margin 0.2)

Two rounds of judging:
- **First round, before ADR-120:** baseline and swap, judged *within\**.
- **Second round, after ADR-120:** the swap and the three reformulated bodies replayed with Gates' allowable in
  place, so *within* includes sustained belt tension. The swap's plays are bit-identical to the first round; only
  the sustained check is now decided.

| body | hold and within, every limit, on all seeds | of the 52 full-search cells | hold and within* |
|---|---|---|---|
| g020-008-r01 (baseline; its 10 mm belt's own 44 N allowable) | 102 | 52 | 103 |
| **g020-008-r01-mc (closest swap)** | **103** | **52** | 103 |
| r18-a | 49 | 33 | 49 |
| r18-b | 62 | 37 | 62 |
| r18-c | 89 | 43 | 89 |

**The swap keeps the repertoire, sustained belt tension included.**
- No swap belt comes near the 9 mm sustained limit: at margin 0.2 it trips only above 143.7 N held for 25 % of a
  2 s window.
- Its highest repertoire peaks are 114 N on the stifle and 132 N on the carpus (both in the lying probe, which is not
  within limits anyway) and 99 N on the hock (the lowered nose-up stand).
- Its highest means are 40 / 23 / 24 N.
- It loses one fast trot, `probe_trot:trot|3|0` (seed 1, right hip ab/ad sustained torque, margin -0.08).
- It gains `probe_gaits:irregular|2|1`, which the baseline loses on hip ab/ad torque.
- Both are seed-to-seed differences at a joint without a belt.
- The baseline also loses `pilot:trot|2|0` on its own 44 N belt limit, which the 9 mm belt does not hit.

**Where the swap binds** (worst seed per behaviour): hind stifle and hock joint speed, and the stifle's torque-speed
envelope. Servos, not belts. The breaking check (assumed strength) trips only in the lying probe (132 N > 129 N).

**The reformulated bodies do not play R16's behaviours as well.** Those controllers were tuned for g020-008-r01's
exact geometry and ratios:
- **r18-a:** 49 behaviours. Bound by hind stifle **joint speed**: its 2.25:1 stifle (20T/45T) lowers the stifle's top
  speed by a third.
- **r18-b:** 62. Bound by the **assumed breaking strength** at the 20T stifle driver (peaks to 216 N) and by front
  shoulder torque.
- **r18-c:** 89. Bound by front **carpus joint speed** (34T/45T, 1.32:1) and front shoulder torque; the assumed breaking
  strength trips in 19 plays.
- These bodies hold most of the R11c suite they were searched on (section 6). They need behaviours searched for their
  own geometry, as R12 found for Stage B's bodies.
- The breaking limit that binds r18-b is the researcher's assumption (643 N). Gates' per-span figure for 9 mm is
  about 1 560 N (note 3: not for drive design).

**What an allowable would have kept** (from the first round: behaviours that also spend at most 25 % of every 2 s
window above 0.8 x allowable on every drive):

| allowable | 25 N | 37.5 N | 50 N | 62.5 N |
|---|---|---|---|---|
| baseline | 15 | 54 | 103 | 103 |
| swap | 14 | 77 | 103 | 103 |

- **9 mm 3MGT (Gates 179.6 N):** far above this range: every behaviour is kept.
- **6 mm 2MGT (Gates 26.2 N, 21 N at the margin):** it would keep about 14. That rules out 2MGT drives for this repertoire.

Tables section 5 gives every behaviour's belt numbers and its time above 20 / 30 / 40 / 50 N.

## 6. Reformulation search (ADR-117)

Preset `hardware_r18`, optimizer `map_elites_hardware`, started from Stage B's candidate g020-008-r01:
- belts: the two McMaster systems only; the carpus may be belted or direct;
- otherwise hardware_r14 v2: the servo per joint pair, geometry within +-10 %, springs, the shoulder drive;
- the R11c suite at margin 0.2, **judged on seed 0** (the researcher's choice of a lighter judge, to fit the session);
  the six best distinct bodies were then **confirmed on seeds 0-2** (`confirm`).

**Timing and the allowable:**
- **The search ran before ADR-120.** It inlined the catalog at its start, with a null allowable, so the sustained
  belt check could not trip during the search and 2MGT drives were not penalised.
- **The confirmation came after ADR-120:** Gates' 179.6 / 26.2 N were in place.
- **Pilot** (`20261112-213030-evolve-b674`): 1 generation of 15 in 11 min on 14 workers.
- **Budget run** (`20261112-214157-evolve-3baa`): 8 generations, seed 1, 91 min while other jobs shared the CPU.
  - 154 draws, 34 rejected before any play: springs off their segment, segment ratios beyond +-5 %.
  - Best seed-0 fitness per generation: -0.75, -0.57, -0.49, -0.44, -0.26, -0.33, -0.26, -0.16. Still rising: not
    converged.

**Budgets** (from the pilot; seed-0 judging, then about 0.3 h to confirm):

| budget | generations | seed 0 | three seeds |
|---|---|---|---|
| S | 5 | ~0.9 h | ~2.6 h |
| M | 10 | ~1.8 h | ~5.2 h |
| L | 20 | ~3.7 h | ~10.3 h |

**Confirmed on seeds 0-2**, with Gates' allowable in place, so sustained belt tension is included:

| body | candidate | suite minutes held | trot within | screen held | cost | fitness, seed 0 -> 3 seeds | what stops plays |
|---|---|---|---|---|---|---|---|
| closest swap | - | 0/33 (seed 0: 0/11) | 550 mm/s | 14/23 | - | -0.75 (seed 0) | - |
| **r18-a** | g007-007 | **29/33** | 287 mm/s | 7/23 | 1.54 | -0.16 -> -0.27 | hind stifle speed, hip ab/ad torque |
| **r18-b** | g004-001 | 25/33 | 399 mm/s | 9/23 | 1.78 | -0.27 -> -0.34 | front carpus and shoulder torque |
| **r18-c** | g006-010-r02 | 27/33 | 556 mm/s | 14/23 | 1.83 | -0.26 -> -0.41 | front shoulder, hip ab/ad torque |
| - | g007-006 | 25/33 | 543 mm/s | 14/23 | 2.08 | -0.26 -> -0.48 | front shoulder torque |
| - | g007-002 | 21/33 | 424 mm/s | 10/23 | 1.79 | -0.33 -> -0.43 | front shoulder, carpus torque |
| - | g007-003 | 11/33 | 297 mm/s | 7/23 | 1.25 | -0.32 -> -0.45 | front carpus torque |

The three best by three-seed fitness were adopted as `r18-a` / `-b` / `-c`:

| body | lengths femur / tibia / rear cannon / upper leg / front cannon (mm) | C002 pairs | springs | stifle | hock | carpus | mass |
|---|---|---|---|---|---|---|---|
| baseline / swap | 198 / 239 / 226 / 340 / 247 | hock, shoulder, carpus | none on | 30T/45T, 450 | 30T/45T, 414 | 45T/45T, 600 | 2073.9 g |
| r18-a | 200 / 241 / 222 / 340 / 235 | + hip ab/ad | hip ab/ad, stifle, hock | 20T/45T (2.25:1), 180 | 30T/45T, 480 | 34T/45T (1.32:1), 600 | 2109.4 g |
| r18-b | 200 / 243 / 220 / 336 / 235 | all five | hip ab/ad, stifle, hock | 20T/45T, 420 | 30T/45T, 414 | **direct** | 2099.2 g |
| r18-c | 198 / 245 / 230 / 336 / 249 | all five | hip ab/ad, stifle, hock | 30T/45T, 450 | 30T/45T, 414 | 34T/45T, 375 | 2154.2 g |

All belts are 3MGT 9 mm. The search played 2MGT on the stifle or hock of 41 of its 120 played bodies; none of the
six front-runners uses one. The baseline/swap stifle
and hock are 40T/60T GT2 on the baseline and 30T/45T 3MGT on the swap.

**What the search found:**
- The gain over the swap is mostly **servos and springs, not belts**:
  - a C002 on the hip ab/ad, the servo that has bound since R14;
  - hip ab/ad, stifle and hock springs;
  - small length changes.
- The stifle moves to a **20T driver (2.25:1)** on two of the three bodies. That raises the stifle's belt tension per
  N*m: confirmed peaks of 149-199 N. They lie over the assumed breaking limit (129 N at the margin) only in plays that
  fail anyway.
- The bodies use **8-10 C002**. The preset counts new C002 beyond the starting body's six, so up to twelve.

## 7. Production sheets (ADR-118)

`docs/studies/sheets_r18/<body>_geometry.csv` (Rhino / Grasshopper) and `<body>_parts.json` (parts, `bom`, open items,
`to_verify`). McMaster part numbers only; prices as read on 2026-11-12, without shipping or tax.

| body | belts | pulleys | bill of materials |
|---|---|---|---|
| closest swap | 7947K795, K792, K815 (2 each) | 3764N134 x 4, 3764N141 x 8 | **USD 301.36** |
| r18-a | 7947K771, K797, K815 (2 each) | 3764N128 x 2, N134 x 2, N136 x 2, N141 x 6 | **USD 288.26** |
| r18-b | 7947K793, K792 (2 each) | 3764N128 x 2, N134 x 2, N141 x 4 | **USD 184.44** |
| r18-c | 7947K795, K792, K789 (2 each) | 3764N134 x 4, N136 x 2, N141 x 6 | **USD 304.24** |

- **Every bill is complete:** all seven belt pages used were read for their price.
- **Open and unpriced:** one servo-to-1/4 in shaft adapter per belted servo, and one 1/4 in axle per belted joint
  (6 each; 4 each on r18-b, whose carpus is direct).
- **Not in any total:** servos, springs and the frame.

## 8. What is not modelled or not known

- The allowable working tension is Gates' recommended working tension for GT2 (ADR-120). It is not a drive-design
  rating by pulley teeth and teeth in mesh, and not specific to the GT3 belts McMaster may ship.
- Their breaking strength (assumed).
- Pulley and belt masses (none listed).
- The set-screw size (not listed).
- The servo-to-1/4 in shaft adapters and the 1/4 in axles: open, no mass or size.
- The lateral stack. Pulleys are 17.6-21.2 mm wide overall against the 9 mm belt, and the lab still places
  everything in one plane.
- `purchase_confirmed` is false for every part.
