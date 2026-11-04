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
| `calflab bridge rhino` | How to install the Rhino commands. `--check` tests them inside Rhino, `--grasshopper` rebuilds and tests `calflab_example.gh` (lab running on a scratch project) |
| `calflab bridge blender --install` | Build the Blender extension and install it into Blender. `--check` verifies it numerically, `--check-ui` clicks through the sidebar panel |

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
  playback), mass-budget colours, collision geometry only, harness routes
  (cables drawn over the body in every display mode, with a dot at each end;
  always shown in the Wire workspace; hidden during playback), sensors,
  ground grid. *(planned: inertia ellipsoids, torque/temperature heat
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

**Make an override with the gumball.** Select a leg segment (or the trunk).
An arrow appears at the end of the part, pointing the way it grows, with a
small bar at the bottom of the viewport:
`leg.fl.shank  length  [170] mm  [Override this part]`.
A leg segment has one arrow (length); the trunk has three (length red, width
green, height blue). The arrow turns yellow under the cursor.

* Drag the arrow with the left mouse button; the bar shows the value as you
  drag. Or type an exact value in the bar and press Enter. Grid snap is in
  the status bar. One drag is one undo step.
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

**Bring a baked design back.** The *Designs* panel (Form, Evolve and Journal
workspaces) shows every baked design with two buttons. **Load** replaces the
working document's genes, graph and overrides with the design's (also
`LoadDesign id=calf-v003`); Ctrl+Z brings the document back. **Evolve from**
starts an evolution from the design without touching the document (see
Evolve below).

### Mass from your own parts: solids, materials, weighed prints

By default every printed part's mass is an estimate from its envelope
(surface area x wall thickness x density). You can replace that, part by
part, with real numbers. Each of these is an override: listed in
*Overrides*, switchable, undoable.

**1. Push a closed solid from Rhino.** Model the part in Rhino in its real
place (pull the calf first, model against it), select it, `CalflabPush`,
give the body ID (`trunk`, `leg.fl.shank`, ...), choose the layer
**Structure**, and name a material (Enter takes the part's material). An
object that carries the user text `calflab.material` (a structure material
key such as `pla`) is weighed with that material and is not asked about.
If the object is a closed solid the part's structure mass becomes
**volume x density**, and its centre of mass and inertia follow the solid,
in the simulation too. Rhino prints the result, for example
`trunk structure mass is now 1240.0 g (1000.0 cm3 of pla; the estimate it
replaces was 629.1 g)`, and where the centre of mass is, in the coordinates
you modelled in.

**A part of several materials (printed PLA with steel rods).** Model each
piece as its own closed solid, with the rods cut out of the plastic so
nothing overlaps. Give each solid its material: *Properties > Attribute
User Text* in Rhino, key `calflab.material`, value the material key (`pla`,
`stainless_304`, ...). Select **all** the solids of the part and run one
`CalflabPush`. Each solid is weighed with its own material; a solid without
the user text takes the material you name at the prompt (the prompt only
appears when at least one solid has none). The part's mass is the sum of
volume x own density, and its centre of mass and inertia combine the solids
with their own densities, so a steel rod pulls the centre of mass towards
itself. Rhino prints one line per solid and the total:

```
CALFLAB: trunk structure mass is now 1319.3 g (1010.0 cm3 of pla + stainless_304; the estimate it replaces was 629.1 g)
CALFLAB:   solid 1 (body): 1000.0 cm3 of pla = 1240.0 g
CALFLAB:   solid 2 (rod): 10.0 cm3 of stainless_304 = 79.3 g
CALFLAB: trunk structure centre of mass is at (6.0, 0.0, 379.5) mm
```

(A 100 mm PLA cube at the trunk origin and a 10 x 10 x 100 mm rod 100 mm in
front of it, with steel entered as 7.93 g/cm3: the centre of mass is 6.0 mm
towards the rod, where the centre of the combined volume would be 1.0 mm.
The name in brackets is the Rhino object's name.) All the solids of one
push are one override: a second push onto the same part replaces all of
them, so always select the whole part. If one of the solids is open or its
material is not in the library, **none** of them is used for mass and the
warning names the one at fault: a part missing its rods would otherwise be
too light without saying so.

**A part printed with infill (the infill estimate).** A solid modelled full
but printed with infill is much lighter than volume x density. Tag the solid
with how it is printed, the same way as its material (*Properties >
Attribute User Text* in Rhino). All three keys are needed; nothing has a
default:

| Key | Value | Example |
|---|---|---|
| `calflab.print.infill` | infill percentage, 0 to 100 (`15` or `15 %`, not `0.15`) | `15` |
| `calflab.print.perimeters` | number of perimeters (walls), a whole number, 1 or more | `2` |
| `calflab.print.line_width` | line (extrusion) width in mm | `0.4` |

`CalflabPush` then weighs that solid as printed:

* **Shell:** everything within one wall thickness (perimeters x line width,
  here 0.8 mm) of the solid's surface, at the material's full density.
* **Core:** everything deeper than that, at the infill percentage of the
  density.
* mass = density x (shell volume + infill x core volume). The density is
  still the material's own (`pla` 1.24 g/cm3, unverified); the estimate is
  applied on top of it, and choosing another material in Properties keeps
  the estimate.
* Centre of mass and inertia follow the same split (the dense solid minus
  the missing part of the core), not a uniform solid scaled down: a part
  with a thick end and a thin end has its centre of mass nearer the thin
  end, and a hollow-ish part is harder to swing than its mass suggests.

A solid without the three tags is weighed fully dense, exactly as before,
so steel rods need nothing. A solid tagged `100` weighs exactly what an
untagged one does. Rhino prints, for a 100 mm PLA cube at 15 %, 2 perimeters,
0.4 mm:

```
CALFLAB: trunk structure mass is now 235.7 g, an INFILL ESTIMATE (1000.0 cm3 outer volume of pla; the envelope estimate it replaces was 629.1 g)
CALFLAB:   infill estimate: 15 % infill, 2 perimeters x 0.4 mm = 0.8 mm wall; shell 47.2 cm3 at full density + core 952.8 cm3 at 15 %; fully dense it would be 1240.0 g
CALFLAB: the volume is Rhino's exact one (the mesh alone would be +0.00 % off)
CALFLAB: trunk structure centre of mass is at (0.0, 0.0, 379.5) mm
CALFLAB: Infill estimate, not a weighed mass: a shell of the wall thickness at full material density plus the core inside it at the infill percentage. It ignores the infill pattern and the slicer's real path. Weigh the print and enter it in Measured for the real value.
```

Check by hand: the core of the cube is 98.4 x 98.4 x 98.4 mm = 952.8 cm3,
the shell 1000 - 952.8 = 47.2 cm3, and (47.2 + 0.15 x 952.8) x 1.24 =
235.8 g. (CALFLAB measures the core on a grid of half the wall thickness
and lands within about 0.1 % of that; all infill would be 186 g, fully
dense 1240 g.) In a push of several solids each tagged solid's line ends
in `(infill estimate)` and is followed by its own `infill estimate: ...`
line; untagged solids print as before.

How it is computed and what it leaves out:

* *Thin features.* Where the solid is thinner than two walls (1.6 mm here)
  there is no point deeper than a wall, so there is no core there: that
  feature counts as fully dense, which is how it prints. The core can never
  be negative or larger than the solid, so the estimate always lies between
  all infill and fully dense. A solid that is thin everywhere prints `no
  core (nowhere thicker than two walls), so all 3.6 cm3 count at full
  density`. Features only just thicker than two walls (up to about one
  grid step, 0.4 mm, more) are counted to within a few percent.
* *One wall thickness all round.* Top and bottom layers are taken to be as
  thick as the walls; the print direction is not known to CALFLAB. Your
  choice on 2026-10-08. If a solid also carries `calflab.print.top_layers`,
  `calflab.print.bottom_layers` or `calflab.print.layer_height`, Rhino
  prints that they `are not used`. A flat part whose top and bottom skins
  are thicker than 0.8 mm (3 layers of 0.2 mm are 0.6 mm, so with your
  settings they are thinner) will differ from the slicer accordingly.
* *It ignores* the infill pattern, the slicer's real path (gap fill, extra
  perimeters around holes, solid layers above and below sloped surfaces),
  supports, brims, and under- or over-extrusion. Compare a few parts with
  your slicer's filament weight at the same settings before relying on it.
* *Internal holes and voids* get walls like any other surface.
* *Incomplete or unreadable tags refuse the push*, naming the solid and the
  tag: `Solid 'cube': it has print tags but not calflab.print.perimeters,
  calflab.print.line_width. An infill estimate needs all of
  calflab.print.infill, calflab.print.perimeters, calflab.print.line_width;
  no value is assumed. Nothing was pushed.`
* A large solid takes a few seconds to push (a 100 mm cube about 5 s).
* **Weighing the print and typing the grams into Measured (3 below) is
  still the most accurate.** The estimate then stays visible as *Computed*.

In the web lab the mass is never shown as a dense or weighed one:
*Properties > Material and mass* carries the badge `infill est.`, an
`infill estimate` marker beside the structure mass, the Source "Pushed
solid, infill estimate (shell + infilled core)", the `infill estimate: ...`
line of each tagged solid, and the note that it is not a weighed mass. The
**Mass** panel shows the part with the badge `infill est.` and sums such
masses on their own line, apart from `geometry`.

* The envelope estimate is no longer counted for that part. Motors, boards,
  battery, skin and hooves are separate items and stay.
* **An open or invalid object is shown but not used for mass.** Rhino prints
  `CALFLAB WARNING: ... it is open (4 naked edges). The parametric estimate
  is kept.` and the same warning appears under the mass readout in Form, in
  the Mass panel and in Properties. Close it (`ShowEdges`, `Cap`, `Join`)
  and push again.
* Without print tags, volume x density is the mass of a **fully dense**
  part. For an infilled print, tag the solid (above) or weigh the part (3
  below); for a hollow one, model the real walls.
* Several separate closed objects add up, each with its own material.
  Objects that overlap are counted twice: `BooleanUnion` them if they are
  the same material, or `BooleanDifference` the rod out of the plastic.
* The simulator still collides with the envelope shape, not the solid.
* A push onto **Skin** changes the look only, as before.
* Switch the override off in *Overrides* and the part is back at its
  parametric value.

**2. Choose a part's material.** Select a part; *Properties > Material and
mass* has a **Material** list (the structure materials in
`config/components/materials.yaml`). On a parametric part the choice is
recorded as a material override and the envelope estimate uses that density.
On a part with a pushed solid it changes the solid's material. A part
pushed as solids of different materials shows them instead of the list
(`pla + stainless_304`): change a solid's `calflab.material` in Rhino and
push the part again.

**3. Enter a weighed mass.** Print the part, weigh it, type the grams into
**Measured** in the same section. That value is used; the computed one stays
beside it as *Computed*. Clear the field to remove it. It stands for the
printed structure of that part only, without motor, skin or hoof.

**Read the result.** *Properties > Material and mass* shows the selected
part's structure mass and its source; for a part of several solids also the
materials, each solid's mass and the centre of mass (in the part's own
frame). In the **Mass** panel such a part reads `pla + stainless_304` with
the source `geometry`, and opens to one row per solid. A weighed
**Measured** mass on top scales the solids together, so the centre of mass
stays where the geometry and densities put it. The **Mass** panel (Form and Mechanism
workspaces) lists every part with the source of its structure mass
(`infill est.`, `geometry`, `measured`, `estimate`), opens to its items (click a row), sums
the total by source, and says how much of it rests on unverified library
entries. The **target** at the top right of that panel is this project's
own mass target; 0 returns to the default. `CalflabPull` writes
`calflab.material`, `calflab.mass_g` and `calflab.mass_source` into each
object's user text (a part of several solids comes back as one object per
solid, each with its own material; a solid weighed with an infill estimate
also gets its three `calflab.print.*` tags back, and `calflab.mass_source`
`infill`). Every simulation run records which parts had geometry-based or
weighed mass (`geometry_parts`, `infill_parts`, `measured_parts`), and each
part's materials and, for a part of several solids, each solid's material
and mass (`inputs.mass.structure` in `runs/<id>/run.json`). For a solid
weighed with an infill estimate the record holds, under
`inputs.mass.structure.<body>.solids[n]`, its estimated `mass_g` and an
`infill` entry with the print settings (`infill_pct`, `perimeters`,
`line_width_mm`, `wall_mm`), the outer, shell and core volumes and the
fully dense mass (`dense_g`); the part's `source` is `infill`.

