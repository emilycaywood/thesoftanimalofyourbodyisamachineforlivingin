"""CALFLAB bridge for Blender 4.x.

Builds an armature from the current RobotSpec (one bone per joint, named by the
joint's stable ID, joint limits as bone constraints, part meshes parented to
bones), exports Blender actions to the CALFLAB motion library, and imports
simulation rollouts as actions.

The add-on is thin: the CALFLAB server sends an explicit armature plan and
keyframes. Only the Python standard library and bpy are used.
"""

import json
import math
import urllib.error
import urllib.request

import bpy
from mathutils import Matrix, Quaternion, Vector

bl_info = {
    "name": "CALFLAB bridge",
    "author": "CALFLAB",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > CALFLAB",
    "description": "Armature from the CALFLAB RobotSpec, motion clip export, rollout import",
    "category": "Rigging",
}

CLIENT = "blender"


class BridgeError(Exception):
    pass


def request(url, path, body=None, timeout=30.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + path, data=data, method="GET" if body is None else "POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-calflab-client", CLIENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
        except ValueError:
            message = str(exc)
        raise BridgeError(message)
    except (urllib.error.URLError, OSError) as exc:
        raise BridgeError("No CALFLAB server at %s (%s). Start it with: calflab lab" % (url, exc))


def _url(context):
    return context.scene.calflab_url


# ---------------------------------------------------------------------- armature
def _hinge_axis_name(bone_vec, axis_world):
    """Which local bone axis carries the hinge: 'Y' if the joint axis runs along
    the bone, otherwise 'Z' (the bone is rolled so local Z = joint axis)."""
    if bone_vec.length == 0:
        return "Z"
    return "Y" if abs(bone_vec.normalized().dot(Vector(axis_world).normalized())) > 0.9 else "Z"


def _primitive_mesh(name, shape, size, scale):
    """A mesh datablock for a primitive in its local frame (axis +Z), scaled to Blender units."""
    import bmesh

    a, b, c = (float(v) * scale for v in size)
    bm = bmesh.new()
    if shape == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(a, b, c), verts=bm.verts)
    elif shape == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=a)
    elif shape == "ellipsoid":
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
        bmesh.ops.scale(bm, vec=(a, b, c), verts=bm.verts)
    else:  # cylinder / capsule (capsule = cylinder with hemispherical ends)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=a, radius2=a, depth=b)
        if shape == "capsule":
            for z in (b / 2.0, -b / 2.0):
                bmesh.ops.create_uvsphere(
                    bm, u_segments=24, v_segments=12, radius=a, matrix=Matrix.Translation((0.0, 0.0, z))
                )
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _matrix(xform, scale):
    m = Matrix([list(row) for row in xform])
    m.translation = m.translation * scale
    return m


def _remove_existing(name):
    """Delete a previous CALFLAB armature and its meshes so a rebuild is clean."""
    old = bpy.data.objects.get(name)
    if old is None:
        return
    for child in list(old.children):
        bpy.data.objects.remove(child, do_unlink=True)
    bpy.data.objects.remove(old, do_unlink=True)


def build_armature(context, plan):
    scale = float(plan.get("scale_to_blender", 0.001))
    name = "CALFLAB_%s" % plan.get("name", "robot")
    _remove_existing(name)
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    context.collection.objects.link(arm)
    arm["calflab_revision"] = plan.get("revision", 0)
    context.view_layer.objects.active = arm
    arm.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    axis_names = {}
    for b in plan["bones"]:
        eb = arm_data.edit_bones.new(b["name"])
        eb.head = Vector(b["head"]) * scale
        eb.tail = Vector(b["tail"]) * scale
        joint = b.get("joint")
        if joint:
            axis = Vector(joint["axis_world"])
            axis_names[b["name"]] = _hinge_axis_name(eb.tail - eb.head, axis)
            if axis_names[b["name"]] == "Z":
                eb.align_roll(axis)
    for b in plan["bones"]:
        if b.get("parent"):
            arm_data.edit_bones[b["name"]].parent = arm_data.edit_bones[b["parent"]]
    bpy.ops.object.mode_set(mode="POSE")

    for b in plan["bones"]:
        joint = b.get("joint")
        if not joint:
            continue
        pb = arm.pose.bones[b["name"]]
        ax = axis_names[b["name"]]
        pb.rotation_mode = "XYZ"
        pb.lock_location = (True, True, True)
        pb.lock_rotation = (ax != "X", ax != "Y", ax != "Z")
        pb["calflab_axis"] = ax
        pb["calflab_rest_deg"] = joint["rest_deg"]
        lo, hi = (math.radians(v) for v in joint["range_deg"])
        con = pb.constraints.new("LIMIT_ROTATION")
        con.name = "CALFLAB joint limit"
        con.owner_space = "LOCAL"
        con.use_limit_x = con.use_limit_y = con.use_limit_z = True
        con.min_x = con.max_x = con.min_y = con.max_y = con.min_z = con.max_z = 0.0
        setattr(con, "min_%s" % ax.lower(), lo)
        setattr(con, "max_%s" % ax.lower(), hi)
    bpy.ops.object.mode_set(mode="OBJECT")

    for m in plan["meshes"]:
        obj = bpy.data.objects.new(m["id"], _primitive_mesh(m["id"], m["shape"], m["size"], scale))
        context.collection.objects.link(obj)
        world = _matrix(m["xform"], scale)
        obj.parent = arm
        obj.parent_type = "BONE"
        obj.parent_bone = m["bone"]
        obj.matrix_world = world
        obj["calflab_id"] = m["id"]
        obj["calflab_layer"] = m["layer"]
        if m["layer"] == "Skin":
            obj.display_type = "WIRE"
    return arm


