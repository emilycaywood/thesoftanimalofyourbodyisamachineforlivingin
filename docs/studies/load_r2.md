# Session R, step 2: where the load goes (2026-11-04)

`projects/robot-calf-final` as it is (scratch copy `projects/_scratch-r`), seed 0, torque-speed servos, margin 0.2,
in memory only. Scripts: `docs/studies/load_r2.py` (decomposition), `docs/studies/levers_r2.py` (levers). ADR-087.

## How the load is split

Each recorded frame is rebuilt in MuJoCo (trunk pose and joint angles as recorded). The 3D hoof forces of that
instant (recorded during the play) are **scaled to carry exactly the body's weight**, so their direction and
their share between hooves are kept, impacts and accelerations are not. Then per joint, servo side:

* **static** = the torque that holds the pose still under gravity on those hooves (no springs);
* **static with springs** = static minus what the springs give: the servo's share of holding the weight;
* **dynamics** = what the servo really gave minus its static share (accelerations, ground forces above the
  weight, damping).

Check on quiet standing: static with springs matches the servo within 0.02 N*m on every joint (dynamics RMS
0.004-0.019 N*m). A first version with vertical-only ground forces gave the hip ab/ad twice its real load: the
hooves' sideways friction matters for splayed legs.

The sustained limits, servo side: torque above **0.47 N*m** (48 % of the 0.98 N*m rated) for more than 25 % of
a 2 s window; belt above its allowable tension x 0.8 = **0.34 N*m** at the servo (35.2 N on a 30T pulley).

## Where it comes from (share of the worst 2 s window above the limit: measured / static with springs / static)

| motion | hooves down | joint, limit | measured | static + springs | static alone | so the load is |
|---|---|---|---|---|---|---|
| walk | 2: 73 %, 3: 19 %, 4: 9 % (planned: 3 at a time) | hr.hip_abd torque | 0.87 | 0.92 | 0.92 | **the weight** on splayed legs; no spring at the hip |
| | | fl/fr.shoulder torque | 0.51 / 0.49 | 0.49 / 0.46 | 0.37 / 0.34 | the weight, **made worse by the shoulder springs** |
| | | hl/hr.stifle belt | 0.26 / 0.27 | 0.20 / 0.20 | 0.15 / 0.59 | mostly the weight; springs over-compensate at hl, are needed at hr |
| | | fr.carpus speed, fl.carpus envelope | 122 deg/s vs 108; 100 % | | | **the gait**: how fast it folds the carpus |
| trot | 2: 48 %, 3: 41 %, 4: 9 % | hl/hr.hip_abd torque | 0.54 / 0.55 | 0.53 / 0.58 | same | **the weight** on the diagonal pair, splayed legs |
| | | hl/hr.stifle belt | 0.49 / 0.49 | 0.41 / 0.39 | 0.30 / 0.28 | weight + springs over-compensating (+0.1) + dynamics (+0.1; RMS 0.35-0.37 N*m) |
| | | fl/fr.shoulder torque | 0.30 / 0.30 | 0.31 / 0.29 | 0.37 / 0.37 | weight; here the springs help |
| interpreted trot | 2: 37 %, 3: 28 %, 4: 35 % | all | <= 0.02 | <= 0.02 | stifle belt 0.15-0.20 | within; its springs keep the stifle belts clear; binding = hock envelope 23 % (dynamics) |

Per-joint means and dynamics RMS for every joint are in the raw output below.

## What the springs carry now (quiet standing, servo side, per leg)

| joint | needed to hold the weight | the springs give | so |
|---|---|---|---|
| stifle | 0.141 N*m | 0.255 N*m | 181 %: the servo pulls 0.114 against its spring |
| hock | 0.050 N*m | 0.096 N*m | 192 % |
| shoulder | 0.054 N*m | 0.197 N*m | **365 %**: the servo holds 0.144 against its spring; in the walk's and the step's poses the shoulder needs the other sign and the spring adds to the load |
| hip ab/ad | 0.166 N*m | none (no spring there) | the servo carries all of it, more on two hooves |
| carpus | 0.055 N*m | none | small |

