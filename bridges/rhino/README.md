# CALFLAB bridge for Rhino 8 and Grasshopper

The bridge is thin on purpose: the CALFLAB server computes an explicit build
list and Rhino follows it. All scripts use only the Python standard library
and RhinoCommon.

## Install the commands (once)

1. Start the lab: `.\calflab.ps1 lab`
2. In Rhino 8, run (the exact path is printed by `.\calflab.ps1 bridge rhino`):

   ```
   _-ScriptEditor _Run "<repo>\bridges\rhino\scripts\CalflabInstall.py"
   ```

   This registers four aliases, which you then type like commands.

| Command | What it does |
|---|---|
| `CalflabConnect` | Set/check the server URL (default `http://127.0.0.1:8000`) |
| `CalflabPull` | Fetch the current design as layered geometry. Layers: `CALFLAB::Structure`, `::Actuators`, `::Transmission`, `::Electronics`, `::Sensors`, `::Skin`, `::Harness`, `::Annotations`. Repeated components are block instances (`calflab.<component>`). Every object has user text `calflab.id` (stable ID), `calflab.body`, `calflab.layer`, and for components `calflab.component` and `calflab.verified`. |
| `CalflabPush` | Send selected geometry (mesh, Brep, extrusion or SubD) back as a named **geometry override** on a body, e.g. a sculpted head shell or skin surface. It shows up in the web app's Properties and can be toggled or removed there. |
| `CalflabLiveSync` | Toggle live updates: Rhino re-pulls whenever the design changes in any client. |

Pulling again replaces only objects that carry `calflab.id`; your own geometry
is left alone. Sculpt on your own layer, then `CalflabPush` it.

## Grasshopper

Two options, both talking to the same server:

**A. Hops** (no scripting). Drop a Hops component and set its path to one of:

```
http://127.0.0.1:8000/hops/getdesign
http://127.0.0.1:8000/hops/setgenomeparams
http://127.0.0.1:8000/hops/runsim
http://127.0.0.1:8000/hops/getmetrics
http://127.0.0.1:8000/hops/baketorhino
```

**B. GH Python 3 components.** For each row, add a *Python 3 Script* component,
create the inputs/outputs, and paste the two-line body:

| Component | Inputs | Outputs | Body |
|---|---|---|---|
| GetDesign | `refresh` (bool) | `genome`, `mass_g`, `revision` | `genome, mass_g, revision = gh.get_design(refresh)` |
| SetGenomeParams | `names` (list, text), `values` (list, number) | `revision` | `revision = gh.set_genome_params(names, values)` |
| RunSim | `run` (bool, from a Button) | `job` | `job = gh.run_sim(run)` |
| GetMetrics | `job` (text) | `status`, `metrics`, `run_id` | `status, metrics, run_id = gh.get_metrics(job)` |
| BakeToRhino | `bake` (bool, from a Button) | `summary` | `summary = gh.bake_to_rhino(bake)` |

Every body starts with:

```python
import sys; sys.path.insert(0, r"<repo>\bridges\rhino\grasshopper")
import calflab_gh as gh
```

`RunSim` is asynchronous: it returns a job id immediately. Wire it into
`GetMetrics` and put a Trigger (1 s) on `GetMetrics` until `status` is `done`.

### Example definition

A binary `.gh` file cannot be authored without Grasshopper, so none is shipped
yet (known gap, see DECISIONS.md ADR-024). The recipe above reproduces the
intended example in about five minutes: sliders -> SetGenomeParams -> Button ->
RunSim -> GetMetrics -> Panel, plus GetDesign -> Panel and a Button ->
BakeToRhino. Save it as `bridges/rhino/grasshopper/calflab_example.gh`.

## Status

* Build-list logic is tested headlessly (`tests/test_bridges.py`), including
  running `calflab_rhino.build` against a fake document.
* Fabrication exports to Rhino (flattened skin pieces, mold halves, nesting
  layouts) are planned for Phase 4.
