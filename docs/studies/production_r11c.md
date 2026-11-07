# R11c — toward a production body (ADR-103)

Everything here is **simulated** and rests on unverified library and catalog values. "Best" means best found under
these limits and behaviours.

## Step 0 — sourced catalog (added 2026-11-06, every entry `verified: false`)

Belt systems (existing, the researcher's figures; nothing changed but the 15 mm system's lengths):

| System | Allowable working tension | Breaking | Source of each | Lengths offered | Pulleys listed for this width |
|---|---|---|---|---|---|
| GT2 2 mm, 10 mm generic | 44 N (4.37 N/mm x 10; SDP-SI per inch of width, narrow belts must be derated) | 860 N (86 N/mm x 10; Ondrives per mm) | as entered by the researcher, ADR-064 | 14 (source C, unchanged) | 20, 30, 36, 40, 45, 48, 60, 80T |
| GT2 2 mm, 15 mm generic | 66 N (same per-width rule) | 1290 N (same) | as ADR-064 | **2 new**: 300, 310 mm (source E) | 20, 40, 60, 80T |
| GT2 2 mm, 9 mm Gates | 39 N | 774 N | ADR-064 | 92 (source B) | **none found**: not offered in the search |
| GT2 3 mm, 9 / 15 mm | unknown | 1422 / 2370 N | ADR-064 | 51 (source D) | none: not buildable, as before |

Scaling per width is the sources' own (SDP-SI gives a figure per inch of width, Ondrives per mm of width); no new
tension figure was entered.

New belt length source **E**: Amazon B0DPV1912G, "GT2/2M Closed Loop Rubber 2GT Timing Belt, Length 300mm 310mm,
Width 6mm/9mm/10mm/12mm/15mm" — search-result title only (https://www.amazon.com/clp/B0DPV1912G). Offered for 15 mm
only. A wider 15 mm range (homediyer, 50T-175T) names no exact lengths; nothing entered from it.

Single pulleys (GT2, 2 mm pitch). "Read" = the listing page itself was read; otherwise only a search result's title
or snippet showed it (several shops refuse automated reading). Masses: the listing's figure, **not used** until
verified.

| Id | Teeth | Belt width | Bores (mm) | Listed mass | Listings (read?) |
|---|---|---|---|---|---|
| GT2-20T-10 | 20 | 10 | 5, 8 | unknown | na3D (read); Bits and Parts 20T 5 mm "for 10mm belt" (title); Sigmanortec 20T 8 mm "10mm belt" (title) |
| GT2-30T-10 | 30 | 10 | 5, 6, 6.35, 8 | 18 g (Bulkman3D, one figure for 6 and 10 mm) | na3D (read); Bulkman3D GT0002-30 (read) |
| GT2-36T-10 | 36 | 10 | 5, 8 | unknown | na3D (read); eBay 283328996026 (title) |
| GT2-40T-10 | 40 | 10 | 5, 8 | unknown | na3D (read); eBay 283328996026 (title) |
| GT2-45T-10 | 45 | 10 | 7 (4-15 stated) | unknown | Fruugo 403436352 (title/snippet) — one listing |
| GT2-48T-10 | 48 | 10 | 5 | 40 g | Bulkman3D (read; its listed OD 28 mm looks wrong for 48T) — one listing |
| GT2-60T-10 | 60 | 10 | 5-14 | 80 g (one figure for 6/10/15 mm) | na3D (read); Bulkman3D GT0002-60 (read); Multan Electronics (title) |
| GT2-80T-10 | 80 | 10 | 5, 8 | unknown | na3D (read; sold out when read) — one listing |
| GT2-20T-15 | 20 | 15 | 5, 6, 6.35, 8 | unknown | eBay.de 284184103238 (snippet) — one listing |
| GT2-40T-15 | 40 | 15 | 5-12 | unknown | eBay.de 284184103238 (snippet) — one listing |
| GT2-60T-15 | 60 | 15 | 5-15 | 80 g | eBay.de 284184103238 (snippet); Bulkman3D GT0002-60 (read) |
| GT2-80T-15 | 80 | 15 | 8, 12 | unknown | Fruugo US 376962330, Fruugo CA 366557887 (titles; maybe one seller) |

Not found for 10 mm: 72T (so 36T/72T cannot be rebuilt from listed singles). 100-140T (na3D) exist but are outside
the proposed 20-80T range. URLs are in `catalog/pulleys.json` and `docs/studies/catalog_r11c.py`.

No belt system lacks matching pulleys among those offered (10 mm and 15 mm both have them), so the run went ahead;
9 mm Gates and the 3 mm systems are simply not offered.

## Search space ranges (preset `hardware_r11c`)

| Gene | Today | Range / steps |
|---|---|---|
| femur | 200 | 180-220 (21 steps of 2 mm) |
| tibia | 245 | 221-269 (25) |
| rear cannon | 230 | 208-252 (23) |
| upper leg | 340 | 306-374 (35) |
| front cannon | 245 | 221-269 (25) |
| ratios tibia/femur, rear cannon/tibia, front cannon/upper leg | 1.225, 0.939, 0.721 | each within +-5 % |
| spring rate (each site) | stifle 0.197, hock 0.129, hip ab/ad 0.178, shoulder 0.022, carpus 0.2 N/mm | x 0.5, 0.75, 1, 1.5, 2 |
| spring preload (standing extension) | stifle 50.1, hock 38.4, hip ab/ad 17.9, shoulder 40.2, carpus 40.0 mm | x 0.5, 1, 1.5 |
| spring anchors along each segment | as today (stifle 30/30, hock 80/-20, shoulder 40/40, carpus 40/40, hip femur 50) | -15, 0, +15 mm |
| spring anchors across | as today (stifle 55/55, hock -10/-15, shoulder -30/-25, carpus 25/25, hip block inward 40) | -10, 0, +10 mm |
| spring site | on today: hip ab/ad, stifle, hock, shoulder; off: carpus | on / off |
| shoulder drive | direct | direct / belted |
| servo per pair | C018 | C018 / C002, at most 6 C002 |
| per drive: system | 10 mm | 10 mm, 15 mm |
| per drive: driver, driven | 30T / 60T | any listed size of that width each |
| per drive: length | as today | the listed lengths that pass on this body |

(Rates, preloads and anchors are the project's working values, which differ from the gene file's defaults.)

## Stage A — seeded check, geometry fixed (run `20261107-024828-evolve-4ae0`, 15 bodies, 2220 s on 7 workers)

All simulated, margin 0.2, three randomised seeds. Minutes = R6c's and R7's 11 behaviours x 3 seeds held for 60 s.
Trot = fastest quick-grid trot within every limit on all seeds (its slowest seed). Walk / turn / lie_rise = worst-seed
margin (held if >= 0). Cost = the R11c index (servos / 4 + 0.25 per new pulley size + 0.25 per spring site added +
1 per added kg). Every belt is from the catalog; no what-if. Every body passed the screen.

