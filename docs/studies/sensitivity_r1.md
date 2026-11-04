# Session R, step 1: what the failures rest on (2026-11-04)

One value varied at a time on `projects/robot-calf-final` as it is (copy `projects/_scratch-r`), in memory only:
no file, gene or component value was changed. Each motion played once in physics exactly as the interpretation
plays a candidate (`calflab.behave.interpret.play_primitive` + `judge`: torque-speed servos, derating 1, seed 0,
nothing random) and judged at margin 0.2. Margins are relative: 0 = exactly at the limit x 0.8, negative = over
it, -3.0 is the floor of the "share of a window" checks. Script: `docs/studies/sensitivity_r1.py` (ADR-086).

* walk, trot: the primitives' defaults (the gaits as they are);
* interpreted trot (fast play) and step: the parameters of run `20261104-042426-interpret-ef3c`.

Variants (ADR-086 says why each is done this way):

* **mass xF**: every geom's mass (and a pushed solid's inertia) x F, 1304 g as entered;
* **armature xF**: `armature_scale`;
* **spring rates xF**: every spring's `k_n_per_mm` x F, free lengths and anchors unchanged;
* **rated torque xF**: the STS3215 C018's `rated_torque_nm` (0.98 N*m) x F, nothing else;
* **servo at V**: stall torque, rated torque and no-load speed x V / 12 V (linear in voltage: an assumption, not
  a datasheet curve). 11.1 V = a 3S pack's nominal, 12.6 V full, 10.5 V = 3.5 V per cell.

## Margins per constraint


### walk (as is)

| variant | worst margin | fell | torque sust | belt sust | speed | envelope | stall | belt peak | at limit |
|---|---|---|---|---|---|---|---|---|---|
| baseline | -2.48 | no | **-2.48** | **-0.07** | **-0.12** | **-0.25** | +0.48 | +0.54 | +1.00 |
| mass x0.9 | -2.4 | no | **-2.40** | +0.12 | **-0.14** | **-0.25** | +0.49 | +0.55 | +1.00 |
| mass x1.1 | -2.44 | no | **-2.44** | **-0.08** | **-0.11** | **-0.25** | +0.47 | +0.53 | +1.00 |
| mass x1.2 | -2.48 | no | **-2.48** | **-0.16** | **-0.11** | **-0.25** | +0.47 | +0.53 | +1.00 |
| mass x1.3 | -2.52 | no | **-2.52** | **-0.16** | **-0.11** | **-0.25** | +0.45 | +0.53 | +1.00 |
| armature x0.2 | -2.56 | no | **-2.56** | +0.21 | **-0.13** | **-0.25** | +0.49 | +0.54 | +1.00 |
| armature x0.5 | -2.52 | no | **-2.52** | +0.00 | **-0.13** | **-0.25** | +0.48 | +0.53 | +1.00 |
| armature x1.5 | -1.76 | no | **-1.76** | **-0.07** | **-0.16** | **-0.25** | +0.48 | +0.60 | +1.00 |
| armature x2.0 | -1.72 | no | **-1.72** | **-0.04** | **-0.19** | **-0.25** | +0.47 | +0.56 | +1.00 |
| spring rates x0.0 | -2.36 | no | **-2.36** | **-1.00** | **-0.13** | **-0.25** | +0.58 | +0.62 | +1.00 |
| spring rates x0.5 | -2.48 | no | **-2.48** | +0.28 | **-0.13** | **-0.25** | +0.53 | +0.62 | +1.00 |
| spring rates x1.5 | -2.604 | no | **-2.44** | **-2.60** | **-0.12** | **-0.25** | +0.43 | +0.46 | +1.00 |
| spring rates x2.0 | -3.0 | no | **-2.44** | **-3.00** | **-0.12** | **-0.25** | +0.39 | +0.38 | +1.00 |
| spring rates x3.0 | -3.0 | no | **-3.00** | **-3.00** | **-0.11** | **-0.25** | +0.30 | +0.22 | +1.00 |
| rated torque x0.8 | -2.8 | no | **-2.80** | **-0.07** | **-0.12** | **-0.25** | +0.48 | +0.54 | +1.00 |
| rated torque x0.9 | -2.6 | no | **-2.60** | **-0.07** | **-0.12** | **-0.25** | +0.48 | +0.54 | +1.00 |
| rated torque x1.1 | -2.36 | no | **-2.36** | **-0.07** | **-0.12** | **-0.25** | +0.48 | +0.54 | +1.00 |
| rated torque x1.2 | -2.24 | no | **-2.24** | **-0.07** | **-0.12** | **-0.25** | +0.48 | +0.54 | +1.00 |
| servo at 10.5 V (stall, rated, speed x V/12) | -2.08 | no | **-2.08** | +0.20 | **-0.12** | **-0.25** | +0.46 | +0.64 | +1.00 |
| servo at 11.1 V (stall, rated, speed x V/12) | -2.44 | no | **-2.44** | +0.00 | **-0.12** | **-0.25** | +0.48 | +0.56 | +1.00 |
| servo at 12.6 V (stall, rated, speed x V/12) | -2.44 | no | **-2.44** | **-0.08** | **-0.13** | **-0.25** | +0.48 | +0.52 | +1.00 |

