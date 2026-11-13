# g020-008-r01-mc — parts list and placement

The McMaster-Carr closest swap of g020-008-r01 (session R18, ADR-115 to ADR-120). Generated from
`g020_008_r01_mc_parts.json` and `g020_008_r01_mc_geometry.csv` (same folder). Prices as read on mcmaster.com on
2026-11-12, without shipping or tax.

**Status:**

- **Nothing is verified:** every part is `verified: false` and `purchase_confirmed: false`.
- **Breaking strength:** the belt's is the researcher's assumption (643 N).
- **Allowable working tension:** Gates 17611-T (179.6 N).

**Coordinates:**

- **Frame:** mm, standing pose, X forward, Y left, Z up.
- **Axles:** the hip ab/ad axles are at X = -275 and the shoulder axles at X = +275, both at Z = 596.9 (the standing
  height).
- **Sides:** right-side parts mirror the left ones (Y negated).

## 1. Belt drive parts (McMaster-Carr) — USD 301.36

| qty | part | McMaster | each | line | used at |
|---|---|---|---|---|---|
| 4 | GT pulley 30T, 3MGT, 9 mm belt, 1/4 in finished bore, set screw, 2 flanges (PD 28.7, OD 32, hub 19.7, overall width 20.6 mm) | 3764N134 | 19.38 | 77.52 | stifle and hock **drivers** (on the servos), both hind legs |
| 8 | GT pulley 45T, 3MGT, 9 mm belt, 1/4 in finished bore, set screw, 2 flanges (PD 43.0, OD 45, hub 31.8, overall width 21.2 mm) | 3764N141 | 16.71 | 133.68 | stifle, hock and carpus **driven** pulleys (on the joints), and the carpus **drivers** |
| 2 | Closed belt 3MGT, 9 mm wide, 450 mm, 150 teeth (Gates 450-3P-09) | 7947K795 | 14.43 | 28.86 | stifle, both hind legs |
| 2 | Closed belt 3MGT, 9 mm wide, 414 mm, 138 teeth (Gates 414-3P-09) | 7947K792 | 14.18 | 28.36 | hock, both hind legs |
| 2 | Closed belt 3MGT, 9 mm wide, 600 mm, 200 teeth (Gates 600-3P-09) | 7947K815 | 16.47 | 32.94 | carpus, both front legs |
| | | | | **301.36** | |

## 2. Where each belt drive goes

Every belt drive is a servo on the segment above the joint, with a pulley on its output, belted to a pulley on the
joint axis. **C** is the centre distance between the two pulley axes; it follows from the belt length and is never
set.

### Stifle (hind legs): 30T -> 45T, 1.5:1, 450 mm belt, C = 168.6 mm

- **Driver:** a 30T 3764N134 on the **stifle servo** (STS3215 C018). The servo rides on the **femur** with its output
  axis 168.6 mm up the femur from the stifle axis, i.e. 29.4 mm from the femur's top. Left driver pulley at
  (-258.2, 157.6, 576.0).
- **Driven:** a 45T 3764N141 on the **stifle axis**, fixed to the tibia. Left at (-152.3, 184.2, 447.5), 13.8 mm
  outboard of the stifle joint centre (-150.6, 170.4, 446.1).
- **Belt:** 7947K795 between them, along the femur.

### Hock (hind legs): 30T -> 45T, 1.5:1, 414 mm belt, C = 150.6 mm

- **Driver:** a 30T 3764N134 on the **hock servo** (STS3250 C002). The servo rides on the **tibia** with its output
  axis 150.6 mm up the tibia from the hock axis, i.e. 88.4 mm below the stifle. Left driver pulley at
  (-203.6, 185.5, 375.5).
- **Driven:** a 45T 3764N141 on the **hock axis**, fixed to the rear cannon. Left at (-290.9, 187.8, 252.8), outboard
  of the hock joint centre (-289.2, 174.0, 251.4).