| # | Body | Minutes /33 | Trot mm/s (setting) | Walk | Turn | lie_rise | Cost | Stopped most by |
|---|---|---|---|---|---|---|---|---|
| 000 | working body | 32 | none | -0.13 | -0.25 | -3.00 | 0.00 | fl.carpus joint speed (8), fl.shoulder torque (4) |
| 001 | + carpus spring | 29 | none | -0.12 | -0.23 | -3.00 | 0.25 | fl.carpus speed (9), fl.shoulder torque (4) |
| 002 | + belted shoulder | 26 | none | -0.28 | -0.15 | -3.00 | 0.00 | shoulder belt tension (7+7) |
| 003 | R10 1:1 45T (now listed pulleys) | 26 | 419 (0.5 s / 2.0) | -0.24 | -0.20 | -2.88 | 1.83 | fr.carpus belt (6), hl.hip_abd torque (3) |
| 004 | + carpus spring | 26 | 417 (0.5/2.0) | -0.16 | -0.19 | -2.88 | 2.08 | fr.carpus belt (6), hl.hip_abd torque (4) |
| 005 | + belted shoulder | 13 | 209 (0.6/1.5) | -0.36 | -0.19 | -1.68 | 1.83 | fl.shoulder belt (16), fr.carpus belt (8) |
| 006 | R10 40T/80T | 28 | 63 (0.8/1.0) | -0.24 | -0.20 | -2.80 | 1.58 | fl.carpus belt (14), fl.shoulder torque (5) |
| 007 | + carpus spring | 28 | 203 (0.6/1.5) | -0.24 | -0.16 | -2.80 | 1.83 | fl.carpus belt (8), fl.shoulder torque (4) |
| 008 | + belted shoulder | 19 | 71 (0.8/1.0) | -0.36 | -0.20 | -1.68 | 1.58 | fl.shoulder belt (15), fl.carpus belt (13) |
| 009 | hips+hocks+carpi C002 (40T/80T belts) | 27 | 73 (0.8/1.0) | **+0.08** | -0.40 | -2.84 | 2.12 | fl.carpus belt (14), fl.shoulder torque (9) |
| 010 | + carpus spring | 28 | 123 (0.6/1.0) | **+0.08** | -0.40 | -2.84 | 2.37 | fl.carpus belt (10), fl.shoulder torque (7) |
| 011 | + belted shoulder | 17 | 75 (0.8/1.0) | **+0.22** | -0.54 | -1.72 | 2.12 | fl.shoulder belt (17), fl.carpus belt (13) |
| 012 | hocks+carpi+shoulders C002 (40T/80T belts) | **31** | 80 (0.8/1.0) | -0.40 | -0.01 | **-1.44** | 2.12 | fl.carpus belt (16), hr.hip_abd torque (4) |
| 013 | + carpus spring | **31** | **214 (0.6/1.5)** | -0.44 | -0.19 | **-1.44** | 2.37 | fl.carpus belt (8), fr.carpus belt (4) |
| 014 | + belted shoulder | 16 | 83 (0.8/1.0) | -0.48 | -0.48 | -1.92 | 2.12 | fl.shoulder belt (18), fl.carpus belt (14) |

Pareto front (minutes, trot, cost): 000, 013, 012, 007, 006, 003, 008. Best fitness within a cell: 012 (-0.239).

Belt tension, simulated (peak / largest mean over every play and seed, N; allowable 44 N sustained at 10 mm, judged
at 0.8 x 44 = 35.2 N; breaking flag 0.25 x 860 = 215 N):

| Body | stifle | hock | carpus | shoulder |
|---|---|---|---|---|
| 000 working | 149 / 29 | 76 / 18 | 100 / 19 | - |
| 003 R10 1:1 45T | 104 / 22 | 70 / 18 | 138 / 19 | - |
| 006 R10 40T/80T | 101 / 23 | 75 / 18 | 70 / 23 | - |
| 012 hocks+carpi+shoulders | 88 / 24 | 71 / 17 | 80 / 23 | - |
| 013 + carpus spring | 94 / 24 | 68 / 17 | 84 / 21 | - |
| 014 + belted shoulder | 124 / 26 | 64 / 18 | 88 / 24 | 174 / 37 |

Springs (both from the geometry through the PROVISIONAL joint range, and the simulated peak, which is the same on every
body because lie_rise takes the joints to the ends of their ranges): stifle 12.0 N at 60.8 mm extension, hock 8.3 N
at 64.3 mm, hip ab/ad 6.0 N at 33.8 mm (simulated 3.7 N), shoulder 1.2 N at 53.7 mm, carpus 9.7 N at 48.3 mm. The
stifle, hock, shoulder and carpus spring lines come within 1.2, 8.3, 1.1 and 0.6 mm of their joint axes somewhere in
the range (flagged; ADR-103).

What Stage A says:
* **The belted shoulder, as laid out (30T/60T on a 10 mm belt, 2:1), costs 6-15 minutes on every body.** It halves the
  shoulder's lie_rise deficit (-3.0 to -1.7) but its belt carries the shoulder's torque at a small driver and binds on
  sustained tension. A larger driver or the 15 mm belt might change that; Stage B can try them.
* **New shoulders (with hocks and carpi) are the strongest assignment**: 31/33 and lie_rise -1.44 (best yet), turn
  nearly within (-0.01). Its carpus belt (40T/80T, 10 mm) is what stops it most.
* **A carpus spring buys trot speed on the 40T/80T carpus** (63 -> 203, 73 -> 123, 80 -> 214 mm/s) without losing
  minutes there, but costs 3 minutes on today's body.
* **New hip ab/ad servos are what make the walk hold** (+0.08 to +0.22); no body holds walk, turn and lie_rise together.
* No body holds lie_rise.

## Stage B — first generation, every gene on (run `20261107-032610-evolve-ba33`)

Two generations of 15: generation 0 re-judged Stage A's bodies from the cache (about 2 min); generation 1 drew 24
bodies (geometry Gaussian, sigma 0.05; each discrete gene redrawn with probability 0.05, an ASSUMPTION: R11's 0.2 would
change about 11 of the 55 discrete genes per child), **rejected 9 (37.5 %, under the 50 % stop)** and judged 15.

Rejections (each recorded with its reason): servo budget 8 > 6 (3); a 4:1 pulley pair (20T/80T) needing 440 deg of
servo travel over the stifle or hock range (4); front legs 0.4-5.8 mm too short for a level back (4, the generator's
check). (A rejection can list more than one reason.)

**Timing:** generation 1 took 34.2 min wall for 15 new bodies on 7 workers (about 137 s per body). Projected, at that
rate and 15 bodies per generation: 10 generations about 5.7 h, 20 about 11.4 h, 30 about 17 h (less as the cache
fills with repeated bodies). **Not continued: Emily decides.**

Generation 1's bodies (simulated; minutes /33, trot mm/s, walk / turn / lie_rise worst-seed margins, cost):

