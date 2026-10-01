#! python3
"""CalflabLiveSync: toggle live updates.

While on, Rhino polls the CALFLAB server about once a second while idle and
re-pulls the design whenever its revision changes (an edit in the web app,
Blender, a notebook...). Run the command again to turn it off.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr
import Rhino
import scriptcontext as sc

KEY = "calflab.livesync"


def _on_idle(sender, args):
    state = sc.sticky.get(KEY)
    if not state or time.time() - state["last"] < 1.0:
        return
    state["last"] = time.time()
    try:
        revision = cr.request("/api/health", timeout=0.4)["revision"]
    except cr.BridgeError:
        return
    if revision != state["revision"]:
        state["revision"] = revision
        try:
            cr.pull()
            print("CALFLAB: live sync pulled revision %s" % revision)
        except Exception as exc:  # never let an error escape into Rhino's idle loop
            print("CALFLAB: live sync could not pull revision %s: %s" % (revision, exc))


def main():
    state = sc.sticky.get(KEY)
    if state:
        Rhino.RhinoApp.Idle -= state["handler"]
        sc.sticky[KEY] = None
        print("CALFLAB: live sync OFF")
        return
    try:
        revision = cr.request("/api/health")["revision"]
        cr.pull()
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    sc.sticky[KEY] = {"handler": _on_idle, "revision": revision, "last": time.time()}
    Rhino.RhinoApp.Idle += _on_idle
    print("CALFLAB: live sync ON (revision %s). Run CalflabLiveSync again to stop." % revision)


main()
