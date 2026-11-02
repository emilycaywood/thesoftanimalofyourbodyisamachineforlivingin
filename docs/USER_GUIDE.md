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

**Turning the legs out (ADR-072).** Form > Rear legs and Front legs have
*toe-out* (hooves pointing outward) and *splay* (lower end of the leg
outward) for each pair. They are fixed mount angles of the leg's servo seat,
not held by a servo. The whole leg turns with its mount, belts included, so
the belts' C does not change. The hooves stay on the ground and the back
stays level. 0 = straight.

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
