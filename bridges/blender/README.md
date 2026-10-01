# CALFLAB bridge for Blender 4.x

## Install

```powershell
.\calflab.ps1 bridge blender     # writes bridges\blender\dist\calflab_blender.zip
```

In Blender: **Edit > Preferences > Add-ons > Install from Disk...**, pick the
zip, enable "CALFLAB bridge". The panel is in the 3D viewport sidebar (N) under
**CALFLAB**.

## What it does

| Button | Effect |
|---|---|
| Build armature from CALFLAB | One bone per joint, named by the joint's stable ID (`joint.fl.knee`). Joint limits become *Limit Rotation* constraints, and every bone is locked to its single hinge axis. Part meshes are parented to their bones. Rebuilding replaces the previous CALFLAB armature. |
| Export action as reference clip | Samples the armature's action (joint angles in degrees relative to the standing pose, plus the root trajectory, with fps and source metadata) into the project's motion library (`motions/`). Clips feed the Behave timeline and Phase 2 imitation rewards. |
| Import simulation rollout | Creates an action from a simulation run (empty run id = latest) for rendering and documentation. |
| Import video pose estimation | Placeholder for calf keypoints -> retargeted clip. |

Lengths are millimetres in CALFLAB and metres in Blender; the add-on applies
the 0.001 scale.

## Status

The armature plan and keyframe conversion are computed and tested in the core
(`calflab.bridge.blender`, `tests/test_bridges.py`). The add-on itself could
not be executed during Phase 1 because Blender was not found on this machine
(`calflab doctor` reports the path once it is installed or on PATH); treat the
first run as a test and report issues.
