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
| `CalflabPull` | Fetch the current design as layered geometry. Layers: `CALFLAB::Structure`, `::Actuators`, `::Transmission`, `::Electronics`, `::Sensors`, `::Skin`, `::Harness`, `::Annotations`. Repeated components are block instances (`calflab.<component>`). Every object has user text `calflab.id` (stable ID), `calflab.body`, `calflab.layer`, `calflab.mass_g`, `calflab.mass_source` (`parametric`, `component`, `geometry` or `measured`) and, where a material applies, `calflab.material`; for components also `calflab.component` and `calflab.verified`. Harness routes are polylines on `CALFLAB::Harness` named by route id (`harness.bus.fl`), with user text `calflab.src`, `calflab.dst`, `calflab.length_mm` (cut length, with slack), `calflab.connector` and `calflab.wires`. |
| `CalflabPush` | Send selected geometry (mesh, Brep, extrusion or SubD) back as a named **geometry override** on a body. It asks for the body ID, the layer (Skin or Structure), a name and, for Structure, a material. On **Skin** it is a sculpt: look only. On **Structure** a closed solid gives the part its mass (volume x material density), centre of mass and inertia; an open one is shown, not used for mass, and the command prints a warning. It shows up in the web app's Properties and Overrides and can be toggled or removed there. |
| `CalflabLiveSync` | Toggle live updates: Rhino re-pulls whenever the design changes in any client. |

Pulling again replaces only objects that carry `calflab.id`; your own geometry
is left alone. Sculpt on your own layer, then `CalflabPush` it.

### Chassis parts with real mass

1. `CalflabPull`, then model the part on your own layer, in place.
2. Optional: give the object the user text `calflab.material` = a structure
   material key (`pla`, `petg`, or one you added to
   `config/components/materials.yaml`). It is then weighed with that
   material. A part of several materials (PLA body, steel rods) is several
   closed solids, each with its own `calflab.material`, selected together
   and pushed in one go (ADR-053).
3. Select it, `CalflabPush`, body ID (for example `trunk`), layer
   `Structure`, a name and, only if a selected solid has no
   `calflab.material`, the material for those (`Default` = the part's
   material).
4. Read the command line. A closed solid:
   `CALFLAB: trunk structure mass is now 1240.0 g (1000.0 cm3 of pla; the
   estimate it replaces was 629.1 g)`, then one line per solid if there are
   several (`solid 2 (rod): 10.0 cm3 of stainless_304 = ... g`) and the
   centre of mass in Rhino's coordinates. An open one:
   `CALFLAB WARNING: The solid pushed onto trunk is not used for mass: it is
   open (4 naked edges). The parametric estimate is kept.`

The lab measures the mesh Rhino makes of the object, and takes the volume
from Rhino's own exact figure when the two agree within 5 % (a meshed sphere
is about 1.6 % small). Objects that overlap are counted twice: union them
first. The mass is that of a fully dense part; see the user guide, section 4.
The envelope the solid replaces is not pulled into Rhino any more; in the
simulator it remains the collision shape.

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

Hops is a separate package and is **not installed on this machine**, so this
path has never been run against Grasshopper (see Status). Install it with
Rhino's `PackageManager` command (search "Hops").

**B. GH Python 3 components** (tested). Open the ready-made example,
`bridges/rhino/grasshopper/calflab_example.gh`, or build your own: for each
row add a *Python 3 Script* component, create the inputs/outputs, and paste
the body.

| Component | Inputs | Outputs | Body |
|---|---|---|---|
| GetDesign | `refresh` (bool) | `genome`, `mass_g`, `revision` | `genome, mass_g, revision = gh.get_design(refresh)` |
| SetGenomeParams | `names` (list, text), `values` (list, number), `apply` (bool) | `revision` | `revision = gh.set_genome_params(names, values) if apply else None` |
| RunSim | `run` (bool, from a Button) | `job` | `job = gh.run_sim(run)` |
| GetMetrics | `job` (text) | `status`, `metrics`, `run_id` | `status, metrics, run_id = gh.get_metrics(job)` |
| BakeToRhino | `bake` (bool, from a Button) | `summary` | `summary = gh.bake_to_rhino(bake)` |

Every body starts by finding `calflab_gh.py` next to the definition:

```python
import os, sys
sys.path.insert(0, os.path.dirname(ghenv.Component.OnPingDocument().FilePath))
import calflab_gh as gh
```

(In a definition saved somewhere else, replace the second line with
`sys.path.insert(0, r"C:\CALFLABHOME\bridges\rhino\grasshopper")`.)

`RunSim` is asynchronous: it returns a job id immediately. Wire it into
`GetMetrics` and put a Trigger (1 s) on `GetMetrics` until `status` is `done`.

### Example definition