- **Belt:** 7947K792 between them, along the tibia.
- **Clearance:** the hock servo's clearance from the stifle belt through the stifle's range is "unknown". It clears
  only for some positions of the servo's output axis on its case, so measure the STS3250 and enter
  `servo.output_axis_offset_mm`.

### Carpus (front legs): 45T -> 45T, 1:1, 600 mm belt, C = 232.5 mm

- **Driver:** a 45T 3764N141 on the **carpus servo** (STS3250 C002). The servo rides on the **upper leg** with its
  output axis 232.5 mm up from the carpus axis, i.e. 107.5 mm below the shoulder. Left driver pulley at
  (301.2, 155.2, 494.4).
- **Driven:** a 45T 3764N141 on the **carpus axis**, fixed to the front cannon. Left at (357.9, 175.8, 269.8),
  outboard of the carpus joint centre (357.9, 161.9, 268.5).
- **Belt:** 7947K815 between them, along the upper leg.

## 3. Servos (from the library; not McMaster)

| qty | servo | joint | drive | left servo body centre (model) |
|---|---|---|---|---|
| 2 | Feetech STS3215 C018 (12 V) | hip ab/adduction | direct, on the hip ab/ad axis | (-275.0, 115.3, 596.9) |
| 2 | Feetech STS3215 C018 (12 V) | stifle | belt, driver on the femur | (-261.1, 181.3, 578.5) |
| 2 | Feetech STS3250 C002 (12 V) | hock | belt, driver on the tibia | (-206.5, 209.2, 378.0) |
| 2 | Feetech STS3250 C002 (12 V) | shoulder | direct, on the shoulder axis | (275.0, 102.7, 596.9) |
| 2 | Feetech STS3250 C002 (12 V) | carpus | belt, driver on the upper leg | (301.2, 179.1, 496.6) |

## 4. Springs (tension; not sourced yet)

| qty | site | rate | free length | stretched to (standing) | most extension, force | anchors (left; upper -> lower) |
|---|---|---|---|---|---|---|
| 2 | hip ab/ad | 0.0889 N/mm | 30.0 mm | 47.9 mm | 33.8 mm, 3.0 N | hip block (-243.0, 99.1, 558.9) -> femur (-243.6, 147.0, 558.8) |
| 2 | stifle | 0.1969 N/mm | 64.5 mm | 114.6 mm | 60.8 mm, 12.0 N | femur (-127.2, 167.1, 504.1) -> tibia (-123.7, 179.6, 390.2) |
| 2 | hock | 0.1285 N/mm | 39.5 mm | 77.9 mm | 64.3 mm, 8.3 N | tibia (-250.8, 171.2, 322.2) -> rear cannon (-307.1, 170.0, 268.4) |

The stifle and hock spring lines pass within the tube radius + 3 mm of their joint somewhere in the joint's range
(flagged, as on the working body since R11c): check them against the real tube.

## 5. Open items (no part chosen, no mass or size in the model)

| qty | item | where |
|---|---|---|
| 6 | Servo output (spline horn) to **1/4 in round shaft** adapter | one under each driver pulley: stifle, hock and carpus servos, both sides |
| 6 | **1/4 in joint axle** carrying the driven pulley (set screw onto it) | stifle, hock and carpus joints, both sides |
| 6 | Tension springs as in section 4 | hip ab/ad, stifle, hock, both sides |

## 6. Before ordering

- **Belts and pulleys:** confirm each is orderable (`purchase_confirmed` is false everywhere).
- **Lateral stack:** the pulleys are 20.6-21.2 mm wide overall (with flanges) for a 9 mm belt, and the model places
  tube, pulley, belt and servo in one plane. Check the stack at each joint and the pulley's own clearance there.
- **Set screws:** fixing the driven pulley to its joint and the driver pulley to its adapter is not checked in
  simulation; McMaster lists no set-screw size.
- **Segment lengths** (mm), unchanged from g020-008-r01: femur 198, tibia 239, rear cannon 226, upper leg 340, front
  cannon 247.
