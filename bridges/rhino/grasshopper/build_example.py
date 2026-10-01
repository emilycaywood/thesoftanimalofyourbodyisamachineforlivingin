#! python3
"""Build calflab_example.gh and test it against a live lab, inside Rhino 8.

    calflab bridge rhino --grasshopper      (the lab must be running)

Grasshopper files are binary, so the example is generated here instead of
being edited by hand: five "Python 3 Script" components whose bodies call
``calflab_gh`` (GetDesign, SetGenomeParams, RunSim, GetMetrics, BakeToRhino),
with a slider, toggles, buttons, a 1 s trigger and panels around them.

Before saving, the definition is solved for real: GetDesign must report the
server's mass, SetGenomeParams must change a gene on the server, RunSim +
GetMetrics must return a finished run, BakeToRhino must put the design in the
Rhino document. The gene edit is undone afterwards. Use a scratch project.
"""
import json
import os
import sys
import time
import traceback

import Rhino
import System

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "calflab_example.gh")
REPORT = os.environ.get("CALFLAB_RHINO_REPORT") or os.path.join(os.environ.get("TEMP", HERE), "calflab_gh_check.json")
GENE = "shank_length"
GH_PLUGIN = System.Guid("b45a29b1-4343-4035-989e-044e8580d9cf")

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import calflab_rhino as cr  # noqa: E402

HEADER = (
    "import os, sys\n"
    "sys.path.insert(0, os.path.dirname(ghenv.Component.OnPingDocument().FilePath))\n"
    "import calflab_gh as gh\n"
)
# name: (inputs [(name, is_list)], outputs, body)
COMPONENTS = {
    "GetDesign": ([("refresh", False)], ["genome", "mass_g", "revision"],
                  "genome, mass_g, revision = gh.get_design(refresh)\n"),
    "SetGenomeParams": ([("names", True), ("values", True), ("apply", False)], ["revision"],
                        "revision = gh.set_genome_params(names, values) if apply else None\n"),
    "RunSim": ([("run", False)], ["job"], "job = gh.run_sim(run)\n"),
    "GetMetrics": ([("job", False)], ["status", "metrics", "run_id"],
                   "status, metrics, run_id = gh.get_metrics(job)\n"),
    "BakeToRhino": ([("bake", False)], ["summary"], "summary = gh.bake_to_rhino(bake)\n"),
}
NOTE = (
    "CALFLAB example\n"
    "1. Start the lab:  .\\calflab.ps1 lab\n"
    "2. GetDesign shows the genome and mass.\n"
    "3. Move the slider, then switch 'apply' on: the gene changes in every client.\n"
    "4. Press 'run': RunSim starts a simulation, GetMetrics polls it once a second.\n"
    "5. Press 'bake': the design is built in the Rhino document (same as CalflabPull)."
)


def first_value(param):
    data = list(param.VolatileData.AllData(True))
    if not data:
        return None
    v = data[0]
    return getattr(v, "Value", v)


def messages(comp):
    from Grasshopper.Kernel import GH_RuntimeMessageLevel as L

    return [str(m) for level in (L.Error, L.Warning) for m in comp.RuntimeMessages(level)]


