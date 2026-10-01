# CALFLAB user guide

CALFLAB is a design environment for a calf-scale quadruped robot: form,
mechanism, control, simulation, evolution, fabrication, wiring and a research
record, in one project. This guide grows with the tool. Features marked
**(planned)** are scaffolded but not usable yet.

Units everywhere in the UI and in files: **mm, g, degrees**. World frame:
**X forward, Y left, Z up** (same as Rhino).

---

## 1. Install and run

Requirements: Windows 11, any Python 3 (only used to bootstrap `uv`), Node LTS.
Rhino 8 and Blender (4.2 or newer) are optional.

```powershell
.\calflab.ps1 setup     # Python env, web dependencies and build, sample project, Blender add-on zip
.\calflab.ps1 doctor    # checks tools, Rhino/Blender paths, ports, plugins
.\calflab.ps1 lab       # starts the server + web app and opens the browser
```

| Command | What it does |
|---|---|
| `calflab setup` | Install web dependencies, build the web app, create `projects/sample-calf` |
| `calflab doctor` | Environment report with a fix for every problem |
| `calflab lab` | Start the lab. `--project <dir>` opens another project, `--port`, `--no-browser`, `--dev` (hot-reloading UI for development) |
| `calflab test` | All tests. `--py` (ruff, pytest, mypy), `--web` (typecheck, eslint, vitest), `--e2e` (Playwright), `--fast` |
| `calflab demo <name>` | Headless smoke demos: `walk`, `override`, `evolve`, `export`, `wire`, `bridges`, `all` |
| `calflab new-plugin <type> <name>` | Generate a plugin template and its contract test |
| `calflab plugins` | List registered plugins (ready / planned) |
| `calflab registry check` / `rebuild` | Verify or rebuild the experiment index |
| `calflab components audit` | Unverified components, the results that depend on them, actuators at their torque limit (section 9) |
| `calflab components worksheet` | Write the datasheet verification worksheet (CSV) |
| `calflab bridge rhino` | How to install the Rhino commands |
| `calflab bridge blender --install` | Build the Blender extension and install it into Blender |

**Where things live.** The working copy is `C:\CALFLABHOME`, a local folder no
sync client touches. The Python environment is in `%LOCALAPPDATA%\calflab`;
web dependencies are in `web\node_modules`. To start clean, delete both and
re-run `setup`. Projects are folders under `projects/`.

> Keep the working copy out of OneDrive / Google Drive / Dropbox: sync clients
> can corrupt a git repository and lock files mid-run. GitHub is the backup.
> If the repo is ever opened from a synced folder anyway, CALFLAB keeps
> `node_modules` outside it automatically (DECISIONS.md ADR-003).

---

## 2. The lab window

```
┌ CALFLAB  project │ Form  Mechanism  Simulate  Evolve  Behave  Fabricate  Wire  Deploy  Journal │ undo redo Simulate Bake ┐
├ Command: ______________________________________________________________  last message     Ctrl K ┤
│ Layers      │                                        │ Properties / Form / ...                      │
│ Scene tree  │              Viewport / Graph          │                                              │
│             ├────────────────────────────────────────┴──────────────────────────────────────────────┤
│             │ Timeline · Runs · Console · Jobs                                                        │
├ Units mm·g·deg │ Tol │ Grid snap │ Nav │                      Backend │ Saved · rev │ Connected ──────┤
```

* **Workspaces** (top tabs) are dock layouts over the same project and scene.
  Drag any panel tab to re-dock it; the layout is remembered per workspace.
  *Reset layout* restores the default.
* **Layers** (Structure, Actuators, Transmission, Electronics, Sensors, Skin,
  Harness, Annotations): eye = visible, padlock = not selectable, swatch =
  colour. Layer state is part of the project, so Rhino and other clients see it.
* **Scene tree**: every part by its stable ID (`leg.fl.shank`). Click to select,
  double-click to zoom to it. The joint that moves a part is shown on the right
  of its row.
* **Status bar**: units, tolerance, grid snap for gumball edits, navigation
  preset, compute backend, save state, server connection.

### Command line

Every action is a named command. Press **Ctrl+K** (or just start typing in the
viewport) and type, for example `Simulate`, `Bake`, `ZoomExtents`,
`DisplayGhosted`, `FourView`, `Hide`, `Isolate`, `Undo`.