## Levers, one at a time (played; margin; negative = over a limit)

| lever | walk | trot | interpreted trot* | interpreted step* |
|---|---|---|---|---|
| today | -2.48 | -1.20 | +0.71 | +0.28 |
| springs = weight at standing (stifle x0.55, hock x0.52, shoulder x0.27) | -2.40 (belt +0.28) | -1.20 (belt -0.70) | +0.73 | +0.28 |
| shoulder springs off | -2.44 | -1.32 | +0.71 | +0.28 |
| hind splay 0 (from 12) | -1.72 | -1.73 | -3.0 | -1.72 |
| hind splay 6 | -1.52 | -0.88 | -1.0 | -0.48 |
| hind splay 18 | -2.48 | -1.46 | +0.04 | +0.28 |
| front splay 0 (from 10.5) | -0.32 | -1.48 | -0.51 | +0.27 |
| **both splay 0** | **-0.13** (speed; torque -0.04) | **-0.16** (belt; torque -0.04) | -0.47 | +0.27 |
| **springs = weight + both splay 0** | **-0.13** (speed; torque -0.08) | **-0.04** (speed only) | -0.62 | +0.27 |
| femur angle 30 (from 40) | -2.60 | -1.24 | -1.02 | -3.0 |
| femur angle 50 | rejected: hock belt check | | | |
| tibia angle 25 (from 35) | -2.72 | -1.36 | +0.16 | -3.0 |
| tibia angle 45 | rejected: hock belt check | | | |
| front angle 0 or 10 | no change: the lab solves it for a level back | | | |
| trot roll gain 0.25 / 0 (from 0.5) | | -1.30 / -1.22 | +0.71 / +0.71 | |
| walk sway 1.5 deg (from 3) | -1.12 | | | |
| walk sway 6 deg | -2.48 | | | |

\* The interpreted parameters were searched on today's body. On another body they are not re-searched here, so
their columns say how fragile today's interpretation is, not what that body could do (step 4 re-tunes per body).

## Raw output

### Decomposition (`load_r2.py`)

Columns: servo-side limit, mean |servo|, mean static + springs, mean static, mean spring, dynamics RMS (N*m);
then sustained fraction measured / static + springs / static, for torque and for the belt.