### Simulating your own modelled robot (ADR-062)

`CalflabPush` only gives one part its mass: the skeleton still comes from the
Form sliders and the simulator still collides the envelope boxes and
capsules. To have the lab simulate a robot you modelled in Rhino, push the
whole model instead.

In Rhino (run `CalflabInstall` once more to get the three new commands):

1. `CalflabPull`, then `CalflabModelSetup`. It creates the layer
   `CALFLAB::Model` with one sublayer per body (`trunk`, `leg.fl.thigh`,
   `leg.fl.shank`, `head` ...) and `CALFLAB::Model::Joints` with one line per
   joint, where the pulled calf has it. Run it again whenever you like: it
   only adds what is missing.
2. Put each of your solids on the layer of the body it belongs to (your own
   sublayers below a body layer are fine). The layer decides, not any
   `calflab.body` user text a copied or mirrored object still carries. All solids of one body are one
   rigid piece in the simulator, whether they touch or not: nothing needs to
   be joined or bolted together in the model, and only the joints move.
3. Move and rotate each line on `CALFLAB::Model::Joints` onto your real joint
   axis. The line's **direction** is the axis; its **midpoint** is where the
   joint is. Which way the line points does not matter. A line of your own
   works too: put it on that layer, name the object with the joint id
   (`joint.fl.knee`) and delete the one it replaces.
4. Tag what needs it: select solids, `CalflabTag`. *Material* for parts that
   are not the material you will name at the push (steel rods, the silicone
   head); *Foot = Yes* for the solids that touch the ground; *Printed with
   infill* for print settings (or leave it and answer once at the push).
5. `CalflabPushModel`. No selection: it sends everything on the model layers.
   Choose **Check** to read the report without changing anything, **Push**
   to store it. It asks once for the material of solids that have none and,
   per material, whether the solids without print tags are printed with
   infill (then: infill percent, perimeters, line width) or fully dense, and
   writes the answers onto those objects as user text.

