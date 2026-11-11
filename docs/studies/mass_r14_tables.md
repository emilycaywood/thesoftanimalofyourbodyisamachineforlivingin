| body | as simulated g | servos | servo horns | pulley axles | leg tubes | batteries | headroom (PROVISIONAL) | head + neck | rails | pulleys | other | explicit_v1 total g | of it real parts | CoM x/z mm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| working | 1304 | 550 | 0 -> 140 | 0 -> 144 | 248 -> 366 | 270 | 0 -> 300 | 150 | 86 | 0 | 0 | **2005** | 1705 | 16/536 -> 13/522 |
| g007-002 | 1383 | 628 | 0 -> 140 | 0 -> 144 | 250 -> 368 | 270 | 0 -> 300 | 150 | 86 | 0 | 0 | **2085** | 1785 | 18/532 -> 16/520 |
| g009-000 | 1380 | 628 | 0 -> 140 | 0 -> 144 | 246 -> 362 | 270 | 0 -> 300 | 150 | 86 | 0 | 0 | **2080** | 1780 | 18/521 -> 15/510 |
| g012-009 | 1421 | 667 | 0 -> 140 | 0 -> 144 | 248 -> 365 | 270 | 0 -> 300 | 150 | 86 | 0 | 0 | **2122** | 1822 | 28/526 -> 24/514 |
| g020-008-r01 | 1419 | 667 | 0 -> 140 | 0 -> 144 | 247 -> 363 | 270 | 0 -> 300 | 150 | 86 | 0 | 0 | **2120** | 1820 | 28/521 -> 24/510 |

| body | behaviours held 3/3 | minutes | trot mm/s (fastest held) | trots held | walk | turn | lie_rise 10 s screen | lie_rise evolved (R13) | lie_rise evolved, lying pose | stoppers |
|---|---|---|---|---|---|---|---|---|---|---|
| working | 11 -> **1** of 12 | 35/36 -> **11/36** | 0 -> **0** (-) | 0 -> **0** | -0.13 -> **-0.84** | -0.25 -> **-1.16** | -3.00 -> **-3.00** | -1.20 -> **-3.00** | -1.20 -> **-3.00** | hr.hip_abd torque (15); fl.shoulder torque (11); fr.shoulder torque (7) |
| g007-002 | 23 -> **4** of 25 | 72/75 -> **25/75** | 0 -> **0** (-) | 0 -> **0** | -0.32 -> **-0.60** | -0.25 -> **-0.48** | -1.44 -> **-3.00** | -0.25 -> **-2.80** | -0.25 -> **-2.80** | hr.hip_abd torque (15); fl.carpus belt (14); fr.carpus speed (11) |
| g009-000 | 16 -> **0** of 17 | 50/51 -> **9/51** | 394 -> **394** (trot 0.5/2) | 7 -> **4** | -0.12 -> **-0.88** | -0.08 -> **-1.08** | -3.00 -> **-3.00** | -1.36 -> **-3.00** | -1.36 -> **-3.00** | fl.shoulder torque (18); fr.shoulder torque (18); fl.carpus belt (8) |
| g012-009 | 14 -> **0** of 16 | 44/48 -> **11/48** | 414 -> **414** (trot 0.5/2) | 16 -> **8** | -0.48 -> **-0.72** | -0.08 -> **-0.96** | -0.24 -> **-2.29** | -0.96 -> **-3.00** | -0.44 -> **-3.00** | hr.stifle torque (11); fl.carpus torque (10); hl.hip_abd torque (8) |
| g020-008-r01 | 8 -> **0** of 11 | 29/33 -> **0/33** | 530 -> **543** (trot 0.4/2) | 16 -> **12** | -0.52 -> **-0.72** | -0.08 -> **-0.84** | -0.16 -> **-2.04** | -1.40 -> **-3.00** | -0.84 -> **-3.00** | fr.carpus torque (18); hr.hip_abd torque (12); fr.shoulder torque (4) |

#### working

| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |
|---|---|---|---|
| g000-000 q2.1 | 3/3 +0.16 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g000-001 q7.2 | 3/3 +0.02 | **0/3 -2.64** | servo_sustained, servo_sustained, servo_sustained |
| g000-008 q6.7 | 2/3 -2.52 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g000-003 q10.0 | 3/3 +0.02 | **0/3 -0.76** | servo_sustained, servo_sustained, servo_sustained |
| g000-005 q8.1 | 3/3 +0.13 | **0/3 -1.00** | servo_sustained, servo_sustained, servo_sustained |
| g000-007 q8.4 | 3/3 +0.00 | **2/3 -2.32** | joint_speed, servo_sustained, joint_speed |
| g000-009 q3.7 | 3/3 +0.03 | **2/3 -2.32** | servo_sustained, joint_speed, joint_speed |
| g006-004 q2.7 | 3/3 +0.03 | **2/3 -0.08** | joint_speed, belt_sustained, joint_speed |
| g004-021 q7.3 | 3/3 +0.10 | **0/3 -1.12** | servo_sustained, servo_sustained, servo_sustained |
| g001-012 q1.8 | 3/3 +0.35 | **3/3 +0.34** | joint_speed, joint_speed, joint_speed |
| g008-010 q4.1 | 3/3 +0.03 | **0/3 -0.56** | servo_sustained, servo_sustained, servo_sustained |
| g014-010 q4.8 | 3/3 +0.03 | **2/3 -0.12** | joint_speed, servo_sustained, joint_speed |

lie_rise evolved: seed 0 -2.32  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -2.64  closest servo_sustained

lie_rise evolved, lying pose: seed 0 -2.32  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -2.64  closest servo_sustained

#### g007-002

| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |
|---|---|---|---|
| g000-000 q2.0 | 3/3 +0.18 | **0/3 -1.08** | belt_sustained, belt_sustained, belt_sustained |
| g002-023 q7.1 | 2/3 -0.32 | **0/3 -0.28** | belt_sustained, belt_sustained, belt_sustained |
| g000-008 q6.7 | 3/3 +0.03 | **0/3 -0.52** | belt_sustained, servo_sustained, servo_sustained |
| g000-003 q9.9 | 3/3 +0.01 | **0/3 -0.72** | servo_sustained, servo_sustained, servo_sustained |
| g000-005 q8.0 | 3/3 +0.13 | **0/3 -0.72** | servo_sustained, servo_sustained, servo_sustained |
| g000-007 q8.3 | 3/3 +0.00 | **2/3 -0.48** | joint_speed, belt_sustained, joint_speed |
| g000-009 q3.7 | 3/3 +0.04 | **3/3 +0.03** | joint_speed, joint_speed, joint_speed |
| g011-002 q4.6 | 3/3 +0.03 | **0/3 -1.48** | servo_sustained, belt_sustained, servo_sustained |
| g013-002 q3.3 | 3/3 +0.03 | **1/3 -0.44** | joint_speed, servo_sustained, servo_sustained |
| g002-025 q8.3 | 3/3 +0.03 | **2/3 -1.04** | joint_speed, belt_sustained, joint_speed |
| g000-027 q7.8 | 3/3 +0.00 | **0/3 -0.88** | servo_sustained, servo_sustained, servo_sustained |
| g004-008 q4.2 | 3/3 +0.02 | **0/3 -0.68** | servo_sustained, servo_sustained, servo_sustained |
| g006-024 q7.3 | 3/3 +0.25 | **3/3 +0.16** | joint_speed, servo_sustained, servo_sustained |
| g009-007 q5.3 | 3/3 +0.02 | **2/3 -0.52** | joint_speed, joint_speed, belt_sustained |
| g008-000 q6.7 | 3/3 +0.03 | **1/3 -0.80** | servo_sustained, belt_sustained, joint_speed |
| g002-007 q5.4 | 3/3 +0.00 | **1/3 -1.00** | servo_sustained, servo_sustained, servo_sustained |
| g006-010 q1.5 | 3/3 +0.71 | **2/3 -0.56** | joint_speed, joint_speed, servo_sustained |
| g006-026 q3.3 | 3/3 +0.03 | **0/3 -0.72** | servo_sustained, servo_sustained, servo_sustained |
| g002-010 q0.6 | 3/3 +0.87 | **3/3 +0.87** | belt_breaking, belt_breaking, belt_breaking |
| g012-024 q4.7 | 3/3 +0.02 | **1/3 -0.88** | envelope, belt_sustained, servo_sustained |
| g013-003 q2.7 | 3/3 +0.03 | **0/3 -0.96** | servo_sustained, servo_sustained, servo_sustained |
| g005-021 q3.6 | 3/3 +0.03 | **0/3 -1.12** | belt_sustained, servo_sustained, belt_sustained |
| g012-026 q7.0 | 3/3 +0.18 | **3/3 +0.16** | joint_speed, servo_sustained, joint_speed |
| g003-021 q4.6 | 3/3 +0.06 | **0/3 -0.68** | servo_sustained, servo_sustained, servo_sustained |
| g005-003 q0.4 | 1/3 -0.04 | **1/3 -0.07** | joint_speed, joint_speed, belt_breaking |