```
  ground/weight mean 1.00 max 1.00; |sum Fz - recorded| max 0.00 N

== stand (check): margin 0.9066 []  hooves down 0:0% 1:0% 2:0% 3:0% 4:100%
joint            thr |servo| stat+sp    stat  spring  dynRMS | sust meas/stat+sp/stat | belt meas/stat+sp/stat
hl.hip_abd      0.47   0.147  -0.166  -0.166  +0.000   0.019 | 0.00/0.00/0.00 | 
hl.stifle       0.47   0.107  +0.114  -0.141  -0.255   0.007 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
hl.hock         0.47   0.049  +0.046  -0.050  -0.096   0.004 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
hr.hip_abd      0.47   0.147  -0.166  -0.166  +0.000   0.019 | 0.00/0.00/0.00 | 
hr.stifle       0.47   0.107  +0.114  -0.141  -0.255   0.007 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
hr.hock         0.47   0.049  +0.046  -0.050  -0.096   0.004 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fl.shoulder     0.47   0.131  -0.144  +0.054  +0.197   0.014 | 0.00/0.00/0.00 | 
fl.carpus       0.47   0.052  -0.055  -0.055  +0.000   0.004 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fr.shoulder     0.47   0.131  -0.144  +0.054  +0.197   0.014 | 0.00/0.00/0.00 | 
fr.carpus       0.47   0.052  -0.055  -0.055  +0.000   0.004 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
  ground/weight mean 0.99 max 2.33; |sum Fz - recorded| max 1.70 N

== walk: margin -2.48 ['servo_sustained', 'belt_sustained', 'joint_speed', 'envelope']  hooves down 0:0% 1:0% 2:73% 3:19% 4:9%
joint            thr |servo| stat+sp    stat  spring  dynRMS | sust meas/stat+sp/stat | belt meas/stat+sp/stat
hl.hip_abd      0.47   0.246  -0.066  -0.066  +0.000   0.097 | 0.46/0.50/0.50 | 
hl.stifle       0.47   0.221  +0.193  -0.060  -0.253   0.069 | 0.03/0.01/0.07 | 0.26/0.20/0.15 (thr 0.34)
hl.hock         0.47   0.116  +0.026  -0.071  -0.097   0.079 | 0.00/0.02/0.07 | 0.16/0.12/0.24 (thr 0.34)
hr.hip_abd      0.47   0.362  -0.215  -0.215  +0.000   0.087 | 0.87/0.92/0.92 | 
hr.stifle       0.47   0.190  +0.131  -0.122  -0.253   0.066 | 0.02/0.00/0.06 | 0.27/0.20/0.59 (thr 0.34)
hr.hock         0.47   0.105  +0.018  -0.079  -0.097   0.061 | 0.00/0.02/0.07 | 0.16/0.14/0.23 (thr 0.34)
fl.shoulder     0.47   0.309  -0.294  -0.098  +0.197   0.065 | 0.51/0.49/0.37 | 
fl.carpus       0.47   0.121  -0.108  -0.108  +0.000   0.078 | 0.04/0.06/0.06 | 0.07/0.06/0.06 (thr 0.34)
fr.shoulder     0.47   0.334  -0.346  -0.149  +0.197   0.070 | 0.49/0.46/0.34 | 
fr.carpus       0.47   0.111  -0.097  -0.097  +0.000   0.078 | 0.03/0.05/0.05 | 0.07/0.05/0.05 (thr 0.34)
  ground/weight mean 1.02 max 2.73; |sum Fz - recorded| max 1.83 N

== trot: margin -1.2 ['servo_sustained', 'belt_sustained', 'envelope']  hooves down 0:0% 1:2% 2:48% 3:41% 4:9%
joint            thr |servo| stat+sp    stat  spring  dynRMS | sust meas/stat+sp/stat | belt meas/stat+sp/stat
hl.hip_abd      0.47   0.422  -0.418  -0.418  +0.000   0.309 | 0.54/0.53/0.53 | 
hl.stifle       0.47   0.272  +0.039  -0.213  -0.252   0.370 | 0.06/0.19/0.25 | 0.49/0.41/0.30 (thr 0.34)
hl.hock         0.47   0.124  +0.083  -0.014  -0.097   0.181 | 0.00/0.12/0.08 | 0.00/0.19/0.16 (thr 0.34)
hr.hip_abd      0.47   0.412  -0.426  -0.426  +0.000   0.291 | 0.55/0.58/0.58 | 
hr.stifle       0.47   0.268  +0.054  -0.198  -0.252   0.354 | 0.07/0.19/0.25 | 0.49/0.39/0.28 (thr 0.34)
hr.hock         0.47   0.119  +0.068  -0.028  -0.096   0.175 | 0.00/0.13/0.08 | 0.00/0.21/0.19 (thr 0.34)
fl.shoulder     0.47   0.328  +0.102  +0.297  +0.195   0.341 | 0.30/0.31/0.37 | 
fl.carpus       0.47   0.138  -0.000  -0.000  +0.000   0.143 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fr.shoulder     0.47   0.320  +0.090  +0.285  +0.195   0.342 | 0.30/0.29/0.37 | 
fr.carpus       0.47   0.138  +0.003  +0.003  +0.000   0.145 | 0.00/0.00/0.00 | 0.02/0.00/0.00 (thr 0.34)
  ground/weight mean 0.99 max 1.16; |sum Fz - recorded| max 1.87 N

== interpreted trot: margin 0.7101 []  hooves down 0:0% 1:0% 2:37% 3:28% 4:35%
joint            thr |servo| stat+sp    stat  spring  dynRMS | sust meas/stat+sp/stat | belt meas/stat+sp/stat
hl.hip_abd      0.47   0.187  -0.184  -0.184  +0.000   0.103 | 0.00/0.02/0.02 | 
hl.stifle       0.47   0.118  +0.112  -0.143  -0.254   0.136 | 0.00/0.00/0.07 | 0.00/0.00/0.20 (thr 0.34)
hl.hock         0.47   0.115  +0.050  -0.046  -0.096   0.055 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
hr.hip_abd      0.47   0.160  -0.150  -0.150  +0.000   0.080 | 0.00/0.00/0.00 | 
hr.stifle       0.47   0.127  +0.128  -0.126  -0.255   0.139 | 0.00/0.00/0.10 | 0.00/0.02/0.15 (thr 0.34)
hr.hock         0.47   0.121  +0.034  -0.062  -0.096   0.053 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fl.shoulder     0.47   0.190  -0.203  -0.005  +0.197   0.043 | 0.00/0.02/0.00 | 
fl.carpus       0.47   0.073  -0.072  -0.072  +0.000   0.029 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fr.shoulder     0.47   0.154  -0.121  +0.076  +0.197   0.051 | 0.00/0.01/0.00 | 
fr.carpus       0.47   0.059  -0.049  -0.049  +0.000   0.027 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
  ground/weight mean 0.99 max 1.12; |sum Fz - recorded| max 0.98 N

== interpreted step: margin 0.2751 []  hooves down 0:0% 1:0% 2:0% 3:23% 4:77%
joint            thr |servo| stat+sp    stat  spring  dynRMS | sust meas/stat+sp/stat | belt meas/stat+sp/stat
hl.hip_abd      0.47   0.112  -0.054  -0.054  +0.000   0.094 | 0.00/0.00/0.00 | 
hl.stifle       0.47   0.176  +0.193  -0.073  -0.266   0.055 | 0.00/0.00/0.00 | 0.06/0.00/0.00 (thr 0.34)
hl.hock         0.47   0.070  +0.040  -0.042  -0.082   0.055 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
hr.hip_abd      0.47   0.077  -0.067  -0.067  +0.000   0.028 | 0.00/0.00/0.00 | 
hr.stifle       0.47   0.101  +0.025  -0.223  -0.248   0.039 | 0.00/0.00/0.00 | 0.00/0.00/0.41 (thr 0.34)
hr.hock         0.47   0.098  +0.103  +0.011  -0.092   0.015 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fl.shoulder     0.47   0.259  -0.261  -0.062  +0.199   0.025 | 0.00/0.00/0.00 | 
fl.carpus       0.47   0.073  -0.074  -0.074  +0.000   0.008 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
fr.shoulder     0.47   0.292  -0.293  -0.095  +0.198   0.026 | 0.15/0.06/0.00 | 
fr.carpus       0.47   0.130  -0.132  -0.132  +0.000   0.009 | 0.00/0.00/0.00 | 0.00/0.00/0.00 (thr 0.34)
```

