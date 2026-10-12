#! python3
"""CalflabPushModel: simulate your own modelled robot instead of the parametric calf.

Sends everything on the ``CALFLAB::Model`` layers (see CalflabModelSetup); no
selection is needed. CALFLAB then builds the simulated robot from it:

* joints where your axis lines are (the line's direction is the axis, its
  midpoint the joint's place);
* mass, centre of mass and inertia of each body from its solids, each with
  its own material and, if tagged, its infill estimate;
* collision from a convex hull of each solid, and the ground touches the
  solids tagged ``calflab.foot`` instead of the lab's hoof spheres.

All solids of one body are one rigid piece in the simulator, whether they
touch or not; only the joints move. Servos, board and battery still come from
the library. The genome and the Form sliders are not changed: the model is one
override ("Rhino model"), and switching it off brings the parametric calf back.

Nothing is stored unless every solid is closed, on a body layer and has a
material; the printout lists every problem at once. Choose Check to see the
report without changing anything.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr
import rhinoscriptsyntax as rs


def ask_missing(layout, solids):
    """Ask once for what untagged solids lack and write it onto them. False = cancelled."""
    untagged = [o for o in solids if not cr.own_material(o)]
    if untagged:
        choices = cr.structure_materials()
        material = rs.GetString("Material of the %d solids without calflab.material" % len(untagged), None, choices)
        if not material:
            return False
        cr.set_user_text(untagged, {"calflab.material": material})
        print("CALFLAB: wrote calflab.material = %s onto %d solids" % (material, len(untagged)))
    # print settings: asked once per material for the solids that say neither "infill" nor "fully dense"
    by_material = {}
    for obj in solids:
        if not cr.own_print(obj) and not obj.Attributes.GetUserString("calflab.dense"):
            by_material.setdefault(cr.own_material(obj), []).append(obj)
    for material in sorted(by_material):
        group = by_material[material]
        answer = rs.GetString("The %d %s solids without print tags: printed with infill, or fully dense?" % (len(group), material),
                              None, ["Infill", "FullyDense"])
        if not answer:
            return False
        if answer.lower() == "infill":
            infill = rs.GetReal("%s: infill, percent" % material)
            perimeters = rs.GetInteger("%s: perimeters (walls)" % material)
            width = rs.GetReal("%s: line width, mm" % material)
            if infill is None or perimeters is None or width is None:
                return False
            cr.set_user_text(group, {"calflab.print.infill": "%g" % infill, "calflab.print.perimeters": "%d" % perimeters,
                                     "calflab.print.line_width": "%g" % width})
            print("CALFLAB: wrote print tags (%g %%, %d x %g mm = %g mm wall) onto %d %s solids" % (
                infill, perimeters, width, perimeters * width, len(group), material))
        else:
            cr.set_user_text(group, {"calflab.dense": "yes"})
            print("CALFLAB: marked %d %s solids as fully dense (calflab.dense = yes)" % (len(group), material))
    return True


def main():
    try:
        layout, lines, solids = cr.collect_model()
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    if not lines and not solids:
        print("CALFLAB: nothing on %s yet. Type CalflabModelSetup first." % layout["root_layer"])
        return
    print("CALFLAB: found %d axis lines and %d solids on %s" % (len(lines), len(solids), layout["root_layer"]))
    mode = rs.GetString("Push the model to CALFLAB, or only check it?", "Push", ["Push", "Check"])
    if mode is None:
        return
    try:
        if not ask_missing(layout, solids):
            print("CALFLAB: cancelled; nothing was sent.")
            return
        print("CALFLAB: meshing and sending %d solids (large models take a minute or two) ..." % len(solids))
        reply = cr.push_model(check_only=mode.lower() == "check")
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    if reply.get("unprotected"):
        print("CALFLAB: removed calflab.id from %d objects on the model layers, so CalflabPull will not delete them" % reply["unprotected"])
    for line in reply["lines"]:
        print("CALFLAB: %s" % line)
    if reply.get("stored"):
        print("CALFLAB: press F5 in the web lab to simulate it. run.json of that run records this model under inputs.geometry.")


main()
