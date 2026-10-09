#! python3
"""CalflabPush: send selected, edited geometry back to CALFLAB.

The geometry becomes a named *geometry override* on a body (for example a
sculpted head shell or skin surface). It is layered over the parametric
result, listed in the Properties panel, and can be toggled or removed there.

Pushed onto the Structure layer, a closed solid also gives the part its mass:
volume x the density of the material you name here (or of the object's
``calflab.material`` user text). An open object is shown but not used for
mass, and the command says so.
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
        material = rs.GetString(
            "Material of this solid (Enter = the part's material)", cr.guess_material(objects) or "Default", ["Default"] + choices
        )
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
