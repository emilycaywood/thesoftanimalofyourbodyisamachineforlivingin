
### 20261106-044751-evolve-dbf1-g000-000 working body: 32/33 min, trot 0 mm/s, cost 0.00, fitness -0.315

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.29 | 1.28 | 2.24 | 1.25 | 0.41 | sustained belt tension | 8 (joint speed) |
| fl.shoulder | 0.90 | 3.56 | - | 1.11 | 1.04 | sustained servo torque | 4 (sustained servo torque) |
| fr.carpus | 1.29 | 1.28 | 2.24 | 1.17 | 0.41 | sustained belt tension | 4 (joint speed) |
| fr.shoulder | 0.88 | 3.56 | - | 1.09 | 1.08 | sustained servo torque | 2 (sustained servo torque) |
| hl.hip_abd | 0.23 | 1.96 | - | 0.58 | 0.50 | sustained servo torque | 2 (sustained servo torque) |
| hl.hock | 1.16 | 1.16 | 2.32 | 1.16 | 0.31 | sustained belt tension | 0 |
| hl.stifle | 1.13 | 1.44 | 4.00 | 1.25 | 0.56 | sustained belt tension | 1 (sustained belt tension) |
| hr.hip_abd | 0.39 | 1.88 | - | 0.76 | 0.67 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.16 | 1.16 | 2.32 | 1.16 | 0.31 | sustained belt tension | 0 |
| hr.stifle | 1.12 | 1.44 | 4.00 | 1.25 | 0.60 | sustained belt tension | 1 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.13 | joint_speed |
| turn | no | -0.25 | envelope |
| lie_rise | no | -3.00 | belt_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.13 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 3/3 | 0.17 | envelope, joint_speed |
| R6c-lively | 3/3 | 0.02 | joint_speed |
| R6c-walking | 3/3 | 0.02 | joint_speed |
| R6c-trotting | 3/3 | 0.05 | joint_speed |
| R7-calm | 3/3 | 0.16 | belt_sustained, joint_speed |
| R7-ambling | 3/3 | 0.03 | joint_speed |
| R7-lively | 3/3 | 0.02 | joint_speed |
| R7-walking | 2/3 | -2.52 | joint_speed, servo_sustained |
| R7-trot-walk | 3/3 | 0.00 | joint_speed |
| R7-trot-shift | 3/3 | 0.13 | joint_speed |
| R7-trotting | 3/3 | 0.02 | joint_speed |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1304 g | +0 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.000 | the costs weighted (preset cost_weights) |

### 20261106-044751-evolve-dbf1-g000-001 R9 best: 20/33 min, trot 394 mm/s, cost 2.33, fitness -0.436

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3250_c002 | new |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 40T-80T | GT2-2mm-444-C | 2.00 | 161.5 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 45T-45T-whatif (WHAT-IF) | GT2-2mm-640-C | 1.00 | 275.0 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 0.97 | 2.76 | 2.72 | 1.07 | 0.87 | sustained servo torque | 3 (sustained servo torque) |
| fl.shoulder | 0.68 | 3.72 | - | 0.94 | 0.89 | sustained servo torque | 6 (sustained servo torque) |
| fr.carpus | 0.96 | 2.76 | 2.72 | 1.07 | 0.87 | sustained servo torque | 6 (sustained servo torque) |
| fr.shoulder | 0.67 | 3.72 | - | 1.04 | 0.87 | sustained servo torque | 0 |
| hl.hip_abd | 0.15 | 0.96 | - | 0.40 | 0.40 | sustained servo torque | 0 |
| hl.hock | 1.05 | 0.04 | 2.00 | 0.79 | 0.23 | sustained belt tension | 1 (joint speed) |
| hl.stifle | 1.11 | 2.24 | 2.36 | 1.24 | 0.58 | sustained belt tension | 1 (torque-speed envelope) |
| hr.hip_abd | 0.20 | 1.20 | - | 0.45 | 0.42 | sustained servo torque | 1 (sustained servo torque) |
| hr.hock | 1.05 | 0.08 | 2.00 | 0.79 | 0.23 | sustained belt tension | 0 |
| hr.stifle | 1.11 | 2.24 | 2.36 | 1.25 | 0.57 | sustained belt tension | 4 (joint speed) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | yes | 0.21 | envelope |
| turn | yes | 0.09 | envelope |
| lie_rise | no | -2.72 | servo_sustained |
| fastest trot within | trot 0.5/2 | 394 mm/s | 12 trot settings hold |
| screen | passed | 0.36 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -1.04 | servo_sustained |
| R6c-lively | 3/3 | 0.12 | envelope, servo_sustained |
| R6c-walking | 2/3 | -0.40 | joint_speed, servo_sustained |
| R6c-trotting | 3/3 | 0.00 | servo_sustained |
| R7-calm | 0/3 | -1.12 | servo_sustained |
| R7-ambling | 3/3 | 0.39 | envelope |
| R7-lively | 2/3 | -0.04 | envelope, servo_sustained |
| R7-walking | 2/3 | -0.64 | servo_sustained |
| R7-trot-walk | 2/3 | -0.04 | joint_speed, servo_sustained |
| R7-trot-shift | 0/3 | -0.08 | servo_sustained |
| R7-trotting | 3/3 | 0.00 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 45T, 2 mm 80T | 12 pulleys |
| new belt lengths | none |  |
| mass | 1382 g | +78 g; 15 masses not entered (0 g) |
| servo current (known servos) | 2.70 A peak | servos without a stall current are not counted |
| not in a catalog | carpus: 45T-45T-whatif | R8 what-if (ADR-099): commercially listed GT2 10 mm pulleys, not in the catalog; masses unknown |
| new servo cost | 0.00 USD |  |
| unknown | 16 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 2.328 | the costs weighted (preset cost_weights) |