`calflab_example.gh` holds the five components wired up: a `shank_length`
slider and an `apply` toggle into SetGenomeParams, a `run` button into RunSim
and GetMetrics (with a 1 s trigger), a `bake` button into BakeToRhino, and
panels on the outputs. `apply` is off when the file opens, so opening it never
changes your design.

The file is generated, not hand-edited: `build_example.py` builds it inside
Rhino, solves it against the running lab and only then saves it. To rebuild
and re-test it (use a scratch project; it edits and undoes one gene):

```powershell
.\calflab.ps1 lab --project <scratch folder> --no-browser
.\calflab.ps1 bridge rhino --grasshopper
```

## Checking the bridge inside Rhino

```powershell
.\calflab.ps1 lab --project <scratch folder> --no-browser
.\calflab.ps1 bridge rhino --check
```

starts Rhino, runs `validate_in_rhino.py` and closes Rhino again. The script
installs the aliases, connects, pulls, models a stand-in head shell, lets the
real `CalflabPush` command push it (the prompts are answered from the macro),
pulls again, pushes a box, a sphere and an open box onto the trunk's
Structure layer and checks the masses and the warning, then turns
`CalflabLiveSync` on and edits a gene on the server.
Re-run it after a Rhino update or after changing the bridge.

## Status (Rhino 8.34, checked 2026-10-01 and again 2026-10-03, against a live server)

Verified by `bridge rhino --check`:

* `CalflabInstall` registers the four aliases, and can be run again.
* `CalflabPull`: 9 layers under `CALFLAB`, 57 objects (34 Breps, 23 block
  instances over 8 block definitions), 18 joint-axis lines, 8 harness
  polylines on `CALFLAB::Harness` (each exactly as long as its route), user
  text on every object; every solid has real thickness and all 9 spheres sit within 0.005 mm
  of where the server puts them. A second pull replaces without duplicating.
* `CalflabPush`, typed as a command: a 384-face head shell became a geometry
  override on `head`; the next pull brought it back as a mesh in exactly the
  same place (0.0 mm) and left the original object alone.
* Structure solids (checked 2026-10-08): a 100 mm box Brep pushed onto
  `trunk` with `pla` gave 1240.0 g (36 mesh faces, closed); a 40 mm sphere
  Brep gave 332.42 g, exact, from Rhino's volume (its 960-face mesh alone is
  1.60 % small); a box with one face removed was refused for mass with "it
  is open (4 naked edges)". These went through the bridge's `push` function
  with real Breps; the new material prompt of the typed command has not been
  answered by hand yet.
* Several solids with their own materials (ADR-053, added 2026-10-08):
  **not yet run in Rhino.** `bridge rhino --check` now also pushes a box
  tagged `pla` with a rod tagged `petg`; run it once to confirm.
* `CalflabLiveSync`: Rhino followed a `shank_length` edit made on the server
  within about a second (shank bounding box moved 20 mm for a 20 mm edit, no
  object lost), and the command turns it off again.

Verified by `bridge rhino --grasshopper` (Grasshopper 1.0.0008):

* The five GH Python 3 components in `calflab_example.gh`: GetDesign matched
  the server's mass and genome, SetGenomeParams changed a gene on the server
  (and did nothing while `apply` was off), RunSim + GetMetrics returned a
  finished run with metrics, BakeToRhino built 75 objects in the Rhino
  document. The saved file reopens with its scripts, parameters and wires.

Three defects were found and fixed this way: `CalflabInstall` crashed when the
aliases already existed; capsules (leg segments) could silently vanish after a
gene edit because Rhino rejected them; an error during a live-sync pull could
escape into Rhino's idle loop.

**Not verified:**

* The Hops endpoints against Grasshopper: Hops is not installed here. The
  server side is covered by HTTP-level tests only.
* `CalflabConnect` as a typed command (its prompt). The function behind it is
  used by the check.
* Anything done with the mouse: opening `calflab_example.gh` on the canvas,
  dragging the slider, pressing the buttons, and how the pulled model looks.
  The checks drive Rhino and Grasshopper from scripts.
* Pushing a Brep, extrusion or SubD (the check pushes a mesh).

Build-list logic is also tested headlessly (`tests/test_bridges.py`,
`tests/test_bridge_scripts.py`). Fabrication exports to Rhino (flattened skin
pieces, mold halves, nesting layouts) are planned for Phase 4.

Checked by hand by the researcher (2026-10-03, Rhino 8, sample project):

* `CalflabConnect` typed as a command works.
* `CalflabPull`: the model looks right on first inspection. The Harness layer
  was empty; fixed the same day (routes are now pulled as polylines) and
  confirmed by `bridge rhino --check`, not yet looked at by hand.
* `CalflabPush` with a Brep (two boolean-unioned spheres, 2810 mesh faces)
  works. The result shows in the web lab only while the Skin layer is
  visible there: a pushed sculpt replaces the Skin geometry of its part.
* `CalflabLiveSync` follows override toggles and gene edits.
