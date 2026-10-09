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
calf. Simulation settings have not been examined for a body this small.

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
steps those legs with the elbow (sweep) and the abduction (lift). The hind
legs always have three motors. After switching, press *Tune for this body*
in Simulate: no gait made for three-motor front legs suits two-motor ones.
It walks acceptably when the front joint is high and points backward
(**Front knee forward** off, a short front thigh and long front shank, set
with overrides on `leg.fl.thigh`, `leg.fr.thigh`, `leg.fl.shank`,
`leg.fr.shank`), and poorly with the knee mid-leg pointing forward.

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
Actuator choice per joint group, knee drive (direct or belt) and battery.
The lists offer every complete actuator and battery entry in
`config/components` (section 9). Then a **torque-margin table**: required peak torque from a chosen simulation run
against available torque (stall x derating). Red means the actuator saturates
in that run. Every actuator carries an **unverified** badge until you check
its data (section 9). *(planned: range-of-motion sweep, interference check)*

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
peak, torque margin, first-order thermal estimate, foot impact speed (noise
proxy), time to stand from lying, time at joint limits.

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

Once complete, an actuator appears in the four actuator lists in Mechanism
and a battery in the battery list, with no other file to edit; a structure
material appears in *Properties > Material* and in the `CalflabPush` prompt.
The bill of materials, mass, torque-margin table, power budget and *Tune for
this body* all read the entry: its no-load speed is the joint speed cap of
gait tuning. Guessed and defaulted values carry a badge on the component
card in Properties. Boards and sensors are chosen for all projects in
`config/robot_defaults.yaml` (not yet per project).

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