| Candidate | Body | Minutes | Trot | Walk | Turn | lie_rise | Cost | Stopped most by |
|---|---|---|---|---|---|---|---|---|
| **g001-006-r05** | new hocks + carpi; carpus 45T/45T 640 (1:1), stifle and hock 40T/80T 444 / 400; springs hip ab/ad (rate x 0.5), stifle, hock, **carpus**, **no shoulder**; femur 198, tibia 245, rear cannon 228, upper leg 342, front cannon 243 | **31** | **405** (0.5 s / 2.0; 14 settings hold) | -0.28 | -0.11 | -3.00 | 2.08 | hl.stifle joint speed (3), fl.shoulder torque (2) |
| g001-004 | new hocks + carpi + shoulders, 40T/80T, carpus spring, no stifle spring, upper leg 336 | 31 | 135 | -0.32 | -0.04 | -1.52 | 2.37 | fl.carpus belt (10), hr.hip_abd torque (6) |
| g001-011 | no new servos, 30T/60T, carpus spring on, front cannon 251 | 32 | 0 | -0.16 | -0.24 | -3.00 | 0.25 | fl.carpus speed (8) |
| g001-012 | new hip ab/ad + hocks + carpi, carpus 45T/80T, hock 444 | 28 | 401 | -0.04 | -0.08 | -3.00 | 2.37 | fl.shoulder torque (8) |
| g001-008 | new hocks + carpi, 40T/80T, hock 444, all five springs | 30 | 207 | -0.40 | -0.27 | -2.88 | 1.83 | fl.carpus belt (9) |
| others (10) | | 6-29 | 0-213 | | | | | belted shoulders (6, 16 min) and 40T/60T stifles do worst |

g001-006-r05 against the previous best bodies (all simulated):

| Body | Minutes /33 | Fastest trot within | Walk | Turn | lie_rise | Cost | Stopped most by |
|---|---|---|---|---|---|---|---|
| working body | 32 | none | -0.13 | -0.25 | -3.00 | 0.00 | fl.carpus speed |
| R10 1:1 45T (R11: a what-if; now listed) | 26 | 419 | -0.24 | -0.20 | -2.88 | 1.83 | carpus belt |
| A012 hocks+carpi+shoulders C002 | 31 | 80 | -0.40 | -0.01 | -1.44 | 2.12 | carpus belt |
| A013 + carpus spring | 31 | 214 | -0.44 | -0.19 | -1.44 | 2.37 | carpus belt |
| **B g001-006-r05** | **31** | **405** | -0.28 | -0.11 | -3.00 | 2.08 | stifle speed, shoulder torque |

Its belts (simulated peak / largest mean): stifle 103 / 23 N, hock 64 / 17 N, carpus 145 / 22 N. Springs through the
range: carpus 0.2 N/mm, free 47.4 mm, 46.9 mm max extension, 9.4 N; stifle 12 N; hock 8.3 N; hip ab/ad 3.0 N (rate
0.089). Sheets: `sheets_r11c/B1_006r05_1to1_45T_carpus_spring_geometry.csv` and `_parts.json`.

Read with care: the 11 behaviours were evolved for today's geometry and servos (Stage C exists for that); and the
C002's stiffness ASSUMPTION (position gain from stall torque) may inflate belt peaks on C002 bodies.

## Stage B — 20 generations (run `20261107-043030-evolve-c02e`, session R11c-B)

Started by Emily with `production_r11c.py ... stageB --generations=21` (seed 0, batch 15, sigma 0.05, flip 0.05, the
same settings as `ba33`). Generation 0 replays Stage A's 15 bodies and **generation 1 replays `ba33`'s generation 1**
from the cache (same seed, 0 new evaluations; `g001-006-r05` is the same body under the new run id), so the run judged
**19 new generations (2-20), 285 new bodies, in 10.8 h wall** (38 848 s; about 34 min per generation, as projected).
432 draws: 315 judged, 117 rejected. Archive: 80 elites, coverage 0.67 of the 12 x 10 grid, QD score 34 -> 200 and
still rising; the best fitness within a cell improved in generations 3, 12 and 20, so **the search has not converged**.

All of it is **simulated** on unverified catalog and library values, with the 11 behaviours evolved for today's body
(Stage C exists for that). The front below is over every distinct judged body up to that generation, on three
objectives: minutes held (of 33, higher), fastest trot within every limit (mm/s, higher), cost index (lower).
Walk / turn / lie_rise are worst-seed margins (held if >= 0), reported but not objectives.

**Read the trot column with care:** 0.4 s / stride 2.0 is the fastest corner of the quick grid
(`trot_cycles_s` 0.4-0.8, `trot_strides` 0.5-2.0). Every body at about 520-535 mm/s trots there, so that figure is the
grid's ceiling, not the body's; how much faster they could go is not measured.

### What the 20 generations say

* **A new best: `g020-008-r01` holds all 33 minutes, trots at 530 mm/s (grid ceiling), and brings lie_rise to -0.16**
  (A012/A013: -1.44; the working body -3.00). Cost 2.12, the same as A012: six C002 on hocks + shoulders + carpi, two
  new pulley sizes (40T, 80T), no spring site added. Its hardware: **stifle and hock 40T/60T (1.5:1)** on today's
  444 / 400 mm belts, **carpus 80T/80T (1:1) on 640 mm (C 240 mm)**, shoulder direct; hip ab/ad spring rate halved
  (0.089 N/mm), **no shoulder spring**, no carpus spring; femur 198, tibia 239, rear cannon 226, upper leg 340, front
  cannon 247 mm (all within 2.5 % of today). Mass 1419 g (+115 g, all servo; pulley masses not entered). It dominates
  A012, A013 and B1's `g001-006-r05`. Its weak point: **walk -0.52**, the worst on the front (hip ab/ad torque on
  the C018s binds there; turn -0.08).
* It is a crossover of `g012-009` (33/33, 414 mm/s, lie_rise -0.24, cost 2.37; same servos and carpus 80T/80T, with
  shoulder and carpus springs, which cost 0.25) and `g009-011` (1 minute: a belted shoulder). The child dropped the
  belted shoulder and both springs that cost, and took 1.5:1 at stifle and hock.
* **lie_rise comes within reach only with C002 shoulders driven directly.** The six closest bodies of the run (-0.16
  to -0.27) all have them, and five of the six have C002 hocks and carpi too (the sixth, `g019-000`, holds 13 minutes).
  Of those five, three have the carpus on 80T/80T and two keep
  A012's 40T/80T and differ from A012 (-1.44) only in small length moves (`g014-006`: rear cannon 226, front cannon
  249; `g018-009`: front cannon 253, a 30T/80T hock). All five have a rear cannon of 226-228 mm and front legs (upper
  leg + front cannon) 2-12 mm longer than today, but `g007-009` has that too and stays at -1.36: **lie_rise's margin
  jumps with small changes**, so read this as a hint, not a rule. What still binds is sustained servo torque.
* **Belted shoulders lose.** They move lie_rise to -0.4 to -0.9 (shoulder belt sustained tension binds instead) but cost
  minutes: 4 of the 24 front bodies are belted and none holds more than 25 minutes. Their share among judged bodies
  stayed about 40 % (it is drawn often) but fell to 17 % on the front.
* **C002 on hocks and carpi is the backbone** (16 of 24 front bodies); C002 shoulders on only 3 front bodies, but on the
  best; C002 hip ab/ad all but vanished (23 % of draws in generations 1-5, 3-7 % later), so the walk gain Stage A saw
  from it is not bought. Stifle C002: never (0-1 %).