### 20261106-044751-evolve-dbf1-g000-002 R10 1:1 45T: 26/33 min, trot 419 mm/s, cost 2.33, fitness -0.445

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3250_c002 | new |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 40T-80T | GT2-2mm-444-C | 2.00 | 161.5 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 45T-45T-whatif (WHAT-IF) | GT2-2mm-640-C | 1.00 | 275.0 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 0.63 | 1.96 | 2.72 | 0.62 | 0.51 | sustained belt tension | 1 (sustained belt tension) |
| fl.shoulder | 0.67 | 3.88 | - | 1.08 | 0.95 | sustained servo torque | 2 (sustained servo torque) |
| fr.carpus | 0.63 | 1.96 | 2.72 | 0.62 | 0.51 | sustained belt tension | 6 (sustained belt tension) |
| fr.shoulder | 0.67 | 3.88 | - | 0.95 | 0.88 | sustained servo torque | 0 |
| hl.hip_abd | 0.27 | 2.20 | - | 0.71 | 0.62 | sustained servo torque | 3 (sustained servo torque) |
| hl.hock | 1.05 | 0.04 | 1.92 | 0.79 | 0.23 | sustained belt tension | 0 |
| hl.stifle | 1.10 | 1.92 | 2.16 | 1.24 | 0.56 | sustained belt tension | 3 (joint speed) |
| hr.hip_abd | 0.39 | 1.60 | - | 0.82 | 0.74 | sustained servo torque | 1 (sustained servo torque) |
| hr.hock | 1.05 | 0.04 | 1.92 | 0.79 | 0.23 | sustained belt tension | 1 (joint speed) |
| hr.stifle | 1.10 | 1.92 | 2.16 | 1.17 | 0.50 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.24 | servo_sustained |
| turn | no | -0.20 | servo_sustained |
| lie_rise | no | -2.88 | servo_sustained |
| fastest trot within | trot 0.5/2 | 419 mm/s | 13 trot settings hold |
| screen | passed | 0.39 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -1.08 | belt_sustained |
| R6c-lively | 3/3 | 0.36 | belt_sustained, envelope |
| R6c-walking | 3/3 | 0.20 | belt_sustained, envelope, servo_sustained |
| R6c-trotting | 3/3 | 0.08 | belt_sustained, servo_sustained |
| R7-calm | 0/3 | -1.12 | belt_sustained |
| R7-ambling | 3/3 | 0.44 | envelope, servo_sustained |
| R7-lively | 3/3 | 0.24 | envelope, servo_sustained |
| R7-walking | 2/3 | -0.60 | belt_sustained, servo_sustained |
| R7-trot-walk | 3/3 | 0.12 | belt_sustained, envelope |
| R7-trot-shift | 3/3 | 0.16 | servo_sustained |
| R7-trotting | 3/3 | 0.08 | belt_sustained, servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 45T, 2 mm 80T | 12 pulleys |
| new belt lengths | none |  |
| mass | 1382 g | +78 g; 15 masses not entered (0 g) |
| servo current (known servos) | 3.71 A peak | servos without a stall current are not counted |
| not in a catalog | carpus: 45T-45T-whatif | R8 what-if (ADR-099): commercially listed GT2 10 mm pulleys, not in the catalog; masses unknown |
| new servo cost | 0.00 USD |  |
| unknown | 16 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 2.328 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-000 working body: 32/33 min, trot 0 mm/s, cost 0.00, fitness -0.315

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.29 | 1.28 | 2.24 | 1.25 | 0.41 | sustained belt tension | 8 (joint speed) |
| fl.shoulder | 0.90 | 3.56 | - | 1.11 | 1.04 | sustained servo torque | 4 (sustained servo torque) |
| fr.carpus | 1.29 | 1.28 | 2.24 | 1.17 | 0.41 | sustained belt tension | 4 (joint speed) |
| fr.shoulder | 0.88 | 3.56 | - | 1.09 | 1.08 | sustained servo torque | 2 (sustained servo torque) |
| hl.hip_abd | 0.23 | 1.96 | - | 0.58 | 0.50 | sustained servo torque | 2 (sustained servo torque) |
| hl.hock | 1.16 | 1.16 | 2.32 | 1.16 | 0.31 | sustained belt tension | 0 |
| hl.stifle | 1.13 | 1.44 | 4.00 | 1.25 | 0.56 | sustained belt tension | 1 (sustained belt tension) |
| hr.hip_abd | 0.39 | 1.88 | - | 0.76 | 0.67 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.16 | 1.16 | 2.32 | 1.16 | 0.31 | sustained belt tension | 0 |
| hr.stifle | 1.12 | 1.44 | 4.00 | 1.25 | 0.60 | sustained belt tension | 1 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.13 | joint_speed |
| turn | no | -0.25 | envelope |
| lie_rise | no | -3.00 | belt_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.13 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 3/3 | 0.17 | envelope, joint_speed |
| R6c-lively | 3/3 | 0.02 | joint_speed |
| R6c-walking | 3/3 | 0.02 | joint_speed |
| R6c-trotting | 3/3 | 0.05 | joint_speed |
| R7-calm | 3/3 | 0.16 | belt_sustained, joint_speed |
| R7-ambling | 3/3 | 0.03 | joint_speed |
| R7-lively | 3/3 | 0.02 | joint_speed |
| R7-walking | 2/3 | -2.52 | joint_speed, servo_sustained |
| R7-trot-walk | 3/3 | 0.00 | joint_speed |
| R7-trot-shift | 3/3 | 0.13 | joint_speed |
| R7-trotting | 3/3 | 0.02 | joint_speed |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1304 g | +0 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.000 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-001 R10 40T/80T: 28/33 min, trot 63 mm/s, cost 1.58, fitness -0.340

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3250_c002 | new |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 40T-80T | GT2-2mm-444-C | 2.00 | 161.5 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.05 | 0.48 | 1.68 | 0.78 | 0.23 | sustained belt tension | 14 (sustained belt tension) |
| fl.shoulder | 0.69 | 3.80 | - | 1.09 | 0.96 | sustained servo torque | 5 (sustained servo torque) |
| fr.carpus | 1.05 | 0.48 | 1.68 | 0.76 | 0.23 | sustained belt tension | 0 |
| fr.shoulder | 0.69 | 3.80 | - | 0.94 | 0.88 | sustained servo torque | 3 (sustained servo torque) |
| hl.hip_abd | 0.24 | 1.84 | - | 0.75 | 0.66 | sustained servo torque | 1 (sustained servo torque) |
| hl.hock | 1.05 | 0.04 | 1.92 | 0.79 | 0.24 | sustained belt tension | 0 |
| hl.stifle | 1.10 | 1.92 | 2.20 | 1.23 | 0.55 | sustained belt tension | 1 (torque-speed envelope) |
| hr.hip_abd | 0.39 | 1.64 | - | 0.88 | 0.80 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.05 | 0.04 | 1.92 | 0.79 | 0.24 | sustained belt tension | 0 |
| hr.stifle | 1.10 | 1.92 | 2.20 | 1.06 | 0.45 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.24 | servo_sustained |
| turn | no | -0.20 | servo_sustained |
| lie_rise | no | -2.80 | servo_sustained |
| fastest trot within | trot 0.8/1 | 63 mm/s | 2 trot settings hold |
| screen | passed | 0.22 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 2/3 | -0.16 | envelope, servo_sustained |
| R6c-lively | 3/3 | 0.39 | joint_speed |
| R6c-walking | 2/3 | -0.60 | joint_speed, servo_sustained |
| R6c-trotting | 3/3 | 0.00 | servo_sustained |
| R7-calm | 2/3 | -0.16 | envelope, servo_sustained |
| R7-ambling | 3/3 | 0.34 | joint_speed |
| R7-lively | 3/3 | 0.16 | joint_speed, servo_sustained |
| R7-walking | 2/3 | -0.84 | servo_sustained |
| R7-trot-walk | 3/3 | 0.20 | joint_speed, servo_sustained |
| R7-trot-shift | 3/3 | 0.12 | servo_sustained |
| R7-trotting | 2/3 | -0.04 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 12 pulleys |
| new belt lengths | none |  |
| mass | 1382 g | +78 g; 14 masses not entered (0 g) |
| servo current (known servos) | 2.03 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.578 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-003-r21 : 0/33 min, trot 0 mm/s, cost 0.01, fitness -1.002

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 2.12 | 2.72 | 1.25 | 0.58 | sustained belt tension | 0 |
| fl.shoulder | 0.68 | 4.00 | - | 1.17 | 1.06 | sustained servo torque | 19 (sustained servo torque) |
| fr.carpus | 1.19 | 1.96 | 2.65 | 1.25 | 0.54 | sustained belt tension | 0 |
| fr.shoulder | 0.69 | 4.00 | - | 1.19 | 0.98 | sustained servo torque | 1 (sustained servo torque) |
| hl.hip_abd | 0.32 | 4.00 | - | 0.80 | 0.77 | sustained servo torque | 1 (sustained servo torque) |
| hl.hock | 1.17 | 0.44 | 1.36 | 1.09 | 0.33 | sustained belt tension | 0 |
| hl.stifle | 1.15 | 2.56 | 3.21 | 0.96 | 0.64 | sustained belt tension | 0 |
| hr.hip_abd | 0.33 | 4.00 | - | 0.81 | 0.77 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.17 | 0.44 | 1.36 | 1.09 | 0.26 | sustained belt tension | 0 |
| hr.stifle | 1.12 | 2.77 | 3.21 | 1.02 | 0.64 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -3.00 | servo_sustained |
| turn | no | -3.00 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -2.72 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1319 g | +15 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.015 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-004-r27 : 0/33 min, trot 0 mm/s, cost 0.00, fitness -0.919

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 1.52 | 4.00 | 1.11 | 0.35 | sustained belt tension | 1 (joint speed) |
| fl.shoulder | 0.90 | 4.00 | - | 1.11 | 0.74 | sustained servo torque | 5 (sustained servo torque) |
| fr.carpus | 1.19 | 1.52 | 4.00 | 1.12 | 0.35 | sustained belt tension | 2 (joint speed) |
| fr.shoulder | 0.90 | 4.00 | - | 1.11 | 0.74 | sustained servo torque | 0 |
| hl.hip_abd | 0.45 | 4.00 | - | 0.77 | 0.76 | sustained servo torque | 5 (sustained servo torque) |
| hl.hock | 1.18 | 1.64 | 2.52 | 1.23 | 0.33 | sustained belt tension | 0 |
| hl.stifle | 1.11 | 2.08 | 4.00 | 0.90 | 0.50 | sustained belt tension | 18 (sustained belt tension) |
| hr.hip_abd | 0.40 | 4.00 | - | 0.68 | 0.67 | sustained servo torque | 17 (sustained servo torque) |
| hr.hock | 1.18 | 1.64 | 2.52 | 1.23 | 0.29 | sustained belt tension | 0 |
| hr.stifle | 1.11 | 2.08 | 4.00 | 1.05 | 0.35 | sustained belt tension | 8 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.56 | servo_sustained |
| turn | no | -0.98 | belt_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.15 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | servo_sustained |
| R6c-lively | 0/3 | -2.04 | servo_sustained |
| R6c-walking | 0/3 | -2.36 | servo_sustained |
| R6c-trotting | 0/3 | -1.40 | servo_sustained |
| R7-calm | 0/3 | -3.00 | servo_sustained |
| R7-ambling | 0/3 | -0.76 | servo_sustained |
| R7-lively | 0/3 | -2.20 | servo_sustained |
| R7-walking | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R7-trot-walk | 0/3 | -2.36 | servo_sustained |
| R7-trot-shift | 0/3 | -1.28 | belt_sustained, servo_sustained |
| R7-trotting | 0/3 | -0.72 | belt_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1300 g | -4 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.000 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-005-r15 : 0/33 min, trot 0 mm/s, cost 0.57, fitness -1.057

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3250_c002 | new |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-318-B | 2.00 | 113.6 | GT2-2mm-9mm-gates |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.23 | 1.08 | 1.31 | 1.25 | 0.31 | sustained belt tension | 0 |
| fl.shoulder | 0.73 | 3.64 | - | 1.25 | 1.14 | sustained servo torque | 6 (sustained servo torque) |
| fr.carpus | 1.24 | 1.08 | 1.32 | 1.25 | 0.30 | sustained belt tension | 0 |
| fr.shoulder | 0.67 | 3.64 | - | 1.25 | 1.18 | sustained servo torque | 2 (sustained servo torque) |
| hl.hip_abd | 0.32 | 2.56 | - | 0.80 | 0.80 | sustained servo torque | 0 |
| hl.hock | 1.15 | 2.04 | 3.52 | 1.25 | 0.41 | sustained belt tension | 10 (sustained belt tension) |
| hl.stifle | 0.52 | 1.52 | 2.88 | 0.88 | 0.55 | sustained belt tension | 0 |
| hr.hip_abd | 0.32 | 2.46 | - | 0.74 | 0.73 | sustained servo torque | 0 |
| hr.hock | 1.13 | 1.88 | 3.48 | 1.25 | 0.40 | sustained belt tension | 5 (sustained belt tension) |
| hr.stifle | 0.53 | 1.32 | 2.84 | 0.88 | 0.55 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -2.48 | belt_sustained |
| turn | no | -2.52 | belt_sustained |
| lie_rise | no | -2.64 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -0.76 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 2 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | GT2-2mm-318-B |  |
| mass | 1373 g | +69 g; 14 masses not entered (0 g) |
| servo current (known servos) | 2.11 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.569 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g000-006-r24 : 0/33 min, trot 0 mm/s, cost 1.05, fitness -1.105

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3250_c002 | new |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 36T-72T | GT2-2mm-640-C | 2.00 | 265.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 0.36 | 0.48 | 1.25 | 0.31 | torque-speed envelope | 0 |
| fl.shoulder | 0.80 | 3.09 | - | 0.91 | 0.73 | sustained servo torque | 0 |
| fr.carpus | 1.20 | 0.36 | 0.48 | 1.19 | 0.31 | joint speed | 0 |
| fr.shoulder | 0.89 | 3.09 | - | 0.96 | 0.73 | sustained servo torque | 0 |
| hl.hip_abd | 0.27 | 1.86 | - | 0.49 | 0.42 | sustained servo torque | 0 |
| hl.hock | 1.21 | 1.94 | 3.72 | 1.25 | 0.48 | sustained belt tension | 7 (sustained belt tension) |
| hl.stifle | 0.62 | 0.76 | 3.48 | 0.55 | 0.32 | sustained belt tension | 9 (sustained belt tension) |
| hr.hip_abd | 0.35 | 2.48 | - | 0.59 | 0.51 | sustained servo torque | 0 |
| hr.hock | 1.24 | 1.94 | 3.72 | 1.17 | 0.44 | sustained belt tension | 2 (sustained belt tension) |
| hr.stifle | 0.62 | 0.80 | 3.41 | 0.56 | 0.32 | sustained belt tension | 5 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -2.48 | belt_sustained |
| turn | no | -2.41 | belt_sustained |
| lie_rise | no | -2.72 | belt_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -1.28 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 2 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 36T, 2 mm 72T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1350 g | +46 g; 16 masses not entered (0 g) |
| servo current (known servos) | 1.48 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.046 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-000-r09 : 0/33 min, trot 0 mm/s, cost 0.50, fitness -1.050

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 36T-72T | GT2-2mm-400-C | 2.00 | 145.5 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 1.68 | 2.48 | 1.11 | 0.40 | sustained belt tension | 0 |
| fl.shoulder | 0.96 | 4.00 | - | 1.14 | 0.69 | sustained servo torque | 0 |
| fr.carpus | 1.19 | 1.68 | 2.48 | 1.12 | 0.40 | sustained belt tension | 0 |
| fr.shoulder | 0.96 | 4.00 | - | 1.13 | 0.69 | sustained servo torque | 0 |
| hl.hip_abd | 0.34 | 1.40 | - | 0.59 | 0.59 | sustained servo torque | 0 |
| hl.hock | 1.18 | 2.16 | 2.56 | 1.25 | 0.30 | sustained belt tension | 0 |
| hl.stifle | 1.13 | 4.00 | 4.00 | 0.96 | 0.50 | sustained servo torque | 12 (sustained belt tension) |
| hr.hip_abd | 0.40 | 1.44 | - | 0.69 | 0.69 | sustained servo torque | 0 |
| hr.hock | 1.16 | 2.16 | 2.56 | 1.25 | 0.30 | sustained belt tension | 0 |
| hr.stifle | 1.14 | 4.00 | 4.00 | 0.88 | 0.44 | sustained servo torque | 11 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -2.32 | belt_sustained |
| turn | no | -2.33 | belt_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -1.20 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 36T, 2 mm 72T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1303 g | -1 g; 16 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.500 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-001-r06 : 0/33 min, trot 0 mm/s, cost 0.00, fitness -0.990

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.35 | 1.48 | 4.00 | 1.11 | 0.39 | sustained belt tension | 2 (joint speed) |
| fl.shoulder | 0.96 | 4.00 | - | 1.17 | 0.80 | sustained servo torque | 1 (sustained servo torque) |
| fr.carpus | 1.21 | 1.48 | 4.00 | 1.12 | 0.39 | sustained belt tension | 0 |
| fr.shoulder | 0.95 | 4.00 | - | 1.12 | 0.69 | sustained servo torque | 1 (sustained servo torque) |
| hl.hip_abd | 0.50 | 4.00 | - | 0.85 | 0.85 | sustained servo torque | 9 (sustained servo torque) |
| hl.hock | 1.21 | 1.44 | 2.44 | 1.25 | 0.40 | sustained belt tension | 3 (sustained belt tension) |
| hl.stifle | 1.10 | 1.80 | 4.00 | 0.94 | 0.52 | sustained belt tension | 22 (sustained belt tension) |
| hr.hip_abd | 0.90 | 4.00 | - | 0.88 | 0.88 | sustained servo torque | 15 (sustained servo torque) |
| hr.hock | 1.21 | 1.44 | 2.44 | 1.24 | 0.32 | sustained belt tension | 1 (sustained belt tension) |
| hr.stifle | 1.11 | 1.92 | 4.00 | 0.99 | 0.33 | sustained belt tension | 2 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.92 | belt_sustained |
| turn | no | -1.92 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.17 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | servo_sustained |
| R6c-lively | 0/3 | -2.72 | servo_sustained |
| R6c-walking | 0/3 | -2.02 | servo_sustained |
| R6c-trotting | 0/3 | -1.76 | belt_sustained |
| R7-calm | 0/3 | -3.00 | servo_sustained |
| R7-ambling | 0/3 | -2.48 | servo_sustained |
| R7-lively | 0/3 | -2.60 | servo_sustained |
| R7-walking | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R7-trot-walk | 0/3 | -2.48 | servo_sustained |
| R7-trot-shift | 0/3 | -1.64 | belt_sustained |
| R7-trotting | 0/3 | -1.72 | belt_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1306 g | +2 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.002 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-002-r26 : 0/33 min, trot 0 mm/s, cost 1.03, fitness -1.103

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 1.68 | 1.80 | 1.17 | 0.42 | sustained belt tension | 0 |
| fl.shoulder | 0.82 | 4.00 | - | 0.90 | 0.66 | sustained servo torque | 0 |
| fr.carpus | 1.19 | 1.68 | 1.80 | 1.12 | 0.42 | sustained belt tension | 0 |
| fr.shoulder | 0.82 | 4.00 | - | 0.90 | 0.66 | sustained servo torque | 0 |
| hl.hip_abd | 0.27 | 2.28 | - | 0.62 | 0.54 | sustained servo torque | 1 (sustained servo torque) |
| hl.hock | 1.05 | 1.56 | 3.56 | 0.94 | 0.25 | sustained belt tension | 0 |
| hl.stifle | 1.09 | 2.04 | 4.00 | 0.89 | 0.42 | sustained belt tension | 15 (sustained belt tension) |
| hr.hip_abd | 0.31 | 2.28 | - | 0.80 | 0.74 | sustained servo torque | 1 (sustained servo torque) |
| hr.hock | 1.05 | 1.56 | 3.56 | 0.96 | 0.26 | sustained belt tension | 1 (sustained belt tension) |
| hr.stifle | 1.09 | 2.04 | 4.00 | 0.74 | 0.36 | sustained belt tension | 5 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -1.84 | belt_sustained |
| turn | no | -2.00 | belt_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -0.48 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 2 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1338 g | +34 g; 16 masses not entered (0 g) |
| servo current (known servos) | 1.58 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.034 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-003-r02 : 0/33 min, trot 0 mm/s, cost 0.50, fitness -1.050

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 1.72 | 2.48 | 1.11 | 0.35 | sustained belt tension | 3 (sustained belt tension) |
| fl.shoulder | 0.88 | 4.00 | - | 1.01 | 0.67 | sustained servo torque | 0 |
| fr.carpus | 1.19 | 1.72 | 2.48 | 1.12 | 0.35 | sustained belt tension | 0 |
| fr.shoulder | 0.86 | 4.00 | - | 0.99 | 0.67 | sustained servo torque | 0 |
| hl.hip_abd | 0.41 | 2.04 | - | 0.91 | 0.91 | sustained servo torque | 2 (sustained servo torque) |
| hl.hock | 1.20 | 1.36 | 1.64 | 1.24 | 0.29 | sustained belt tension | 0 |
| hl.stifle | 1.11 | 3.04 | 4.00 | 0.91 | 0.44 | sustained belt tension | 14 (sustained belt tension) |
| hr.hip_abd | 0.42 | 2.56 | - | 0.81 | 0.81 | sustained servo torque | 1 (sustained servo torque) |
| hr.hock | 1.20 | 1.36 | 1.64 | 1.22 | 0.33 | sustained belt tension | 0 |
| hr.stifle | 1.11 | 3.04 | 4.00 | 0.77 | 0.36 | sustained belt tension | 3 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -1.08 | servo_sustained |
| turn | no | -1.56 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -0.48 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1304 g | +0 g; 16 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.500 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-004-r19 : 2/33 min, trot 0 mm/s, cost 1.58, fitness -1.088

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3250_c002 | new |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.05 | 0.44 | 1.60 | 0.94 | 0.26 | sustained belt tension | 12 (sustained belt tension) |
| fl.shoulder | 0.71 | 3.48 | - | 1.19 | 1.19 | sustained servo torque | 8 (sustained servo torque) |
| fr.carpus | 1.05 | 0.44 | 1.52 | 0.94 | 0.24 | sustained belt tension | 3 (sustained belt tension) |
| fr.shoulder | 0.71 | 3.52 | - | 1.12 | 1.12 | sustained servo torque | 23 (sustained servo torque) |
| hl.hip_abd | 0.37 | 2.12 | - | 1.09 | 0.97 | sustained servo torque | 4 (sustained servo torque) |
| hl.hock | 1.06 | 0.36 | 1.48 | 0.77 | 0.27 | sustained belt tension | 0 |
| hl.stifle | 1.10 | 0.88 | 1.28 | 0.89 | 0.41 | sustained belt tension | 0 |
| hr.hip_abd | 0.60 | 2.44 | - | 1.09 | 0.98 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.06 | 0.36 | 1.48 | 0.77 | 0.27 | sustained belt tension | 0 |
| hr.stifle | 1.10 | 0.88 | 3.04 | 0.95 | 0.42 | sustained belt tension | 2 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -1.44 | servo_sustained |
| turn | no | -0.44 | servo_sustained |
| lie_rise | no | -1.40 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.03 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -1.60 | belt_sustained, servo_sustained |
| R6c-lively | 0/3 | -1.64 | servo_sustained |
| R6c-walking | 1/3 | -2.52 | envelope, servo_sustained |
| R6c-trotting | 0/3 | -1.20 | servo_sustained |
| R7-calm | 0/3 | -2.28 | belt_sustained, servo_sustained |
| R7-ambling | 1/3 | -2.48 | envelope, servo_sustained |
| R7-lively | 0/3 | -2.20 | servo_sustained |
| R7-walking | 0/3 | -2.20 | servo_sustained |
| R7-trot-walk | 0/3 | -2.40 | servo_sustained |
| R7-trot-shift | 0/3 | -1.84 | servo_sustained |
| R7-trotting | 0/3 | -1.76 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 8 pulleys |
| new belt lengths | none |  |
| mass | 1387 g | +83 g; 16 masses not entered (0 g) |
| servo current (known servos) | 2.09 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.583 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-005-r08 : 0/33 min, trot 0 mm/s, cost 2.08, fitness -1.208

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3215_c018 |  |
| carpus | sts3250_c002 | new |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 40T-80T | GT2-2mm-444-C | 2.00 | 161.5 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 36T-72T | GT2-2mm-640-C | 2.00 | 265.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.05 | 0.44 | 2.40 | 0.69 | 0.24 | sustained belt tension | 0 |
| fl.shoulder | 0.72 | 4.00 | - | 1.25 | 1.16 | sustained servo torque | 0 |
| fr.carpus | 1.05 | 0.44 | 2.40 | 0.65 | 0.24 | sustained belt tension | 0 |
| fr.shoulder | 0.67 | 4.00 | - | 1.01 | 0.91 | sustained servo torque | 0 |
| hl.hip_abd | 0.37 | 4.00 | - | 1.03 | 1.02 | sustained servo torque | 22 (sustained servo torque) |
| hl.hock | 1.05 | 0.04 | 1.88 | 0.79 | 0.22 | sustained belt tension | 0 |
| hl.stifle | 1.10 | 2.24 | 2.36 | 1.11 | 0.49 | sustained belt tension | 0 |
| hr.hip_abd | 0.28 | 4.00 | - | 0.85 | 0.85 | sustained servo torque | 1 (sustained servo torque) |
| hr.hock | 1.05 | 0.04 | 1.88 | 0.79 | 0.20 | sustained belt tension | 0 |
| hr.stifle | 1.10 | 2.24 | 2.36 | 0.97 | 0.43 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -3.00 | servo_sustained |
| turn | no | -3.00 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -2.00 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 36T, 2 mm 40T, 2 mm 72T, 2 mm 80T | 12 pulleys |
| new belt lengths | none |  |
| mass | 1385 g | +81 g; 16 masses not entered (0 g) |
| servo current (known servos) | 2.04 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 2.081 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g001-006-r01 : 15/33 min, trot 0 mm/s, cost 0.50, fitness -0.674

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.28 | 1.60 | 1.76 | 1.16 | 0.37 | sustained belt tension | 7 (joint speed) |
| fl.shoulder | 0.73 | 4.00 | - | 1.25 | 1.15 | sustained servo torque | 13 (sustained servo torque) |
| fr.carpus | 1.19 | 1.60 | 1.76 | 1.12 | 0.37 | sustained belt tension | 3 (joint speed) |
| fr.shoulder | 0.72 | 4.00 | - | 1.05 | 0.97 | sustained servo torque | 3 (sustained servo torque) |
| hl.hip_abd | 0.28 | 1.44 | - | 0.50 | 0.50 | sustained servo torque | 0 |
| hl.hock | 1.17 | 0.76 | 2.12 | 1.08 | 0.32 | sustained belt tension | 0 |
| hl.stifle | 1.12 | 1.64 | 4.00 | 0.94 | 0.44 | sustained belt tension | 9 (sustained belt tension) |
| hr.hip_abd | 0.25 | 1.19 | - | 0.74 | 0.67 | sustained servo torque | 0 |
| hr.hock | 1.17 | 0.76 | 2.12 | 1.10 | 0.28 | sustained belt tension | 0 |
| hr.stifle | 1.12 | 1.68 | 4.00 | 1.05 | 0.39 | sustained belt tension | 6 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.40 | servo_sustained |
| turn | no | -0.16 | envelope |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.14 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 1/3 | -3.00 | belt_sustained, joint_speed, servo_sustained |
| R6c-lively | 2/3 | -0.36 | belt_sustained, joint_speed |
| R6c-walking | 1/3 | -0.36 | belt_sustained, joint_speed, servo_sustained |
| R6c-trotting | 0/3 | -1.16 | servo_sustained |
| R7-calm | 1/3 | -1.56 | belt_sustained, joint_speed, servo_sustained |
| R7-ambling | 3/3 | 0.02 | joint_speed |
| R7-lively | 3/3 | 0.01 | joint_speed |
| R7-walking | 0/3 | -1.52 | servo_sustained |
| R7-trot-walk | 3/3 | 0.00 | joint_speed |
| R7-trot-shift | 1/3 | -1.40 | servo_sustained |
| R7-trotting | 0/3 | -1.44 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1306 g | +2 g; 16 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.502 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-000-r04 : 0/33 min, trot 0 mm/s, cost 1.00, fitness -1.018

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 40T-80T | GT2-2mm-444-C | 2.00 | 161.5 | GT2-2mm-10mm-generic |
| hock | 36T-72T | GT2-2mm-400-C | 2.00 | 145.5 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.28 | 1.40 | 3.84 | 1.11 | 0.36 | sustained belt tension | 16 (sustained belt tension) |
| fl.shoulder | 0.95 | 4.00 | - | 1.20 | 0.84 | sustained servo torque | 5 (sustained servo torque) |
| fr.carpus | 1.33 | 1.40 | 4.00 | 1.12 | 0.36 | sustained belt tension | 13 (sustained belt tension) |
| fr.shoulder | 0.95 | 4.00 | - | 1.19 | 0.82 | sustained servo torque | 0 |
| hl.hip_abd | 0.32 | 1.84 | - | 0.62 | 0.62 | sustained servo torque | 1 (sustained servo torque) |
| hl.hock | 1.23 | 1.56 | 2.40 | 1.14 | 0.41 | sustained belt tension | 17 (sustained belt tension) |
| hl.stifle | 1.11 | 2.24 | 2.40 | 0.85 | 0.45 | sustained belt tension | 0 |
| hr.hip_abd | 0.30 | 3.20 | - | 0.59 | 0.59 | sustained servo torque | 0 |
| hr.hock | 1.22 | 1.56 | 2.40 | 1.14 | 0.40 | sustained belt tension | 4 (sustained belt tension) |
| hr.stifle | 1.12 | 2.24 | 2.40 | 1.00 | 0.36 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.40 | servo_sustained |
| turn | no | -1.08 | belt_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.16 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -2.84 | belt_sustained |
| R6c-lively | 0/3 | -1.24 | belt_sustained |
| R6c-walking | 0/3 | -1.20 | belt_sustained |
| R6c-trotting | 0/3 | -0.96 | belt_sustained, servo_sustained |
| R7-calm | 0/3 | -3.00 | belt_sustained |
| R7-ambling | 0/3 | -1.08 | belt_sustained |
| R7-lively | 0/3 | -1.32 | belt_sustained |
| R7-walking | 0/3 | -2.84 | belt_sustained, servo_sustained |
| R7-trot-walk | 0/3 | -1.48 | belt_sustained |
| R7-trot-shift | 0/3 | -1.68 | belt_sustained, servo_sustained |
| R7-trotting | 0/3 | -0.88 | belt_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 36T, 2 mm 40T, 2 mm 72T, 2 mm 80T | 8 pulleys |
| new belt lengths | none |  |
| mass | 1296 g | -8 g; 18 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 19 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.000 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-001-r01 : 0/33 min, trot 0 mm/s, cost 0.54, fitness -0.952

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3250_c002 | new |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.24 | 0.32 | 1.15 | 1.11 | 0.32 | joint speed | 8 (joint speed) |
| fl.shoulder | 0.70 | 2.72 | - | 1.25 | 1.21 | sustained servo torque | 14 (sustained servo torque) |
| fr.carpus | 1.27 | 0.36 | 1.12 | 1.11 | 0.32 | joint speed | 2 (joint speed) |
| fr.shoulder | 0.73 | 2.72 | - | 1.25 | 1.16 | sustained servo torque | 1 (sustained servo torque) |
| hl.hip_abd | 0.14 | 1.70 | - | 0.36 | 0.36 | sustained servo torque | 0 |
| hl.hock | 1.17 | 0.44 | 1.16 | 1.13 | 0.32 | joint speed | 0 |
| hl.stifle | 0.96 | 2.12 | 3.88 | 1.25 | 0.71 | sustained belt tension | 8 (sustained belt tension) |
| hr.hip_abd | 0.17 | 1.84 | - | 0.36 | 0.36 | sustained servo torque | 0 |
| hr.hock | 1.17 | 0.44 | 1.16 | 1.22 | 0.28 | torque-speed envelope | 0 |
| hr.stifle | 1.05 | 2.22 | 4.00 | 1.25 | 0.73 | sustained belt tension | 23 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -1.08 | belt_sustained |
| turn | no | -0.72 | belt_sustained |
| lie_rise | no | -1.72 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.15 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | belt_sustained |
| R6c-lively | 0/3 | -2.56 | belt_sustained |
| R6c-walking | 0/3 | -2.16 | belt_sustained |
| R6c-trotting | 0/3 | -0.24 | servo_sustained |
| R7-calm | 0/3 | -3.00 | belt_sustained |
| R7-ambling | 0/3 | -1.60 | belt_sustained |
| R7-lively | 0/3 | -2.48 | belt_sustained |
| R7-walking | 0/3 | -2.88 | belt_sustained, servo_sustained |
| R7-trot-walk | 0/3 | -2.28 | belt_sustained |
| R7-trot-shift | 0/3 | -1.12 | servo_sustained |
| R7-trotting | 0/3 | -0.28 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 2 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1346 g | +42 g; 14 masses not entered (0 g) |
| servo current (known servos) | 1.68 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.542 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-002-r02 : 0/33 min, trot 0 mm/s, cost 1.04, fitness -1.096

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3250_c002 | new |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 40T-80T | GT2-2mm-400-C | 2.00 | 139.4 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.05 | 0.48 | 3.76 | 1.01 | 0.22 | sustained belt tension | 10 (sustained belt tension) |
| fl.shoulder | 0.70 | 4.00 | - | 0.98 | 0.98 | sustained servo torque | 7 (sustained servo torque) |
| fr.carpus | 1.05 | 0.48 | 3.76 | 1.01 | 0.22 | sustained belt tension | 0 |
| fr.shoulder | 0.75 | 4.00 | - | 0.99 | 0.99 | sustained servo torque | 25 (sustained servo torque) |
| hl.hip_abd | 0.25 | 4.00 | - | 0.69 | 0.68 | sustained servo torque | 4 (sustained servo torque) |
| hl.hock | 1.17 | 0.48 | 0.48 | 1.09 | 0.39 | joint speed | 4 (joint speed) |
| hl.stifle | 1.13 | 2.04 | 2.68 | 1.03 | 0.48 | sustained belt tension | 1 (sustained belt tension) |
| hr.hip_abd | 0.30 | 2.22 | - | 0.68 | 0.68 | sustained servo torque | 3 (sustained servo torque) |
| hr.hock | 1.17 | 0.48 | 0.48 | 1.10 | 0.39 | joint speed | 0 |
| hr.stifle | 1.13 | 2.04 | 3.08 | 0.94 | 0.42 | sustained belt tension | 2 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -1.40 | belt_sustained |
| turn | no | -1.44 | belt_sustained |
| lie_rise | no | -2.76 | belt_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.15 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | servo_sustained |
| R6c-lively | 0/3 | -3.00 | servo_sustained |
| R6c-walking | 0/3 | -3.00 | servo_sustained |
| R6c-trotting | 0/3 | -1.60 | servo_sustained |
| R7-calm | 0/3 | -3.00 | servo_sustained |
| R7-ambling | 0/3 | -2.96 | servo_sustained |
| R7-lively | 0/3 | -3.00 | servo_sustained |
| R7-walking | 0/3 | -3.00 | servo_sustained |
| R7-trot-walk | 0/3 | -3.00 | servo_sustained |
| R7-trot-shift | 0/3 | -1.04 | servo_sustained |
| R7-trotting | 0/3 | -0.84 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 2 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 8 pulleys |
| new belt lengths | none |  |
| mass | 1341 g | +37 g; 16 masses not entered (0 g) |
| servo current (known servos) | 1.56 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.037 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-003-r07 : 0/33 min, trot 0 mm/s, cost 0.50, fitness -1.050

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.19 | 1.56 | 1.84 | 1.11 | 0.38 | sustained belt tension | 0 |
| fl.shoulder | 0.95 | 4.00 | - | 1.15 | 0.92 | sustained servo torque | 0 |
| fr.carpus | 1.23 | 1.56 | 1.84 | 1.12 | 0.38 | sustained belt tension | 0 |
| fr.shoulder | 0.95 | 4.00 | - | 1.15 | 0.96 | sustained servo torque | 0 |
| hl.hip_abd | 0.23 | 1.44 | - | 0.53 | 0.53 | sustained servo torque | 0 |
| hl.hock | 1.23 | 2.88 | 3.48 | 1.25 | 0.33 | sustained belt tension | 0 |
| hl.stifle | 1.15 | 4.00 | 4.00 | 1.14 | 0.77 | sustained servo torque | 19 (sustained servo torque) |
| hr.hip_abd | 0.28 | 1.12 | - | 0.48 | 0.45 | sustained servo torque | 0 |
| hr.hock | 1.24 | 2.88 | 3.48 | 1.25 | 0.33 | sustained belt tension | 0 |
| hr.stifle | 1.15 | 4.00 | 4.00 | 1.10 | 0.72 | sustained servo torque | 4 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -3.00 | servo_sustained |
| turn | no | -3.00 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -2.84 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1302 g | -2 g; 16 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.500 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-004-r01 : 0/33 min, trot 0 mm/s, cost 0.01, fitness -0.831

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.20 | 2.92 | 4.00 | 1.25 | 0.60 | sustained belt tension | 7 (joint speed) |
| fl.shoulder | 0.72 | 4.00 | - | 1.25 | 1.25 | sustained servo torque | 11 (sustained servo torque) |
| fr.carpus | 1.19 | 4.00 | 4.00 | 1.25 | 0.58 | sustained servo torque | 9 (sustained belt tension) |
| fr.shoulder | 0.71 | 4.00 | - | 1.21 | 1.21 | sustained servo torque | 21 (sustained servo torque) |
| hl.hip_abd | 0.46 | 3.80 | - | 1.21 | 1.16 | sustained servo torque | 1 (sustained servo torque) |
| hl.hock | 1.17 | 0.80 | 1.96 | 1.13 | 0.45 | sustained belt tension | 0 |
| hl.stifle | 1.11 | 2.00 | 4.00 | 1.04 | 0.53 | sustained belt tension | 1 (sustained belt tension) |
| hr.hip_abd | 0.44 | 4.00 | - | 1.23 | 1.18 | sustained servo torque | 6 (sustained servo torque) |
| hr.hock | 1.17 | 0.76 | 1.96 | 1.11 | 0.45 | sustained belt tension | 0 |
| hr.stifle | 1.11 | 2.00 | 4.00 | 1.02 | 0.52 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -0.20 | servo_sustained |
| turn | no | -0.44 | servo_sustained |
| lie_rise | no | -3.00 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.18 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | servo_sustained |
| R6c-lively | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R6c-walking | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R6c-trotting | 0/3 | -3.00 | servo_sustained |
| R7-calm | 0/3 | -3.00 | servo_sustained |
| R7-ambling | 0/3 | -2.20 | belt_sustained |
| R7-lively | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R7-walking | 0/3 | -3.00 | servo_sustained |
| R7-trot-walk | 0/3 | -3.00 | servo_sustained |
| R7-trot-shift | 0/3 | -3.00 | servo_sustained |
| R7-trotting | 0/3 | -3.00 | servo_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | none |  |
| mass | 1311 g | +7 g; 14 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.007 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-005-r21 : 0/33 min, trot 0 mm/s, cost 0.50, fitness -1.050

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3215_c018 |  |
| shoulder | sts3215_c018 |  |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-444-C | 2.00 | 176.7 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 40T-80T | GT2-2mm-640-C | 2.00 | 259.7 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.20 | 0.44 | 0.60 | 1.18 | 0.32 | joint speed | 0 |
| fl.shoulder | 0.74 | 2.20 | - | 1.20 | 1.06 | sustained servo torque | 1 (sustained servo torque) |
| fr.carpus | 1.20 | 0.56 | 0.88 | 1.12 | 0.32 | joint speed | 0 |
| fr.shoulder | 0.72 | 2.20 | - | 1.15 | 1.05 | sustained servo torque | 0 |
| hl.hip_abd | 0.27 | 1.72 | - | 0.55 | 0.54 | sustained servo torque | 0 |
| hl.hock | 1.16 | 1.66 | 3.28 | 1.25 | 0.36 | sustained belt tension | 15 (sustained belt tension) |
| hl.stifle | 1.09 | 1.36 | 1.96 | 1.25 | 0.61 | sustained belt tension | 0 |
| hr.hip_abd | 0.40 | 1.64 | - | 0.71 | 0.64 | sustained servo torque | 0 |
| hr.hock | 1.07 | 1.48 | 3.32 | 1.25 | 0.38 | sustained belt tension | 7 (sustained belt tension) |
| hr.stifle | 1.06 | 1.40 | 1.96 | 1.25 | 0.61 | sustained belt tension | 0 |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -2.32 | belt_sustained |
| turn | no | -2.05 | belt_sustained |
| lie_rise | no | -1.20 | servo_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | screened out | -0.84 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s (not played: screened out)

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | none | budget 4 sts3250_c002 |
| new pulley sizes | 2 mm 40T, 2 mm 80T | 4 pulleys |
| new belt lengths | none |  |
| mass | 1304 g | -0 g; 16 masses not entered (0 g) |
| servo current (known servos) | unknown A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 17 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 0.500 | the costs weighted (preset cost_weights) |

