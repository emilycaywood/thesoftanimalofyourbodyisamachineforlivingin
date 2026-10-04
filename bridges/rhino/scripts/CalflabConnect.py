#! python3
"""CalflabConnect: point Rhino at a running CALFLAB server."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calflab_rhino as cr
import rhinoscriptsyntax as rs


def main():
    current = cr.load_settings().get("url", cr.DEFAULT_URL)
    url = rs.GetString("CALFLAB server URL", current)
    if url is None:
        return
    try:
        health = cr.connect(url or current)
    except cr.BridgeError as exc:
        print("CALFLAB: %s" % exc)
        return
    print("CALFLAB: connected to project '%s' (revision %s, v%s)" % (health["project"], health["revision"], health["version"]))


main()