* **1:1 or near-1:1 carpus drives carry the trot speed** (45T/45T x7, 40T/45T x6, 80T/80T x2 on the front). 40T/60T
  (1.5:1) at stifle and hock is new in this run and is on 15 of the front's 48 hind drives.
* **Springs:** hip ab/ad, stifle and hock springs stay on (24, 24, 22 of 24); shoulder spring on 21 of 24 but off on
  the best; carpus spring on 7 of 24. Rates and anchors move on a third to a half of the bodies, but no consistent
  direction stands out except the halved hip ab/ad rate on the two best. (The free lengths change on almost every body
  because they are derived from the standing length, which moves with the segment lengths.)
* **Lengths barely move as a population**: front medians equal today's for femur, tibia, upper leg and front cannon;
  rear cannon median 228 (today 230). The front spans femur 194-210, tibia 239-251, rear cannon 220-234, upper leg
  330-354, front cannon 239-253 mm.
* **Rejections stayed at 23-35 % per block of five generations** (highest single generation 44 %, number 13; the stop is
  50 %). Front legs too short for a level back and segment ratios outside +-5 % are the commonest; then pulley ratios
  needing more than 360 deg of servo travel, the servo budget and spring anchors off their segments. No draw failed for
  want of a feasible listed belt length.
* **What the best bodies' parts rest on (verify before ordering):** the **80T 10 mm pulley has one listing**, na3D,
  marked sold out when read; two 80T pulleys (50.9 mm pitch diameter) at the carpus, at both ends, are not checked for
  clearance; and the stifle and hock spring lines still come within 1.2 and 8.3 mm of their axes (flagged, ADR-103).

### The front after every five generations

Each table: the front at that point, then the reference bodies that are not on it.
**After generation 5** (14 on the front of 90 distinct bodies; entered: g000-000, g000-003, g000-007, g001-002, g001-006-r05, g001-007, g001-008-r01, g002-014, g003-003, g003-004, g004-001-r02, g004-003, g004-013-r01, g005-013-r01; left: none)

| Body | Min /33 | Trot mm/s | Cost | Walk | Turn | lie_rise |
|---|---|---|---|---|---|---|
| g000-000 (working) | 32 | 0 | 0.00 | -0.13 | -0.25 | -3.00 |
| g001-006-r05 (B1-r05) | 31 | 405 | 2.08 | -0.28 | -0.11 | -3.00 |
| g001-008-r01 | 30 | 207 | 1.83 | -0.40 | -0.27 | -2.88 |
| g004-003 | 29 | 423 | 2.08 | -0.20 | -0.16 | -2.92 |
| g001-002 | 29 | 66 | 1.58 | -0.16 | -0.08 | -3.00 |
| g000-007 | 28 | 203 | 1.83 | -0.24 | -0.16 | -2.80 |
| g004-001-r02 | 28 | 74 | 1.29 | -0.04 | -0.27 | -3.00 |
| g000-003 | 26 | 419 | 1.83 | -0.24 | -0.20 | -2.88 |
| g003-004 | 25 | 24 | 0.75 | +0.07 | +0.05 | -2.36 |
| g003-003 | 24 | 535 | 2.12 | -0.12 | -0.20 | -3.00 |
| g004-013-r01 | 24 | 277 | 1.29 | -0.12 | -0.01 | -2.76 |
| g001-007 | 24 | 40 | 1.04 | -0.08 | -0.56 | -2.52 |
| g002-014 | 22 | 530 | 2.12 | +0.16 | -0.03 | -3.00 |
| g005-013-r01 | 12 | 211 | 1.04 | -0.32 | -0.24 | -3.00 |
| g000-012 (A012), off the front | 31 | 80 | 2.12 | -0.40 | -0.01 | -1.44 |
| g000-013 (A013), off the front | 31 | 214 | 2.37 | -0.44 | -0.19 | -1.44 |

**After generation 10** (18 on the front of 165 distinct bodies; entered: g006-011, g007-000, g007-002, g007-009, g008-006, g009-000, g009-005; left: g000-007, g001-007, g001-008-r01)

| Body | Min /33 | Trot mm/s | Cost | Walk | Turn | lie_rise |
|---|---|---|---|---|---|---|
| g007-002 | 33 | 0 | 1.58 | -0.32 | -0.25 | -1.44 |
| g007-009 | 32 | 408 | 2.62 | -0.36 | -0.11 | -1.36 |
| g009-000 | 32 | 394 | 1.83 | -0.12 | -0.08 | -3.00 |
| g000-000 (working) | 32 | 0 | 0.00 | -0.13 | -0.25 | -3.00 |
| g001-006-r05 (B1-r05) | 31 | 405 | 2.08 | -0.28 | -0.11 | -3.00 |
| g004-003 | 29 | 423 | 2.08 | -0.20 | -0.16 | -2.92 |
| g009-005 | 29 | 403 | 1.83 | -0.16 | -0.08 | -2.13 |
| g001-002 | 29 | 66 | 1.58 | -0.16 | -0.08 | -3.00 |
| g004-001-r02 | 28 | 74 | 1.29 | -0.04 | -0.27 | -3.00 |
| g000-003 | 26 | 419 | 1.83 | -0.24 | -0.20 | -2.88 |
| g003-004 | 25 | 24 | 0.75 | +0.07 | +0.05 | -2.36 |
| g003-003 | 24 | 535 | 2.12 | -0.12 | -0.20 | -3.00 |
| g004-013-r01 | 24 | 277 | 1.29 | -0.12 | -0.01 | -2.76 |
| g006-011 | 24 | 45 | 0.79 | -0.12 | -0.27 | -3.00 |
| g002-014 | 22 | 530 | 2.12 | +0.16 | -0.03 | -3.00 |
| g005-013-r01 | 12 | 211 | 1.04 | -0.32 | -0.24 | -3.00 |
| g008-006 | 10 | 420 | 1.83 | -0.16 | -0.11 | -3.00 |
| g007-000 | 5 | 444 | 1.83 | -0.12 | -0.44 | -3.00 |
| g000-012 (A012), off the front | 31 | 80 | 2.12 | -0.40 | -0.01 | -1.44 |
| g000-013 (A013), off the front | 31 | 214 | 2.37 | -0.44 | -0.19 | -1.44 |

**After generation 15** (23 on the front of 240 distinct bodies; entered: g011-003, g011-009, g012-006, g012-009, g013-002-r01, g014-003, g014-009, g015-004, g015-012-r01; left: g000-003, g007-000, g007-009, g008-006)

