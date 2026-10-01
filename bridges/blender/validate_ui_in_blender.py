"""Click through the CALFLAB sidebar panel in Blender's real UI:

    calflab bridge blender --check-ui       (the lab must be running, with a sim run)

Blender is started with a window and ``--enable-event-simulate``. The script
uses the *installed* extension, opens the 3D viewport sidebar, and then sends
real mouse events: it clicks down the tab strip until the CALFLAB tab is
active, clicks down the panel to find each button (it knows a button was hit
because that operator ran), and finally clicks Build armature, Import
simulation rollout and Export action as reference clip in that order and
checks what each one did. A screenshot of the window is saved next to the
JSON report. It leaves one clip named ``zz-ui-validation`` in the motion
library.
"""
import json
import os
import traceback
import urllib.request

import bpy

REPORT = os.environ.get("CALFLAB_BLENDER_REPORT") or os.path.join(bpy.app.tempdir, "calflab_blender_ui.json")
SHOT = os.path.splitext(REPORT)[0] + ".png"
CLIP = "zz-ui-validation"
BUTTONS = ("build_armature", "export_clip", "import_rollout", "import_pose_estimation")
report = {"ok": False, "blender": bpy.app.version_string}
calls = []


def view3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                return window, area, next(r for r in area.regions if r.type == "UI")
    raise RuntimeError("no 3D viewport in this Blender window")


def spy(name):
    """Record every run of an operator, however it was started."""
    cls = getattr(bpy.types, "CALFLAB_OT_" + name)
    original = cls.execute

    def execute(self, context):
        result = original(self, context)
        calls.append((name, sorted(result)))
        return result

    cls.execute = execute


def click(window, x, y):
    window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=int(x), y=int(y))
    window.event_simulate(type="LEFTMOUSE", value="PRESS", x=int(x), y=int(y))
    window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=int(x), y=int(y))


def escape(window):
    window.event_simulate(type="ESC", value="PRESS")
    window.event_simulate(type="ESC", value="RELEASE")


def clips(url):
    """Motion-library clips on the server: id -> frames."""
    with urllib.request.urlopen(url.rstrip("/") + "/api/motions", timeout=10) as resp:
        return {c["id"]: c.get("frames") for c in json.loads(resp.read().decode("utf-8"))}


def script():
    """A generator: each yield is the number of seconds to let Blender's event loop run."""
    window, area, sidebar = view3d()
    scene = window.scene
    system = bpy.context.preferences.system
    fac = system.ui_scale * system.pixel_size

    panel = getattr(bpy.types, "CALFLAB_PT_panel", None)
    assert panel is not None, "the CALFLAB extension is not enabled (calflab bridge blender --install)"
    report["extension"] = panel.__module__
    for name in BUTTONS:
        spy(name)
    scene.calflab_url = os.environ.get("CALFLAB_URL", scene.calflab_url)
    scene.calflab_clip_name = CLIP
    escape(window)  # the splash screen
    yield 0.5
    area.spaces.active.show_region_ui = True
    yield 0.5

    # ---- the CALFLAB tab: click down the tab strip until it is the active one
    window, area, sidebar = view3d()
    x_tab = sidebar.x + sidebar.width - 11 * fac
    y = sidebar.y + sidebar.height - 8 * fac
    while sidebar.active_panel_category != "CALFLAB" and y > sidebar.y:
        click(window, x_tab, y)
        yield 0.25
        y -= 14 * fac
    report["tab"] = sidebar.active_panel_category
    assert sidebar.active_panel_category == "CALFLAB", "could not click the CALFLAB tab"

    # ---- find the buttons: click down the panel (below its header) and see which operator runs
    x_mid = sidebar.x + (sidebar.width - 22 * fac) / 2
    y = sidebar.y + sidebar.height - 34 * fac
    found = {}
    while y > sidebar.y + 4 * fac and len(found) < len(BUTTONS):
        before = len(calls)
        click(window, x_mid, y)
        yield 0.6
        if len(calls) > before:
            found.setdefault(calls[-1][0], y)
            y -= 16 * fac
        else:
            escape(window)  # leave a text field if the click landed in one
            yield 0.15
            y -= 7 * fac
    report["buttons_found"] = sorted(found)
    assert set(found) == set(BUTTONS), "buttons not reached by clicking: %s" % sorted(set(BUTTONS) - set(found))

    # ---- now use them in the order a person would
    report["discovery"] = [list(c) for c in calls]

    def press(name, wait):
        """Click a button; a report popup left by the previous operator swallows
        one click, so dismiss it and click again if nothing ran."""
        before = len(calls)
        for _attempt in range(3):
            escape(window)
            yield 0.5
            click(window, x_mid, found[name])
            yield wait
            if len(calls) > before:
                break
        assert len(calls) > before and calls[-1] == (name, ["FINISHED"]), "%s did not finish when clicked" % name

    yield from press("build_armature", 2.0)
    arm = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    assert arm is not None, "Build armature made no armature"
    report["build_armature"] = {"bones": len(arm.data.bones), "meshes": len([o for o in scene.objects if o.type == "MESH"])}

    yield from press("import_rollout", 4.0)
    report["import_rollout"] = {"frames": scene.frame_end}
    assert scene.frame_end > 10, "the imported rollout has no frames"

    had = clips(scene.calflab_url)
    yield from press("export_clip", 3.0)
    new = {k: v for k, v in clips(scene.calflab_url).items() if k not in had}
    report["export_clip"] = {"new_clips": new}
    assert len(new) == 1 and list(new.values())[0] == scene.frame_end, "the click did not add the imported action as one clip"

    scene.frame_set(max(1, scene.frame_end // 3))
    yield 1.0
    with bpy.context.temp_override(window=window, area=area):
        bpy.ops.screen.screenshot(filepath=SHOT)
    report["screenshot"] = SHOT
    report["clicks"] = len(calls)
    report["ok"] = True


steps = script()


def tick():
    try:
        return next(steps)
    except StopIteration:
        pass
    except Exception:
        report["error"] = traceback.format_exc()
        report["calls"] = [list(c) for c in calls]
        try:
            window, area, _sidebar = view3d()
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.screen.screenshot(filepath=SHOT)
        except Exception:
            pass
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print("CALFLAB_BLENDER_UI_CHECK " + json.dumps(report))
    if not os.environ.get("CALFLAB_BLENDER_KEEP_OPEN"):
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=2.0)
