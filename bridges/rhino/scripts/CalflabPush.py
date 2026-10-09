#! python3
"""CalflabPush: send selected, edited geometry back to CALFLAB.

The geometry becomes a named *geometry override* on a body (for example a
sculpted head shell or skin surface). It is layered over the parametric
result, listed in the Properties panel, and can be toggled or removed there.

Pushed onto the Structure layer, a closed solid also gives the part its mass:
volume x the density of the object's ``calflab.material`` user text, or of
the material you name here if it has none. Several solids pushed together
are each weighed with their own material (PLA body, steel rods). An open
object is shown but not used for mass, and the command says so.

A solid printed with infill: give it the user text ``calflab.print.infill``
(percent), ``calflab.print.perimeters`` and ``calflab.print.line_width`` (mm).
It is then weighed as a shell of that wall thickness at full density plus the
core at the infill percentage, and the printout marks the mass as an infill
estimate. A solid without these tags is weighed fully dense.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr
import rhinoscriptsyntax as rs
import scriptcontext as sc


def main():
    ids = rs.GetObjects("Select geometry to push to CALFLAB", preselect=True)
    if not ids:
        return
    objects = [sc.doc.Objects.FindId(i) for i in ids]
    target = rs.GetString("Body this geometry replaces (stable ID)", cr.guess_target(objects) or "head")
    if not target:
        return
    layer = rs.GetString("CALFLAB layer to replace", "Skin", ["Skin", "Structure"])
    name = rs.GetString("Name of this override", "%s sculpt" % target)
    material = ""
    if (layer or "Skin") == "Structure":
        try:
            choices = cr.structure_materials()
        except cr.BridgeError as exc:
            print("CALFLAB: %s" % exc)
            return
        own = [cr.own_material(o) for o in objects]
        tagged = sorted(set(m for m in own if m))
        if tagged:
            # a solid is weighed with its own calflab.material; the prompt is only for solids without one
            print("CALFLAB: %d of %d solids carry their own calflab.material (%s)" % (
                len([m for m in own if m]), len(own), ", ".join(tagged)))
        if not all(own):
            prompt = "Material of the solids without calflab.material" if tagged else "Material of this solid"
            material = rs.GetString("%s (Enter = the part's material)" % prompt, "Default", ["Default"] + choices)
            if material is None:
                return
            if material.lower() == "default":
                material = ""
    try:
        r = cr.push(objects, target, name or "", layer or "Skin", material)
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    for line in cr.push_report(r, target):
        print(line)


main()