| Body | Min /33 | Trot mm/s | Cost | Walk | Turn | lie_rise |
|---|---|---|---|---|---|---|
| g012-009 | 33 | 414 | 2.37 | -0.48 | -0.08 | -0.24 |
| g007-002 | 33 | 0 | 1.58 | -0.32 | -0.25 | -1.44 |
| g011-003 | 32 | 410 | 2.08 | -0.03 | -0.04 | -3.00 |
| g009-000 | 32 | 394 | 1.83 | -0.12 | -0.08 | -3.00 |
| g000-000 (working) | 32 | 0 | 0.00 | -0.13 | -0.25 | -3.00 |
| g001-006-r05 (B1-r05) | 31 | 405 | 2.08 | -0.28 | -0.11 | -3.00 |
| g004-003 | 29 | 423 | 2.08 | -0.20 | -0.16 | -2.92 |
| g009-005 | 29 | 403 | 1.83 | -0.16 | -0.08 | -2.13 |
| g015-004 | 29 | 88 | 1.58 | -0.04 | -0.36 | -3.00 |
| g001-002 | 29 | 66 | 1.58 | -0.16 | -0.08 | -3.00 |
| g004-001-r02 | 28 | 74 | 1.29 | -0.04 | -0.27 | -3.00 |
| g013-002-r01 | 26 | 517 | 1.57 | +0.00 | -0.36 | -3.00 |
| g003-004 | 25 | 24 | 0.75 | +0.07 | +0.05 | -2.36 |
| g003-003 | 24 | 535 | 2.12 | -0.12 | -0.20 | -3.00 |
| g004-013-r01 | 24 | 277 | 1.29 | -0.12 | -0.01 | -2.76 |
| g006-011 | 24 | 45 | 0.79 | -0.12 | -0.27 | -3.00 |
| g002-014 | 22 | 530 | 2.12 | +0.16 | -0.03 | -3.00 |
| g011-009 | 21 | 79 | 1.29 | -0.40 | -0.16 | -3.00 |
| g014-009 | 19 | 217 | 1.04 | -0.48 | -0.08 | -3.00 |
| g015-012-r01 | 18 | 386 | 1.53 | +0.08 | -0.01 | -2.13 |
| g012-006 | 17 | 43 | 0.79 | -0.24 | -0.32 | -2.60 |
| g005-013-r01 | 12 | 211 | 1.04 | -0.32 | -0.24 | -3.00 |
| g014-003 | 6 | 528 | 2.08 | -0.04 | -0.40 | -3.00 |
| g000-012 (A012), off the front | 31 | 80 | 2.12 | -0.40 | -0.01 | -1.44 |
| g000-013 (A013), off the front | 31 | 214 | 2.37 | -0.44 | -0.19 | -1.44 |

**After generation 20** (25 on the front of 315 distinct bodies; entered: g017-001, g017-007, g019-008, g019-011, g019-013, g020-003-r02, g020-006-r01, g020-008-r01, g020-013; left: g002-014, g003-004, g006-011, g011-009, g012-006, g012-009, g014-003)

| Body | Min /33 | Trot mm/s | Cost | Walk | Turn | lie_rise |
|---|---|---|---|---|---|---|
| g020-008-r01 | 33 | 530 | 2.12 | -0.52 | -0.08 | -0.16 |
| g007-002 | 33 | 0 | 1.58 | -0.32 | -0.25 | -1.44 |
| g011-003 | 32 | 410 | 2.08 | -0.03 | -0.04 | -3.00 |
| g009-000 | 32 | 394 | 1.83 | -0.12 | -0.08 | -3.00 |
| g000-000 (working) | 32 | 0 | 0.00 | -0.13 | -0.25 | -3.00 |
| g001-006-r05 (B1-r05) | 31 | 405 | 2.08 | -0.28 | -0.11 | -3.00 |
| g004-003 | 29 | 423 | 2.08 | -0.20 | -0.16 | -2.92 |
| g009-005 | 29 | 403 | 1.83 | -0.16 | -0.08 | -2.13 |
| g015-004 | 29 | 88 | 1.58 | -0.04 | -0.36 | -3.00 |
| g001-002 | 29 | 66 | 1.58 | -0.16 | -0.08 | -3.00 |
| g004-001-r02 | 28 | 74 | 1.29 | -0.04 | -0.27 | -3.00 |
| g020-006-r01 | 26 | 534 | 2.87 | -0.24 | -0.15 | -3.00 |
| g013-002-r01 | 26 | 517 | 1.57 | +0.00 | -0.36 | -3.00 |
| g017-007 | 26 | 52 | 0.75 | +0.08 | +0.03 | -2.16 |
| g019-008 | 26 | 46 | 0.50 | +0.08 | -0.24 | -2.96 |
| g017-001 | 25 | 81 | 0.50 | -0.24 | -0.03 | -1.76 |
| g003-003 | 24 | 535 | 2.12 | -0.12 | -0.20 | -3.00 |
| g004-013-r01 | 24 | 277 | 1.29 | -0.12 | -0.01 | -2.76 |
| g014-009 | 19 | 217 | 1.04 | -0.48 | -0.08 | -3.00 |
| g015-012-r01 | 18 | 386 | 1.53 | +0.08 | -0.01 | -2.13 |
| g020-003-r02 | 15 | 528 | 2.08 | -0.12 | -0.08 | -3.00 |
| g005-013-r01 | 12 | 211 | 1.04 | -0.32 | -0.24 | -3.00 |
| g020-013 | 6 | 421 | 1.30 | -0.04 | -0.20 | -3.00 |
| g019-013 | 3 | 230 | 1.29 | -0.12 | -0.20 | -1.68 |
| g019-011 | 3 | 125 | 1.00 | -0.12 | -0.58 | -2.24 |
| g000-012 (A012), off the front | 31 | 80 | 2.12 | -0.40 | -0.01 | -1.44 |
| g000-013 (A013), off the front | 31 | 214 | 2.37 | -0.44 | -0.19 | -1.44 |

### The final front in detail (after generation 20: 25 bodies of 315 judged; **new** = entered in generations 16-20)