Before it sends anything, the command lists the joint of every axis line it
found and the foot solids per body, so a wrong name or tag shows at once.
The printout then says what the simulator will treat as one piece (`1 free body
(the trunk) + 8 hinges = 14 degrees of freedom. 145 solids on 10 bodies ...
0 loose solids`), lists every joint against the pulled calf's (`moved 3.7 mm
(dx +3.6, dy -0.5, dz -0.6), axis 0.0 deg off`), every body with its solids,
mass, materials and number of collision hulls, the lowest point of each foot
as modelled, and the total mass. **Nothing is stored unless every solid is
closed, on a body layer and has a structure material**; otherwise it prints
`NOT PUSHED` and every problem at once.

What the lab then builds:

* **Joints** at your lines. Standing angles, joint ranges and the servo on
  each joint stay as they were; everything below a joint moves with it. A
  joint without a line keeps the pulled calf's place relative to the part
  above and the printout says so. The model is taken to be drawn in the
  standing pose.
* **Mass, centre of mass and inertia** of each body from its solids, exactly
  as for pushed solids above (own material per solid, infill estimate if
  tagged). Servos, board and battery still come from the library and sit
  where the lab puts them in their body. A body you gave no solids keeps the
  lab's shapes and estimate, and is named in a warning.
* **Collision** from your solids: one convex hull per solid, simplified to at
  most 32 points; the envelope boxes and capsules of that body are gone. The
  solids tagged `calflab.foot` on a leg become that leg's foot (one hull
  round all of them) and the lab's hoof sphere is removed. A hull fills
  hollows: a concave sole collides as if it were flat. Parts of the robot
  still do not collide with each other, only with the ground.
* The calf starts with its own lowest foot point just above the floor. Feet
  that are not level as modelled are reported.

It is **one override**, "Rhino model", in the Overrides panel (`whole robot
from Rhino (file): 8 joint axes, 145 solids on 10 bodies`). Untick it and the
parametric calf is back; `Ctrl+Z` undoes the push; a second push replaces the
first. The genome, the Form sliders, the proportion study and Evolve are not
changed. (A proportion study or an evolution started while the model is on
varies the genes under a fixed model, which is not meaningful yet: switch the
override off for those.) `CalflabPull` never touches the model layers; it
does bring the model's solids back as meshes on `CALFLAB::Structure`.

Press F5. The run is titled `Simulate (Rhino model)` and its
`runs/<id>/run.json` says which geometry it used, under `inputs.geometry`:
`source` (`rhino_model` or `parametric`), `label`, `file`, `override`,
`pushed`, `collision` (`hulls`, `mixed` or `envelope`), `joints` (per joint:
`pos_mm`, `axis`, the parametric ones, `delta_mm`, `distance_mm`,
`axis_angle_deg`), `bodies` (per body: number of solids and hulls, and the
SHA-256 of every mesh as stored), `feet`, `hooves_removed` and
`parametric_bodies`. Tune, evolve and study runs carry the same entry.

Cost, measured on a stand-in model of 145 detailed solids (159,000 faces) on
the two-joint body: the push takes about 5 s; the simulator runs at 19,000
steps per second instead of 31,000 (still about 38 times faster than real
time at a 2 ms step).

---

## 5. Workspaces

### Form
Genome sliders grouped by Scale, Trunk, Legs, Neck and head, Tail and ears,
Mechanism, Shell and skin, Sensing; live mass against the target, height,
length and centre of mass, and a line of warnings when the design has any.
The **Mass** tab beside it is the breakdown (section 4).
*(planned: reference images on view planes)*

**Overall scale** makes a small test calf: 0.33 gives one about 200 mm
tall. It resizes the whole body and keeps its proportions, so every length
slider below it moves when you change it. All of those sliders are in **real
millimetres**, the same numbers as Properties, the gumball and Rhino: at
0.33 the thigh reads 56.1 with a range of 33 to 85.8, and typing 60 makes a
60 mm thigh. (Underneath, lengths are stored at full size, which is what
keeps the proportions and what evolution searches; project files and run
records show those stored values, and so do `set_genes` from the command
line, the Python client and Grasshopper unless they pass `real=true`.) Wall thickness, skin thickness and all components keep
their size, so at a small scale the motors, boards and battery are nearly
all of the mass: choose lighter ones in Mechanism (section 9 says how to add
them), set the project's mass target in the Mass panel, and press *Tune for
this body* in Simulate, since the default gait was tuned for the full-size
calf. The simulation settings were examined for a body this small on
2026-10-10: see *A small body* under Simulate.

Under Neck and head, three switches say which of those joints the body
really has: **Neck yaw motor**, **Neck pitch motor**, **Head pitch motor**
(genes `has_neck_yaw`, `has_neck_pitch`, `has_head_pitch`; all on by
default). Switching one off removes that joint and its motor: nothing to
drive, no motor in the BOM, the power budget or the mass (55 g each with the
default STS3215, unverified), and the neck servo bus in Wire ends at the
furthest motor that is left, or disappears. The neck and head themselves
stay, fixed where they stand (at the *Neck angle* and *Head tilt* sliders),
with the same IDs (`neck.base`, `neck`, `head`), so solids pushed onto them
still attach and still weigh. With all three off, and **Has tail** and **Has
ears** off under Tail and ears, the only motors left are the legs'. A motion
clip from Blender that moves a removed joint simply has nothing to move.

Under Legs, **Front knee forward** and **Hind knee forward** choose which way
each pair of knees bends. New projects start with front knees forward and
hind knees backward, and with a trot tuned for that body. Turn on the *Joint
axes + limit arcs* overlay to see the limit arc and the standing tick flip.

**Front hip flex** (on by default) is the hip-flexion motor of the two front
legs. Switch it off for **two-motor front legs**: abduction at the shoulder
and the knee working as an elbow. The upper segment is then fixed at its
standing angle, two XH540 motors leave the bill of materials, and the gait
steps those legs with the elbow (sweep) and the abduction (lift). After switching, press *Tune for this body*
in Simulate: no gait made for three-motor front legs suits two-motor ones.
It walks acceptably when the front joint is high and points backward
(**Front knee forward** off, a short front thigh and long front shank, set
with overrides on `leg.fl.thigh`, `leg.fr.thigh`, `leg.fl.shank`,
`leg.fr.shank`), and poorly with the knee mid-leg pointing forward.

**Front legs have hip abduction** and **Hind legs have hip abduction** (genes
`front_hip_abd`, `hind_hip_abd`; both on by default) say whether that pair of
legs can swing sideways. Switch one off and each leg of that pair loses its
abduction joint (`joint.<leg>.hip_abd`), its actuator and its motor: nothing
to drive, no motor in the Mass tab, the BOM or the power budget. With both
off and everything else as it is, **each leg is two joints: hip pitch
(`joint.<leg>.hip_flex`, shown as *Hip flexion*), then knee
(`joint.<leg>.knee`)**, eight leg motors in all.

The bodies keep their IDs and their places, so solids are pushed onto the
same parts as before:

| Body ID | What it is without abduction | Moves with |
|---|---|---|
| `trunk` | chassis | - |
| `leg.fl.hip`, `leg.fr.hip`, `leg.hl.hip`, `leg.hr.hip` | the hip block, now **fixed to the trunk**; it holds the hip-pitch motor | the trunk |
| `leg.fl.thigh`, `leg.fr.thigh`, `leg.hl.thigh`, `leg.hr.thigh` | upper segment; holds the knee motor | hip pitch |
| `leg.fl.shank`, `leg.fr.shank`, `leg.hl.shank`, `leg.hr.shank` | lower segment and hoof | knee |

A bracket that carries a hip-pitch servo can go onto `leg.<leg>.hip` or onto
`trunk`: both are the same rigid piece now, and the mass lands in the same
place either way. The other leg settings work as before on such a leg: own
front and hind lengths, **Front knee forward**, **Hind knee forward**,
**Front legs have a thigh** (off: that front leg is one pitch joint and a
shank, six leg motors in all) and *Overall scale*. Two combinations to
avoid: with **Front hip flex** off as well, a front leg has only its knee
left; and a body with no abduction anywhere cannot step sideways or correct
a roll (see *Proportions* under Evolve for how that shows). The two switches
are not varied by Evolve. After switching, press *Tune for this body*.

**Rotated servo mounts** (all 0 by default; a calf that leaves them at 0 is
built exactly as before). A servo's mount can be turned so that the limb it
carries comes off at an angle; the joint axis and the servo drawn in the
part turn with it, and so does everything further down the leg.

| Setting in Form > Legs | Gene | Range | What it does |
|---|---|---|---|
| Front leg splay | `front_leg_splay` | -30 to 45 deg | front hips rolled outward: the legs lean out, the hooves stand wider |
| Hind leg splay | `hind_leg_splay` | -30 to 45 deg | the same for the hind pair |
| Front leg toe-out | `front_leg_toe` | -45 to 45 deg | front hips turned about the vertical: the legs swing in a plane pointing outward at the front (negative: inward) |
| Hind leg toe-out | `hind_leg_toe` | -45 to 45 deg | the same for the hind pair |

* Left and right are mirrored: one positive number leans both legs of the
  pair outward.
* **One servo only:** select the part, and in Properties set **Mount roll
  (outward)** or **Mount yaw (toe-out)** and press *Override this part*.
  Every hip, thigh and shank has the two; on a hip they are labelled *Splay
  (mount roll, outward)* and *Toe-out (mount yaw)* and start at the Form
  value. Rotating a thigh turns the hip-pitch servo's output (thigh, knee
  and shank follow); rotating a shank turns the knee's. From the command
  line: `add_override target=leg.hl.shank param=mount_roll value=12`.
* Leaning a segment fore or aft is not a mount angle: that is *Knee bend*
  and the standing pose.
* **Every hoof still stands on the ground.** Leaning legs reach less far
  down, so the trunk comes down, and if the pairs differ the hips of the
  pair that reaches further sit lower in the trunk.
* What to expect: splay widens the base (the only other way is *Stance
  width*). On the small two-joint calf 20 deg of splay took the hoof track
  from 78 to 150 mm, lowered it by 10 mm, halved the roll in a trot and cost
  6 % of speed. The body then hangs on a sideways lever: a leg with
  abduction shows that load on its abduction servo in the torque table; a
  leg without has no motor to take it, so it bends the hip-pitch servo's
  shaft and bracket, and **the lab does not show that load at all**. Toe-out makes left and right hooves pull
  against each other a little on every stride. Neither gives sideways
  control. Large angles can push a leg's envelope into the trunk; nothing
  checks that. The proportion study does not vary these angles.
* After changing them, press *Tune for this body*.

**Front and hind legs that differ** (all off or unused by default; a calf
that leaves them alone is built exactly as before):

| Setting in Form > Legs | Gene | Range (default) | At scale 0.337 |
|---|---|---|---|
| Front legs have a thigh | `front_thigh` | on / off (on) | |
| Front and hind legs have their own lengths | `own_leg_lengths` | on / off (off) | |
| Front thigh length | `front_thigh_length` | 5 to 300 mm (170) | 1.69 to 101.1 mm |
| Front shank length | `front_shank_length` | 30 to 450 mm (170) | 10.11 to 151.65 mm |
| Hind thigh length | `hind_thigh_length` | 5 to 300 mm (170) | 1.69 to 101.1 mm |
| Hind shank length | `hind_shank_length` | 30 to 450 mm (170) | 10.11 to 151.65 mm |

* **Front and hind legs have their own lengths**: on, the four lengths in
  the table are used and **Thigh length** / **Shank length** are ignored (the
  two sliders stay in the panel and do nothing). Like every length they
  follow *Overall scale* and are shown in real millimetres. A thigh is
  measured from the hip flexion axis to the knee axis; a shank from the knee
  axis to the centre of the hoof ball, so *axis to the ground = shank length
  + hoof radius* (the **Hoof radius** slider).
* The thigh sliders go down to 5 mm at full size (1.7 mm at scale 0.337),
  for a leg whose hip flexion and knee axes nearly coincide. The shared
  **Thigh length** still stops at 100 mm.
* **Every hoof stands on the ground.** *Hip drop* is the height of the hip
  axes of the longest legs below the trunk centre line; the hips of the
  shorter pair sit lower by the difference. The trunk stays level. (Without
  the switch, a leg shortened by an override still hangs short, as before.)
* **Front legs have a thigh**: off, a front leg has no thigh body at all.
  It is `leg.fl.hip` (abduction), then one pitch joint, then `leg.fl.shank`
  hanging straight down, with the hoof directly below the pitch axis. The
  pitch joint keeps the IDs `joint.fl.knee` / `act.fl.knee` and is named
  *Shoulder pitch*; its motor is the one chosen as **act knee** in
  Mechanism (shared with the hind knees), drawn in the hip, and it has its
  own row in the torque-margin table. It may swing 75 degrees each way.
  **Front knee forward**, **Front hip flex** and a belt knee drive have no
  effect on such a leg. There is no `leg.fl.thigh` / `leg.fr.thigh` in the
  Scene tree, the Mass tab, Rhino or Blender; an override or a pushed solid
  that still targets one is reported as a warning and otherwise ignored.
  The thigh's printed shell and skin leave the mass, its collision capsule
  is gone, and the hip-flexion motors go with it if they were on.
* The four lengths and the two switches are not varied by Evolve.
* After changing the leg layout, press *Tune for this body* in Simulate.

Projects, runs, candidates and baked designs made before 2026-10-04 keep the
backward front knees they were made with. To bring an older document to the
new default: *Reset to defaults* in Form (genes, including the knees) and
*Reset to defaults* on the Controller section in Simulate (the gait), or just
switch **Front knee forward** on and reset the gait. Each is one undo step.

### Mechanism
Actuator choice per joint group, knee drive (direct or belt), battery and
boards. The lists offer every complete actuator, battery and board entry in
`config/components` (section 9).

**Boards** are the last two lists of *Actuators and transmission*:

* **Control board**: the board the battery lead, the servo buses and the IMU
  cable run to. Default `teensy_41`.
* **Second board**: a second board in the trunk, linked to the control
  board. Default `raspberry_pi_5`. Choose `none` for a body with one board.

So a prototype whose only board is an ESP32 is *Control board* =
`esp_wroom_32`, *Second board* = `none`. The trunk then carries that board
alone: its mass in the **Mass** tab (open the trunk row), its power in the
power budget (Wire > Output), no board link in the harness. A board's watts
are added to the motors' and divided by the battery voltage to give battery
current, with no regulator loss in between. Naming the same board in both
lists also gives one board. Each choice is one undo step (Ctrl+Z), and every
project keeps its own: a project saved before these lists existed carries
the Teensy 4.1 and the Raspberry Pi 5 as before. Every run records the
boards its body carried (`inputs.boards` in `runs/<id>/run.json`, and
`boards` in a proportion study's `study.json`). From Python:
`lab.set_genes(board_control="esp_wroom_32", board_compute="none")`.
Not affected by the choice: the firmware skeleton export, which is still
written for a Teensy 4.1 and a Raspberry Pi; the sensors (IMU, microphone,
foot and touch sensors), which are still the same for all projects.

Then a **torque-margin table**: required peak torque from a chosen simulation run
against available torque (stall x derating). Red means the actuator saturates
in that run. Every actuator carries an **unverified** badge until you check
its data (section 9). *(planned: range-of-motion sweep, interference check)*

#### The final feral calf: belts and springs (ADR-063 to ADR-069)

The final calf is its own kind of project, with its own genome
(`config/genes/feral_calf.yaml`). Create one with

```powershell
.\calflab.ps1 new-project projects\robot-calf-final --template feral_calf
.\calflab.ps1 lab --project projects\robot-calf-final
```

`projects\robot-calf-final` already exists. The body: a hip block and a
chest block on two rails; rear legs hip ab/adduction, a femur fixed at 40 deg,
stifle, hock; front legs shoulder, carpus; ten STS3215 C018 servos; stifles
and hocks belted 2:1, and the carpi too (since ADR-071; *Belt-drive the
carpus* in Mechanism turns it off). Form shows your dimensions as sliders. A **PROV** badge
marks a starting value you have not confirmed. The front leg angle is
solved so the back stays level: 7.2 deg with your lengths, where you said
about 5. The values that are not genes live in `config/feral_calf.yaml`:
battery, servo case layout, part masses still to enter, design dimensions
and joint ranges.

**Belts and springs** (a tab beside Mechanism):

* **Belt drives.** Each drive has exactly three dropdowns: *Belt system*,
  *Pulley pair*, *Belt length*. They list the project's catalog
  (`<project>\catalog\belt_systems.json`, `belt_lengths.json`,
  `pulleys.json`). A length whose source is not confirmed in the belt's
  width is greyed ("width unconfirmed"). A belt you have not confirmed you
  can buy says "purchase unconfirmed"; set `purchase_confirmed: true` in
  `belt_lengths.json` once you can. Everything else is read-only:
  * the centre distance C;
  * the servo's position from both joints;
  * pitch diameters, wrap and teeth in mesh;
  * the belt's allowable and breaking tension ("unknown" where not given);
  * the tension slot (a ± build tolerance, never used to reach a C);
  * the checks, each pass, fail or unknown:
    * servo case on its segment;
    * pulleys apart;
    * at least 6 teeth in mesh;
    * for the hock, its servo against the stifle pulley and belt through the
      whole stifle range.

  **There is no way to type or drag C.** It changes only when you choose
  another catalog entry. A choice that fails a check is rejected, with the
  reason shown in red, and the document does not change. Choosing another
  system or pulley pair alone re-picks the length by the default rule:
  closest to the target C while passing every check. A drive that fails
  after a change to the body (say, a shorter tibia) is listed in red, and
  F5 and the load analysis refuse to run until you choose again. From the
  command line: `set_belt_drive drive=hock length=GT2-2mm-394-C`.
* **Springs (tension only).** Sliders for the rate, the free length and the
  four anchor coordinates of the stifle, hock and shoulder springs. Anchors
  are measured from the joint axis: along the segment, and across it
  (positive = toward the front). The table gives each spring in the standing
  pose:
  * force, moment arm and torque;
  * which side it is on: green *resists* means it works against the way
    gravity folds the joint; red *helps collapse* is a warning;
  * what it takes off the servo and the belt at standing.

  The viewport draws the springs in the same colours, and they follow the
  legs during playback.
* **Loads.** *Run load analysis* simulates quiet standing, the slow walk and
  lying down then rising. Each scenario runs with your springs and again
  without them. Each becomes a run (`kind: loads`) that replays in the
  viewport. In its folder:
  * `loads.csv`: per frame and joint, angle, joint torque, servo torque,
    spring torque, total, belt tension, % of rated and % of stall;
  * `loads_summary.csv`: one row per joint;
  * `loads.json`: the summary plus the spring relief and the flags.

  A run is flagged for:
  * a servo above 60 % of rated torque for more than a set fraction of any
    gait cycle;
  * a servo at stall at any moment;
  * a belt above its allowable working tension for more than that fraction
    of a cycle;
  * a belt peak above the set fraction of its breaking strength.

  The thresholds are under *Belt checks and limits*. *Compare belts* runs
  the same walk on every belt system x pulley pair and tabulates C, peak
  tension and the limits (`belt_comparison.csv`). Use it to choose a belt.
* **Provisional and missing values** lists every PROVISIONAL value with where
  it lives, and every part mass not entered yet (counted as 0 g; the Mass
  tab lists them too).

**Gaits.** Simulate > Controller has a *Controller* list. It greys out a
controller that cannot drive this body. Switching keeps each controller's
settings for when you come back (ADR-075). For gaits, use *Feral calf
motions*: mode
`stand`, `walk` (slow, one leg at a time), `trot` (diagonal pairs, about
0.3 m/s) or `lie_rise`. Every mode keeps each joint under 90 % of its
servo's speed (*speed fraction*; a 2:1 belt halves that speed). For a mix of
behaviors, see the Behave workspace.

**Turning the legs out (ADR-072).** Form > Rear legs and Front legs have
*toe-out* (hooves pointing outward) and *splay* (lower end of the leg
outward) for each pair. They are fixed mount angles of the leg's servo seat,
not held by a servo. The whole leg turns with its mount, belts included, so
the belts' C does not change. The hooves stay on the ground and the back
stays level. 0 = straight.

**Wide hooves without splay, and hip springs (ADR-089).** Splayed legs
stand wide, but the hooves are then outside the hip ab/ad axes and the
weight twists those servos (session R step 2). Two genes widen the base
instead. Form > Body > *Hip block: wider per side* and *Chest block: wider
per side* (mm, default 0) widen each block on both sides beyond the rail
spacing plus margins, and the legs move out with them. The rails keep their
spacing. The blocks' masses are not entered yet; once one is, widening
keeps the entered mass and warns you to weigh the wider block. Form >
Springs > *Hip ab/ad springs* (off by default) adds a tension spring per
hind leg, like the adductor muscles. It runs from under the hip block,
inboard of the leg, to the femur below the axis, and pulls the leg in
against the weight. Its rate, free length and three anchor distances are
sliders like the other springs, and evolution may vary them.

**Evolving it (ADR-070).** The body evolves in the Evolve workspace like
the reference calf. What it varies and what it never touches:
* Varied: segment lengths and angles, the axle spacing and the springs.
* **Never varied: the belts.** They are part of the genome as catalog ids
  (Belts panel only; Form does not show them). Every candidate keeps them,
  so its belts are the same parts at the same C as yours.
* Femur and tibia lengths and angles (and the upper leg, if the carpus is
  belted) feed the belt checks. Each run first finds how far each can move
  before a belt fails and searches only there; the run log lists the
  ranges.
* A candidate whose body cannot be built (a belt fails, the front legs
  cannot reach the ground with the back level) is rejected without being
  simulated, and counted under *Infeasible*.

The archive axes default to *Standing height* and *Gait cycle*, and CMA-ES
tunes the walk's ten numbers for each body. To change the belts themselves,
choose them in the Belts panel and evolve again.

The load runs let each servo go up to its stall torque (*torque derating*
1): "at stall" is the moment it saturates. The project's own F5 uses the
same setting.

### Simulate
Controller (CPG gait: trot, walk, pace, bound; *Reset to defaults* restores
the default trot; **Tune for this body** searches a gait for the design as it
is, see below), simulation settings (duration,
seed, start pose, pushes), model settings (terrain, servo model, skin on/off,
domain randomization) and the fitness preset. **F5** runs it; body poses stream
into the viewport. The **Timeline** scrubs the run and plots any channel
(speed, pitch, roll, power, per-actuator torque and temperature, foot forces)
with a cursor synced to the viewport. *Runs* lists every recorded run; click
a row to replay it (the viewport comes to the front, the row is marked with
a play triangle, and the status line says which run is replaying). An identical simulation is not re-run: the recorded one is
reused. *(planned: side-by-side comparison, interactive push tool)*

**Tune for this body.** Whenever the body changes enough that it walks badly
(different leg proportions, knee direction, two-motor front legs), press
*Tune for this body* on the Controller section (command `TuneGait`). A job
searches the gait numbers with the body left alone, tries a trot and a walk,
and writes the best gait into the Controller; Ctrl+Z restores the previous
one. It takes about a minute with the default settings (30 iterations x 12
gaits x 2 patterns, 8 s trials). It only accepts gaits that do not fall,
that survive a 20 s check, and whose commanded joint speeds stay within 0.67
of each motor's recorded no-load speed (the *speed fraction*; the simulator
itself does not limit speed). The console prints speed, stability and lowest
torque margin before and after; then press F5 and read the torque table. If
it reports that no gait was found, the body cannot walk within those limits
with this controller: raise the iterations, or change the body. The gait
controls *Elbow amplitude*, *Elbow offset* and *Swing abduction* only act on
two-motor legs.

Metrics: forward speed, distance, cost of transport, stability, torque RMS and
peak, torque margin, **worst joint speed margin**, first-order thermal
estimate, foot impact speed (noise proxy), time to stand from lying, time at
joint limits. The joint speed margin is 1 - (fastest any joint turned) / (its
motor's recorded no-load speed). The simulator still limits torque only, so
a negative value means the run moved a joint faster than the motor can turn.
Each run also records, per actuator, the peak joint speed, the no-load speed
it is compared with, and the share of the time the motor was at its torque
limit (`metrics.by_actuator` in `run.json`).

**A small body.** Three things in *Model (terrain, servos, skin)* matter for
a calf of a few hundred grams, and none of them follows *Overall scale*:

* **Include skin**: on, the skin's mass and its stiffness at every joint are
  simulated whether or not your prototype has a skin. Switch it off for a
  bare printed body.
* **Joint loss scale** (1 by default): multiplies the passive joint damping
  (0.05 N*m*s/rad) and friction (0.02 N*m) of `config/robot_defaults.yaml`.
  They were chosen for the 5 kg calf with 4 to 10 N*m servos. A servo with
  0.23 N*m of stall torque has about 0.14 N*m usable: at 1 the friction and
  damping alone take most of that at walking speeds.
* **Armature scale** (1 by default): multiplies every servo's reflected
  inertia. A servo whose datasheet does not give it (`armature_kgm2` is
  blank in the library) runs on the library default, 0.005 kg*m^2, made for
  50 to 160 g servos; on a 13 g servo that inertia, not the legs, is what
  the motor mostly accelerates. The honest fix is a value in the component
  entry (measured, or yours and listed in `guessed:`); this setting is for
  seeing how much a result depends on it.

Both scales at 1 give exactly the results of earlier versions. Whatever you
set is stored with every run (`inputs.compile`). The time step (2 ms) and
the contact softness were checked on a 0.4 kg, 190 mm body: halving and
quartering the step changed nothing measurable with the library values, and
about a tenth of the speed once the armature is scaled down, so use
**Timestep ms** 1 when you lower *Armature scale*. Hooves sink 0.1 mm or
less into the ground when standing.

### Evolve
Choose what to **start from**, the optimizer (MAP-Elites + CMA-ES), budget,
the two behavior descriptors of the archive, rollout length, fitness preset
and compute backend, then **Start evolution**.

*What evolution starts from.* **Working document** (the default): the design
as it is now. Or any **baked design** (pick it under *Start from*, or press
*Evolve from* in the Designs panel): then body, gait and overrides come from
that design, the document is not changed, and the fitness preset and rollout
length are still the ones in the panel. The first candidate is the starting
design itself; the others vary its evolvable genes around it. Genes marked
not evolvable (knee direction, actuators, has_tail...) stay as they are in
the starting design. The run record stores the start: `parent` is the design
id and `inputs.start` is `{source: design, design: <id>}` or
`{source: document, revision: N}`; the Archive tab shows it above the heatmap
and the list of past runs says `from <design>`.

*Overrides are not genes.* The enabled overrides of the starting point are
built into every candidate unchanged. A one-leg override (say
`leg.fl.shank.length = 200`) keeps that shank at 200 mm in every candidate
while `shank_length` evolves for the other three legs; it is never mutated
and never removed. Disabled overrides are ignored.

The *Archive* tab shows the MAP-Elites heatmap filling in, fitness over
generations, coverage and rollout count. **Click a cell** to replay that
candidate in the viewport and see its fitness terms, lineage and **genes**:
each gene's value and its difference from the current design and from its
parent (or from the starting design, for the first generation). The table
lists the genes that differ; *show unchanged* lists all. **Pin to compare**
keeps the selected candidate as an extra column: click another cell and the
column *vs pinned* is the difference between the two bodies. Overrides built
into the run are listed under the table. Nothing is adopted by looking.

**Adopt into design** loads the candidate's genes and gait into the document
(undoable). If the document's overrides differ from the ones the candidate
was evaluated with, they are replaced by the run's and the log says so;
otherwise the adopted body would not be the one that was scored.
All candidates and their parents are stored in the registry.
*(planned: Pareto front, parallel coordinates, interactive selection)*

A caution on evolved gaits: the simulator limits each motor's torque but not
its speed. Evolution can therefore find fast gaits the real servos could not
follow (the default trot was tuned with joint speed capped at 120 deg/s for
this reason; ADR-047). Read high stride frequencies with that in mind.

#### Evolving the body to perform a repertoire (ADR-079)
1. In Behave, put your clips into the stochastic behaviors and mark the
   ones the body must perform: in the repertoire, `"required": true` (and
   `"imitation_weight"` to weigh them).
2. In Evolve, choose the fitness preset **repertoire**. The panel shows how
   it evaluates each candidate:
   * three seeds, each with floor friction 0.7-1.1 and mass x0.95-1.05;
   * scored as the mean minus the spread;
   * safety as constraints: **stall and belt breaking reject a candidate;
     sustained servo load over rated, sustained belt tension over its
     allowable, joint speed over the servo's, and time at joint limits cost
     fitness**.

   The required clips play first in each evaluation.
3. The inner loop now tunes, per clip, the top of its speed range (never
   faster than this body's servos can follow, from the clip report) and
   of its amplitude.
4. Good archive axes: **Expressive range** x **Safety margin** (or Quantity
   of motion), to see the trade-off.
5. Press **Estimate cost** first. It times one rollout and tells you how
   long the run will take, and offers **Use the small budget** (2 x 4) to
   try first.

Each candidate shows its seeds (friction, mass, fitness, falls) and the
worst seed's safety table (value / limit for each constraint, rejects in
red, penalties in orange). Candidates a constraint rejected are counted as
**Unsafe**, stored with the reason, and never repaired. Belts stay fixed,
as in every evolution of the feral calf.

To change what rejects and what costs fitness, edit
`config\fitness\repertoire.yaml` (`evaluation: safety: actions:`) and bump
its `version`.

#### Evolving a body for vigorous movement within limits (ADR-090)

Fitness preset **vigour** judges each candidate body on five motions, each
with its parameters searched for that body:
* the feral **walk** and **trot**: how much of their speed is kept, against
  the gait at its defaults on the starting body;
* the **stand**, **step** and **fast play** of the latest interpretation of
  the footage reading: how much of the calf's features is kept (1 = every
  feature as the calf; a feature off by 2x counts about 0.6).

Each motion is searched on one seed. Its best settings within every limit
at margin 0.2 are then checked on three seeds with friction and mass
varied. Only a setting that stays within every limit on every seed, without
falling, counts. A motion with none keeps nothing.

Fitness is the mean kept share minus how far the worst motion goes over the
limits. Use the archive axes **Vigour kept** x **Worst safety margin**.
**Hoof width** is also available as an axis. A run needs an interpretation
(Behave > Interpret footage) and measures the gaits' reference speeds when
it starts. Every play is cached per body in the project's
`.cache\interpret`, so a body seen before costs almost nothing.

**Estimate cost** counts plays for this preset; its number is an upper
bound. A body takes about 55-60 plays, a little over a minute of one core.
Each candidate's metrics list every motion's setting, kept share, margin
and seeds. *Simulate candidate* plays its walk.

#### Behaviour diversity: what this body can do (ADR-093)

Optimizer **MAP-Elites over behaviour** with fitness preset **diversity**
keeps the body as it is. What evolves is a *behaviour generator*:
* **which movements:** stand, weight shifts, steps, walk, trot and turn,
  each with its own parameters free;
* **how they follow one another:** a chain that either wanders between
  related movements or jumps anywhere;
* **how long each lasts, and the cross-fade.**

Each generator plays 24 s on three seeds with friction and mass varied, and
is judged against every limit at margin 0.2. The archive spreads them by
what the robot actually did: by default *Quantity of motion* x *Tempo
regularity* (rhythmic versus irregular). Also available are *Stillness
ratio*, *Expressive range* and *Unpredictability*.

Within a cell, a generator that stays within every limit always beats one
that does not. Among those within the limits, more headroom and a less
predictable sequence win. The heatmap marks which cells are within the
limits; only those are results. *Simulate candidate* plays a cell's
generator.

Before the first generation, the run spends about a minute finding, for
each movement on its own, a setting within the limits; the first generation
starts around those. **Estimate cost** shows the run's length.
How much the robot resembles the calf is not scored.

#### Proportions: comparing bodies instead of finding one

The lab has three ways to look for a better body or gait:

| Tool | Changes the body? | Gaits | Gives you |
|---|---|---|---|
| **Tune for this body** (Simulate) | no | trot and walk (bound if you add it) | one gait written into the document |
| **Start evolution** (Evolve) | yes, all evolvable genes within their slider ranges | the one in the Controller | an archive of bodies scored by one fitness number |
| **Run proportion study** (Evolve, tab *Proportions*) | yes, only the lengths you give a range | walk, trot, bound, each tuned per body | a table of every body tried, per gait |

The **Proportions** tab is beside *Archive*. On its left, under *Ranges and
search*, give a **From** and a **To** in real millimetres for any of *Thigh
length*, *Shank length*, *Trunk length*, *Stance width*, *Hip drop*; 0 to 0
leaves that length as the design has it. *Overall height* From / To leaves
out bodies that would stand lower or taller (it is the height readout of
Form: the highest part's centre, 187 mm for a calf without ears at scale
0.337). *Front and hind legs* > **Vary separately** gives front and hind
legs their own thigh and shank (twice the unknowns: raise *Bodies*). Under
*Search*: **Bodies** (how many to try besides the design itself), **Gaits**,
**Iterations** and **Popsize** (how hard each gait is searched, as in Tune),
**Duration s**, **Speed fraction** (as in Tune), **Min speed mps** (slower
than this does not count as walking). Press **Run proportion study**. It is a
job with progress and Cancel; 40 bodies with the defaults take about five
minutes on this machine (24 with the defaults about three). The document is not changed.

What it does: it spreads the bodies evenly over your ranges (a Latin
hypercube), builds each from the working design with only those lengths
changed, searches a gait for it in each footfall pattern within the motors'
speed caps, then runs the best one for 15 s and measures that run. Leg
lengths are set through the front/hind length sliders (it switches *Front
and hind legs have their own lengths* on in the bodies it tries) because
those reach further than *Thigh length* / *Shank length*. A range wider than
a slider is cut to the slider and the study says so: at scale 0.337 the
trunk can be 101 to 189 mm.

Reading it:

* **Read this first** lists what the numbers rest on: ranges that were cut,
  each motor and battery value that is unverified, guessed or a library
  default, the voltage note, and the model settings in use.
* The buttons **walk n/m**, **trot n/m**, **bound n/m** switch the gait; n of
  m bodies work in it.
* **Bodies in <gait>**: one row per body. `b00` with the badge *design* is
  the working design. Columns: the lengths you varied, **Height** (mm),
  **Mass** (g, as simulated), **Works**, **Speed** (m/s), **Torque margin**
  (the worst joint: 1 - peak torque / usable torque), **Speed margin** (the
  worst joint: 1 - peak joint speed / the motor's no-load speed), **Battery
  peak** (A). Click a header to sort. Red is under 5 %, orange under 30 %.
* **Works** = yes means: upright for the whole 15 s, forward faster than
  *Min speed mps*, at a joint limit at most 2 % of the time, and no joint
  faster than its motor. Hover *no* for the reasons. "A motor is at its
  torque limit" and "battery peak current over its limit" are reported but
  do not by themselves make it *no*.
* The badge **front** marks the bodies no other working body beats on both
  speed and torque margin at once: the trade-off. Everything not marked is
  worse than some marked body on both counts.
* **Trends in <gait>** (with ten or more bodies): which lengths go with more
  or less speed, torque margin and stability, as rank correlations. A
  direction to look in, not a law, and blind to interactions.
* Click a row for **<body> in <gait>**: the flags, then the **torque-margin
  table per joint** (*Peak torque*, *Usable*, *Margin*, *At limit* = share of
  the time at the torque limit, *Peak speed*, *No-load*, *Margin*) and the
  battery line (mean and peak current against the pack's limit, runtime).
  **Replay** simulates that body with that gait without changing the
  document (the poses play in the *Viewport* tab; click it). **Use this
  body** loads the body and that gait into the document; Ctrl+Z undoes it.

A study is a run like any other: `runs/<id>/run.json` (kind `study`: the
settings, the ranges used, model and simulation settings, mass record, the
boards, the notes, how many bodies work per gait) and `runs/<id>/study.json`
(the boards every body carried, then every
body: its genome, lengths, height, mass, and per gait the tuned gait, the
metrics, the joint table and the battery load). From the command line:
`run_study thigh_min=20 thigh_max=100 shank_min=20 shank_max=100`,
`simulate_study_body run=<id> body=b07 gait=trot`,
`adopt_study_body run=<id> body=b07 gait=trot`.

Cautions. The gait search is short and has luck in it: two studies with
different seeds will not rank the bodies identically, and a body that "does
not work" may only not have found its gait in 10 iterations. Compare groups
of bodies, not neighbours in the table. **Bound**: the controller can
command the footfall pattern (front pair together, hind pair together), but
it is open loop: it has no flight phase to aim for and no pitch feedback, so
what the simulation calls a bound is a rocking shuffle. A real bound needs a
controller that times push-off and landing from the trunk's pitch; that is
not built. **No abduction**: all eight joints turn about the same sideways
axis, so the legs can neither place a hoof sideways nor push back against a
roll. In the simulation that shows as *sideways drift* and *roll* that
nothing corrects (both are in the body's detail line), and as falls to the
side in the gaits that stand on two legs at a time; *Stance width* is the
only setting that widens the base.

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
harness with routed cable lengths and a diagram. The cables are drawn in the
viewport (switch to the Viewport tab); click a row of the harness table to
highlight that cable in yellow. Each cable is drawn along the path its
length is measured on: from its source, through the origins of the leg
parts it passes, to its destination, before slack. The model has the battery
lead, one servo bus per leg (to the knee motor), the neck bus, the IMU and
the Pi link; foot, touch and microphone sensors have no cables yet. WireViz YAML is exported
always; the full WireViz drawing needs Graphviz (`winget install
Graphviz.Graphviz`), otherwise a simple built-in diagram is shown.

### Journal
Markdown entries stored in `journal/`, with the viewport beside the editor
and *Runs* and *Designs* on the right. *Link run...* is a list of every run
(time, kind, title, fitness); the run you last clicked in *Runs* is at the
top as "Selected in Runs". *Link design...* lists the baked designs. The
link (`calflab://run/<id>`, `calflab://design/<id>`) goes in at the caret, so
one entry can link several runs without typing an id. In a saved entry a run
link replays that run. *Capture viewport* attaches an image with provenance.