def _find_armature(context):
    obj = context.active_object
    if obj is not None and obj.type == "ARMATURE" and obj.name.startswith("CALFLAB_"):
        return obj
    for o in context.scene.objects:
        if o.type == "ARMATURE" and o.name.startswith("CALFLAB_"):
            return o
    return None


def _hinge_bones(arm):
    return [pb for pb in arm.pose.bones if "calflab_axis" in pb.keys()]


# ---------------------------------------------------------------------- clips
def action_to_clip(context, arm, name):
    """Sample the armature's current action into a CALFLAB motion clip."""
    scene = context.scene
    action = arm.animation_data.action if arm.animation_data else None
    if action is None:
        raise BridgeError("The CALFLAB armature has no action to export.")
    start, end = (int(round(v)) for v in action.frame_range)
    fps = scene.render.fps / scene.render.fps_base
    bones = _hinge_bones(arm)
    joints = {pb.name: [] for pb in bones}
    root_pos, root_quat = [], []
    rest = arm.matrix_world.copy()
    current = scene.frame_current
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        for pb in bones:
            angle = getattr(pb.rotation_euler, pb["calflab_axis"].lower())
            joints[pb.name].append(round(math.degrees(angle), 4))
        loc, rot, _ = arm.matrix_world.decompose()
        root_pos.append([round(v * 1000.0, 3) for v in loc])
        root_quat.append([round(v, 6) for v in rot])
    scene.frame_set(current)
    _ = rest
    return {
        "name": name or action.name,
        "fps": fps,
        "joints": joints,
        "root_pos": root_pos,
        "root_quat": root_quat,
        "source": "blender",
        "meta": {"blend_file": bpy.data.filepath, "action": action.name, "frame_range": [start, end]},
    }


def keyframes_to_action(context, arm, data):
    """Create an action from rollout keyframes (joint angles relative to rest, root trajectory)."""
    scale = 0.001
    action = bpy.data.actions.new("CALFLAB_%s" % data.get("run_id", "rollout"))
    arm.animation_data_create()
    arm.animation_data.action = action
    context.scene.render.fps = int(round(data["fps"]))
    arm.rotation_mode = "QUATERNION"
    bones = {pb.name: pb for pb in _hinge_bones(arm)}
    origin = Vector(data["root_pos"][0]) * scale if data["root_pos"] else Vector()
    base = arm.location.copy()
    for i in range(data["frames"]):
        frame = i + 1
        for jid, values in data["joints"].items():
            pb = bones.get(jid)
            if pb is None:
                continue
            setattr(pb.rotation_euler, pb["calflab_axis"].lower(), math.radians(values[i]))
            pb.keyframe_insert("rotation_euler", frame=frame)
        if data["root_pos"]:
            p = Vector(data["root_pos"][i]) * scale
            arm.location = base + Vector((p.x - origin.x, p.y - origin.y, p.z - origin.z))
            arm.keyframe_insert("location", frame=frame)
        if data["root_quat"]:
            arm.rotation_quaternion = Quaternion(data["root_quat"][i])
            arm.keyframe_insert("rotation_quaternion", frame=frame)
    context.scene.frame_start = 1
    context.scene.frame_end = max(1, data["frames"])
    return action