### trot (as is)

| variant | worst margin | fell | torque sust | belt sust | speed | envelope | stall | belt peak | at limit |
|---|---|---|---|---|---|---|---|---|---|
| baseline | -1.2 | no | **-1.20** | **-0.96** | +0.03 | **-0.01** | +0.43 | +0.66 | +1.00 |
| mass x0.9 | -1.1386 | no | **-1.14** | **-0.28** | +0.00 | **-0.00** | +0.47 | +0.69 | +1.00 |
| mass x1.1 | -1.7327 | no | **-1.42** | **-1.73** | +0.02 | **-0.02** | +0.37 | +0.64 | +1.00 |
| mass x1.2 | -1.9703 | no | **-1.53** | **-1.97** | +0.02 | **-0.03** | +0.33 | +0.60 | +1.00 |
| mass x1.3 | -2.12 | no | **-1.65** | **-2.12** | +0.02 | **-0.04** | +0.31 | +0.56 | +1.00 |
| armature x0.2 | -1.24 | no | **-1.24** | **-0.60** | +0.16 | +0.11 | +0.42 | +0.65 | +1.00 |
| armature x0.5 | -1.2 | no | **-1.20** | **-0.68** | +0.05 | +0.04 | +0.41 | +0.65 | +1.00 |
| armature x1.5 | -1.297 | no | **-1.30** | **-1.10** | **-0.07** | **-0.11** | +0.42 | +0.67 | +1.00 |
| armature x2.0 | -1.4 | no | **-1.30** | **-1.40** | **-0.09** | **-0.21** | +0.44 | +0.62 | +1.00 |
| spring rates x0.0 | -1.32 | no | **-1.32** | **-0.98** | +0.03 | +0.02 | +0.32 | +0.50 | +1.00 |
| spring rates x0.5 | -1.28 | no | **-1.28** | **-0.56** | +0.01 | **-0.00** | +0.36 | +0.58 | +1.00 |
| spring rates x1.5 | -1.4 | no | **-1.24** | **-1.40** | +0.01 | **-0.04** | +0.47 | +0.65 | +1.00 |
| spring rates x2.0 | -1.44 | no | **-1.30** | **-1.44** | **-0.02** | **-0.07** | +0.51 | +0.57 | +1.00 |
| spring rates x3.0 | -2.4 | no | **-2.04** | **-2.40** | +0.02 | **-0.09** | +0.53 | +0.40 | +1.00 |
| rated torque x0.8 | -1.495 | no | **-1.50** | **-0.96** | +0.03 | **-0.01** | +0.43 | +0.66 | +1.00 |
| rated torque x0.9 | -1.4158 | no | **-1.42** | **-0.96** | +0.03 | **-0.01** | +0.43 | +0.66 | +1.00 |
| rated torque x1.1 | -1.16 | no | **-1.16** | **-0.96** | +0.03 | **-0.01** | +0.43 | +0.66 | +1.00 |
| rated torque x1.2 | -1.099 | no | **-1.10** | **-0.96** | +0.03 | **-0.01** | +0.43 | +0.66 | +1.00 |
| servo at 10.5 V (stall, rated, speed x V/12) | -1.4158 | no | **-1.42** | **-1.40** | **-0.12** | **-0.20** | +0.37 | +0.69 | +1.00 |
| servo at 11.1 V (stall, rated, speed x V/12) | -1.3762 | no | **-1.38** | **-1.34** | **-0.07** | **-0.13** | +0.39 | +0.67 | +1.00 |
| servo at 12.6 V (stall, rated, speed x V/12) | -1.2 | no | **-1.20** | **-0.62** | +0.05 | +0.03 | +0.43 | +0.65 | +1.00 |