| Body | Hardware and geometry (changes from the working body) | Min /33 | Trot mm/s | Walk | Turn | lie_rise | Cost | Mass g | Stopped most by |
|---|---|---|---|---|---|---|---|---|---|
| **new** g020-008-r01 | C002 on hocks + shoulders + carpi; stifle 40T/60T 444; hock 40T/60T 400; carpus 80T/80T 640; shoulder direct; hip ab/ad rate x0.5, no shoulder spring; femur 198, tibia 239, rear cannon 226, front cannon 247 | 33 | 530 (trot 0.4/2) | -0.52 | -0.08 | -0.16 | 2.12 | 1419 | hl.hip_abd torque (3), hr.hip_abd torque (2) |
| g007-002 | C002 on hocks + shoulders; stifle 40T/80T 444; hock 40T/60T 400; carpus 40T/80T 640; shoulder direct; stifle spring lower_normal moved; rear cannon 232, upper leg 344 | 33 | 0  | -0.32 | -0.25 | -1.44 | 1.58 | 1383 | fl.carpus speed (9), fr.carpus speed (8) |
| g011-003 | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 45T/80T 640; shoulder direct; hip ab/ad spring lower_along moved, stifle spring lower_normal moved, no shoulder spring, +carpus spring; rear cannon 226, front cannon 247 | 32 | 410 (trot 0.5/2) | -0.03 | -0.04 | -3.00 | 2.08 | 1382 | fl.carpus belt (8), hl.hip_abd torque (3) |
| g009-000 | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 48T/80T 640; shoulder direct; stifle rate x0.5, shoulder spring upper_along moved; tibia 243, rear cannon 224, upper leg 342, front cannon 239 | 32 | 394 (trot 0.5/2) | -0.12 | -0.08 | -3.00 | 1.83 | 1380 | fl.carpus belt (8), hl.hip_abd torque (3) |
| g000-000 (working body) | C002 on none; stifle 30T/60T 444; hock 30T/60T 400; carpus 30T/60T 640; shoulder direct; lengths as today | 32 | 0  | -0.13 | -0.25 | -3.00 | 0.00 | 1304 | fl.carpus speed (8), fl.shoulder torque (4) |
| g001-006-r05 (B1 g001-006-r05) | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 45T/45T 640; shoulder direct; hip ab/ad rate x0.5, no shoulder spring, +carpus spring; femur 198, rear cannon 228, upper leg 342, front cannon 243 | 31 | 405 (trot 0.5/2) | -0.28 | -0.11 | -3.00 | 2.08 | 1381 | hl.stifle speed (3), fl.shoulder torque (2) |
| g004-003 | C002 on hocks + carpi; stifle 40T/80T 500; hock 40T/80T 400; carpus 40T/45T 640; shoulder direct; +carpus spring; tibia 241, rear cannon 232, upper leg 342, front cannon 243 | 29 | 423 (trot 0.5/2) | -0.20 | -0.16 | -2.92 | 2.08 | 1382 | fl.shoulder torque (3), hl.hip_abd torque (3) |
| g009-005 | C002 on hocks + carpi; stifle 30T/60T 444; hock 30T/60T 400; carpus 48T/80T 640; shoulder direct; +carpus spring; femur 196, tibia 251, rear cannon 226, upper leg 344 | 29 | 403 (trot 0.5/2) | -0.16 | -0.08 | -2.13 | 1.83 | 1383 | hl.hock belt (6), fl.shoulder torque (5) |
| g015-004 | C002 on hocks + carpi; stifle 40T/60T 444; hock 40T/80T 400; carpus 40T/80T 640; shoulder direct; femur 204, tibia 239, front cannon 251 | 29 | 88 (trot 0.8/1.5) | -0.04 | -0.36 | -3.00 | 1.58 | 1383 | fl.carpus belt (12), fr.carpus belt (4) |
| g001-002 | C002 on hocks + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 40T/80T 640; shoulder direct; femur 202, tibia 241, rear cannon 228, front cannon 249 | 29 | 66 (trot 0.8/1) | -0.16 | -0.08 | -3.00 | 1.58 | 1382 | fl.carpus belt (12), fl.shoulder torque (4) |
| g004-001-r02 | C002 on carpi; stifle 40T/60T 444; hock 40T/80T 450; carpus 15 mm 60T/80T 310; shoulder direct; +carpus spring; femur 196, upper leg 336, front cannon 247 | 28 | 74 (trot 0.8/1) | -0.04 | -0.27 | -3.00 | 1.29 | 1342 | hl.hock speed (14), fl.shoulder torque (5) |
| **new** g020-006-r01 | C002 on hocks + shoulders + carpi; stifle 15 mm 60T/80T 300; hock 48T/60T 400; carpus 40T/45T 640; shoulder direct; stifle spring upper_along, lower_normal moved, no hock spring, +carpus spring; femur 202, tibia 241, rear cannon 226, upper leg 338, front cannon 241 | 26 | 534 (trot 0.4/2) | -0.24 | -0.15 | -3.00 | 2.87 | 1419 | fr.carpus belt (6), hl.hip_abd torque (4) |
| g013-002-r01 | C002 on hocks + carpi; stifle 40T/60T 376; hock 40T/60T 400; carpus 45T/45T 640; shoulder direct; stifle rate x0.75; femur 198, tibia 247, rear cannon 222, upper leg 334, front cannon 243 | 26 | 517 (trot 0.4/2) | +0.00 | -0.36 | -3.00 | 1.57 | 1379 | fr.carpus belt (6), hl.hip_abd torque (3) |
| **new** g017-007 | C002 on none; stifle 40T/80T 444; hock 30T/60T 400; carpus 40T/45T 640; shoulder direct; stifle spring upper_normal moved, hock spring upper_along moved; tibia 243, upper leg 336 | 26 | 52 (trot 0.8/1) | +0.08 | +0.03 | -2.16 | 0.75 | 1303 | hl.hock speed (10), fr.carpus belt (6) |
| **new** g019-008 | C002 on none; stifle 40T/60T 444; hock 30T/60T 400; carpus 45T/45T 640; shoulder direct; hock spring upper_along moved; tibia 243, rear cannon 228, upper leg 338, front cannon 241 | 26 | 46 (trot 0.8/0.5) | +0.08 | -0.24 | -2.96 | 0.50 | 1302 | hl.hock speed (13), fr.carpus torque (6) |
| **new** g017-001 | C002 on none; stifle 30T/80T 444; hock 40T/60T 400; carpus 15 mm 80T/80T 310; shoulder 30T/60T 460; stifle rate x0.75, stifle spring lower_along moved; femur 196, rear cannon 222, upper leg 330, front cannon 243 | 25 | 81 (trot 0.5/0.5) | -0.24 | -0.03 | -1.76 | 0.50 | 1300 | hl.stifle speed (12), fr.carpus torque (6) |
| g003-003 | C002 on hip ab/ad + hocks + carpi; stifle 40T/60T 444; hock 40T/60T 394; carpus 45T/45T 640; shoulder direct; femur 202, tibia 243, rear cannon 232, upper leg 338, front cannon 247 | 24 | 535 (trot 0.4/2) | -0.12 | -0.20 | -3.00 | 2.12 | 1422 | fl.shoulder torque (4), fr.carpus belt (4) |
| g004-013-r01 | C002 on hocks; stifle 15 mm 40T/80T 300; hock 40T/60T 400; carpus 40T/45T 640; shoulder direct; stifle spring lower_normal moved, no hock spring; femur 210, tibia 247, rear cannon 234, upper leg 350, front cannon 249 | 24 | 277 (trot 0.4/1) | -0.12 | -0.01 | -2.76 | 1.29 | 1349 | fr.carpus belt (11), fl.carpus speed (4) |
| g014-009 | C002 on carpi; stifle 30T/60T 550; hock 40T/60T 444; carpus 40T/45T 640; shoulder 30T/60T 460; hip ab/ad spring upper_inward moved; tibia 251, rear cannon 228, upper leg 344, front cannon 243 | 19 | 217 (trot 0.6/1.5) | -0.48 | -0.08 | -3.00 | 1.04 | 1344 | fl.shoulder belt (13), fr.carpus belt (6) |
| g015-012-r01 | C002 on hocks; stifle 40T/80T 376; hock 40T/80T 444; carpus 45T/45T 640; shoulder direct; hip ab/ad spring lower_along moved, stifle spring lower_normal moved, +carpus spring; femur 194, rear cannon 220, front cannon 243 | 18 | 386 (trot 0.5/2) | +0.08 | -0.01 | -2.13 | 1.53 | 1340 | fl.carpus torque (7), fr.carpus torque (6) |
| **new** g020-003-r02 | C002 on hocks + carpi; stifle 36T/60T 444; hock 48T/80T 460; carpus 45T/36T 640; shoulder 60T/60T 394; stifle spring lower_normal moved, shoulder rate x0.5; femur 204, rear cannon 226, upper leg 338, front cannon 243 | 15 | 528 (trot 0.4/2) | -0.12 | -0.08 | -3.00 | 2.08 | 1381 | hr.hip_abd torque (10), fr.carpus belt (7) |
| g005-013-r01 | C002 on carpi; stifle 30T/60T 444; hock 40T/60T 400; carpus 45T/45T 640; shoulder 30T/60T 460; femur 198, rear cannon 226, upper leg 342, front cannon 243 | 12 | 211 (trot 0.6/1.5) | -0.32 | -0.24 | -3.00 | 1.04 | 1342 | fr.carpus belt (14), fl.shoulder belt (9) |
| **new** g020-013 | C002 on hocks; stifle 15 mm 40T/80T 300; hock 40T/80T 460; carpus 40T/45T 640; shoulder direct; femur 208, tibia 247, rear cannon 234, upper leg 354, front cannon 253 | 6 | 421 (trot 0.5/2) | -0.04 | -0.20 | -3.00 | 1.30 | 1350 | fr.carpus belt (23), fl.carpus belt (9) |
| **new** g019-013 | C002 on carpi; stifle 30T/48T 460; hock 40T/60T 450; carpus 45T/45T 640; shoulder direct; hock rate x2; tibia 249, rear cannon 232, upper leg 352, front cannon 251 | 3 | 230 (trot 0.6/1.5) | -0.12 | -0.20 | -1.68 | 1.29 | 1348 | fr.carpus belt (15), fl.carpus belt (13) |
| **new** g019-011 | C002 on none; stifle 40T/80T 450; hock 48T/80T 400; carpus 60T/36T 640; shoulder direct; stifle spring upper_normal moved, hock spring upper_along moved; tibia 241, front cannon 241 | 3 | 125 (trot 0.6/1) | -0.12 | -0.58 | -2.24 | 1.00 | 1303 | fr.carpus torque (23), fl.carpus torque (12) |
| (off the front) g000-012 (A012) | C002 on hocks + shoulders + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 40T/80T 640; shoulder direct; lengths as today | 31 | 80 (trot 0.8/1) | -0.40 | -0.01 | -1.44 | 2.12 | 1421 | fl.carpus belt (16), hr.hip_abd torque (4) |
| (off the front) g000-013 (A013) | C002 on hocks + shoulders + carpi; stifle 40T/80T 444; hock 40T/80T 400; carpus 40T/80T 640; shoulder direct; +carpus spring; lengths as today | 31 | 214 (trot 0.6/1.5) | -0.44 | -0.19 | -1.44 | 2.37 | 1421 | fl.carpus belt (8), fr.carpus belt (4) |

