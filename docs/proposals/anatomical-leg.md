# Proposal: a leg that is more faithful to a calf

Status: **proposal, nothing built.** Written 2026-10-03 at the researcher's
request. It needs a decision before any code changes (questions at the end).

## Where we are

Every leg is the same two-segment chain (ADR-015): hip abduction, hip
flexion, one "knee", then a hoof on the end of the shank. Fore and hind legs
differ only in which way that one joint bends: `hind_knee_forward` and, since
this session, `front_knee_forward`. Twelve leg actuators, twelve leg joints.

A calf's legs are not that. Seen from the side, standing:

| | Fore limb | Hind limb |
|---|---|---|
| Top joint | shoulder (scapula on the trunk, no bony joint to it) | hip |
| First segment | humerus, points **back and down** | femur, points **forward and down** |
| Middle joint | elbow, close under the trunk, points back | stifle, close to the belly, points forward |
| Second segment | radius/ulna, near vertical | tibia, points back and down |
| Lower joint | **carpus** ("front knee"), points forward | **hock**, points back |
| Third segment | metacarpus (cannon), vertical | metatarsus (cannon), near vertical |
| Below | fetlock, pastern, hoof | fetlock, pastern, hoof |

So the silhouette that reads as "calf" is a zigzag of **three** long segments
per leg, with the carpus at the front of the fore leg and the hock at the
back of the hind leg. The current leg can put one bend in the right
direction, but it cannot make the zigzag, and its bend sits in the middle of
the leg instead of near the trunk (elbow/stifle) and low down (carpus/hock).

## What would change

**Geometry and genome.** A third segment per leg (`cannon`) and separate
fore/hind proportions:

* new part IDs `leg.<k>.cannon`; the hoof moves from the shank to the cannon
  (its ID `leg.<k>.hoof` stays);
* new joints `joint.<k>.carpus` (fore) / `joint.<k>.hock` (hind). The existing
  `joint.<k>.knee` becomes the elbow/stifle. Keeping the ID `knee` for it
  avoids renaming an existing stable ID (CLAUDE.md rule 8) but is anatomically
  wrong for the fore leg; renaming it needs a migration of every stored run
  and design. This is decision 3 below;
* genes: `thigh_length`, `shank_length` split into fore and hind
  (`fore_upper_length`, `fore_forearm_length`, `fore_cannon_length`,
  `hind_thigh_length`, `hind_gaskin_length`, `hind_cannon_length`), plus
  standing angles for the two bends of each pair. `knee_bend`,
  `hind_knee_forward` and `front_knee_forward` would be replaced. Genome
  version 2 -> 3 with a migration that maps a v2 leg onto a v3 leg with a
  zero-length-change cannon (old runs must still reload and look the same);
* the standing pose becomes a two-bend inverse-kinematics problem (hoof under
  the hip at a given height) instead of the one-line formula used now.

**Actuation: the real choice.** Three ways to drive the extra joint:

| Option | Leg actuators | What it is | Cost |
|---|---|---|---|
| A. Actuated | 16 (+4) | a fourth motor per leg at the carpus/hock | +4 motors: mass and money on the legs, where the mass budget is tightest and where `act.fr.hip_abd` already saturates. Needs datasheet-verified numbers before it can be judged. |
| B. Coupled (pantograph) | 12 | the cannon is linked to the segment two above it by a rod or belt, so carpus/hock flexes with the elbow/stifle, as the reciprocal apparatus does in a real hind limb | no new motors; one new transmission type (four-bar or 1:1 belt) in the model, the simulator and the CAD export. The mechanism has to be designed and printed. |
| C. Passive spring | 12 | sprung carpus/hock with a hard stop | cheapest to build; least control; needs spring stiffness in the model, which is another unverified number |

B is the closest to the animal and to the "soft machine" idea, and keeps the
motor count. A is the simplest to simulate. C is the simplest to build.

**Everything that reads the leg.** The following assume two segments and the
names `thigh` / `shank` / `knee` today:

* `core/calflab/morphology/calf.py` (generator, standing pose, harness
  routes, skin sleeves, belt drive placement);
* `core/calflab/control/cpg.py` (finds `hip_abd`, `hip_flex`, `knee`; a third
  joint needs a phase and amplitude of its own, or the coupling);
* `core/calflab/sim/mjcf.py` if a coupled joint is added (an equality
  constraint or tendon), and the servo/thermal model per added actuator;
* behaviour descriptor `leg_length`, the CAD leg-segment exporter, the Blender
  armature plan and the Rhino build list (both derive from the spec, so they
  mostly follow), the firmware joint map;
* tests, the sample project, `docs/USER_GUIDE.md`, `docs/CHAT_GUIDE_PROMPT.md`.

## What it costs

Rough size, in sessions like this one:

1. Geometry + genome v3 + migration + standing pose + tests: one session.
2. Gait: extend the CPG and re-tune the default trot; expect the walking
   speed and stability numbers (0.36 m/s today) to move: one session, more if
   option B's linkage has to be simulated faithfully.
3. Fabricate (CAD segment with the new joint, harness, BOM) and bridges
   re-checked in Rhino and Blender: one session.

Risks: every recorded run and baked design was made on the two-segment leg.
They will still load (migration), but their fitness numbers are not
comparable with three-segment runs, and an evolution archive started before
the change should not be continued after it. The torque-margin picture gets
worse before it gets better: a longer, more articulated leg raises hip
torque, and the hip-abduction actuator is already at its limit.

## Effect on the ADRs

* **ADR-015** (proportions; "the leg is simplified to two segments (3 DOF)
  for every leg; the real fore/hind limb difference is expressed only by knee
  bend direction") would be **superseded** by a new ADR recording the
  three-segment leg, the chosen actuation option and the fore/hind
  proportions (still marked VERIFY: they would again be scaled from a
  silhouette, not measured).
* **ADR-017** (mass model) is unchanged in method; the numbers change.
* **ADR-032** (default CPG numbers are starting points) stays, with new
  starting points.
* The new **ADR-041** (front knee direction gene) becomes obsolete: the two
  direction toggles are an interim way to get one bend the right way round.

Until then the honest description of the current leg is: one bend per leg,
direction selectable per pair, proportions identical front and back.

## An intermediate step that costs almost nothing

With today's two toggles the closest calf-like stance is
`front_knee_forward = on`, `hind_knee_forward = off`: the fore bend reads as a
carpus, the hind bend as a hock. It is in the Form panel now. The default
trot is tuned for backward knees and **falls** with either toggle on (checked
in simulation on 2026-10-03: with `front_knee_forward` the calf covers ground
at about 0.19 m/s and then falls; the same already happened with
`hind_knee_forward`). It needs a gait tuned for it, which is what the Evolve
workspace's inner CMA-ES loop does.

## Decisions needed

1. Is the goal a calf-like **silhouette** (a posed, skinned figure reads
   right) or calf-like **locomotion** (the leg works the way the animal's
   does)? Silhouette alone could be met with a fixed, unactuated cannon
   angle, at a fraction of the cost.
2. Actuation: A (four more motors), B (coupled), or C (passive)?
3. Stable IDs: keep `joint.<k>.knee` for the upper joint (no migration of
   IDs, wrong name on the fore leg), or rename to elbow/stifle + carpus/hock
   (correct names, one-time migration of every stored run, design and
   journal link)?
4. Should fore and hind proportions come from measurements of a real calf
   (photographs with a scale, or published anatomy) before this is built? The
   current proportions are assumptions (ADR-015), and a three-segment leg
   built on assumed proportions would need redoing.