### interpreted trot (fast play)

| variant | worst margin | fell | torque sust | belt sust | speed | envelope | stall | belt peak | at limit |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 0.7101 | no | +1.00 | +1.00 | +0.76 | +0.71 | +0.81 | +0.83 | +1.00 |
| mass x0.9 | 0.7129 | no | +1.00 | +1.00 | +0.75 | +0.71 | +0.82 | +0.83 | +1.00 |
| mass x1.1 | 0.6 | no | +0.60 | +1.00 | +0.78 | +0.71 | +0.72 | +0.81 | +1.00 |
| mass x1.2 | 0.24 | no | +0.24 | +0.80 | +0.76 | +0.66 | +0.66 | +0.77 | +1.00 |
| mass x1.3 | 0.04 | no | +0.04 | +0.80 | +0.77 | +0.67 | +0.67 | +0.77 | +1.00 |
| armature x0.2 | 0.7507 | no | +1.00 | +1.00 | +0.80 | +0.75 | +0.82 | +0.83 | +1.00 |
| armature x0.5 | 0.7305 | no | +1.00 | +1.00 | +0.78 | +0.73 | +0.82 | +0.83 | +1.00 |
| armature x1.5 | 0.6976 | no | +1.00 | +1.00 | +0.74 | +0.70 | +0.80 | +0.83 | +1.00 |
| armature x2.0 | 0.6736 | no | +1.00 | +1.00 | +0.73 | +0.67 | +0.80 | +0.83 | +1.00 |
| spring rates x0.0 | 0.7557 | no | +1.00 | +1.00 | +0.76 | +0.76 | +0.82 | +0.83 | +1.00 |
| spring rates x0.5 | 0.7308 | no | +1.00 | +1.00 | +0.76 | +0.73 | +0.82 | +0.86 | +1.00 |
| spring rates x1.5 | -0.4653 | no | +0.36 | **-0.47** | +0.76 | +0.69 | +0.71 | +0.75 | +1.00 |
| spring rates x2.0 | -2.44 | no | **-0.52** | **-2.44** | +0.77 | +0.60 | +0.60 | +0.63 | +1.00 |
| spring rates x3.0 | -3.0 | no | **-3.00** | **-3.00** | +0.76 | +0.47 | +0.47 | +0.45 | +1.00 |
| rated torque x0.8 | -0.16 | no | **-0.16** | +1.00 | +0.76 | +0.71 | +0.81 | +0.83 | +1.00 |
| rated torque x0.9 | 0.64 | no | +0.64 | +1.00 | +0.76 | +0.71 | +0.81 | +0.83 | +1.00 |
| rated torque x1.1 | 0.7101 | no | +1.00 | +1.00 | +0.76 | +0.71 | +0.81 | +0.83 | +1.00 |
| rated torque x1.2 | 0.7101 | no | +1.00 | +1.00 | +0.76 | +0.71 | +0.81 | +0.83 | +1.00 |
| servo at 10.5 V (stall, rated, speed x V/12) | 0.2 | no | +0.20 | +0.84 | +0.72 | +0.66 | +0.66 | +0.78 | +1.00 |
| servo at 11.1 V (stall, rated, speed x V/12) | 0.56 | no | +0.56 | +1.00 | +0.73 | +0.68 | +0.72 | +0.82 | +1.00 |
| servo at 12.6 V (stall, rated, speed x V/12) | 0.7261 | no | +1.00 | +1.00 | +0.77 | +0.73 | +0.82 | +0.83 | +1.00 |

### interpreted step

