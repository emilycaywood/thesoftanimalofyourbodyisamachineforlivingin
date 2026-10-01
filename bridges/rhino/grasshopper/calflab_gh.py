#! python3
"""Source for the five CALFLAB Grasshopper components (GH Python 3, Rhino 8).

Each function below is the body of one "Python 3 Script" component. Create
the component, add the listed inputs/outputs, and paste the matching call (see
README.md in this folder). The functions only use the standard library and
``calflab_rhino`` (the shared Rhino bridge module), so nothing needs to be
installed in Rhino.

Alternatively use Hops components pointed at http://127.0.0.1:8000/hops/<name>.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
import calflab_rhino as cr


def get_design(refresh=True):
    """Inputs: refresh (bool).  Outputs: genome (JSON text), mass_g, revision."""
    scene = cr.request("/api/scene")
    return json.dumps(scene["genome"]["values"]), scene["mass"]["total_g"], scene.get("revision")


def set_genome_params(names, values):
    """Inputs: names (list of text), values (list of numbers).  Output: revision."""
    if not names or len(names) != len(values):
        return None
    cr.CLIENT = "grasshopper"
    r = cr.request("/api/commands/set_genes", {"values": dict(zip(names, [float(v) for v in values]))})
    return r["revision"]


def run_sim(run):
    """Input: run (bool; use a button).  Output: job id (asynchronous; poll with get_metrics)."""
    if not run:
        return None
    return cr.request("/api/commands/run_sim", {})["result"]["job"]


def get_metrics(job):
    """Input: job id.  Outputs: status, metrics (JSON text), run id."""
    if not job:
        return "no job", "{}", None
    j = cr.request("/api/jobs/%s" % job)
    metrics = dict(j["result"].get("metrics", {}))
    metrics.pop("by_actuator", None)
    return j["status"], json.dumps(metrics), j["result"].get("run_id")


def bake_to_rhino(bake):
    """Input: bake (bool; use a button).  Output: summary text.
    Bakes the current design into the Rhino document (same result as CalflabPull)."""
    if not bake:
        return "idle"
    s = cr.pull()
    return "revision %s: %d objects, %d blocks" % (s["revision"], s["objects"], s["blocks"])