* Autocomplete shows matches; **Tab** completes, **Enter** runs.
* **Enter** or **Space** on an empty line repeats the last command.
* Commands with parameters open a small form. You can also type them:
  `Bake name=long-neck note=first_try`.
* The empty command line lists your recent commands.

### Keyboard shortcuts (rebindable: press F1)

| Key | Command | Key | Command |
|---|---|---|---|
| F5 | Simulate | B | Bake design |
| Ctrl+Z / Ctrl+Y | Undo / Redo (shared by all clients) | K | Play / pause |
| Ctrl+Alt+W / S / G / X / R | Wireframe / Shaded / Ghosted / X-Ray / Rendered | M | Measure distance |
| Ctrl+Shift+E / S | Zoom extents / selected | H / Alt+H / I | Hide / Show all / Isolate |
| Ctrl+A / Esc | Select all / none | F1 | Shortcuts and navigation |

Single-letter shortcuts act immediately; any other letter starts typing a
command.

---

## 3. Viewport

* **Navigation presets** (F1): **Rhino** (default): right-drag orbits,
  Shift+right-drag pans, wheel zooms. **Blender**: middle-drag orbits,
  Shift+middle-drag pans. **Fusion**: middle-drag pans, Shift+middle-drag orbits.
* **Views**: Perspective, Top, Front, Right from the toolbar, or `ViewTop` etc.
  `FourView` toggles the four-viewport layout. `SaveView` stores the current
  camera under a name; saved views appear in the view menu.
* **Display modes**: Wireframe, Shaded, Ghosted, X-Ray, Rendered (PBR materials,
  soft shadows, skin material preview).
* **Selection**: click; Shift/Ctrl-click adds. Drag **left to right** for a
  *window* (objects entirely inside), **right to left** for a *crossing*
  (anything touched). The selection filter picks *Parts* or *Geometry /
  components* (to select an actuator or a board). `Hide`, `Show`, `Isolate`.
* **Overlays** (layers icon): centre of mass, joint axes with limit arcs (the
  white tick is the standing angle), support polygon, contact forces (during
  playback), mass-budget colours, collision geometry only, harness routes,
  sensors, ground grid. *(planned: inertia ellipsoids, torque/temperature heat
  map, range-of-motion sweep)*
* **Measure** (M): click two points on the robot for a distance. *(planned:
  angle, clearance across the joint range)*
* **Capture** (camera icon): saves the viewport image with provenance (state
  revision, run, frame, display mode) and links it into the journal.

---

## 4. Parametric and explicit editing

CALFLAB keeps two layers and never mixes them silently.

1. **Parametric**: the *genome* (sliders in the Form panel) drives every part
   through the part generator.
2. **Explicit overrides**: direct edits of one part, stored as named records on
   top of the parametric result.

**Make an override with the gumball.** Select a leg segment (or the trunk). A
handle appears with a small bar at the bottom of the viewport:
`leg.fl.shank  length  [170] mm  [Override this part]`.

* Drag the handle, or type an exact value in the bar and press Enter (typing
  also works while you are dragging). Grid snap is in the status bar.
* **Override this part** creates/updates an override for that one part.
* **Drive gene** changes the gene behind the parameter instead, so all parts
  sharing it follow.

**See and manage overrides.** *Properties* shows, per parameter, the current
value, an `override` badge with the parametric value, and two buttons:

* **Remove**: back to the parametric value.
* **Internalize**: write the value into the gene and delete the override.

The *Overrides* panel lists all of them with an enable checkbox. Geometry
pushed from Rhino (`CalflabPush`) also appears there as a geometry override.

**Undo/redo** (Ctrl+Z / Ctrl+Y) is a server-side command log shared by every
client; a slider drag is one step. The log (`commands.jsonl`) is kept with the
project as a record of how a design was reached.

**Bake** (B) freezes the current state into an immutable, versioned Design
(`calf-v003`) with its genome, overrides, graph, evaluated spec, code version
and a thumbnail. Baked designs are what you cite.

---

## 5. Workspaces

### Form
Genome sliders grouped by Trunk, Legs, Neck and head, Tail and ears, Mechanism,
Shell and skin, Sensing; live mass against the 7 kg target, height, length and
centre of mass. *(planned: reference images on view planes)*

