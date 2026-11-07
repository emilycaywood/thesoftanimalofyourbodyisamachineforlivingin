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
