# CALFLAB bridge for Blender (4.2 or newer; verified on 5.2.2)

## Install

```powershell
.\calflab.ps1 bridge blender --install
```

builds `bridges\blender\dist\calflab_blender.zip` and installs it into Blender
as an extension, enabled. To install by hand instead: **Edit > Preferences >
Get Extensions > (arrow menu, top right) > Install from Disk...** and pick the
zip. Re-run the command after pulling new CALFLAB code to update it.

The panel is in the 3D viewport sidebar (press **N**) under **CALFLAB**. The
lab must be running (`.\calflab.ps1 lab`).

## What it does

| Button | Effect |
|---|---|
| **Build armature from CALFLAB** | One bone per joint, named by the joint's stable ID (`joint.fl.knee`). Each bone is locked to its single hinge axis and carries a *Limit Rotation* constraint with the joint's limits. Part meshes are parented to their bones and named by their IDs. Building again replaces the previous CALFLAB armature. |
| **Export action as reference clip** | Samples the armature's action into the project's motion library (`motions/`): joint angles in degrees relative to the standing pose, the trunk trajectory, fps and source metadata. Clips feed the Behave timeline and Phase 2 imitation rewards. |
| **Import simulation rollout** | Creates an action from a simulation run (empty run id = the latest) for rendering and documentation. |
| Import video pose estimation | Placeholder for calf keypoints -> retargeted clip. |

### Animating by hand

Select the CALFLAB armature, switch to **Pose Mode**, and rotate a bone: it
only turns about its joint axis and stops at the joint limits. Keyframe as
usual (I), then *Export action as reference clip*.

Conventions worth knowing:

* Lengths are millimetres in CALFLAB and metres in Blender; the add-on applies
  the 0.001 scale. Both are Z-up.
* The standing pose is the armature's rest pose, so every joint reads 0 when
  the robot stands. Angles are positive about the joint's axis as CALFLAB
  defines it (the add-on stores the sign per bone as `calflab_sign`).
* Bones are deliberately built **perpendicular to their joint axis**, so some
  do not point exactly at the next joint. That is what lets Blender hinge
  them about the true axis.
* The trunk's motion is carried by the armature *object* (location and
  quaternion rotation), not by a bone.

## Status (verified 2026-10-01 on Blender 5.2.2 LTS, headless, against a live server)

* Build: 19 bones, 57 meshes, limits and locks applied; a rebuild replaces
  rather than duplicates.
* Every one of the 18 hinges, rotated 20 degrees, turned exactly 20 degrees
  about its true joint axis.
* An imported 321-frame walking rollout placed hooves, shanks, neck, head and
  tail within **0.02 mm** of the simulator's positions at five sampled frames.
* Exporting that action back as a clip reproduced the simulator's joint angles
  exactly and the trunk trajectory within 0.004 mm.
* The extension installs with `--install`, is enabled, and registers its
  panel and operators in a normal Blender session.

Re-run that verification any time (after a Blender update, or after changing
the bridge) with the lab running:

```powershell
.\calflab.ps1 bridge blender --check
```

It leaves one clip named `zz-validation` in the project's motion library.

### The sidebar panel, clicked (2026-10-01, Blender 5.2.2)

```powershell
.\calflab.ps1 bridge blender --check-ui
```

starts Blender with its window and sends real mouse events to the installed
extension (`validate_ui_in_blender.py`; do not touch the mouse while it runs,
about a minute). It clicked the **CALFLAB** sidebar tab, found all four
buttons by clicking down the panel, then clicked *Build armature* (19 bones,
58 meshes), *Import simulation rollout* (321 frames) and *Export action as
reference clip* (one new 321-frame clip on the server). A screenshot of the
window is saved next to the report. It leaves a clip named `zz-ui-validation`
(numbered if repeated) in the motion library.

Known gap seen in that screenshot: in a new Blender file the default 2 m cube
hides the 0.6 m calf. Delete the cube (or open an empty file) first.

Not yet exercised: posing and keyframing by hand in Pose Mode, typing into the
Server / Clip name / Run id fields, and Blender 4.2-4.5.