# ---------------------------------------------------------------------- operators
class CALFLAB_OT_build_armature(bpy.types.Operator):
    bl_idname = "calflab.build_armature"
    bl_label = "Build armature from CALFLAB"
    bl_description = "Fetch the current design and build an armature with one bone per joint"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            plan = request(_url(context), "/api/bridge/blender/armature")
            arm = build_armature(context, plan)
        except BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "CALFLAB: %d bones, %d meshes (revision %s)" % (
            len(plan["bones"]), len(plan["meshes"]), arm["calflab_revision"]))
        return {"FINISHED"}


class CALFLAB_OT_export_clip(bpy.types.Operator):
    bl_idname = "calflab.export_clip"
    bl_label = "Export action as reference clip"
    bl_description = "Send the armature's action to the CALFLAB motion library"

    def execute(self, context):
        arm = _find_armature(context)
        if arm is None:
            self.report({"ERROR"}, "No CALFLAB armature in the scene. Build one first.")
            return {"CANCELLED"}
        try:
            clip = action_to_clip(context, arm, context.scene.calflab_clip_name)
            r = request(_url(context), "/api/motions", clip)
        except BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "CALFLAB: clip '%s' saved (%d frames)" % (r["id"], r["frames"]))
        return {"FINISHED"}


class CALFLAB_OT_import_rollout(bpy.types.Operator):
    bl_idname = "calflab.import_rollout"
    bl_label = "Import simulation rollout"
    bl_description = "Import a CALFLAB simulation run as an action (empty run id = latest)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = _find_armature(context)
        if arm is None:
            self.report({"ERROR"}, "No CALFLAB armature in the scene. Build one first.")
            return {"CANCELLED"}
        try:
            run_id = context.scene.calflab_run_id.strip()
            if not run_id:
                runs = request(_url(context), "/api/runs?kind=sim&limit=1")
                if not runs:
                    raise BridgeError("No simulation runs yet. Run one in the lab first.")
                run_id = runs[0]["id"]
            data = request(_url(context), "/api/bridge/blender/rollout/%s" % run_id, timeout=120.0)
            keyframes_to_action(context, arm, data)
        except BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "CALFLAB: imported run %s (%d frames)" % (run_id, data["frames"]))
        return {"FINISHED"}


class CALFLAB_OT_import_pose_estimation(bpy.types.Operator):
    bl_idname = "calflab.import_pose_estimation"
    bl_label = "Import video pose estimation (planned)"
    bl_description = "Placeholder: calf keypoints from video -> retargeted reference clip"

    def execute(self, context):
        self.report({"WARNING"}, "Planned: keypoints -> retargeted clip (see calflab.bridge.blender.retarget_keypoints).")
        return {"CANCELLED"}


class CALFLAB_PT_panel(bpy.types.Panel):
    bl_label = "CALFLAB"
    bl_idname = "CALFLAB_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CALFLAB"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "calflab_url")
        layout.operator(CALFLAB_OT_build_armature.bl_idname, icon="ARMATURE_DATA")
        box = layout.box()
        box.label(text="Reference motion")
        box.prop(context.scene, "calflab_clip_name")
        box.operator(CALFLAB_OT_export_clip.bl_idname, icon="EXPORT")
        box = layout.box()
        box.label(text="Simulation")
        box.prop(context.scene, "calflab_run_id")
        box.operator(CALFLAB_OT_import_rollout.bl_idname, icon="IMPORT")
        layout.operator(CALFLAB_OT_import_pose_estimation.bl_idname, icon="CAMERA_DATA")


CLASSES = (
    CALFLAB_OT_build_armature,
    CALFLAB_OT_export_clip,
    CALFLAB_OT_import_rollout,
    CALFLAB_OT_import_pose_estimation,
    CALFLAB_PT_panel,
)


def register():
    bpy.types.Scene.calflab_url = bpy.props.StringProperty(
        name="Server", default="http://127.0.0.1:8000", description="CALFLAB server URL")
    bpy.types.Scene.calflab_clip_name = bpy.props.StringProperty(
        name="Clip name", default="", description="Name in the motion library (default: action name)")
    bpy.types.Scene.calflab_run_id = bpy.props.StringProperty(
        name="Run id", default="", description="Simulation run to import (empty = latest)")
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.calflab_url
    del bpy.types.Scene.calflab_clip_name
    del bpy.types.Scene.calflab_run_id