### Levers (`levers_r2.py`)

```
today                                                        walk           -2.48 fell=False servo_su=-2.48 belt_sus=-0.07 joint_sp=-0.12 envelope=-0.25
today                                                        trot            -1.2 fell=False servo_su=-1.20 belt_sus=-0.96 joint_sp=+0.03 envelope=-0.01
today                                                        interp trot   0.7101 fell=False 
today                                                        interp step   0.2751 fell=False joint_sp=+0.28
springs = gravity at standing (stifle x0.55, hock x0.52, shoulder x0.27) walk            -2.4 fell=False servo_su=-2.40 belt_sus=+0.28 joint_sp=-0.13 envelope=-0.25
springs = gravity at standing (stifle x0.55, hock x0.52, shoulder x0.27) trot            -1.2 fell=False servo_su=-1.20 belt_sus=-0.70 joint_sp=+0.01 envelope=-0.01
springs = gravity at standing (stifle x0.55, hock x0.52, shoulder x0.27) interp trot   0.7288 fell=False 
springs = gravity at standing (stifle x0.55, hock x0.52, shoulder x0.27) interp step   0.2754 fell=False joint_sp=+0.28
shoulder springs off                                         walk           -2.44 fell=False servo_su=-2.44 belt_sus=+0.00 joint_sp=-0.13 envelope=-0.25
shoulder springs off                                         trot           -1.32 fell=False servo_su=-1.26 belt_sus=-1.32 joint_sp=+0.01 envelope=-0.02
shoulder springs off                                         interp trot   0.7097 fell=False 
shoulder springs off                                         interp step   0.2775 fell=False joint_sp=+0.28
hind splay 0.0                                               walk           -1.72 fell=False servo_su=-1.72 joint_sp=-0.23 envelope=-0.25
hind splay 0.0                                               trot         -1.7327 fell=False servo_su=-1.73 stall=-0.25 belt_sus=-1.42 belt_bre=+0.16 joint_sp=-0.05 envelope=-0.25
hind splay 0.0                                               interp trot     -3.0 fell=False servo_su=-3.00 belt_sus=-0.86
hind splay 0.0                                               interp step    -1.72 fell=False servo_su=-1.72 joint_sp=+0.28 envelope=+0.28
hind splay 6.0                                               walk           -1.52 fell=False servo_su=-1.52 belt_sus=+0.24 joint_sp=-0.16 envelope=-0.25
hind splay 6.0                                               trot           -0.88 fell=False servo_su=-0.36 stall=+0.09 belt_sus=-0.88 joint_sp=-0.07 envelope=-0.01
hind splay 6.0                                               interp trot     -1.0 fell=False servo_su=-1.00
hind splay 6.0                                               interp step    -0.48 fell=False servo_su=-0.48 joint_sp=+0.28
hind splay 18.0                                              walk           -2.48 fell=False servo_su=-2.48 belt_sus=-0.16 joint_sp=-0.11 envelope=-0.23
hind splay 18.0                                              trot         -1.4554 fell=False servo_su=-1.46 belt_sus=+0.24 joint_sp=+0.00 envelope=-0.04
hind splay 18.0                                              interp trot     0.04 fell=False servo_su=+0.04
hind splay 18.0                                              interp step    0.276 fell=False joint_sp=+0.28 envelope=+0.28
front splay 0.0                                              walk           -0.32 fell=False servo_su=-0.32 belt_sus=+0.16 joint_sp=-0.13 envelope=-0.15
front splay 0.0                                              trot           -1.48 fell=False servo_su=-1.32 stall=+0.20 belt_sus=-1.48 joint_sp=+0.05 envelope=+0.06
front splay 0.0                                              interp trot   -0.505 fell=False servo_su=-0.51
front splay 0.0                                              interp step   0.2662 fell=False joint_sp=+0.27 envelope=+0.27
front splay 5.0                                              walk            -1.0 fell=False servo_su=-1.00 belt_sus=-0.08 joint_sp=-0.11 envelope=-0.24
front splay 5.0                                              trot         -1.5347 fell=False servo_su=-1.30 belt_sus=-1.53 joint_sp=+0.02 envelope=-0.00
front splay 5.0                                              interp trot  -0.0693 fell=False servo_su=-0.07
front splay 5.0                                              interp step    0.271 fell=False joint_sp=+0.27
both splay 0                                                 walk         -0.1337 fell=False servo_su=-0.04 joint_sp=-0.13 envelope=+0.07
both splay 0                                                 trot           -0.16 fell=False servo_su=-0.04 belt_sus=-0.16 joint_sp=-0.04 envelope=+0.02
both splay 0                                                 interp trot  -0.4653 fell=False servo_su=-0.47 belt_sus=-0.08
both splay 0                                                 interp step   0.2691 fell=False joint_sp=+0.27
femur_angle 30.0                                             walk            -2.6 fell=False servo_su=-2.60 belt_sus=-0.24 joint_sp=-0.17 envelope=-0.25
femur_angle 30.0                                             trot           -1.24 fell=False servo_su=-1.24 belt_sus=-1.16 joint_sp=-0.01 envelope=-0.06
femur_angle 30.0                                             interp trot  -1.0198 fell=False servo_su=-1.02 belt_sus=-0.27
femur_angle 30.0                                             interp step     -3.0 fell=False servo_su=-3.00 joint_sp=+0.29
femur_angle 50.0                                             walk         REJECTED belts ['hock']
femur_angle 50.0                                             trot         REJECTED belts ['hock']
femur_angle 50.0                                             interp trot  REJECTED belts ['hock']
femur_angle 50.0                                             interp step  REJECTED belts ['hock']
tibia_angle 25.0                                             walk           -2.72 fell=False servo_su=-2.72 belt_sus=-0.16 joint_sp=-0.18 envelope=-0.25
tibia_angle 25.0                                             trot           -1.36 fell=False servo_su=-1.08 belt_sus=-1.36 joint_sp=-0.01 envelope=-0.06
tibia_angle 25.0                                             interp trot     0.16 fell=False belt_sus=+0.16
tibia_angle 25.0                                             interp step     -3.0 fell=False servo_su=-3.00 joint_sp=+0.29
tibia_angle 45.0                                             walk         REJECTED belts ['hock']
tibia_angle 45.0                                             trot         REJECTED belts ['hock']
tibia_angle 45.0                                             interp trot  REJECTED belts ['hock']
tibia_angle 45.0                                             interp step  REJECTED belts ['hock']
front_angle 0.0                                              walk           -2.48 fell=False servo_su=-2.48 belt_sus=-0.07 joint_sp=-0.12 envelope=-0.25
front_angle 0.0                                              trot            -1.2 fell=False servo_su=-1.20 belt_sus=-0.96 joint_sp=+0.03 envelope=-0.01
front_angle 0.0                                              interp trot   0.7101 fell=False 
front_angle 0.0                                              interp step   0.2751 fell=False joint_sp=+0.28
front_angle 10.0                                             walk           -2.48 fell=False servo_su=-2.48 belt_sus=-0.07 joint_sp=-0.12 envelope=-0.25
front_angle 10.0                                             trot            -1.2 fell=False servo_su=-1.20 belt_sus=-0.96 joint_sp=+0.03 envelope=-0.01
front_angle 10.0                                             interp trot   0.7101 fell=False 
front_angle 10.0                                             interp step   0.2751 fell=False joint_sp=+0.28
trot roll_gain 0.25                                          trot          -1.297 fell=False servo_su=-1.24 belt_sus=-1.30 joint_sp=-0.00 envelope=-0.02
trot roll_gain 0.25                                          interp trot    0.713 fell=False 
trot roll_gain 0                                             trot         -1.2178 fell=False servo_su=-1.22 belt_sus=-1.20 joint_sp=+0.03 envelope=+0.01
trot roll_gain 0                                             interp trot   0.7133 fell=False 
walk sway 1.5                                                walk           -1.12 fell=False servo_su=-1.12 belt_sus=+0.12 joint_sp=-0.13 envelope=-0.20
walk sway 6                                                  walk           -2.48 fell=False servo_su=-2.48 stall=+0.12 belt_sus=-0.04 joint_sp=-0.17 envelope=-0.25
springs GC + both splay 0                                    walk         -0.1336 fell=False servo_su=-0.08 joint_sp=-0.13 envelope=+0.10
springs GC + both splay 0                                    trot         -0.0439 fell=False joint_sp=-0.04 envelope=+0.11
springs GC + both splay 0                                    interp trot  -0.6238 fell=False servo_su=-0.62 belt_sus=-0.35
springs GC + both splay 0                                    interp step   0.2701 fell=False joint_sp=+0.27
```