### 20261106-045624-evolve-59fd-g002-006 : 0/33 min, trot 0 mm/s, cost 1.08, fitness -1.065

Servos per pair

| pair | servo |  |
|---|---|---|
| hip_abd | sts3215_c018 |  |
| stifle | sts3215_c018 |  |
| hock | sts3250_c002 | new |
| shoulder | sts3250_c002 | new |
| carpus | sts3215_c018 |  |

Belt drives (catalog ids; C derived)

| drive | pulleys | belt | ratio | C mm | system |
|---|---|---|---|---|---|
| stifle | 30T-60T | GT2-2mm-540-C | 2.00 | 224.8 | GT2-2mm-10mm-generic |
| hock | 30T-60T | GT2-2mm-400-C | 2.00 | 154.7 | GT2-2mm-10mm-generic |
| carpus | 30T-60T | GT2-2mm-640-C | 2.00 | 274.8 | GT2-2mm-10mm-generic |

Binding limit per joint (use = value / limit at margin; > 1 = over)

| joint | speed | torque | belt | envelope | stall | binds | stopped plays |
|---|---|---|---|---|---|---|---|
| fl.carpus | 1.20 | 1.84 | 3.16 | 1.25 | 0.48 | sustained belt tension | 4 (sustained belt tension) |
| fl.shoulder | 0.47 | 1.80 | - | 0.67 | 0.66 | sustained servo torque | 0 |
| fr.carpus | 1.22 | 1.76 | 2.80 | 1.25 | 0.53 | sustained belt tension | 15 (sustained belt tension) |
| fr.shoulder | 0.47 | 1.88 | - | 0.77 | 0.70 | sustained servo torque | 0 |
| hl.hip_abd | 0.48 | 2.48 | - | 0.81 | 0.74 | sustained servo torque | 2 (sustained servo torque) |
| hl.hock | 1.05 | 0.24 | 1.72 | 0.75 | 0.31 | sustained belt tension | 6 (sustained belt tension) |
| hl.stifle | 1.04 | 2.12 | 4.00 | 1.25 | 0.64 | sustained belt tension | 6 (sustained belt tension) |
| hr.hip_abd | 0.48 | 2.68 | - | 0.77 | 0.72 | sustained servo torque | 2 (sustained servo torque) |
| hr.hock | 1.06 | 0.32 | 1.72 | 0.77 | 0.32 | sustained belt tension | 0 |
| hr.stifle | 1.04 | 4.00 | 4.00 | 1.25 | 0.69 | sustained servo torque | 21 (sustained belt tension) |