| variant | worst margin | fell | torque sust | belt sust | speed | envelope | stall | belt peak | at limit |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 0.2751 | no | +0.40 | +0.76 | +0.28 | +0.33 | +0.78 | +0.74 | +1.00 |
| mass x0.9 | 0.2779 | no | +0.96 | +0.80 | +0.28 | +0.33 | +0.80 | +0.75 | +1.00 |
| mass x1.1 | -0.12 | no | **-0.12** | +0.68 | +0.27 | +0.33 | +0.76 | +0.73 | +1.00 |
| mass x1.2 | -0.36 | no | **-0.36** | +0.72 | +0.27 | +0.32 | +0.74 | +0.72 | +1.00 |
| mass x1.3 | -0.52 | no | **-0.52** | +0.60 | +0.27 | +0.32 | +0.73 | +0.71 | +1.00 |
| armature x0.2 | 0.4132 | no | +0.48 | +0.96 | +0.41 | +0.45 | +0.79 | +0.79 | +1.00 |
| armature x0.5 | 0.3582 | no | +0.44 | +0.80 | +0.36 | +0.51 | +0.79 | +0.78 | +1.00 |
| armature x1.5 | 0.214 | no | +0.40 | +0.72 | +0.21 | +0.22 | +0.78 | +0.71 | +1.00 |
| armature x2.0 | 0.1745 | no | +0.44 | +0.68 | +0.19 | +0.17 | +0.77 | +0.68 | +1.00 |
| spring rates x0.0 | 0.0 | no | +1.00 | +0.00 | +0.28 | +0.33 | +0.83 | +0.75 | +1.00 |
| spring rates x0.5 | 0.2752 | no | +1.00 | +1.00 | +0.28 | +0.35 | +0.81 | +0.81 | +1.00 |
| spring rates x1.5 | -1.48 | no | **-0.80** | **-1.48** | +0.28 | +0.27 | +0.75 | +0.65 | +1.00 |
| spring rates x2.0 | -3.0 | no | **-3.00** | **-3.00** | +0.28 | +0.26 | +0.70 | +0.57 | +1.00 |
| spring rates x3.0 | -3.0 | no | **-3.00** | **-3.00** | +0.28 | +0.23 | +0.58 | +0.40 | +1.00 |
| rated torque x0.8 | -0.76 | no | **-0.76** | +0.76 | +0.28 | +0.33 | +0.78 | +0.74 | +1.00 |
| rated torque x0.9 | -0.36 | no | **-0.36** | +0.76 | +0.28 | +0.33 | +0.78 | +0.74 | +1.00 |
| rated torque x1.1 | 0.2751 | no | +1.00 | +0.76 | +0.28 | +0.33 | +0.78 | +0.74 | +1.00 |
| rated torque x1.2 | 0.2751 | no | +1.00 | +0.76 | +0.28 | +0.33 | +0.78 | +0.74 | +1.00 |
| servo at 10.5 V (stall, rated, speed x V/12) | -0.44 | no | **-0.44** | +0.80 | +0.15 | +0.15 | +0.75 | +0.74 | +1.00 |
| servo at 11.1 V (stall, rated, speed x V/12) | -0.2 | no | **-0.20** | +0.76 | +0.20 | +0.21 | +0.76 | +0.74 | +1.00 |
| servo at 12.6 V (stall, rated, speed x V/12) | 0.3162 | no | +0.84 | +0.72 | +0.32 | +0.36 | +0.79 | +0.74 | +1.00 |


## Which joint, for the baselines and the deciding variants

Each block belongs to the summary line below it.