### Behave (ADR-073 to ADR-078)
Behaviors from reference footage.
#### From a video in a folder (ADR-076, ADR-077, ADR-080, ADR-081)
1. **Drop a video** (mp4, mov, avi, mkv) of a calf into
   `<project>\footage\videos\`. In **3D mode** (below) any view works
   (turned, walking toward or away, an off-axis camera); in 2D mode, film
   from the side. The lab looks at that folder every two
   seconds; the **Video inbox** at the top of the Behave panel lists each
   file:

   | Status | Meaning |
   |---|---|
   | *waiting* | still being copied |
   | *queued* | waiting for its turn (one video at a time) |
   | *tracking* | the pose tracker reads it, with a progress bar and *Cancel* |
   | *retargeting* | turning the keypoints into joint angles |
   | *needs review* | candidate clips are ready |
   | *ready* | every candidate accepted or rejected |
   | *failed* | with the reason; *Retry* after fixing it |

   *Retry* tracks the video again; *Analyse again* keeps its tracks and
   only re-runs the analysis with the current *Settings* (use it after
   switching between 2D and 3D or changing a map).

   A video is processed once. The lab keeps its SHA-256; a file you replace
   with different content is processed again, a file merely touched is not.
   *Scan now* looks at once.
2. **The tracker.** By default *RTMPose AP-10K*: a pretrained animal model
   (17 keypoints, Apache-2.0, trained on AP-10K, CC-BY-4.0) that runs on
   your AMD graphics card through DirectML. Its weights live in
   `C:\CALFLABHOME\models\`; if they are missing, the panel offers
   *Download* (or run `.\calflab.ps1 tracker download`). Other trackers:
   *CSV next to the video* (put `myvideo.csv` from DeepLabCut, SLEAP or
   hand tracking beside `myvideo.mp4`) and *Colour markers* (painted
   markers, and the synthetic test calf). Change them under *Settings*,
   with the retarget map and the segmentation thresholds;
   `.\calflab.ps1 tracker list` shows what is ready.
3. **2D or 3D** (*Settings* > *mode*, per project). **3D** is the default
   for new projects; a project that processed videos before stays 2D until
   you switch it.
   * **3D lift**: the robot's own skeleton (its joints, ranges and standing
     pose) and a camera are fitted to every frame so that the robot's
     landmarks land on the tracked points. Both sides are used, so the far
     legs are tracked, hip ab/adduction is measured where the view shows it,
     and the animal's turning becomes part of the clip. Map: `ap10k_3d`
     (or `feral_calf_3d` for points on the robot's own joints).
   * **2D side view**: angles measured in the image, as before; map
     `ap10k_side`.

   In 3D the lab also reports, for the whole video: the camera's elevation
   (and whether it seems fixed), the calf's proportions against the robot's
   (trunk length, width and front leg, relative to the hind leg), and where
   the tracker's Hip, Knee and Shoulder sit on the robot (hover the ⓘ).
   When the footage cannot tell the calf's width, it uses 0.35 x the trunk
   length (PROVISIONAL) and says so.
4. **What the lab works out (2D).** Which side faces the camera (an animal
   facing right shows its right side; with AP-10K the confidence of each
   side is a cross-check) and whether it is a side view: "side view OK",
   "too oblique" (judged from how far apart the left and right hips and
   shoulders appear; that assumes a trunk width of 0.35 x its length), or
   "unknown" with one side tracked. Then it cuts the video into
   **candidates**:
   * *idle*: still for a second or more;
   * *gait*: moving with a repeating rhythm, cut to whole cycles, its
     period shown, far legs half a period behind;
   * *other*: moving without a clear rhythm.

   Angles are relative to the middle of the video's longest still stretch.

   **In 3D** there is no "too oblique": each frame gets a **reliability**
   instead: *ok*, *ambiguous* (usable, but a second answer fits nearly as
   well: whether the calf is turned toward or away from you, or a leg bent
   one way or the other) or *unreliable* (too few points, a fit that stands
   out, or more than 70 deg from a side view: nearly head-on or tail-on).
   Unreliable stretches longer than a third of a second are gaps that no
   candidate covers. Candidates are cut on the 3D angles; each shows how
   much of it is reliable, its yaw range and how far the calf turns. If the
   video has no still stretch, the angles are relative to the robot's own
   standing pose and the candidate says so.
5. **Review** (click *Review*): the video frame with the tracked points
   drawn over it (orange = the points the map uses, hollow red = below the
   confidence threshold), *Play* and a frame slider. *Play* shows the frames
   as fast as they arrive and skips late ones (it never stalls on the
   first). In 3D a **strip under the slider** shows each frame's
   reliability (green ok, amber ambiguous, red unreliable) and a line for
   the estimated yaw (middle = side view, up = turned toward you, down =
   away); below it, the current frame's state, yaw, heading, fit residual
   and reasons. Click the strip to jump. *Start here* /
   *End here* trim the cut (a gait stays whole cycles). *Preview on robot*
   poses the body with the cut (no physics), replays it in the viewport and
   shows the body report: per joint the range the clip uses against the
   joint's range and the peak speed against the servo's (ab/adduction
   included in 3D), and in 3D how far it turns and travels and how each leg
   was obtained (*tracked*, or copied from the other side where a leg was
   hidden most of the time). The turn is in the clip and the preview; the
   simulator does not steer to follow it yet. Then:
   * **Accept as clip**: give it a name and **your affect tags**: valence
     (-1 unpleasant to +1 pleasant), arousal (0 calm to 1 agitated), words
     (comma-separated: wary, curious) and a note. Leave a value *not set*
     if you have no reading. The lab never infers or fills these.
   * **Reject**.

   The clip keeps where it came from: the video's hash, frames, tracker
   and model version, the map, the cleaning and segmentation settings, and
   its smoothing (below).

   **Clip smoothing** (*Settings* > *clip_smoothing*, ADR-082). A tracker's
   points jitter by a few pixels per frame, which reads as hundreds of deg/s
   in the body report. Every clip previewed or accepted is therefore
   low-passed (joint angles and the trunk's path; no lag; never past the
   range the raw angles covered):
   * **auto** (new projects): the cutoff is found from the video (Winter's
     residual analysis: the lowest cutoff at which what the filter removes
     is down to the noise level). The clip records the cutoff, the noise
     level in degrees, and every joint's peak speed before and after.
   * **lowpass**: at *clip_smoothing_hz* (6 Hz is the usual choice for
     walking).
   * **none**: as retargeted. Projects whose settings were saved before this
     existed start at *none*; clips already accepted are never changed.

   **Repeated frames** (*Settings* > *repeated_frames*, ADR-083). A screen
   recording of a video playing, or a phone that drops frames, writes some
   images twice: the file says 30 fps but the calf moves in every other
   frame, so per frame the motion is nothing, then a double step, and peak
   speeds double. When a video is analysed the lab finds such frames in the
   images themselves (a frame barely different from the one before; runs of
   more than 3 count as a still scene and are kept), and with
   **interpolate** (new projects) every clip is re-timed across them: a
   value at a repeated frame is interpolated between the frames around it.
   **keep** uses every frame as it is (projects whose settings were saved
   before this). The clip records how many of its frames were re-timed.
   Better still, record the original file rather than a screen recording.

   **Which way a leg bends** (*Settings* > *lift* > `bend_choice`,
   ADR-083). Where a leg could be bent two ways that fit a frame nearly
   equally, **window** (new projects) keeps both per frame and chooses the
   bend over the whole video, on the fit of every frame and how smoothly
   the leg moves between them; a leg is *ambiguous* only where the whole
   video cannot decide. **frame** chooses frame by frame, as before
   (projects whose settings were saved before this).
6. **Clips** can be filtered by your tags (*Filter by your affect tags*)
   and renamed or re-tagged (*Name and tags*).

**Check on your own footage** before trusting it: tracking accuracy, where
AP-10K puts "Knee" on a calf's hind leg and "Elbow" on its fore leg (the
`ap10k_side` map splits the hind fold half and half between stifle and
hock, and takes the carpus from the fore "Elbow"), and where the
segmentation cuts. To change the map, copy
`config\retarget\ap10k_side.yaml` (2D) or `ap10k_3d.yaml` (3D) to
`<project>\motions\maps\`, edit it, pick it in *Settings* and *Analyse
again*.

**Comparing 3D lifts.** The last lift with each map and bend choice is kept
per video (`footage\lift\<hash>.<map>.json` frame by frame,
`<hash>.<map>.window.json` over the window). After *Analyse again* with a
second map or bend choice, the command `compare_lift_maps file="<video>"`
(command line; `maps=[...]` to pick lifts, `ranges=[[0,109],[140,225]]` for
frame ranges, `jump_deg=12`) gives, side by side: reliable and ambiguous
shares, per leg how often it is ambiguous, how often a second bend fits in
the frame alone, and how many steps between reliable frames move one of its
joints more than 12 deg (also after re-timing); the median residual per
landmark, the fitted proportions, the hind angles over the frames all lifts
call reliable; and the playable speed of each candidate (or range) raw,
smoothed, and smoothed and re-timed, with the joint that limits it.
`projects\robot-calf-final` has `ap10k_3d_hock`: AP-10K's hind Knee on the
hock, the hock untied.

**What 3D cannot recover from one camera:** a camera that pans or zooms
looks like the calf turning or approaching (keep the camera still); how far
the calf travels toward or away from you rests on an assumed 60 deg field
of view; the head, neck and tail (the robot has no joints there); a calf
seen head-on or tail-on (unreliable); the calf's width when it never turns
and the camera is level (the 0.35 prior is used); and hip pitch on the hind
legs (the robot has none, so the stifle and hock carry the swing). Joint
speeds from noisy tracks are higher than the calf's real ones; clip
smoothing and re-timing (above) remove the jitter and the recorder's
stutter, not a fast movement the fit really sees.

#### Judging a clip in physics, and a feasible version (ADR-084)
*Preview on robot* poses the body frame by frame: it knows the joint ranges
and the servos' no-load speed, but not mass, contact, belts or springs. Two
buttons beside it (in the candidate review, and on every clip row) judge
the clip on the hardware's limits instead. Both are jobs with progress and
*Cancel*, and both leave runs that replay in the viewport.

**Play in physics** plays the clip once in MuJoCo through the behaviors
controller: a 1 s ease from standing into the clip's first pose, the clip
at its own speed, a 1 s return and half a second of standing. Servos are
limited by their **torque-speed envelope**: stall torque falling to zero at
the no-load speed, from the library's two numbers only. Belts and springs
are as the design has them. Every limit is lowered by your **margin**
(0.2 = keep 20 % in hand). The report shows:

* a verdict (*within limits*, *over a limit*, *falls*) and the limit that
  is crossed first: which joint, which force, when, and the video frame;
* per joint: tracking against the clip (RMS, peak), peak torque against
  rated and stall, peak speed against the servo's speed at the joint,
  envelope use, and belt tension against the allowable working tension.
  After a fall the table stops at the fall, like the constraints;
* the constraints with the margin: the same ones the repertoire evolution
  judges by;
* hooves: share of the clip on the ground (and the planned share, if the
  clip was planted), peak force against body weight, impacts. The library
  has no hoof limit, so these are reported, not judged;
* the battery: mechanical power, and the current only as a **lower bound**
  while the servo has no stall current in the library;
* a **time strip**: one row per limit, green within, amber over 90 %, red
  over. The top band marks lead-in, clip and return. Click a cell to move
  the replay there, and the review frame to the matching video frame.
  Under it, every span over a limit is listed and clickable too;
* what the numbers rest on: mass as entered and the parts with no mass, the
  servo entry (unverified, missing values, default armature), the
  PROVISIONAL values.

**Make feasible** searches for a version that stays within every limit with
the margin. It never changes the clip itself. What it may do, in this order:

1. scale the amplitude per joint (left and right together);
2. low-pass the angles;
3. keep them a few degrees inside the ranges;
4. **plant** the clip: decide from the clip which hooves support in each
   frame, keep at least three down (four if three falls), hold supporting
   hooves still on the floor and the centre of mass over them, and solve
   the ease in and out the same way;
5. slow the clip.

It starts from the clip planted, 2 deg inside the ranges and slowed until
every joint is within its servo's speed with the margin. Then it plays a
version, takes the worst limit (a fall first) and tries what helps that
limit. For a fall: keep four hooves down, a larger stability margin,
smaller, slower, smoother. For torque or a belt: smaller at that joint,
slower, smaller overall. If nothing aimed at the limit helps, it tries the
broad remedies too. Once every limit holds, it **gives back**: faster, and
larger at each joint pair, as long as everything still holds.

The report then shows raw and adapted side by side. For each: what limits
it first, what is still over, tracking, the smallest margin, the busiest
servo, the duration and the **character kept**. Character is quantity of
motion, expressive range, tempo, and shape (the angles reached against the
clip's at the same point of the clip, so slowing alone costs nothing
there), each against the raw clip and capped at 1, plus their geometric
mean. It is a measure of movement, not of feeling. Then the constraints
with values against limits, the search's steps, and buttons to see the
details (and the replay) of either version.

* For a **library clip** the version is saved as a new clip
  `<id>-feasible`, with `meta.adapted_from`, the operations, the margin,
  the stance numbers and the run. The clip itself is never changed.
* For a **candidate** it stays in the run: press *Keep adapted clip* to add
  it to the library.

Each row lists its last physics play and feasible version with *Show*.
The search plays the clip 15-60 times; on the first video it took 4-6
minutes per candidate.

Command line: `play_in_physics clip=<id>` or
`play_in_physics file="<video>" candidate=c1 margin=0.2`,
`adapt_clip ... settings={"max_rounds": 12, "min_support": 3}`,
`keep_adapted_clip run=<adapt run>`, `physics_report run=<id>` (or with
`clip=` / `file= candidate=` to list runs). Runs: kind `physics`
(`physics.json`) and `adapt` (`adapt.json`, `adapted_clip.json`). The
as-retargeted play of an adapt run is a `physics` run whose parent is the
adapt run.

What it does not do yet: move contact phases in time, let the robot step
to new places while slowed (four hooves down means the hooves stay where
they stood), or optimise a trajectory.

#### Interpreting footage as the robot's own movement (ADR-085)
Replaying a calf's joint angles makes slow sways on this body (above).
Interpretation reads **what the calf does** and says it in movements the
robot balances by itself. The **Interpretation** section of the Behave panel
has two buttons:

* **Read footage** labels every lifted video in stretches: *stand*, *weight
  shift* (all hooves down, the body moving), *step* (one or two lifts),
  *walk*, *turn* (turning more than it travels) and *other* (fast: two or
  more hooves up most of the time, as in trotting, cantering or bucking).
  Each stretch keeps its rule, its features and a confidence. A hoof counts
  as lifted while its tracked paw moves over the ground (paw speed minus the
  ground's shift in the image, so a following camera does not count).
  Videos that cannot be read are listed with the reason (too few reliable
  frames, a calf too small in the image). Per behaviour it measures tempo,
  phrasing, amplitude, quantity of motion, footfall order, duty factor,
  trunk sway, pitch, turn, lean and how abruptly it starts, and fits a
  semi-Markov model (which behaviour follows which, how long each lasts),
  with each video's counts kept. It says in words how much the footage can
  support. Stored in `footage/readings/<id>.json`; the command
  `reading_report` shows it. To try it without footage:
  `read_footage synthetic=[["stand",2],["walk",4]]` reads a known sequence
  posed on the robot.
* **Interpret** takes the latest reading. For each behaviour it tries every
  *motion primitive* that may stand for it (stand, weight shift, step, walk,
  turn, trot, lie/rise), with a small search over its few parameters. Every
  candidate is played in physics (torque-speed servos, belts, springs) and
  read back by the same reader as the calf; the closest one within every
  limit with your margin wins. Then it plays a minute with three seeds,
  drawing behaviours, durations and parameters from the model and switching
  only where every hoof is down. A job of a few minutes (plays are cached
  per body, so a second run costs little); a run of kind `interpret`.

The report shows, side by side with the calf:

* shares of each behaviour (calf; robot as played; robot read back by the
  same reader), median durations, transitions;
* per behaviour, the primitive and parameters chosen, and per feature
  *kept*, *exaggerated*, *reduced*, *reversed* or *dropped* with the reason:
  the limits that stopped closer candidates, a limit it is close to, or the
  primitive's own range;
* the walk and trot as they are and as interpreted, at margin 0.2;
* each performance's verdict, margin and falls;
* what the calf did that this body cannot express (head and neck, tail,
  hind hip swing, front ab/adduction, spine, fetlocks, airborne movement):
  listed, never approximated;
* the character kept by Make feasible (ADR-084) for comparison;
* a time strip: the calf's stretches per video (click one to open its
  frames in the Review) and each performance's behaviours and limits (click
  to seek the replay of the first seed).

Commands: `read_footage`, `reading_report`, `interpret_footage`
(`seconds`, `seeds`, `margin`, `settings` such as `popsize`, `generations`,
`primitives`), `interpretation_report`. A new primitive is a plugin:
`.\calflab.ps1 new-plugin motion_primitive <name>`.

#### Composing behaviors (ADR-078)
The Stochastic behaviors form has a **Composition** group:

| Setting | What it does |
|---|---|
| *Tempo* | clip speed, the gaits' clock and the idle sway's pace |
| *Amplitude* | scales clip angles and the idle sway |
| *Idle share* | stillness: the chance the next behavior is an idle one (-1 = weights decide) |
| *Low-pass* | smoothness: filters the commands (lower Hz = smoother); with *Blend* |
| *Repeat* | phrasing: the chance to play the same behavior again right away |
| *Pause*, *pause length* | phrasing: hold the pose for a moment between behaviors |

A clip entry of the repertoire can choose its clips **by your tags**
instead of by id: `{"name": "wary moments", "kind": "clip", "select":
{"words": ["wary"]}}`, or `"select": {"arousal": [0.6, 1]}`.

The **affect curve** sets any of these over the run, e.g. calm then
agitated:

```json
[{"t_s": 0, "label": "calm", "tempo": 0.7, "idle_share": 0.6, "lowpass_hz": 2, "target_arousal": 0.2},
 {"t_s": 40, "label": "agitated", "tempo": 1.4, "idle_share": 0.1, "target_arousal": 0.8}]