### Rejections per block

| Generations | Draws | Rejected | Share | Reasons (a draw can have several) |
|---|---|---|---|---|
| 1-5 | 116 | 41 | 35 % | front legs too short for a level back 13; pulley ratio needs > 360 deg servo travel 10; segment ratio outside +-5 % 9; servo budget > 6 C002 6; spring anchor / free length off its range 3 |
| 6-10 | 97 | 22 | 23 % | front legs too short for a level back 7; segment ratio outside +-5 % 6; pulley ratio needs > 360 deg servo travel 4; servo budget > 6 C002 3; spring anchor / free length off its range 3 |
| 11-15 | 106 | 31 | 29 % | segment ratio outside +-5 % 10; pulley ratio needs > 360 deg servo travel 9; front legs too short for a level back 8; servo budget > 6 C002 4; spring anchor / free length off its range 3 |
| 16-20 | 98 | 23 | 23 % | segment ratio outside +-5 % 10; front legs too short for a level back 7; pulley ratio needs > 360 deg servo travel 5; spring anchor / free length off its range 2 |

Highest share in one generation: 13 (12 of 27, 44 %); the stop is 50 %.

### Which genes move (share of judged bodies whose gene differs from the working body; inert genes left out)

| Gene | gen 1-5 | gen 6-10 | gen 11-15 | gen 16-20 | front at 20 |
|---|---|---|---|---|---|
| femur | 73 % | 79 % | 75 % | 69 % | 62 % |
| tibia | 68 % | 85 % | 72 % | 80 % | 67 % |
| rear cannon | 69 % | 79 % | 87 % | 84 % | 83 % |
| upper leg | 84 % | 87 % | 87 % | 81 % | 75 % |
| front cannon | 77 % | 68 % | 84 % | 81 % | 88 % |
| servo hip ab/ad | 23 % | 16 % | 3 % | 7 % | 4 % |
| servo stifles | 0 % | 0 % | 1 % | 1 % | 0 % |
| servo hocks | 72 % | 83 % | 83 % | 81 % | 67 % |
| servo shoulders | 28 % | 31 % | 29 % | 25 % | 12 % |
| servo carpi | 84 % | 81 % | 88 % | 76 % | 67 % |
| stifle pulleys | 84 % | 87 % | 92 % | 99 % | 88 % |
| hock pulleys | 91 % | 92 % | 93 % | 92 % | 88 % |
| carpus pulleys | 89 % | 93 % | 95 % | 100 % | 100 % |
| stifle belt length | 15 % | 25 % | 37 % | 32 % | 38 % |
| hock belt length | 32 % | 40 % | 51 % | 53 % | 29 % |
| carpus belt length | 4 % | 3 % | 1 % | 5 % | 8 % |
| stifle belt system | 4 % | 5 % | 8 % | 8 % | 12 % |
| hock belt system | 1 % | 4 % | 5 % | 5 % | 0 % |
| carpus belt system | 1 % | 1 % | 0 % | 3 % | 8 % |
| shoulder belted | 41 % | 37 % | 45 % | 43 % | 17 % |
| hip_abd spring on/off | 3 % | 4 % | 1 % | 5 % | 0 % |
| stifle spring on/off | 5 % | 11 % | 7 % | 4 % | 0 % |
| hock spring on/off | 4 % | 4 % | 3 % | 1 % | 8 % |
| shoulder spring on/off | 4 % | 8 % | 8 % | 8 % | 12 % |
| carpus spring on/off | 39 % | 37 % | 33 % | 21 % | 29 % |
| hip_abd spring rate/anchors | 3 % | 13 % | 27 % | 27 % | 21 % |
| stifle spring rate/anchors | 23 % | 35 % | 41 % | 44 % | 46 % |
| hock spring rate/anchors | 12 % | 9 % | 27 % | 24 % | 17 % |
| shoulder spring rate/anchors | 26 % | 11 % | 24 % | 33 % | 8 % |
| carpus spring rate/anchors | 9 % | 5 % | 8 % | 12 % | 4 % |
| (bodies) | 74 | 75 | 75 | 75 | 24 |

### Choices on the final front (24 bodies, the working body left out)