```
    servo_sustained  m=  -2.48  hr.hip_abd: above 48% of rated for 87% of a 2 s window
    stall            m= 0.4808  fl.shoulder: peak 41 % of stall
    belt_sustained   m=-0.0693  hr.stifle: above allowable for 27% of a window
    belt_breaking    m= 0.5361  hl.stifle: peak 9% of breaking strength
    joint_speed      m=-0.1249  fr.carpus: 122 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.2513  fl.carpus: 100% of its torque-speed envelope (0.60 N*m at 121 deg/s)
    fall             m=   None  stood
walk (as is)                   baseline                                     margin   -2.48 worst servo_sustained  fell False viol servo_sustained,belt_sustained,joint_speed,envelope
    servo_sustained  m=  -2.44  hr.hip_abd: above 48% of rated for 86% of a 2 s window
    stall            m= 0.4736  fr.shoulder: peak 42 % of stall
    belt_sustained   m=  -0.08  hl.stifle: above allowable for 27% of a window
    belt_breaking    m= 0.5324  hl.stifle: peak 9% of breaking strength
    joint_speed      m=-0.1076  fl.carpus: 120 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.2513  fl.carpus: 100% of its torque-speed envelope (0.80 N*m at 117 deg/s)
    fall             m=   None  stood
walk (as is)                   mass x1.1                                    margin   -2.44 worst servo_sustained  fell False viol servo_sustained,belt_sustained,joint_speed,envelope
    servo_sustained  m=  -2.44  hr.hip_abd: above 48% of rated for 86% of a 2 s window
    stall            m= 0.4822  fl.shoulder: peak 41 % of stall
    belt_sustained   m=    0.0  hl.stifle: above allowable for 25% of a window
    belt_breaking    m= 0.5642  hl.stifle: peak 9% of breaking strength
    joint_speed      m=-0.1184  fl.carpus: 112 deg/s against 125
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.2513  fl.carpus: 100% of its torque-speed envelope (0.67 N*m at 110 deg/s)
    fall             m=   None  stood
walk (as is)                   servo at 11.1 V                              margin   -2.44 worst servo_sustained  fell False viol servo_sustained,joint_speed,envelope
    servo_sustained  m=  -2.44  hr.hip_abd: above 48% of rated for 86% of a 2 s window
    stall            m= 0.4339  fl.shoulder: peak 45 % of stall
    belt_sustained   m= -2.604  hr.stifle: above allowable for 90% of a window
    belt_breaking    m= 0.4587  hl.stifle: peak 11% of breaking strength
    joint_speed      m=-0.1219  fl.carpus: 121 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.2513  fl.carpus: 100% of its torque-speed envelope (0.97 N*m at 114 deg/s)
    fall             m=   None  stood
walk (as is)                   spring rates x1.5                            margin  -2.604 worst belt_sustained   fell False viol servo_sustained,belt_sustained,joint_speed,envelope
    servo_sustained  m=  -2.36  hr.hip_abd: above 48% of rated for 84% of a 2 s window
    stall            m= 0.5754  hr.hip_abd: peak 34 % of stall
    belt_sustained   m=   -1.0  hr.stifle: above allowable for 50% of a window
    belt_breaking    m= 0.6235  hl.stifle: peak 8% of breaking strength
    joint_speed      m=-0.1304  fr.carpus: 122 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.2513  fl.carpus: 100% of its torque-speed envelope (0.93 N*m at 115 deg/s)
    fall             m=   None  stood
walk (as is)                   spring rates x0.0                            margin   -2.36 worst servo_sustained  fell False viol servo_sustained,belt_sustained,joint_speed,envelope
    servo_sustained  m=   -1.2  hr.hip_abd: above 48% of rated for 55% of a 2 s window
    stall            m= 0.4271  fl.shoulder: peak 46 % of stall
    belt_sustained   m=  -0.96  hl.stifle: above allowable for 49% of a window
    belt_breaking    m= 0.6565  hl.stifle: peak 7% of breaking strength
    joint_speed      m= 0.0293  hr.hock: 105 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.0076  hr.hock: 81% of its torque-speed envelope (0.17 N*m at 105 deg/s)
    fall             m=   None  stood
trot (as is)                   baseline                                     margin    -1.2 worst servo_sustained  fell False viol servo_sustained,belt_sustained,envelope
    servo_sustained  m=-1.4158  hr.hip_abd: above 48% of rated for 60% of a 2 s window
    stall            m= 0.3701  fl.shoulder: peak 50 % of stall
    belt_sustained   m=-1.7327  hl.stifle: above allowable for 68% of a window
    belt_breaking    m= 0.6366  hr.stifle: peak 7% of breaking strength
    joint_speed      m= 0.0232  hl.hock: 106 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.0245  hr.hock: 82% of its torque-speed envelope (0.27 N*m at 104 deg/s)
    fall             m=   None  stood
trot (as is)                   mass x1.1                                    margin -1.7327 worst belt_sustained   fell False viol servo_sustained,belt_sustained,envelope
    servo_sustained  m=-1.3762  hl.hip_abd: above 48% of rated for 59% of a 2 s window
    stall            m= 0.3939  fr.shoulder: peak 48 % of stall
    belt_sustained   m=-1.3366  hr.stifle: above allowable for 58% of a window
    belt_breaking    m= 0.6709  hl.stifle: peak 7% of breaking strength
    joint_speed      m=-0.0697  hl.hock: 107 deg/s against 125
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.1322  hl.hock: 90% of its torque-speed envelope (0.27 N*m at 107 deg/s)
    fall             m=   None  stood
trot (as is)                   servo at 11.1 V                              margin -1.3762 worst servo_sustained  fell False viol servo_sustained,belt_sustained,joint_speed,envelope
    servo_sustained  m=  -1.24  hl.hip_abd: above 48% of rated for 56% of a 2 s window
    stall            m= 0.4655  fr.shoulder: peak 43 % of stall
    belt_sustained   m=   -1.4  hl.stifle: above allowable for 60% of a window
    belt_breaking    m= 0.6505  hl.stifle: peak 7% of breaking strength
    joint_speed      m= 0.0124  hr.hock: 107 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=-0.0359  hr.hock: 83% of its torque-speed envelope (0.41 N*m at 102 deg/s)
    fall             m=   None  stood
trot (as is)                   spring rates x1.5                            margin    -1.4 worst belt_sustained   fell False viol servo_sustained,belt_sustained,envelope
    servo_sustained  m=  -1.32  hr.hip_abd: above 48% of rated for 58% of a 2 s window
    stall            m= 0.3229  fl.shoulder: peak 54 % of stall
    belt_sustained   m=-0.9802  hl.stifle: above allowable for 50% of a window
    belt_breaking    m= 0.5008  hl.stifle: peak 10% of breaking strength
    joint_speed      m= 0.0263  hl.hock: 105 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.0193  hl.hock: 78% of its torque-speed envelope (0.03 N*m at 105 deg/s)
    fall             m=   None  stood
trot (as is)                   spring rates x0.0                            margin   -1.32 worst servo_sustained  fell False viol servo_sustained,belt_sustained
    servo_sustained  m=    1.0  hl.hip_abd: above 48% of rated for 0% of a 2 s window
    stall            m= 0.8119  fl.shoulder: peak 15 % of stall
    belt_sustained   m=    1.0  hl.stifle: above allowable for 0% of a window
    belt_breaking    m= 0.8313  hl.stifle: peak 3% of breaking strength
    joint_speed      m=  0.761  hr.hock: 26 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.7101  hr.hock: 23% of its torque-speed envelope (0.25 N*m at 26 deg/s)
    fall             m=   None  stood
interpreted trot (fast play)   baseline                                     margin  0.7101 worst envelope         fell False viol 
    servo_sustained  m=    0.6  fr.shoulder: above 48% of rated for 10% of a 2 s window
    stall            m=  0.724  fr.shoulder: peak 22 % of stall
    belt_sustained   m=    1.0  hl.stifle: above allowable for 0% of a window
    belt_breaking    m= 0.8116  hr.stifle: peak 4% of breaking strength
    joint_speed      m= 0.7769  hr.hock: 24 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.7143  hr.hock: 23% of its torque-speed envelope (0.30 N*m at 24 deg/s)
    fall             m=   None  stood
interpreted trot (fast play)   mass x1.1                                    margin     0.6 worst servo_sustained  fell False viol 
    servo_sustained  m=   0.56  fr.shoulder: above 48% of rated for 11% of a 2 s window
    stall            m= 0.7216  fr.shoulder: peak 22 % of stall
    belt_sustained   m=    1.0  hl.stifle: above allowable for 0% of a window
    belt_breaking    m= 0.8152  hr.stifle: peak 4% of breaking strength
    joint_speed      m= 0.7298  hr.hock: 27 deg/s against 125
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.6804  hr.hock: 26% of its torque-speed envelope (0.21 N*m at 27 deg/s)
    fall             m=   None  stood
interpreted trot (fast play)   servo at 11.1 V                              margin    0.56 worst servo_sustained  fell False viol 
    servo_sustained  m=   0.36  fl.shoulder: above 48% of rated for 16% of a 2 s window
    stall            m= 0.7054  fr.shoulder: peak 24 % of stall
    belt_sustained   m=-0.4653  hr.stifle: above allowable for 37% of a window
    belt_breaking    m= 0.7481  hr.stifle: peak 5% of breaking strength
    joint_speed      m= 0.7636  hr.hock: 26 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.6922  hr.hock: 25% of its torque-speed envelope (0.34 N*m at 25 deg/s)
    fall             m=   None  stood
interpreted trot (fast play)   spring rates x1.5                            margin -0.4653 worst belt_sustained   fell False viol belt_sustained
    servo_sustained  m=    1.0  hl.hip_abd: above 48% of rated for 0% of a 2 s window
    stall            m= 0.8187  hl.hip_abd: peak 14 % of stall
    belt_sustained   m=    1.0  hl.stifle: above allowable for 0% of a window
    belt_breaking    m= 0.8271  hr.hock: peak 3% of breaking strength
    joint_speed      m= 0.7616  hr.hock: 26 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.7557  hr.hock: 20% of its torque-speed envelope (0.08 N*m at 25 deg/s)
    fall             m=   None  stood
interpreted trot (fast play)   spring rates x0.0                            margin  0.7557 worst envelope         fell False viol 
    servo_sustained  m=    0.4  fr.shoulder: above 48% of rated for 15% of a 2 s window
    stall            m=   0.78  fr.shoulder: peak 18 % of stall
    belt_sustained   m=   0.76  hl.stifle: above allowable for 6% of a window
    belt_breaking    m= 0.7398  hl.stifle: peak 5% of breaking strength
    joint_speed      m= 0.2751  hl.hock: 78 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m=  0.329  hl.hock: 54% of its torque-speed envelope (0.19 N*m at 68 deg/s)
    fall             m=   None  stood
interpreted step               baseline                                     margin  0.2751 worst joint_speed      fell False viol 
    servo_sustained  m=  -0.12  fr.shoulder: above 48% of rated for 28% of a 2 s window
    stall            m= 0.7623  fr.shoulder: peak 19 % of stall
    belt_sustained   m=   0.68  hl.stifle: above allowable for 8% of a window
    belt_breaking    m= 0.7299  hl.stifle: peak 5% of breaking strength
    joint_speed      m= 0.2719  hl.hock: 79 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.3261  hl.hock: 54% of its torque-speed envelope (0.20 N*m at 68 deg/s)
    fall             m=   None  stood
interpreted step               mass x1.1                                    margin   -0.12 worst servo_sustained  fell False viol servo_sustained
    servo_sustained  m=   -0.2  fr.shoulder: above 48% of rated for 30% of a 2 s window
    stall            m= 0.7605  fr.shoulder: peak 19 % of stall
    belt_sustained   m=   0.76  hl.stifle: above allowable for 6% of a window
    belt_breaking    m= 0.7361  hl.stifle: peak 5% of breaking strength
    joint_speed      m= 0.2036  hl.hock: 80 deg/s against 125
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.2053  hl.hock: 64% of its torque-speed envelope (0.01 N*m at 79 deg/s)
    fall             m=   None  stood
interpreted step               servo at 11.1 V                              margin    -0.2 worst servo_sustained  fell False viol servo_sustained
    servo_sustained  m=   -0.8  fl.shoulder: above 48% of rated for 45% of a 2 s window
    stall            m=  0.746  fr.shoulder: peak 20 % of stall
    belt_sustained   m=  -1.48  hl.stifle: above allowable for 62% of a window
    belt_breaking    m= 0.6525  hl.stifle: peak 7% of breaking strength
    joint_speed      m=  0.275  hl.hock: 78 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.2692  hl.hock: 58% of its torque-speed envelope (0.02 N*m at 78 deg/s)
    fall             m=   None  stood
interpreted step               spring rates x1.5                            margin   -1.48 worst belt_sustained   fell False viol servo_sustained,belt_sustained
    servo_sustained  m=    1.0  hl.hip_abd: above 48% of rated for 0% of a 2 s window
    stall            m= 0.8277  hr.stifle: peak 14 % of stall
    belt_sustained   m=    0.0  hr.stifle: above allowable for 25% of a window
    belt_breaking    m= 0.7535  hr.stifle: peak 5% of breaking strength
    joint_speed      m= 0.2753  hl.hock: 78 deg/s against 135
    joint_limit      m=    1.0  0% of the time within 1 deg of a limit
    envelope         m= 0.3265  hl.hock: 54% of its torque-speed envelope (0.08 N*m at 71 deg/s)
    fall             m=   None  stood
interpreted step               spring rates x0.0                            margin     0.0 worst belt_sustained   fell False viol 
done 23 s
```