lie_rise evolved: seed 0 -2.80  closest servo_sustained; seed 1 -2.80  closest servo_sustained; seed 2 -2.56  closest servo_sustained

lie_rise evolved, lying pose: seed 0 -2.80  closest servo_sustained; seed 1 -2.80  closest servo_sustained; seed 2 -2.56  closest servo_sustained

#### g009-000

| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |
|---|---|---|---|
| g000-000 q2.1 | 3/3 +0.26 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g002-023 q7.0 | 3/3 +0.45 | **0/3 -1.52** | servo_sustained, servo_sustained, servo_sustained |
| g000-003 q9.9 | 3/3 +0.08 | **0/3 -0.56** | servo_sustained, servo_sustained, servo_sustained |
| g000-010 q6.3 | 3/3 +0.35 | **0/3 -2.96** | servo_sustained, servo_sustained, servo_sustained |
| g012-001 q7.9 | 3/3 +0.32 | **0/3 -2.28** | servo_sustained, servo_sustained, servo_sustained |
| g000-007 q8.1 | 3/3 +0.28 | **2/3 -1.76** | joint_speed, servo_sustained, joint_speed |
| g002-012 q4.3 | 3/3 +0.35 | **0/3 -2.52** | servo_sustained, servo_sustained, servo_sustained |
| g014-010 q5.6 | 3/3 +0.48 | **2/3 -1.96** | joint_speed, servo_sustained, joint_speed |
| g005-024 q4.7 | 3/3 +0.35 | **0/3 -2.60** | servo_sustained, servo_sustained, servo_sustained |
| g014-020 q4.6 | 3/3 +0.36 | **0/3 -2.76** | servo_sustained, servo_sustained, servo_sustained |
| g006-008 q5.2 | 3/3 +0.44 | **0/3 -2.04** | servo_sustained, servo_sustained, servo_sustained |
| g012-022 q4.1 | 3/3 +0.36 | **1/3 -1.32** | servo_sustained, servo_sustained, servo_sustained |
| g007-022 q6.7 | 3/3 +0.34 | **0/3 -1.16** | servo_sustained, belt_sustained, belt_sustained |
| g009-024 q3.2 | 3/3 +0.34 | **2/3 -1.12** | envelope, servo_sustained, joint_speed |
| g007-013 q9.8 | 2/3 -2.04 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g008-010 q5.6 | 3/3 +0.16 | **0/3 -0.60** | servo_sustained, servo_sustained, servo_sustained |
| g010-004 q1.4 | 3/3 +0.43 | **2/3 -0.12** | servo_sustained, belt_sustained, belt_sustained |

lie_rise evolved: seed 0 -3.00  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -3.00  closest servo_sustained

lie_rise evolved, lying pose: seed 0 -3.00  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -3.00  closest servo_sustained

#### g012-009

| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |
|---|---|---|---|
| g000-000 q2.0 | 3/3 +0.33 | **0/3 -2.40** | servo_sustained, belt_sustained, servo_sustained |
| g000-001 q6.9 | 3/3 +0.61 | **0/3 -0.88** | servo_sustained, servo_sustained, servo_sustained |
| g000-010 q6.3 | 3/3 +0.52 | **0/3 -0.76** | servo_sustained, servo_sustained, servo_sustained |
| g000-003 q9.7 | 3/3 +0.44 | **0/3 -0.84** | servo_sustained, servo_sustained, servo_sustained |
| g000-005 q7.9 | 3/3 +0.44 | **0/3 -0.88** | servo_sustained, servo_sustained, servo_sustained |
| g000-007 q8.1 | 3/3 +0.54 | **2/3 -1.04** | envelope, servo_sustained, envelope |
| g000-009 q3.6 | 3/3 +0.52 | **2/3 -0.04** | servo_sustained, belt_sustained, servo_sustained |
| g013-002 q2.9 | 3/3 +0.54 | **1/3 -0.60** | belt_sustained, servo_sustained, servo_sustained |
| g001-019 q5.4 | 3/3 +0.40 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g000-019 q3.9 | 3/3 +0.36 | **2/3 -0.64** | servo_sustained, belt_sustained, servo_sustained |
| g007-023 q3.2 | 3/3 +0.36 | **2/3 -0.28** | stall, belt_breaking, servo_sustained |
| g012-015 q6.9 | 3/3 +0.16 | **0/3 -3.00** | belt_sustained, servo_sustained, servo_sustained |
| g013-003 q3.6 | 3/3 +0.49 | **2/3 -0.44** | servo_sustained, servo_sustained, belt_sustained |
| g013-012 q6.8 | 1/3 -2.64 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g003-026 q4.7 | 3/3 +0.40 | **0/3 -1.32** | servo_sustained, servo_sustained, servo_sustained |
| g007-025 q6.0 | 1/3 -2.64 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |

lie_rise evolved: seed 0 -2.80  closest belt_sustained; seed 1 -3.00  closest belt_sustained; seed 2 -1.60  closest servo_sustained

lie_rise evolved, lying pose: seed 0 -3.00  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -3.00  closest servo_sustained

#### g020-008-r01

| behaviour | as simulated: held, worst margin | explicit_v1: held, worst margin | closest per seed |
|---|---|---|---|
| g014-011 q6.1 | 3/3 +0.24 | **0/3 -2.28** | servo_sustained, servo_sustained, servo_sustained |
| g000-008 q6.5 | 2/3 -0.28 | **0/3 -1.68** | servo_sustained, servo_sustained, servo_sustained |
| g000-003 q9.7 | 3/3 +0.04 | **0/3 -0.92** | servo_sustained, servo_sustained, servo_sustained |
| g000-005 q7.9 | 3/3 +0.48 | **0/3 -1.04** | servo_sustained, servo_sustained, servo_sustained |
| g000-007 q8.1 | 3/3 +0.00 | **0/3 -2.24** | servo_sustained, servo_sustained, servo_sustained |
| g001-019 q5.5 | 3/3 +0.41 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g000-019 q3.9 | 3/3 +0.32 | **0/3 -1.12** | servo_sustained, belt_sustained, servo_sustained |
| g004-027 q1.8 | 1/3 -0.08 | **0/3 -1.68** | servo_sustained, servo_sustained, servo_sustained |
| g009-024 q7.6 | 3/3 +0.32 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g014-008 q7.3 | 2/3 -0.08 | **0/3 -3.00** | servo_sustained, servo_sustained, servo_sustained |
| g012-001 q4.6 | 3/3 +0.52 | **0/3 -2.40** | servo_sustained, servo_sustained, servo_sustained |

lie_rise evolved: seed 0 -3.00  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -3.00  closest belt_sustained

lie_rise evolved, lying pose: seed 0 -3.00  closest servo_sustained; seed 1 -3.00  closest servo_sustained; seed 2 -3.00  closest servo_sustained