```

Values move linearly between keyframes. A target valence or arousal
favours clips *you* tagged near it. What "calm" means in tempo or stillness
is yours to set: the lab has no mapping of its own. The episodes list shows
which label was in effect.

**Composition study** (bottom of the panel): list compositions as
`[{"name": "...", "params": {...}}]` (behaviors settings over the ones
above), the seeds and the length, and *Run study*. The table gives, per
composition, mean +/- spread over seeds of:
* falls;
* clip tracking error;
* safety margin and the constraints violated (see Evolve);
* the **movement features**: quantity of motion, trunk speed, jerk and
  smoothness, tempo and its regularity, stillness ratio, expressive range,
  postural height, openness (stance width), approach / retreat.

These are kinematics, not emotions: how a composition *reads* is your
judgement. The study is compiled with full servo torque (as the load
analysis), and its CSV is in the run folder.

#### Keypoints tracked elsewhere (CSV import)
The older route, still there for tracking done outside CALFLAB:
1. **Track the video** with a pose tracker: DeepLabCut, SLEAP, or clicking
   points by hand in any video tool. Track the landmarks the retarget map
   names: hip, withers, stifle, hock, hind fetlock, shoulder, carpus, fore
   fetlock, and the hooves for the ground line. From a side view, track the
   near legs.
2. **Copy its CSV** into `<project>\footage\`. DeepLabCut's own CSV works,
   as does a long one (`frame,keypoint,x,y,likelihood`) or a wide one
   (`frame,hip_x,hip_y,...`).
3. **Import footage keypoints**: pick the file, the frame rate and the
   retarget map (`feral_calf_side`; copy it to `<project>\motions\maps\`
   and edit it if your labels differ). The clip records the animal's change
   from its reference frame (the first, the median or a frame you give),
   applied to the robot's standing pose. The far legs copy the near ones,
   or follow half a gait later.
4. **Clips** shows, for each clip, what this body can play of it:
   * *plays*;
   * *clamped*: some frames are past a joint's range and are played at the
     limit;
   * *too fast*: faster than the servos; play it at the speed shown.

   Click a clip's name for the per-joint table. *Preview* poses the body
   frame by frame (no physics) and replays it.
5. **Add to behaviors** puts the clip into the stochastic behaviors at a
   speed the servos can follow, switching the simulation's controller to
   *Stochastic behaviors* if needed.

That controller picks, with the run's seed, among idle sway, walking,
trotting and your clips, each with a random duration, speed and amplitude,
and sometimes mirrored left/right. The *transitions* table makes it a Markov
chain. F5 simulates; the behaviors it chose are listed under the panel and
stored with the run. Fitness preset `behave` rewards following the clips
(the `imitation` term) without falling.

### Deploy *(planned, Phase 3)*
This tab explains what will live there and lists the plugins already
scaffolded.

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
  runs/<id>/             run.json + rollout, scene, model, archive, candidates, study
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
  as layered geometry with blocks and ID user text (and each object's
  material, mass and mass source), and the harness routes as polylines on
  `CALFLAB::Harness`; `CalflabPush` sends geometry back as an override: a
  sculpted skin, or a closed solid that gives a part its mass (section 4);
  `CalflabLiveSync` follows changes.
* **Grasshopper**: open `bridges/rhino/grasshopper/calflab_example.gh` with the
  lab running: GetDesign shows the genome and mass; move the slider and switch
  `apply` on to change a gene; `run` simulates and GetMetrics shows the result;
  `bake` builds the design in Rhino. (Hops endpoints also exist at
  `http://127.0.0.1:8000/hops/...` but are untested: Hops is not installed.)
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

