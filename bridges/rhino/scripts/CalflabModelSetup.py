#! python3
"""CalflabModelSetup: lay out the layers for modelling your own robot.

Creates ``CALFLAB::Model`` with one sublayer per body (``trunk``,
``leg.fl.thigh``, ``leg.fl.shank`` ...) and ``CALFLAB::Model::Joints`` with one
axis line per joint, placed where the pulled calf has it.

Then, in your own time:

* put each of your solids on the layer of the body it belongs to (sublayers
  of a body layer are fine);
* move and rotate each axis line onto your real joint axis: its direction is
  the axis, its midpoint is where the joint is;
* tag the solids that touch the ground as feet, and steel or silicone parts
  with their material (CalflabTag does both);
* type CalflabPushModel.

Running this again adds only what is missing; it never moves your lines.
CalflabPull does not touch anything on these layers.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr


def main():
    try:
        r = cr.model_setup()
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    layout = r["layout"]
    print("CALFLAB: layers under %s for %d bodies: %s" % (
        layout["root_layer"], len(layout["bodies"]), ", ".join(b["id"] for b in layout["bodies"])))
    if r["added"]:
        print("CALFLAB: added %d axis lines on %s (user text %s): %s" % (
            len(r["added"]), layout["joints_layer"], layout["joint_key"], ", ".join(r["added"])))
    if r["kept"]:
        print("CALFLAB: left your %d existing axis lines as they are: %s" % (len(r["kept"]), ", ".join(r["kept"])))
    print("CALFLAB: move each line onto your joint axis, put your solids on the body layers, then CalflabPushModel.")


main()