* stifle: 40T/80T x11, 40T/60T x6, 30T/60T x3, 60T/80T x1, 30T/80T x1, 36T/60T x1, 30T/48T x1
* hock: 40T/60T x9, 40T/80T x9, 30T/60T x3, 48T/80T x2, 48T/60T x1
* carpus: 45T/45T x7, 40T/45T x6, 40T/80T x3, 48T/80T x2, 80T/80T x1, 45T/80T x1, 60T/80T x1, 80T/80T x1, 45T/36T x1, 60T/36T x1
* servos on C002: hocks x16, carpi x16, shoulders x3, hip ab/ad x1
* shoulder belted: 4 of 24
* hip_abd spring on: 24 of 24
* stifle spring on: 24 of 24
* hock spring on: 22 of 24
* shoulder spring on: 21 of 24
* carpus spring on: 7 of 24
* femur_length: today 200; front 194-210, median 200
* tibia_length: today 245; front 239-251, median 245
* rear_cannon_length: today 230; front 220-234, median 228
* upper_leg_length: today 340; front 330-354, median 340
* front_cannon_length: today 245; front 239-253, median 245

### Belt loads and simulated spring peaks, top bodies (peak / largest mean belt tension over every play and seed, N; allowable 44 N sustained at 10 mm, judged at 35.2 N)

* g020-008-r01: stifle 95/25, hock 89/19, carpus 61/15; springs sim {'stifle': 12.0, 'hock': 8.2, 'hip_abd': 1.8}
* g012-009: stifle 95/25, hock 67/17, carpus 66/12; springs sim {'stifle': 12.0, 'hock': 8.2, 'shoulder': 1.1, 'carpus': 9.0, 'hip_abd': 1.8}
* g011-003: stifle 91/25, hock 65/17, carpus 77/19; springs sim {'stifle': 17.4, 'hock': 8.2, 'carpus': 9.2, 'hip_abd': 3.7}
* g009-000: stifle 108/22, hock 64/18, carpus 70/20; springs sim {'stifle': 6.0, 'hock': 8.2, 'shoulder': 1.2, 'hip_abd': 3.7}
* g007-002: stifle 113/24, hock 88/20, carpus 84/15; springs sim {'stifle': 12.5, 'hock': 8.2, 'shoulder': 0.7, 'hip_abd': 3.7}
* g001-006-r05: stifle 103/23, hock 64/17, carpus 145/22; springs sim {'stifle': 12.0, 'hock': 8.2, 'carpus': 9.4, 'hip_abd': 1.9}
* g000-000: stifle 149/29, hock 76/18, carpus 100/19; springs sim {'stifle': 12.0, 'hock': 8.2, 'shoulder': 1.1, 'hip_abd': 3.7}

### Production sheets

`docs/studies/sheets_r11c/B20_<candidate>_geometry.csv` and `_parts.json` for every body on the final front (23, the
working body and `g001-006-r05` already have sheets: `A00_working_body_*`, `B1_006r05_*`) and for `g012-009` (33/33,
on the front through generation 15; dominated at 20 only by its own child). Written with
`production_r11c.py <project> sheets --cands=<run>-<id>:B20_<id>`; nothing in the project document changed. Every
part on them is `verified: false`, pulley masses are not entered, and each parts list ends with what to verify
before ordering.

### Watch the best body's line of descent side by side

The working body and five of `g020-008-r01`'s ancestors and itself (A013 at generation 0 -> `g002-012` -> `g006-005` ->
`g012-009` -> `g020-008-r01`; its other parent line runs through a belted-shoulder body) each play lie_rise, the fastest
trot setting (0.4 s / stride 2.0) and R7-lively on seed 0, stored as `sim` runs titled `R11c-B <label> <play>: seed 0`
(`docs/studies/store_r11cb.py`, record in `store_r11cb.json`; plays are not stopped at a fall so the whole replay
shows). Start the lab on port 8020 (`.\calflab.ps1 lab --project projects/robot-calf-final --port 8020`), then open a
link: a 3 x 2 grid of replays, each cell its own viewport and timeline, with *Restart all / Play all / Pause all*.
The labels give each play's worst margin (over = past a limit at margin 0.2).

﻿* **R7-lively**: [side by side](http://localhost:8020/compare.html?runs=20261107-200025-sim-fd74,20261107-200030-sim-da88,20261107-200033-sim-80a5,20261107-200035-sim-185f,20261107-200038-sim-dbf9,20261107-200034-sim-27fc&labels=0%20working%20body%20%28within%20%2B0.03%29%7Cgen%200%20A013%20%28within%20%2B0.37%29%7Cgen%202%20g002-012%20%28within%20%2B0.04%29%7Cgen%206%20g006-005%20%28over%20-0.76%29%7Cgen%2012%20g012-009%20%28within%20%2B0.61%29%7Cgen%2020%20g020-008-r01%20%28within%20%2B0.56%29)
* **lie_rise**: [side by side](http://localhost:8020/compare.html?runs=20261107-200006-sim-0a14,20261107-200007-sim-c847,20261107-200007-sim-426d,20261107-200011-sim-dac0,20261107-200012-sim-b6de,20261107-200015-sim-1b3a&labels=0%20working%20body%20%28over%20-3.00%29%7Cgen%200%20A013%20%28over%20-1.44%29%7Cgen%202%20g002-012%20%28over%20-2.00%29%7Cgen%206%20g006-005%20%28over%20-1.73%29%7Cgen%2012%20g012-009%20%28over%20-0.24%29%7Cgen%2020%20g020-008-r01%20%28over%20-0.16%29)
* **trot 0.4/2**: [side by side](http://localhost:8020/compare.html?runs=20261107-200004-sim-dee6,20261107-200005-sim-e744,20261107-200007-sim-59b0,20261107-200009-sim-74ee,20261107-200012-sim-75ad,20261107-200014-sim-c10f&labels=0%20working%20body%20%28over%20-0.25%29%7Cgen%200%20A013%20%28over%20-0.24%29%7Cgen%202%20g002-012%20%28over%20-0.11%29%7Cgen%206%20g006-005%20%28over%20-0.05%29%7Cgen%2012%20g012-009%20%28over%20-0.05%29%7Cgen%2020%20g020-008-r01%20%28within%20%2B0.21%29)

The replays reproduce the run's judgements: lie_rise -3.00, -1.44, -2.00, -1.73, -0.24, -0.16 along the line; the fast
trot is within limits only on `g020-008-r01` (+0.21) on this seed; R7-lively holds on all but `g006-005` (-0.76).

### What to read next

* **Watch `g020-008-r01`** (Evolve > Archive or Journal > Runs, run `20261107-043030-evolve-c02e`), especially
  lie_rise (-0.16) and walk (-0.52), against `g012-009` and A012.
* Stage C (re-evolved behaviours for the top bodies) should take `g020-008-r01`, `g012-009`, `g011-003` (32/33, walk
  -0.03, turn -0.04, no shoulder C002), `g009-000` (32/33, cost 1.83) and `g007-002` (33/33, no trot).
* The trot grid's ceiling hides differences above about 530 mm/s; a faster corner (cycle 0.35 s or stride 2.5) would
  be a change to the judging, not made here.