Screen (every seed)

| play | held | worst margin | closest limit |
|---|---|---|---|
| walk | no | -2.12 | belt_sustained |
| turn | no | -1.32 | belt_sustained |
| lie_rise | no | -0.72 | belt_sustained |
| fastest trot within | none | 0 mm/s | 0 trot settings hold |
| screen | passed | -0.18 | best play's worst-seed margin against -0.25 |

Behaviours, 60 s

| behaviour | seeds held | worst margin | closest limit |
|---|---|---|---|
| R6c-calm | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R6c-lively | 0/3 | -3.00 | belt_sustained |
| R6c-walking | 0/3 | -2.68 | belt_sustained |
| R6c-trotting | 0/3 | -0.84 | belt_sustained, servo_sustained |
| R7-calm | 0/3 | -3.00 | belt_sustained, servo_sustained |
| R7-ambling | 0/3 | -2.24 | belt_sustained |
| R7-lively | 0/3 | -3.00 | belt_sustained |
| R7-walking | 0/3 | -3.00 | belt_sustained |
| R7-trot-walk | 0/3 | -2.64 | belt_sustained |
| R7-trot-shift | 0/3 | -1.56 | belt_sustained |
| R7-trotting | 0/3 | -1.04 | belt_sustained |

Hardware costs (catalogs and library only)

|  |  |  |
|---|---|---|
| new servos | 4 x sts3250_c002 | budget 4 sts3250_c002 |
| new pulley sizes | none | 0 pulleys |
| new belt lengths | GT2-2mm-540-C |  |
| mass | 1380 g | +76 g; 14 masses not entered (0 g) |
| servo current (known servos) | 3.40 A peak | servos without a stall current are not counted |
| not in a catalog | none |  |
| new servo cost | 0.00 USD |  |
| unknown | 15 values | sts3215_c018 stall current (its current is not counted); mass of Hip block (0 g); mass of Chest block (0 g); mass of Neck rods (0 g); mass of Electronics (0 g); mass of Skin (0 g) |
| cost index | 1.076 | the costs weighted (preset cost_weights) |