### Mechanism
Actuator choice per joint group and knee drive (direct or belt), and a
**torque-margin table**: required peak torque from a chosen simulation run
against available torque (stall x derating). Red means the actuator saturates
in that run. Every actuator carries an **unverified** badge until you check
its data (section 9). *(planned: range-of-motion sweep, interference check)*

### Simulate
Controller (CPG gait: trot, walk, pace, bound), simulation settings (duration,
seed, start pose, pushes), model settings (terrain, servo model, skin on/off,
domain randomization) and the fitness preset. **F5** runs it; body poses stream
into the viewport. The **Timeline** scrubs the run and plots any channel
(speed, pitch, roll, power, per-actuator torque and temperature, foot forces)
with a cursor synced to the viewport. *Runs* lists every recorded run; click
one to replay it. An identical simulation is not re-run: the recorded one is
reused. *(planned: side-by-side comparison, interactive push tool)*

Metrics: forward speed, distance, cost of transport, stability, torque RMS and
peak, torque margin, first-order thermal estimate, foot impact speed (noise
proxy), time to stand from lying, time at joint limits.

### Evolve
Choose the optimizer (MAP-Elites + CMA-ES), budget, the two behavior
descriptors of the archive, rollout length, fitness preset and compute
backend, then **Start evolution**. The *Archive* tab shows the MAP-Elites
heatmap filling in, fitness over generations, coverage and rollout count.
**Click a cell** to replay that candidate in the viewport and see its fitness
terms and lineage; **Adopt into design** loads it into the document (undoable).
All candidates and their parents are stored in the registry.
*(planned: Pareto front, parallel coordinates, interactive selection, compare)*

### Fabricate
Parts list by ID and exporters: *Leg segment (CAD)* produces a printable
segment with actuator mount and embossed part ID as STEP, STL, 3MF and .3dm;
STL/3MF envelope meshes; Rhino .3dm; glTF; MJCF; URDF; firmware skeleton.
Select parts first to export only those. Files are written to
`exports/<exporter>/` and can be downloaded from the panel.
*(planned: nesting, exploded view, molds, skin patterns)*

### Wire
Power budget from the latest run's torque profile (mean/peak power, battery
runtime), bill of materials with costs, links and unverified badges, and the
harness with routed cable lengths and a diagram. WireViz YAML is exported
always; the full WireViz drawing needs Graphviz (`winget install
Graphviz.Graphviz`), otherwise a simple built-in diagram is shown.

### Journal
Markdown entries stored in `journal/`. *Link run* / *Link design* insert live
links (`calflab://run/<id>`, `calflab://design/<id>`); *Capture viewport*
attaches an image with provenance.

### Behave *(planned, Phase 4)* and Deploy *(planned, Phase 3)*
These tabs explain what will live there and list the plugins already
scaffolded. Blender clips can already be sent to the motion library.

---

## 6. Node editor (Graph tab)

The pipeline is a graph: `genome -> morphology -> MJCF -> simulate (<- controller) -> metrics -> fitness`.

* **Double-click** the canvas to add a node (search box). Drag between sockets
  to wire; wire colour is the data type. **Delete** removes nodes or wires.
* Node border: grey = ok, **orange** = warning, **red** = error (hover for the
  message), dashed = needs to be run, faded = disabled.
* Header buttons: run (expensive nodes), preview, enable/disable.
* Select a node to edit its parameters in *Properties* and see its output in
  the inspector at the bottom.
* *Group* frames the selection; *Cluster* collapses it into one reusable node
  with exposed inputs and outputs.
* Results are cached by the hash of each node's inputs and code version, so a
  change only recomputes what is downstream of it.

Try it: add a *Number slider* and a *Set gene* node, wire
`genome -> Set gene -> morphology` and `slider -> Set gene.value`, and the
slider now drives that gene.

---

## 7. Project files and the research record

```
projects/<name>/
  project.calflab.json   the document (graph, overrides, layers)
  commands.jsonl         every edit, append-only (undo/redo and history)
  index.sqlite           index of runs/designs (rebuildable)
  runs/<id>/             run.json + rollout, scene, model, archive, candidates
  designs/<id>/          baked designs (immutable)
  journal/               Markdown entries
  assets/                captures, reference images, sculpted geometry
  motions/               reference-motion clips from Blender
  exports/               fabrication and wiring outputs
```