**Adding your own component or material.**

```powershell
.\calflab.ps1 components new actuator my_servo --name "Maker Model 123"
```

appends a blank entry to `config/components/actuators.yaml` (kinds:
`actuator`, `sensor`, `board`, `battery`, `material`). Open the file and
enter each value from the datasheet; the comment on each line gives the unit.

* `verified: false` stays until you have checked every value and set it.
* A value marked REQUIRED that is still blank keeps the entry **incomplete**:
  it is not offered anywhere and the audit lists what is missing. Nothing is
  filled in for you.
* A value the datasheet does not give: enter your best guess and add the
  field's name to `guessed:` (for example `guessed: [armature_kgm2]`).
* An optional value left blank uses the program's default and is reported as
  **default assumed**. For a small servo the defaults (armature inertia,
  thermal values) are those of a much larger motor, so do not leave them.

Once complete, an actuator appears in the four actuator lists in Mechanism,
a battery in the battery list and a board in the two board lists, with no
other file to edit; a structure
material appears in *Properties > Material* and in the `CalflabPush` prompt.
The bill of materials, mass, torque-margin table, power budget and *Tune for
this body* all read the entry: its no-load speed is the joint speed cap of
gait tuning. Guessed and defaulted values carry a badge on the component
card in Properties. Sensors are chosen for all projects in
`config/robot_defaults.yaml` (not yet per project).