def build():
    import clr

    clr.AddReference("Grasshopper")
    import Grasshopper
    from Grasshopper.Kernel import GH_Document, GH_DocumentIO, GH_ParamAccess, GH_ParameterSide

    server = Grasshopper.Instances.ComponentServer
    proxies = {str(p.Desc.Name): p.Guid for p in server.ObjectProxies if not p.Obsolete}
    doc = GH_Document()
    doc.FilePath = OUT  # the component bodies find calflab_gh.py next to the definition
    Grasshopper.Instances.DocumentServer.AddDocument(doc)

    def emit(name, x, y, nick=None):
        obj = server.EmitObject(proxies[name])
        obj.CreateAttributes()
        obj.Attributes.Pivot = System.Drawing.PointF(float(x), float(y))
        if nick:
            obj.NickName = nick
        doc.AddObject(obj, False)
        return obj

    def script(name, x, y):
        inputs, outputs, body = COMPONENTS[name]
        comp = emit("Python 3 Script", x, y, name)
        comp.SetSource(HEADER + body)
        for side, names, params, first in (
            (GH_ParameterSide.Input, [n for n, _ in inputs], comp.Params.Input, 0),
            (GH_ParameterSide.Output, outputs, comp.Params.Output, 1),  # output 0 is "out" (stdout)
        ):
            while params.Count - first > len(names):
                if side == GH_ParameterSide.Input:
                    comp.Params.UnregisterInputParameter(params[params.Count - 1])
                else:
                    comp.Params.UnregisterOutputParameter(params[params.Count - 1])
            while params.Count - first < len(names):
                p = comp.CreateParameter(side, params.Count)
                if side == GH_ParameterSide.Input:
                    comp.Params.RegisterInputParam(p)
                else:
                    comp.Params.RegisterOutputParam(p)
            for i, n in enumerate(names):
                params[first + i].Name = params[first + i].NickName = n
        for i, (_n, is_list) in enumerate(inputs):
            comp.Params.Input[i].Access = GH_ParamAccess.list if is_list else GH_ParamAccess.item
        comp.VariableParameterMaintenance()
        comp.Params.OnParametersChanged()
        return comp

    def panel(x, y, nick, text="", source=None, w=260, h=90):
        p = emit("Panel", x, y, nick)
        p.UserText = text
        p.Attributes.Bounds = System.Drawing.RectangleF(float(x), float(y), float(w), float(h))
        if source is not None:
            p.AddSource(source)
        return p

    def toggle(x, y, nick, value):
        t = emit("Boolean Toggle", x, y, nick)
        t.Value = value
        return t

    value = float(cr.request("/api/scene")["genome"]["values"][GENE])

    panel(20, 20, "Read me", NOTE, w=470, h=120)
    refresh = toggle(20, 190, "refresh", True)
    get_design = script("GetDesign", 220, 180)
    get_design.Params.Input[0].AddSource(refresh)
    panel(480, 160, "genome", source=get_design.Params.Output[1], h=120)
    panel(480, 290, "mass_g", source=get_design.Params.Output[2], h=40)

    names = panel(20, 380, "names", GENE, w=150, h=40)
    slider = emit("Number Slider", 20, 440, GENE)
    slider.Slider.Minimum = System.Decimal(100.0)
    slider.Slider.Maximum = System.Decimal(240.0)
    slider.Slider.DecimalPlaces = 0
    slider.SetSliderValue(System.Decimal(value))
    apply = toggle(20, 480, "apply", False)
    set_genes = script("SetGenomeParams", 300, 400)
    for i, src in enumerate((names, slider, apply)):
        set_genes.Params.Input[i].AddSource(src)
    panel(560, 400, "revision", source=set_genes.Params.Output[1], h=40)

    run_toggle = toggle(20, 580, "run (test)", False)
    run_sim = script("RunSim", 220, 570)
    run_sim.Params.Input[0].AddSource(run_toggle)
    get_metrics = script("GetMetrics", 420, 570)
    get_metrics.Params.Input[0].AddSource(run_sim.Params.Output[1])
    panel(680, 540, "status", source=get_metrics.Params.Output[1], h=40)
    panel(680, 590, "metrics", source=get_metrics.Params.Output[2], h=160)

    bake_toggle = toggle(20, 800, "bake (test)", False)
    bake = script("BakeToRhino", 220, 790)
    bake.Params.Input[0].AddSource(bake_toggle)
    panel(480, 790, "summary", source=bake.Params.Output[1], h=40)

    comps = {"GetDesign": get_design, "SetGenomeParams": set_genes, "RunSim": run_sim,
             "GetMetrics": get_metrics, "BakeToRhino": bake}
    rep = {"grasshopper": str(Grasshopper.Versioning.Version)}

    def solve(expire=None):
        if expire is not None:
            expire.ExpireSolution(False)
        doc.NewSolution(expire is None)
        errors = {n: messages(c) for n, c in comps.items() if messages(c)}
        assert not errors, "component errors: %s" % errors

    # ---- GetDesign
    doc.Enabled = True
    solve()
    scene = cr.request("/api/scene")
    mass = float(first_value(get_design.Params.Output[2]))
    genome = json.loads(str(first_value(get_design.Params.Output[1])))
    rep["get_design"] = {"mass_g": round(mass, 1), "genes": len(genome)}
    assert abs(mass - scene["mass"]["total_g"]) < 0.01 and genome[GENE] == value, "GetDesign disagrees with the server"
    assert first_value(set_genes.Params.Output[1]) is None, "SetGenomeParams ran although 'apply' is off"

    # ---- SetGenomeParams
    slider.SetSliderValue(System.Decimal(value + 15.0))
    apply.Value = True
    apply.ExpireSolution(False)
    solve(slider)
    got = float(cr.request("/api/scene")["genome"]["values"][GENE])
    rep["set_genome_params"] = {"gene": GENE, "sent": value + 15.0, "server": got,
                                "revision": int(first_value(set_genes.Params.Output[1]))}
    assert abs(got - (value + 15.0)) < 1e-6, "SetGenomeParams did not change the gene on the server"
    apply.Value = False
    slider.SetSliderValue(System.Decimal(value))
    apply.ExpireSolution(False)
    solve(slider)
    cr.request("/api/undo", {})
    assert float(cr.request("/api/scene")["genome"]["values"][GENE]) == value

    # ---- RunSim + GetMetrics (polled the way the trigger does)
    run_toggle.Value = True
    solve(run_toggle)
    job = str(first_value(run_sim.Params.Output[1]))
    run_toggle.Value = False
    t0, status = time.time(), ""
    while time.time() - t0 < 120.0:
        solve(get_metrics)
        status = str(first_value(get_metrics.Params.Output[1]))
        if status in ("done", "failed", "cancelled"):
            break
        time.sleep(0.5)
    metrics = json.loads(str(first_value(get_metrics.Params.Output[2])))
    rep["run_sim"] = {"job": job, "status": status, "seconds": round(time.time() - t0, 1),
                      "run_id": str(first_value(get_metrics.Params.Output[3])), "speed_mps": metrics.get("speed_mps")}
    assert status == "done" and metrics.get("speed_mps") is not None, "the simulation did not finish through Grasshopper"

    # ---- BakeToRhino
    bake_toggle.Value = True
    solve(bake_toggle)
    rdoc = Rhino.RhinoDoc.ActiveDoc
    baked = len([o for o in rdoc.Objects if o.Attributes.GetUserString(cr.ID_KEY)])
    rep["bake_to_rhino"] = {"summary": str(first_value(bake.Params.Output[1])), "rhino_objects": baked}
    assert baked > 50, "BakeToRhino did not build the design in Rhino"

    # ---- ship it with buttons instead of the test toggles, and a trigger on GetMetrics
    for old, target, x, y, nick in ((run_toggle, run_sim, 20, 580, "run"), (bake_toggle, bake, 20, 800, "bake")):
        target.Params.Input[0].RemoveAllSources()
        doc.RemoveObject(old, False)
        button = emit("Button", x, y, nick)
        target.Params.Input[0].AddSource(button)
    timer = emit("Trigger", 420, 520)
    timer.Interval = 1000
    timer.AddTarget(get_metrics.InstanceGuid)
    doc.Enabled = False  # nothing runs while saving
    ok = GH_DocumentIO(doc).SaveQuiet(OUT)
    rep["saved"] = {"file": OUT, "ok": bool(ok), "bytes": os.path.getsize(OUT) if os.path.isfile(OUT) else 0,
                    "objects": int(doc.ObjectCount)}
    assert ok and rep["saved"]["bytes"] > 0, "the definition could not be saved"

    # ---- reopen what was saved
    io = GH_DocumentIO()
    assert io.Open(OUT), "the saved definition does not open"
    kinds = {}
    for o in io.Document.Objects:
        kinds[str(o.Name)] = kinds.get(str(o.Name), 0) + 1
        if str(o.Name) == "Python 3 Script":
            inputs, outputs, body = COMPONENTS[str(o.NickName)]
            found, source = o.TryGetSource()
            assert found and str(source).replace("\r\n", "\n") == HEADER + body, "%s lost its script" % o.NickName
            assert [str(p.NickName) for p in o.Params.Input] == [n for n, _ in inputs], "%s lost its inputs" % o.NickName
            assert [str(p.NickName) for p in o.Params.Output][1:] == outputs, "%s lost its outputs" % o.NickName
            assert all(p.SourceCount == 1 for p in o.Params.Input), "%s lost a wire" % o.NickName
    rep["reopened"] = kinds
    assert kinds.get("Python 3 Script") == 5 and kinds.get("Button") == 2
    return rep


def main():
    rep = {"ok": False}
    try:
        rep["rhino"] = str(Rhino.RhinoApp.Version)
        assert Rhino.PlugIns.PlugIn.LoadPlugIn(GH_PLUGIN), "Grasshopper could not be loaded"
        rep.update(build())
        rep["ok"] = True
    except Exception:
        rep["error"] = traceback.format_exc()
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    print("CALFLAB_GH_CHECK " + json.dumps(rep))
    if not os.environ.get("CALFLAB_RHINO_KEEP_OPEN"):
        Rhino.RhinoDoc.ActiveDoc.Modified = False
        Rhino.RhinoApp.Exit()


main()