Every sim, evolution, bake and export records its inputs, genome, the full
fitness preset, seed, git hash, package versions, compute backend, metrics,
artifacts and duration. `calflab registry check` verifies it; `calflab
registry rebuild` recreates the index from the text files.

---

## 8. Rhino, Grasshopper, Blender, notebooks

All clients talk to the same running lab; an edit in one appears in the others.

* **Rhino 8**: see `bridges/rhino/README.md`. `CalflabPull` brings the design in
  as layered geometry with blocks and ID user text; `CalflabPush` sends sculpted
  geometry back as an override; `CalflabLiveSync` follows changes.
* **Grasshopper**: Hops endpoints at `http://127.0.0.1:8000/hops/...` or GH
  Python 3 components (same README).
* **Blender 4.2+ / 5.x**: `.\calflab.ps1 bridge blender --install`, then open
  the 3D viewport sidebar (N) > CALFLAB. Build an armature from the design
  (one bone per joint, limits applied), pose and keyframe it, export the
  action as a reference clip, or import a simulation run as an action for
  rendering. Details and conventions: `bridges/blender/README.md`.
* **Python / Jupyter**: `docs/notebooks/quickstart.ipynb`

  ```python
  from calflab.client import Client
  lab = Client()                      # the running lab
  lab.set_genes(shank_length=190)     # appears live in the web app
  run = lab.simulate()
  run["metrics"]["speed_mps"]
  ```

---

## 9. Verifying component data

Nothing about hardware is trusted by default. Every entry in
`config/components/*.yaml` has `source:` and `verified: false`, and shows an
orange **unverified** badge in Properties, Mechanism, Wire and exports.

To verify one: check the numbers against the datasheet (or a bench test), fix
them in the YAML, set `verified: true`. The lab re-reads the library the next
time the design is evaluated (any edit, or reload the page). Only you set that
flag; no code does.

**The worksheet.** `docs/component_verification.csv` (open it in Excel) has
one row per recorded value: component, field, unit, the recorded value, what
the lab uses it for, and its source. Fill in `datasheet_value`,
`datasheet_reference` (document and page) and `ok`. Rows marked "not used by
any calculation yet" can wait. `calflab components worksheet` regenerates the
file from the YAML; it refuses to overwrite an existing worksheet unless you
pass `--force` or `--out <other file>`, so your filled-in columns are safe.

**The audit.** `calflab components audit` prints three tables:

1. every library component, whether it is verified and how much of it the
   current design uses;
2. the headline results (BOM total, mass, worst torque margin, mean power,
   battery runtime) with the unverified components each one rests on;
3. torque margins per joint from the latest sim run, lowest first. Red rows
   reach their usable torque (stall x derating) in that run.

`--simulate` simulates the current design first, `--run <id>` picks a
specific run. The same report is the `component_audit` analysis
(`lab.analysis("component_audit")` in Python or a notebook).

---

## 10. Extending CALFLAB

```powershell
.\calflab.ps1 new-plugin fitness_term quiet_feet
```

writes `plugins/quiet_feet.py` and a contract test. Edit the file; the running
lab hot-reloads it, and its parameters appear as sliders with units and
tooltips without any UI code. Plugin types: gene definitions, part generators,
joint types, components, controllers, behaviors, fitness terms, behavior
descriptors, optimizers, simulators, compute backends, exporters, analyses,
panels, commands. `CLAUDE.md` has the rules for each.

---

## 11. Troubleshooting

| Symptom | What to do |
|---|---|
| "The CALFLAB server is not reachable" | Start `.\calflab.ps1 lab`; check `doctor` for port 8000 |
| Viewport says the design cannot be built | Open the Graph tab; the red node says why. `ResetGraph` restores the default pipeline |
| A panel shows an error | Click *Try again*; the rest of the lab keeps working. Report the message |
| Layout is a mess | *Reset layout* (top right) |
| Plugin does not appear | `calflab plugins` shows load errors; the status bar shows a plugin error badge |
| Evolution is slow | Reduce rollout length or budget; it uses half your CPU cores by default |
| Web app looks outdated after pulling code | `.\calflab.ps1 setup` rebuilds it |
