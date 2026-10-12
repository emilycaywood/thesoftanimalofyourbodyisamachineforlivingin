#! python3
"""CalflabTag: write CALFLAB user text onto the selected solids in one go.

* Material: ``calflab.material`` (a structure material of the library).
* Foot: ``calflab.foot = yes`` for solids that touch the ground. The simulator
  then collides the ground with them instead of the lab's hoof sphere.
* Print settings: ``calflab.print.infill`` (percent), ``calflab.print.perimeters``
  and ``calflab.print.line_width`` (mm), for a solid printed with infill. Its
  mass is then an infill estimate; without them a solid is weighed fully dense.

Each prompt can be skipped with Enter; a skipped tag is left as it is. The same
tags can be typed by hand in Properties > Attribute User Text.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr

# Rhino keeps an imported module for the whole session: load this one again if its file has changed since
if getattr(cr, "_loaded_mtime", None) != os.path.getmtime(cr.__file__):
    import importlib

    cr = importlib.reload(cr)
    cr._loaded_mtime = os.path.getmtime(cr.__file__)
import rhinoscriptsyntax as rs
import scriptcontext as sc


def main():
    ids = rs.GetObjects("Select solids to tag for CALFLAB", preselect=True)
    if not ids:
        return
    objects = [sc.doc.Objects.FindId(i) for i in ids]
    try:
        choices = cr.structure_materials()
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    values = ask(choices)
    if not values:
        print("CALFLAB: nothing to tag.")
        return
    cr.set_user_text(objects, values)
    shown = ", ".join("%s = %s" % (k, "(removed)" if v is None else v) for k, v in sorted(values.items()))
    print("CALFLAB: tagged %d objects: %s" % (len(objects), shown))


def ask(choices):
    """The tags to write. Esc at any prompt stops asking and keeps the answers given so far."""
    values = {}
    material = rs.GetString("Material (Enter = leave as it is)", "Skip", ["Skip"] + choices)
    if material is None:
        return values
    if material.lower() != "skip":
        values["calflab.material"] = material
    foot = rs.GetString("Do these touch the ground as a foot? (Enter = leave as it is)", "Skip", ["Skip", "Yes", "No"])
    if foot is None:
        return values
    if foot.lower() == "yes":
        values["calflab.foot"] = "yes"
    elif foot.lower() == "no":
        values["calflab.foot"] = None
    printed = rs.GetString("Printed with infill? (Enter = leave as it is)", "Skip", ["Skip", "Yes", "FullyDense"])
    if printed is None:
        return values
    if printed.lower() == "yes":
        infill = rs.GetReal("Infill, percent")
        perimeters = rs.GetInteger("Perimeters (walls)")
        width = rs.GetReal("Line width, mm")
        if infill is None or perimeters is None or width is None:
            print("CALFLAB: print settings not completed, so none were written.")
            return values
        values.update({"calflab.print.infill": "%g" % infill, "calflab.print.perimeters": "%d" % perimeters,
                       "calflab.print.line_width": "%g" % width, "calflab.dense": None})
    elif printed.lower() == "fullydense":
        values.update({"calflab.print.infill": None, "calflab.print.perimeters": None, "calflab.print.line_width": None,
                       "calflab.dense": "yes"})
    return values


main()
