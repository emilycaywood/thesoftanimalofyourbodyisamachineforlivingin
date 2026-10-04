"""Numerical check of the CALFLAB Blender bridge, run inside Blender:

    calflab bridge blender --check          (the lab must be running)

or directly:

    blender --background --factory-startup --python validate_in_blender.py

It builds the armature, then verifies that (1) every hinge rotates about its
true joint axis, (2) an imported simulation rollout puts parts where the
simulator had them, and (3) exporting that action reproduces the joint angles
and trunk trajectory. It leaves one clip named ``zz-validation`` in the motion
library. Exit code 0 = pass.
"""
import json
import math
import os
import sys
import traceback

TOL_MM = 0.2
TOL_DEG = 0.05
PROBES = ["leg.fl.hoof", "leg.hr.hoof", "leg.fr.shank.tube", "head.shell", "neck.tube", "trunk.shell"]

report = {"ok": False}
try:
    import bpy
    from mathutils import Quaternion, Vector

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import calflab_blender as cb

    cb.register()
    ctx = bpy.context
    url = os.environ.get("CALFLAB_URL", ctx.scene.calflab_url)
    ctx.scene.calflab_url = url
    report["blender"] = bpy.app.version_string
    assert "FINISHED" in bpy.ops.calflab.build_armature(), "build_armature failed (is the lab running?)"
    arm = cb._find_armature(ctx)

    # 1. hinges
    plan = cb.request(url, "/api/bridge/blender/armature")
    axes = {b["name"]: b["joint"]["axis_world"] for b in plan["bones"] if b.get("joint")}
    worst_angle, worst_dot = 0.0, 1.0
    for pb in cb._hinge_bones(arm):
        rest = (arm.matrix_world @ pb.bone.matrix_local).to_quaternion()
        setattr(pb.rotation_euler, pb["calflab_axis"].lower(), math.radians(20.0) * pb["calflab_sign"])
        ctx.view_layer.update()
        delta = (arm.matrix_world @ pb.matrix).to_quaternion() @ rest.inverted()
        axis, angle = delta.to_axis_angle()
        dot = axis.dot(Vector(axes[pb.name]).normalized())
        if dot < 0 and angle > math.pi:
            dot, angle = -dot, 2 * math.pi - angle
        worst_angle = max(worst_angle, abs(math.degrees(angle) - 20.0))
        worst_dot = min(worst_dot, dot)
        setattr(pb.rotation_euler, pb["calflab_axis"].lower(), 0.0)
    ctx.view_layer.update()
    report["hinges"] = {"bones": len(axes), "worst_angle_error_deg": round(worst_angle, 4), "worst_axis_dot": round(worst_dot, 5)}

    # 2. rollout
    runs = cb.request(url, "/api/runs?kind=sim&limit=1")
    assert runs, "no simulation run in the project: press F5 in the lab first"
    run_id = runs[0]["id"]
    ctx.scene.calflab_run_id = run_id
    assert "FINISHED" in bpy.ops.calflab.import_rollout(), "import_rollout failed"
    roll = cb.request(url, "/api/runs/%s/rollout" % run_id, timeout=120)
    geoms = {}
    for body in roll["scene"]["bodies"]:
        for g in body["geoms"]:
            geoms[g["id"]] = (roll["body_ids"].index(body["id"]), g["pos"])
    n = len(roll["t"])
    worst = 0.0
    for frame in sorted({1, n // 4, n // 2, (3 * n) // 4, n}):
        ctx.scene.frame_set(frame)
        ctx.view_layer.update()
        for gid in PROBES:
            if gid not in geoms or gid not in bpy.data.objects:
                continue
            k, lp = geoms[gid]
            p = Vector(roll["pos"][frame - 1][3 * k: 3 * k + 3])
            q = Quaternion(roll["quat"][frame - 1][4 * k: 4 * k + 4])
            expected = (p + q @ Vector(lp)) * 0.001
            worst = max(worst, (bpy.data.objects[gid].matrix_world.translation - expected).length * 1000.0)
    report["rollout"] = {"run": run_id, "frames": n, "worst_error_mm": round(worst, 4)}

    # 3. clip round trip
    ctx.scene.calflab_clip_name = "zz-validation"
    assert "FINISHED" in bpy.ops.calflab.export_clip(), "export_clip failed"
    clips = [c for c in cb.request(url, "/api/motions") if c["id"].startswith("zz-validation")]
    clip = cb.request(url, "/api/motions/" + sorted(clips, key=lambda c: c["created"])[-1]["id"])
    src = cb.request(url, "/api/bridge/blender/rollout/%s" % run_id, timeout=120)
    jerr = max(abs(a - b) for jid, vals in src["joints"].items() for a, b in zip(vals, clip["joints"][jid]))
    rerr = max((Vector(a) - Vector(b)).length for a, b in zip(src["root_pos"], clip["root_pos"]))
    report["clip"] = {"max_joint_error_deg": round(jerr, 4), "max_root_error_mm": round(rerr, 4)}

    report["ok"] = (
        worst_angle < TOL_DEG and worst_dot > 0.9999 and worst < TOL_MM and jerr < TOL_DEG and rerr < TOL_MM
    )
except Exception:
    report["error"] = traceback.format_exc()

print("CALFLAB_BLENDER_CHECK " + json.dumps(report))
sys.exit(0 if report["ok"] else 1)
