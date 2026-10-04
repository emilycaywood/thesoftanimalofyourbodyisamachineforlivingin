#! python3
"""CalflabPush: send selected, edited geometry back to CALFLAB.

The geometry becomes a named *geometry override* on a body (for example a
sculpted head shell or skin surface). It is layered over the parametric
result, listed in the Properties panel, and can be toggled or removed there.
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
    try:
        r = cr.push(objects, target, name or "", layer or "Skin")
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    print("CALFLAB: pushed %d faces as override %s on %s" % (r["faces"], r["override"], target))


main()