A board entry needs only `mass_g`. Its load in the power budget is
`power_w`: if the datasheet gives a supply voltage and a current instead,
enter their product (3.3 V x 0.1 A = 0.33 W) and say so in the comment.
Left blank it counts as 0 W and is reported as **default assumed**. Without
`dims_mm` the board is drawn as a 10 x 10 x 3 mm box. The library has
`esp_wroom_32` (ESP-WROOM-32, 7 g weighed by the researcher, 3.3 V,
0.33 W from "~100 mA"; unverified, no size or cost entered).

`carbon_fibre_leg_tube` (in `materials.yaml`, added 2026-11-04, ADR-086) is
the carbon fibre leg tube you committed the final calf to. You confirmed
it the same day (ADR-088): 15 mm outer, 12 mm inner (1.5 mm wall),
1.55 g/cm3, the values in Form > Tubes, which no longer carry a
PROVISIONAL badge. The density is not a weighed value, so the entry stays
unverified. If you weigh a length: density (g/cm3) = mass per metre (g/m)
/ (pi / 4 x (OD² - ID²) in mm²) x 1000. The robot carries two
`lipo_3s_5000` packs in parallel (11.1 V nominal).

**How much a result rests on an unverified value.** `docs/studies/` holds
one-at-a-time sensitivity studies: `sensitivity_r1.md` (2026-11-04) plays
the walk, the trot and the interpreted trot and step with the mass, the
armature, the spring rates and the servo's torque at the battery's voltage
varied one at a time, and lists which missing value changes a verdict.
`load_r2.md` splits each joint's load in the walk and the trot into the
part that holds the weight and the part that is dynamics, shows how much
the springs carry against what the weight needs at standing, and plays the
levers (springs, splay, leg angles, roll feedback, sway) one at a time.

**The audit.** `calflab components audit` prints these tables:

1. every library component, whether it is verified and how much of it the
   current design uses; then the values that are guesses or assumed
   defaults, and any incomplete entries with what they are missing;
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
panels, commands, pose trackers (`new-plugin pose_tracker my_tracker`: video in,
keypoints with confidences out). `CLAUDE.md` has the rules for each.

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
