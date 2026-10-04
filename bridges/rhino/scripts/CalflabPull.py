#! python3
"""CalflabPull: fetch the current design as layered Rhino geometry.

Layers mirror the CALFLAB layers under a CALFLAB parent layer, repeated
components (actuators, boards) are block instances, and every object carries
its stable ID as user text (key: calflab.id). Pulling again replaces the
previous CALFLAB objects; your own geometry is never touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr


def main():
    try:
        s = cr.pull()
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    print(
        "CALFLAB: pulled revision %s: %d objects, %d blocks, %d layers, %d joint axes"
        % (s["revision"], s["objects"], s["blocks"], s["layers"], s["annotations"])
    )


main()
