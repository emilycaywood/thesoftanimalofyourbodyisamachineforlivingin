# Decision log (ADRs)

Append-only. One entry per decision or assumption. Status is `accepted` unless
noted. Entries marked **VERIFY** are assumptions the researcher must check.

---

## ADR-001 — Python 3.12 managed by uv, not the system Python
The machine has only Python 3.14. MuJoCo, pyribs, rhino3dm and the OpenCascade
wheels behind build123d are not all published for 3.14, so the project pins
`>=3.11,<3.13` and uv downloads 3.12.

## ADR-002 — `calflab.ps1` is the bootstrap entry point
`uv` was installed with `python -m pip install --user uv` and is not guaranteed
to be on PATH. `.\calflab.ps1 <subcommand>` sets the environment variables below
and runs `uv run calflab ...`. After `calflab setup` the same commands work as
plain `calflab` inside the activated environment.

## ADR-003 — Environments live outside the repo (`%LOCALAPPDATA%\calflab`)
The repo is on a Google Drive virtual volume (FAT32, no junctions, no
symlinks, every file is synced). A virtualenv or `node_modules` there is slow
and unreliable. Therefore:

* Python venv: `%LOCALAPPDATA%\calflab\venv` (`UV_PROJECT_ENVIRONMENT`).
* Web: when the repo filesystem cannot host `node_modules`, a work directory
  `%LOCALAPPDATA%\calflab\web` holds `node_modules`, copies of the top-level
  config files, and directory junctions back to `web/src`, `web/public`,
  `web/tests`. Vite/TypeScript run there with `preserveSymlinks`. On a normal
  NTFS checkout `web/` is used directly.
* `CALFLAB_HOME` overrides the location.

**Recommendation:** move the working copy to a local folder (e.g.
`C:\dev\calflab`) and rely on GitHub for backup. Git inside a synced Drive
folder is a known source of repository corruption.

**Update 2026-10-01:** the working copy now lives in `C:\CALFLABHOME`, a
plain local NTFS folder that no sync client touches, so `web/node_modules`
and `web/dist` are in-tree there. (It briefly sat in a OneDrive folder, which
is NTFS but still cloud-synced.) The rule that remains in the code is "never
put environments inside a cloud-synced folder":
`calflab.cli.webenv.cloud_synced` detects OneDrive / Google Drive / Dropbox /
iCloud and falls back to the out-of-tree work directory.
`CALFLAB_WEB_IN_TREE=1` overrides it. The Python venv stays in
`%LOCALAPPDATA%\calflab` in every case. GitHub is the backup of the repo.

## ADR-004 — One distribution, two import packages
`pyproject.toml` at the repo root builds `calflab` (from `core/`) and
`calflab_server` (from `server/`). The boundary is enforced by a test that
fails if `calflab` imports `calflab_server`, FastAPI or any UI module outside
`calflab.cli`.

## ADR-005 — World frame and units
X forward, Y left, Z up. mm / g / degrees in files, API payloads and UI; SI
inside the simulator. `calflab.units` is the only conversion site. The three.js
scene is Z-up so Rhino and the web viewport agree.

## ADR-006 — Stable IDs are dotted, human-readable paths
`trunk`, `leg.fl.thigh`, `joint.fl.knee`, `act.fl.knee`. They are produced
deterministically by the part generator and used as Rhino user text
(`calflab.id`), Blender bone names, scene-graph keys and fabrication labels.

## ADR-007 — Two-stage part generators make overrides explicit
`PartGenerator.element_params(genome)` yields per-element parametric values
with the gene that drives each one; `PartGenerator.build(params)` produces the
`RobotSpec`. Overrides are applied between the stages, so a direct edit is
always a named record against `(element, param)` and can be toggled, removed
or internalized into the driving gene. Rhino-sculpted geometry is an override
of kind `geometry` that replaces an element's visual mesh.

## ADR-008 — The graph is the document
Genome values and controller parameters are stored as params of their nodes in
the project graph. Convenience commands (`SetGenes`) address the node by type.
There is exactly one source of truth and the node editor always reflects it.

## ADR-009 — Event-sourced undo with state patches
Each document command records forward and inverse JSON patches (whole-value
replacement at a path). The log is `commands.jsonl` (git-friendly). Undo/redo
is a cursor; a new command after undo truncates the redo tail (kept in the
file as `"discarded": true` for the research record).

## ADR-010 — Viewport renders primitives from scene JSON; glTF is an exporter
The server evaluates the design into a scene description (bodies, primitive
geoms, joints, rest poses). The viewport instantiates three.js primitives from
it, which makes slider edits cheap and lets simulation playback drive the same
objects by ID. A glTF export of the same scene exists for Blender,
documentation and any mesh-based consumers; geoms of type `mesh` are served as
binary assets.

## ADR-011 — Simulation streaming = body poses in chunks
The sim job pushes pose chunks (`body id → position + quaternion` per frame)
over the websocket while it runs and stores the full rollout as `.npz`.
Playback, scrubbing and all overlays operate on poses, never on video.

## ADR-012 — Evolution structure
Outer loop: MAP-Elites (pyribs `GridArchive` + Gaussian/iso-line emitters) over
morphology genes. Inner loop: CMA-ES (`cma`) over controller parameters for
each candidate morphology, with a small budget. The unit of parallel work is
one outer candidate (the inner loop runs inside the worker).

## ADR-013 — Compute tasks are named functions with JSON payloads
`Task(fn="module:function", payload={...})`. This keeps LocalProcessPool,
RemoteSSH and CloudNotebook interchangeable: a task can be pickled, shipped as
a bundle, or run in Colab.

## ADR-014 — Registry: text files are the truth, SQLite is an index
`runs/<id>/run.json`, `designs/<id>/design.json`, `journal/*.md`. The SQLite
index can be rebuilt with `calflab registry rebuild`.

## ADR-015 — Reference calf proportions (**VERIFY**)
Defaults in `config/robot_defaults.yaml` and `config/genes/calf.yaml`: overall
height 610 mm (top of head, standing), nose-to-rump length ~700 mm, trunk
420 × 150 × 170 mm, hip height ~360 mm, thigh 170 mm, shank 170 mm, hoof 30 mm.
These are design assumptions scaled from a newborn calf silhouette, not
measurements. The leg is simplified to two segments (3 DOF) for every leg; the
real fore/hind limb difference is expressed only by knee bend direction.

## ADR-016 — Component specs are recalled from datasheets (**VERIFY**)
All entries in `config/components/*.yaml` carry `verified: false` and a
`source` URL. Values were written from memory of public datasheets and must be
checked before any purchasing or structural decision. The default assignment
(XM430-W350 on hip abduction, XH540-W270 on hip flexion and knee, STS3215 on
neck/head/tail/ears) is a starting point for the torque-margin check, not a
recommendation.

## ADR-017 — Mass model (**VERIFY**)
Structure mass = primitive volume × material density × a shell/infill factor
(default PETG, 18 % effective fill). Actuators, boards, battery are point-like
boxes with library mass. Skin = area × areal density per region. Target
≤ 7 kg; the UI reports the budget, it does not enforce it.

## ADR-018 — Skin model
Per-joint passive stiffness and damping plus added mass distributed over the
covered bodies, computed from the skin region's material and thickness
(`config/components/materials.yaml`). Coefficients are placeholders until
fitted in Phase 3 (**VERIFY**).

## ADR-019 — Actuator model in simulation
Position servos: MuJoCo `position` actuators with `kp`, joint damping, and
`forcerange` = stall torque × derating (default 0.6). The thermal estimate is
first-order: `dT/dt = (I²R − (T−T_amb)/R_th) / C_th` with current from
torque/kt. Thermal constants are guesses (**VERIFY**).

## ADR-020 — Web stack pinned to known-good majors
React 18.3, React Three Fiber 8 / drei 9, three 0.170, dockview 4,
@xyflow/react 12, Zustand 5, Tailwind 4, visx 3, Vite 6, Vitest 3,
TypeScript 5.7, ESLint 9. Newer majors existed on the build date (React 19,
R3F 9, dockview 8, Vite 8, TypeScript 7, ESLint 10); they were not adopted
because their APIs could not be verified during the build. Upgrade one at a
time behind the Playwright smoke test.

## ADR-021 — shadcn/ui-style primitives are vendored, without Radix
`web/src/components/ui.tsx` holds a small set of shadcn-style components
(Tailwind classes, no runtime UI library). The shadcn CLI and Radix were not
used so setup needs no interactive prompts; add Radix primitives when a
component needs real accessibility behaviour (menus, popovers).

## ADR-022 — WireViz output with a built-in fallback renderer
The harness is written as WireViz YAML. If `wireviz` and Graphviz `dot` are
installed it is rendered by WireViz; otherwise a simple built-in SVG renderer
draws connectors and wires so the Wire workspace is never empty. The fallback
is labelled as such.

## ADR-023 — Rhino commands are scripts + aliases
Building a compiled Rhino plug-in needs the Rhino Script Editor GUI. The bridge
ships CPython 3 scripts (`CalflabConnect`, `CalflabPull`, `CalflabPush`,
`CalflabLiveSync`) and an installer script that registers them as Rhino
aliases, so they are typed like commands. The scripts use only the standard
library plus RhinoCommon.

## ADR-024 — Grasshopper via Hops endpoints on the CALFLAB server
`/hops/*` implements the Hops HTTP protocol for GetDesign, SetGenomeParams,
RunSim, GetMetrics and BakeToRhino. GH Python 3 component sources are also
provided; they use the standard-library bridge module (`calflab_rhino`) rather
than `calflab.client`, so nothing has to be pip-installed inside Rhino. A
binary `.gh` example cannot be authored without Grasshopper; a step-by-step
recipe is provided instead (known gap). Neither path has been run inside
Grasshopper yet.

## ADR-025 — Work on a feature branch
Phase 1 is committed incrementally on `phase-1-vertical-slice`; `main` is left
untouched for the researcher to merge.

## ADR-026 — Sample project location
`calflab setup` creates `projects/sample-calf/` in the repo (git-ignored).
User projects default to `projects/<name>/`; bulky derived data (`runs/`,
`exports/`, `.cache/`, SQLite) is git-ignored, text documents are tracked.

## ADR-027 — Flat `node_modules` (`nodeLinker: hoisted`)
The out-of-tree web work directory reaches `web/src` through a junction, which
requires `preserveSymlinks` in Vite and TypeScript. pnpm's default symlinked
layout cannot resolve transitive packages in that mode, so
`web/pnpm-workspace.yaml` sets `nodeLinker: hoisted`. The `e2e/` folder is
copied (not junctioned) into the work directory because Playwright resolves
test files to their real path.

## ADR-028 — Gumball handles are declared by the part generator
`ParamValue.handle_axis` / `handle_frac` tell clients which body-local
direction drives which parameter and where the handle sits. The UI only
projects the drag onto that axis; it never decides what a drag means.

## ADR-029 — Playback overlays are computed server-side
Per-frame foot contact points and support polygons are part of the rollout
payload (`calflab.app.scene.foot_tracks`), so clients draw them without doing
geometry.

## ADR-030 — Single-letter shortcuts act immediately
`B` bakes, `K` plays, `H` hides, `I` isolates, `M` measures (rebindable).
Any other letter typed outside a text field starts a command in the command
line, as in Rhino. This differs from Rhino, where single letters are aliases
confirmed with Enter; it follows the brief's "press B or click Bake".

## ADR-031 — An identical simulation is not re-run
The simulation node's cache key (inputs + code version) is stored with each
run. Running again with identical inputs replays the recorded run instead of
creating a duplicate record. Change the seed to force a new run.

## ADR-032 — Default CPG and fitness numbers are starting points (**VERIFY**)
The CPG defaults (1.6 Hz trot, 14 deg hip sweep, 24 deg knee lift) and the
`walk` preset weights were chosen so the reference calf walks in simulation;
they are not derived from calf gait data. (Defaults replaced on 2026-10-04,
see ADR-047; the reasoning here still holds.) The simulated speed (~0.36 m/s for
the default, up to ~0.8 m/s after evolution) says nothing about the real robot
until actuator and skin parameters are identified (Phase 3).

## ADR-033 — Environment built during Phase 1 is inside the Claude app sandbox
The Phase 1 build ran inside the Claude desktop app, whose `%LOCALAPPDATA%` is
redirected to a per-app location. The venv and `node_modules` created there are
not the ones a normal PowerShell session sees: run `.\calflab.ps1 setup` once
in your own terminal.

## ADR-034 — Blender bones are perpendicular to their joint axes
A Blender bone hinges cleanly only about one of its own local axes. The
armature plan (`calflab.bridge.blender`) therefore moves each bone's tail so
the bone is exactly perpendicular to its joint axis; the add-on rolls the bone
so local Z is that axis and stores the sign (`calflab_sign`). Bones may not
point exactly at the next joint: that is cosmetic. Found by checking every
hinge numerically in Blender 5.2.2 (head pitch was 46 degrees off its axis).

## ADR-035 — Recorded body poses are synchronous with joint angles
`mj_step` leaves body poses one physics step behind `qpos`. The rollout
recorder now refreshes kinematics before recording, so poses and joint angles
describe the same instant and clients that rebuild poses from angles
(Blender) agree with the viewport to ~0.02 mm. `CODE_VERSION` was bumped to 2,
which invalidates cached rollouts; runs recorded before this have poses that
lag their joint angles by 2 ms.

## ADR-036 — The Blender bridge ships as an extension (Blender 4.2+)
`blender_manifest.toml` plus a flat zip, installed with
`calflab bridge blender --install` (`blender --command extension
install-file`). Blender 4.0/4.1 (legacy add-on zips) are no longer supported.
The trunk trajectory is carried by the armature object, as
`T(p) R(q) T(-p0)` with `p0` the trunk's standing position.

## ADR-037 — Component audit: what each spec field feeds is declared, not traced
`calflab.wiring.audit.FIELD_USES` states, per component kind, which results
each spec field feeds (mass, geometry, simulated torque limit, torque margins,
power, runtime, thermal estimate, BOM cost). It was written by reading the
code that consumes the library, not derived automatically; a test fails when
a component model gains a field that the table does not classify. Fields with
no uses (`no_load_speed_rpm`, `gear_ratio`, `max_temp_c`, actuator and board
`voltage_v`) are recorded but read by no calculation yet. An actuator counts
as "at its limit" when its torque margin in the chosen run is 1 % or less.
The verification worksheet (`docs/component_verification.csv`) is tracked in
git because the researcher fills it in; the command will not overwrite it
without `--force`.

## ADR-038 — Bridges are checked by scripts that drive the real applications
"Verified in Rhino / Grasshopper / Blender" means a check script ran inside
the application against a live lab and asserted numbers:
`calflab bridge rhino --check` (`validate_in_rhino.py`),
`calflab bridge rhino --grasshopper` (`grasshopper/build_example.py`) and
`calflab bridge blender --check` / `--check-ui`. The Rhino check types the
real `CalflabPush` alias with its prompts answered from the macro; the Blender
UI check sends simulated mouse events (`--enable-event-simulate`). None of
this is a person using the tool: what the model looks like, and anything
dragged or typed by hand, stays on the researcher's verify list. The checks
edit the open project (and undo it), so they are meant for a scratch project.

## ADR-039 — Rhino primitives are NURBS Breps
Sphere, capsule and cylinder Breps are converted to NURBS
(`Brep.MakeValidForV2`) before the server's transform is applied. The
transforms are rounded to six decimals and therefore not exactly rigid; a
revolved capsule could become invalid under one, and Rhino then refused to add
it without an error (the shanks disappeared after a shank-length edit).
`add_primitive` now raises if Rhino rejects an object. Consequence: pulled
spheres and capsules are NURBS surfaces, not exact revolved surfaces.

## ADR-040 — The Grasshopper example is generated, and gated by "apply"
`calflab_example.gh` is written by `build_example.py` inside Rhino (GH files
are binary) and is committed. Its components locate `calflab_gh.py` next to
the definition file. SetGenomeParams has an extra `apply` input, off in the
saved file, so opening the example never edits the design. This supersedes
the "recipe only" gap recorded in ADR-024. The Hops path of ADR-024 is still
untested: Hops is not installed on this machine and was not installed by the
session (installing software into Rhino is the researcher's call).

## ADR-041 — Front knee direction is a gene, added without a genome version bump
`front_knee_forward` (bool, not evolvable) sits next to `hind_knee_forward`.
It was added with default off; ADR-047 made forward the default and records
how older genomes keep backward knees. No migration is registered. The
proposal for a three-segment leg (`docs/proposals/anatomical-leg.md`) was
written and then set aside by the researcher on 2026-10-04: the body needs
forward front knees on the current two-segment leg, not another joint.

## ADR-042 — Viewport handles and cables are drawn over the model
The gumball is CALFLAB's own arrow (one per `ParamValue.handle_axis`), not
three's TransformControls: constant size on screen, pointing outward from the
part, drawn after everything else without depth test. Harness routes are
drawn the same way. Reason: both exist to be seen and picked, and both sit
inside or against the shells. The drag-to-value conversion
(`axisParam` in `web/src/viewport/viewLogic.ts`) is screen geometry and stays
in the UI; clamping to the gene range is repeated by the server.
The active arrow's screen position is published on the canvas element
(`data-gumball`) so the Playwright test can drag it with a real mouse.

## ADR-043 — A harness route is drawn along the path its length is measured on
`calflab.wiring.harness_paths` returns, per route, source element ->
origins of `via_bodies` -> destination element in the standing pose. The web
overlay and the Rhino build list both draw exactly these points, so a drawn
cable times the slack factor is its `length_mm`. It is a schematic path
through joint centres, not a routed cable inside the shells, and only the
routes the generator defines exist (battery, one bus per leg, neck bus, IMU,
Pi link). Foot, touch and microphone sensors have no routes: adding them
means choosing connectors and wire gauges, which is component data and is
left to the researcher.

## ADR-044 — Evolution starts from the document or from a baked design; overrides ride along
`run_evolve(design=...)` takes body and gait (genome, generator and model
parameters, controller, overrides) from a baked design and evaluation
settings (fitness preset, simulation) from the working document, which it
does not modify. The run records `parent = <design id>` and
`inputs.start = {source, design | revision}`.
The enabled overrides of the starting point are applied to every candidate
and are never varied: an override is an explicit statement about one part,
not a gene. Consequently a candidate is only reproduced by its genome *plus*
the overrides of its run. Showing, replaying and adopting a candidate use
the run's recorded overrides and model parameters; `adopt_candidate`
replaces the document's overrides when they differ and logs that it did
(rule 6: never silent). Runs recorded before this ADR have no `inputs.start`
and are shown as started from the working document.
`load_design` replaces the document's graph and overrides with the design's
as one undoable command; layers, references and settings are kept.

## ADR-045 — Candidate comparison is computed in the core
`Lab.candidate_genes` returns every gene of a candidate with value, the
reference values (working design, first parent or the run's starting design,
an optional second candidate), numeric deltas and "differs" flags. The web
panel only formats it. With two parents (line mutation) the comparison is
against the first: the one the child was mutated from.

## ADR-046 — Replaying a run brings the viewport forward
Clicking a run (Runs panel, a journal link) loads it and activates the
viewport panel; in the Journal workspace the viewport sits beside the
journal instead of behind it (`beside` in `web/src/workspaces.ts`).
`LAYOUT_VERSION` is 4: saved dock layouts were reset once.

## ADR-047 — Forward front knees and a gait tuned for them are the default (**VERIFY**)
Decided by the researcher on 2026-10-04: the final body has forward-facing
front knees, so `front_knee_forward` defaults to on for new projects.

*Existing work is not changed.* A gene definition may carry `absent`: the
value a stored genome had before the gene existed. `front_knee_forward` has
`default: true, absent: false`, and `GenomeDefinition.complete` fills a
missing gene with `absent`. Every document, undo record, run, candidate and
baked design saved before the gene existed therefore still builds backward
front knees; `reset_genes` and new projects get the default. This needs no
genome version bump and no migration, and unlike a migration it also covers
graph node parameters and the command log, which carry no genome version.

*The gait.* The old default trot fell on this body. The CPG defaults are now
frequency 2.0 Hz, hip amplitude 10.5 deg, knee amplitude 10.5 deg, swing
fraction 0.55, hip offset -3 deg, crouch -7 deg (trot). Found with CMA-ES
over the six CPG parameters, body fixed, `walk` fitness preset, 8 s rollouts,
then rounded. In simulation on the default body: 0.51 m/s over 20 s (old
default on backward knees: 0.39), stability 0.93 (0.74), mean power 6.2 W
(10.2), lowest leg torque margin 0.41 (0.00: hip abduction was saturated), no
fall in 60 s, unchanged at floor friction 0.6 and 1.2. It is open loop and
veers: 0.15 m sideways in 20 s, 2.6 m in 60 s. The one shared set of numbers
was enough; no separate front/hind gait parameters were added.

*Joint speed is not simulated.* The servo model limits torque, not speed.
The unconstrained optimum was a 3 Hz trot at 0.9 m/s that commands about
260 deg/s at the hip; the recorded no-load speed of the leg servo (XH540-W270,
30 rpm, unverified) is 180 deg/s, and at no-load speed a motor has no torque
left. The search was therefore repeated with the peak *commanded* joint speed
held at 120 deg/s (two thirds of that figure) and the default is from that
search. The old default commanded about 300 deg/s at the knee. Until the
simulator has a torque-speed curve, gaits found by Evolve can exceed what
the motors can follow; 120 deg/s rests on an unverified datasheet value.

Controller parameters are stored in each document, so existing documents
keep their gait. New projects get the new one; in an existing document
*Reset to defaults* on the Controller section (`reset_node_params
node=controller`) brings it in, and *Reset to defaults* in Form brings the
forward knees. Both are undoable.

## ADR-048 — Front legs may have two motors: abduction and an elbow (**VERIFY**)
Decided by the researcher on 2026-10-04: the front pair should have two
motors per leg, the hind pair keeps three. Gene `front_hip_flex` (bool, not
evolvable): off removes `joint.<fl|fr>.hip_flex`, its actuator and its motor
(2 x XH540-W270: 330 g and $900 by the recorded figures). The thigh keeps
its ID and is fixed to the hip at the angle the standing pose gives it, so
the standing body is geometrically identical; URDF export writes a fixed
joint. The knee keeps the ID `joint.<k>.knee` and works as an elbow.

The gene defaults to **on** (three motors) and `absent: true`, so nothing
changes until it is switched off in a project. It was not made the default
body because a two-motor leg only walks acceptably when the joint is high
and points backward, and those proportions are still being explored with
per-part overrides (there are no front-specific length genes yet).

*The gait.* With one fore-and-aft joint the hoof travels a single arc, so a
two-motor leg is stepped differently by the CPG: the knee does the sweep
(`elbow_amplitude`, `elbow_offset`) and hip abduction swings the leg outward
to clear the ground during swing (`swing_abduction`). Legs with hip flexion
are driven as before; the two kinds coexist in one gait. In simulation
(tuned with `tune_gait`, joint speeds capped): front joint backward with
thigh 100 mm / shank 236 mm, a walk at about 0.21 m/s, stability 0.88,
0.003 m sideways in 20 s; the researcher's test body of that day, 0.29 m/s,
stability 0.90. The front abduction motors then work near their torque
limit (3-10 % margin): they carry the lift. With the knee mid-leg and
pointing forward the two-motor leg walks poorly (0.15-0.22 m/s, abduction
saturated). These are simulation results on unverified component data and a
simulator without joint-speed limits.

## ADR-049 — Gait tuning for a fixed body is a lab job, speed-capped
`tune_gait` (command, and *Tune for this body* on the Controller section)
runs CMA-ES over the controller's optimisable parameters for the working
design as it is, on the compute backend, and writes the result into the
document as one undoable `set_node_params`. It is what was done by hand for
ADR-047, made repeatable because the body keeps changing.
Rules built in: commanded joint speeds, from
`Controller.peak_joint_speeds`, must stay at or below `speed_fraction`
(default 0.67) of each actuator's recorded no-load speed; a gait that falls
is never chosen; the winner of each footfall pattern is re-run for 2.5 x the
trial length (at least 20 s) and must survive that; parameters with no
effect on the body (`Controller.relevant_dims`) are not searched; trials
start standing whatever the document's start pose. A run record of kind
`tune` keeps the settings, the caps, the before and after figures and the
gait. The speed cap is a stand-in for a torque-speed curve in the servo
model, which is still missing; Evolve's inner loop is still uncapped.

## ADR-050 — Mass comes from pushed solids, per-part materials and weighed parts (**VERIFY**)
Requested by the researcher on 2026-10-08: model the chassis in Rhino part by
part and have the lab's mass come from that geometry and real materials, not
from the envelope estimate of ADR-017.

*What was wrong.* A solid pushed onto a body's `Structure` layer replaced
nothing (the code replaced only `visual` geoms; structure geoms are `both`),
weighed nothing, and reached the simulator as a 5 mm sphere at the body
origin. Pushed geometry was display only.

*Every geom now says where its mass comes from* (`Geom.mass_source`):
`parametric` (the envelope estimate), `component` (a library entry),
`geometry` (a pushed closed solid x material density) or `measured` (a
weighed part). `calflab.model.mass.mass_breakdown` only groups and sums the
geoms, so the breakdown always adds up to the total.

*Pushed solids.* A pushed mesh is measured once, when it arrives
(`calflab.model.solid.analyze_mesh`): vertices closer than 0.0001 mm are
welded; it is a solid if every edge is then shared by exactly two faces, the
faces can be oriented consistently and it encloses a volume. Volume, centre
of mass and unit-density inertia, in the body frame, are stored on the
override (`meta.solid`). They are stored, not recomputed, because building a
design must not need the project folder (evolution workers build from a JSON
payload) and so that a run record carries what its masses were computed from.
On the Structure layer a closed solid gives the part
`mass = volume x density`. The envelope primitives of that body's structure
stay as **massless collision shapes** (`role = "collision"`, same IDs), so
nothing is counted twice and the simulator's contact geometry does not
change; they are drawn only with the collision overlay and are not pulled
into Rhino. An open or invalid solid is shown but **not used for mass**: the
envelope estimate stays, and a warning goes to the pushing client, the log,
the design's warnings, Properties and the Mass panel. Assumptions:

* *Solid means solid.* Volume x density is the mass of a fully dense part. A
  hollow or infilled print needs either a model of its real walls or a
  material entry with the effective density measured on a printed sample.
* *Separate closed shells add up; overlapping ones are counted twice.* Join
  them in Rhino first.
* *Hooves, motors, boards, belts and skin are separate parts.* A structure
  solid replaces the printed structure of its body only (`structure_geoms`).
* *A Skin push still changes the look only* and keeps the envelope's skin
  mass, as before. Skin mass from sculpted area x thickness is not built.
* *Exact volume from Rhino.* The bridge also sends what Rhino says about the
  selection (closed? exact volume). A meshed curved solid is a little small
  (a 40 mm sphere at Rhino's default meshing: -1.6 %), so when the two
  volumes agree within 5 % the exact one is used and the inertia is scaled
  with it; beyond 5 % the mesh volume is used and a warning says so. The
  centre of mass is always the mesh's.
* A body may now carry one geometry override per layer (a structure solid
  and a skin sculpt together); before, the last push on a body hid the other.

*In the simulator.* MuJoCo composes body inertia from primitives. A pushed
solid is emitted as the non-colliding box with the same mass, centre of mass
and inertia tensor (`equivalent_box`: extents `a^2 = 6 (I2 + I3 - I1) / m`
along the principal axes), which is dynamically identical to the solid.
Collision still uses the envelope, so a part modelled much larger or smaller
than its envelope collides as the envelope does.

*Material per part.* Structure only. A material named at push time belongs
to that solid (`meta.material` of the geometry override), so switching the
solid off returns the part exactly to its parametric value. A material
chosen in Properties on a part without a solid is its own override
(`kind = "material"`); on a part with a solid it changes the solid's
material. Resolution: the solid's material, else the part's material
override, else `structure.material`. The BOM books structure mass to the
material each part was computed with; hooves are now booked as cast silicone
instead of printed PETG (BOM total 5253 -> 5256 USD).

*Weighed parts.* `set_measured_mass` (override `kind = "mass"`) replaces the
structure mass of one body. The masses, and inertias, of its structure geoms
are scaled to the weighed total, so centre of mass and inertia keep the shape
the geometry gave them. The computed value stays visible beside it.

*Recorded with runs.* `inputs.mass` of sim, evolve and tune runs lists the
parts with geometry-based and with measured mass, mass by source, and each
part's structure mass, source and material.

*Also.* A project may set its own mass target (`set_mass_target`, stored in
the document settings); the default stays in `robot_defaults.yaml`. Sensors
without a body in the model (foot FSRs, touch zones) carry no mass; the
breakdown lists them as "not in the mass model" rather than hiding that.

Checked in Rhino 8.34 by `bridge rhino --check` (2026-10-08): a 100 mm box
Brep in PLA gives 1240.0 g; a 40 mm sphere gives 332.42 g (exact); a box with
a face removed is refused with "it is open (4 naked edges)".

## ADR-051 — Component entries never take a value silently; choices come from the library (**VERIFY**)
*Problem.* A field left out of a component entry took the code's default
without a trace (a servo with no armature got 0.005 kg*m^2; one with no mass
weighed 0 g), and a new actuator had to be added by hand to four `choices`
lists in the gene file before it could be selected.

*Rules, enforced by the loader.*
* A required value that is missing or `null` makes the entry **incomplete**:
  it is not in the library, cannot be selected, and the audit lists it with
  the fields still to enter. Mass is required for every kind but materials.
* An optional value that is missing takes the model default and the field is
  recorded in `defaulted` ("default assumed").
* A value that is not on the datasheet is entered as the researcher's best
  guess and named in the entry's `guessed:` list.
Both lists show in `calflab components audit`, the worksheet (`flag`
column) and as badges on the component card in Properties. The existing
entries got `guessed:` lists for exactly what their files already called a
guess (servo thermal parameters, skin coefficients, the Pi's power draw). No
value was changed. Nothing sets `verified`.

`calflab components new <kind> <key>` appends an entry with every spec field
blank, a comment giving its unit, `verified: false` and `guessed: []`.

*Choices.* An enum gene may carry `choices_from: <kind>`: its listed choices
come first, then every other complete library entry of that kind. The four
actuator genes use it, and a new gene `battery` (default `lipo_3s_5000`,
which is what `robot_defaults.yaml` named and every existing genome
therefore had) makes the battery a per-project choice. The power budget's bus
voltage is the chosen battery's. Boards and sensors are still set in
`robot_defaults.yaml` for all projects: their geom IDs contain the component
key and the harness names the two boards, so making them genes needs an ID
decision first.

A design that names a component later removed from the library fails to
build with a message naming it, as an unknown enum value always did.

Not checked on a real part: no small servo, board, battery or material was
added, because the researcher's list was not given and specs are never
invented. The mechanism is covered by tests with a made-up fixture entry in
a private copy of `config/`.

## ADR-052 — A `scale` gene for small test calves (**VERIFY**)
Requested 2026-10-08: a calf about 200 mm tall for testing with lighter
parts. Almost every length gene's minimum stops at about half size.

*Decision.* One gene, `scale` (0.25 to 1.25, default 1, not evolvable),
multiplies every gene marked `scale_by: scale` in the gene file (the 18
length genes) and the generator's fixed millimetre constants (motor offsets,
ear and tail radius, the belt). `scale = 0.33` gives a calf 200.6 mm tall.

*Stored at full size, shown in real millimetres* (the researcher's choice,
2026-10-08). The stored value of a length gene is the full-size one, so
proportions, ranges and evolution's search space do not depend on the scale.
Everything a person reads or types is real: the Form sliders and their
ranges (`Lab.genome_form`, edits through `set_genes real=true`), Properties,
the gumball, overrides, the gene table in Evolve, and Rhino. A 170 mm thigh
gene at scale 0.33 reads 56.1 with a range of 33 to 85.8; typing 60 stores
181.8. Changing only the scale keeps the proportions, so every length
slider moves. What still carries stored (full-size) values: the project
file, run and design records, `scene.genome` (its real twin is
`scene.genome_real`), and `set_genes` without `real=true`, which is what
the command line, the Python client, Grasshopper and Hops send.

*Why not lower the minimums.* The ranges are also the evolution search
space and the proportions of ADR-015. Widening each by a factor of three
would make evolution from the default body search mostly absurd shapes, and
a small calf would sit at the floor of every range with no room to vary.

*What does not scale.* Wall thickness and skin thickness (a printer's wall
does not shrink with the model), skin clearance, per-part offset overrides,
and every component: at 0.33 the 2.4 kg of full-size motors, boards and
battery are unchanged, which is the point of choosing lighter ones (ADR-051).
Component boxes are drawn at their library size, so full-size servos stick
out of a small calf.

*Targets.* Target height and length scale with the gene. The mass target
does not (structure scales roughly with the square, components not at all):
set the project's own with `set_mass_target`.

*Known limits.* Evolve's `trunk_length` and `leg_length` descriptors report
the full-size value, so their ranges still hold; the `body_mass`
(3500-8000 g) and `speed` (0-1 m/s) descriptor ranges are for the full-size
calf and are not rescaled, so do not use those two on a small calf. The
default gait was
tuned for the full-size body: at 0.33 with the existing servos it walks at
about 0.11 m/s without falling, which says little; *Tune for this body*
after choosing real small servos. Simulator settings (time step, contact
parameters) were not re-examined for a 200 mm, sub-kilogram body.

## ADR-053 — A part may be pushed as several solids, each with its own material (**VERIFY**)
Requested by the researcher on 2026-10-08: chassis parts are printed PLA
with stainless steel rods, modelled in Rhino as separate closed solids (the
rods cut out of the PLA), and one part's mass, centre of mass and inertia
must be right for the mix. Extends ADR-050.

*What was wrong.* `CalflabPush` joined the whole selection into one mesh and
sent one material. Each object's own `calflab.material` user text was used
only as the default of the prompt (the first one found in the selection).
The joined mesh was measured once, at unit density, and multiplied by one
density, so a PLA body with steel rods weighed as if it were all one
material and its centre of mass was the centroid of the combined volume.
A second push replaces the first, so there was no other way to give one
part two materials.

*Decision.* On the Structure layer the bridge sends the selection object by
object (`parts` of `/api/bridge/rhino/push`: name, own material, mesh,
Rhino's closedness and exact volume). Each is measured and stored as its own
solid (its own GLB asset) and kept in the one geometry override of that
part and layer as `meta.solids` (`name`, `asset`, `material`, `solid`).
Building the design gives **one mass geom per solid** (`<body>.override.<id>.<n>`),
with `mass = volume x own density`, its own centre of mass and its own
inertia. Nothing new is needed downstream: `mass_breakdown` lists them as
items, the BOM books each to its material, the simulator gets one
equivalent box per solid and composes the body's inertia itself, a weighed
mass scales them together, and `CalflabPull` brings each back as its own
object with its own `calflab.material`. A push of a single object is
stored exactly as before (`meta.solid`, `meta.material`), so old documents
and runs need no migration.

*Material of a solid.* Its own `calflab.material` user text; else the
material named at the push prompt (`meta.material`); else the part's
material override; else `structure.material`. The prompt is asked only when
at least one selected solid has no user text of its own. This changes one
thing for single solids: a tagged object used to offer its tag as the
prompt's default, which could be overtyped; now the tag decides and the
prompt is skipped. Chosen so that one rule holds for one solid and for many.

*Assumptions.*
* *All or nothing.* If any solid of a push is open, or its material is not a
  structure material in the library, none of them is used for mass: the
  envelope estimate stays and the warning names the solid. A part-mass that
  silently lacks its rods would be worse than an estimate that says it is one.
* *No overlap check.* Overlapping solids are still counted twice (ADR-050);
  the rods must be cut out of the plastic in Rhino.
* *One push is the whole part.* The solids of a push are one override; a
  second push onto the same part and layer replaces all of them.
* *Properties cannot flatten a mixed part.* `set_part_material` on a part
  whose solids carry different materials is refused with a message pointing
  to Rhino; if they all share one material it changes it for the part.
  Changing one solid's material from the web lab is not built.
* *Skin pushes are unchanged* (objects joined, look only).

*Reported.* The breakdown's structure row gained `materials`,
`material_label` ("pla + stainless_304"), `solids` (each pushed solid's
material and mass) and `com_mm` (centre of mass of the structure in the body
frame, mass-weighted); `material` is null for a mixed part. The push reply
adds `solids` (volume, material, mass) and `com_world_mm`, which Rhino
prints. `inputs.mass.structure.<body>` of a run now also holds `materials`
and, for a part of several solids, `solids`.

Not checked in Rhino: the typed `CalflabPush` with two tagged Breps. The
path from the bridge's request format to the masses is covered by
`tests/test_mass.py` (a 100 mm PLA box and a 10 x 10 x 100 mm box of
`stainless_304`, densities read from the library).

## ADR-054 — A pushed solid tagged with print settings is weighed with an infill estimate (**VERIFY**)
Requested by the researcher on 2026-10-08: PLA parts are modelled as full
solids but printed with infill, so volume x density (ADR-050) overestimates
them several times over. Extends ADR-050 and ADR-053.

*Decision.* A solid that carries the user text `calflab.print.infill`
(percent), `calflab.print.perimeters` and `calflab.print.line_width` (mm) is
weighed as printed: a **shell** of the wall thickness (perimeters x line
width) all round the solid at the material's full density, plus the **core**
inside it at the infill fraction of that density. The density stays the
material's own; nothing is baked into a new material. A solid without these
tags is fully dense, exactly as before.

*No defaults.* All three tags or none. An incomplete, unreadable or
out-of-range tag refuses the push with a message naming the solid and the
tag. An infill between 0 and 1 is refused as a probable fraction. The
researcher's own settings (15 %, 2 perimeters, 0.4 mm; also 3 top and 3
bottom layers of 0.2 mm) are used in tests and documentation only.

*One wall thickness all round* (the researcher's choice, 2026-10-08, asked
because the request left it open). Top and bottom layers would need the
print direction of each solid, which is not the direction it is modelled in.
The alternatives offered were a required or optional
`calflab.print.up` tag. So top and bottom skins are taken to be as thick as
the walls; `calflab.print.*` tags other than the three are reported as not
used.

*The core* is the set of points of the solid deeper than the wall thickness
below its surface (`calflab.model.infill.measure_core`). It is measured once,
at the push, and stored beside the solid (`meta.print`, `meta.print_core`,
or the same keys in each entry of `meta.solids`): building a design still
needs no file access. Method: a grid of pitch wall / 2 (coarser above 16
million cells); inside or outside by counting surface crossings along Z;
cells far from the surface count whole; cells near the wall depth get the
exact distance to the surface and count in proportion (so a flat wall is
exact at any pitch). A 100 mm cube with a 0.8 mm wall: shell within 0.1 % of
100^3 - 98.4^3, about 5 s.

*Thin features.* Where the solid is thinner than two walls no point is that
deep, so there is no core and the feature is fully dense. A cell a little
short of the wall depth counts only if the solid does reach that depth just
beyond it, which keeps a 1.5 mm fin from getting a sliver of core. The core
is a subset of the solid and is clamped to its volume, so the estimate lies
between all infill and fully dense. Features between two walls and two walls
plus one pitch thick are counted to within a few percent.

*Centre of mass and inertia* are those of the dense solid minus
(1 - infill) x the core (`printed_solid`), not a uniform solid scaled down.
The simulator gets the equivalent box of that inertia, as for any solid.
100 % infill returns the dense solid's values unchanged.

*Never shown as dense or weighed.* A fifth mass source, `infill` ("Pushed
solid, infill estimate (shell + infilled core)"), listed before `geometry`
so a body with one tagged solid reads as an estimate. `geometry_parts` still
lists every body whose mass comes from pushed solids; `infill_parts` lists
those resting on an estimate. Each such geom carries `Geom.infill`
(settings, outer / shell / core volume, dense mass, one line of text), which
the breakdown, the push reply, Rhino's printout, the web panels and the run
record (`inputs.mass.structure.<body>.solids[n].infill`) all show.
`CalflabPull` writes the three tags back.

*Assumptions and limits.* The infill pattern, the slicer's real path (gap
fill, extra perimeters round holes, solid layers under slopes), supports and
extrusion error are ignored. The printed walls are taken at full material
density. Print tags can only be set in Rhino. A weighed mass (`measured`)
still replaces the estimate and is the most accurate.

Not checked: against a slicer's filament weight (the researcher will compare
two or three real parts), and `CalflabPush` typed by hand on a tagged
object. Checked: `tests/test_infill.py`, a step in
`web/e2e/structure.spec.ts`, and `bridge rhino --check` in Rhino 8.34 on
2026-10-09 (a Brep cube with the three tags, read with
`Attributes.GetUserStrings()`, pushed and printed as an infill estimate;
the two-solid push of ADR-053 passed in the same run).

## ADR-055 — A switch per neck and head joint (**VERIFY**)
Requested by the researcher on 2026-10-09: the small prototype has no neck
or head motors, and the generator always built three (`act.neck_yaw`,
`act.neck_pitch`, `act.head_pitch`), 165 g of servos high at the front with
the default STS3215. Asked whether one switch or several, the researcher
chose separate ones.

*Decision.* Three bool genes in group *Neck and head*: `has_neck_yaw`,
`has_neck_pitch`, `has_head_pitch`, named like `has_tail` and `has_ears`.
Default on, not evolvable, `absent: true` (ADR-047), so every saved genome,
run and design keeps its three motors and no migration or version bump is
needed. The request said "pitch and yaw"; there are two pitch joints (neck
and head), so each got its own switch rather than sharing one.

*Off means* no `joint.<name>`, no `act.<name>` and no motor geom, as for
`front_hip_flex` (ADR-048). The bodies `neck.base`, `neck` and `head` stay,
with their IDs, welded to their parent: the neck angle and head tilt are in
the geometry, so the standing pose is unchanged and pushed solids still
attach. The neck skin region lists only the joints that exist. The harness's
neck bus ends at the furthest neck or head motor left (head pitch, else neck
pitch, else neck yaw) and is omitted when there is none.

*Not changed.* The microphone and the optional depth camera stay in the
head. `joint_groups.neck` in `config/robot_defaults.yaml` still names all
three; nothing reads the missing ones. A motion clip that names a removed
joint has nothing to drive.

Checked by `tests/test_neck_switches.py` (every combination: joints,
actuators, mass, poses, skin, harness; compile, simulate, Blender plan,
Rhino build list) and by a script that ran every exporter and analysis on a
body with all three off. Not looked at in the web lab or in Rhino.

## ADR-056 — Front and hind legs of their own lengths; front legs without a thigh (**VERIFY**)
Requested by the researcher on 2026-10-09 for a prototype at scale 0.337:
hind legs whose hip flexion and knee axes nearly coincide, front legs that
are shoulder abduction, one pitch joint and a shank with no thigh. One
`thigh_length` served all four legs and stopped at 100 mm (33.7 mm at that
scale), and a front leg without hip flexion still had its thigh as a strut
(ADR-048). The request's measurements were placeholders; nothing here
depends on them.

*Decision: additive, off by default.* `thigh_length` and `shank_length` are
used throughout tests, the Grasshopper example and saved work, so they were
not renamed or split by a migration. Instead:

* `own_leg_lengths` (bool, default and `absent` false). On: the front legs
  read `front_thigh_length` / `front_shank_length` and the hind legs
  `hind_thigh_length` / `hind_shank_length`; the shared two are ignored.
* The four lengths: `scale_by: scale`, thigh 5 to 300 mm, shank 30 to
  450 mm, default 170. Wide on purpose, a hand-built body is not bound by the
  proportions of ADR-015. **Not evolvable**, so the default calf's search
  space, and hence its evolution runs, are unchanged; the cost is that Evolve
  does not vary the leg lengths of a body that uses them.
* `front_thigh` (bool, default and `absent` true). Off: no `leg.f*.thigh`
  body. `leg.f*.shank` is a child of `leg.f*.hip` at the lateral leg offset
  and hangs straight down (rest 0), on `joint.f*.knee`.

*The pitch joint keeps the knee's IDs* (`joint.<k>.knee`, `act.<k>.knee`,
motor from `act_knee`) and is only named "Shoulder pitch". Stable IDs are
API: the CPG already steps a leg with a knee and no hip flexion as a
two-motor leg (knee sweeps, abduction lifts), the torque table, speed caps,
firmware and bridges key on these IDs, and nothing needed to learn a new
one. Consequence: its motor cannot be chosen apart from the hind knees'.
Its range is that of hip flexion (a straight leg swings both ways), not the
knee's one-sided range. `front_knee_forward`, `front_hip_flex` and a belt
drive do nothing on such a leg; its motor is drawn in the hip.

*Grounding.* Legs of different standing heights used to leave the shorter
pair in the air (trunk height follows the longest leg). With
`own_leg_lengths` on or `front_thigh` off, the hip of each shorter leg is
lowered in the trunk by the difference, so every hoof stands and the trunk
stays level; `hip_drop` then belongs to the longest legs. Assumed: the
prototype's trunk is level and its front and hind pitch axes sit at
different heights. A tilted trunk is not modelled. Without either switch
nothing changes: a leg shortened by an override still hangs short, as saved
projects have it.

*A very short thigh* is an ordinary body (a capsule of length 5 mm full size
at the least); its direct-drive knee motor is drawn at the hip instead of
above it.

Checked: specs of six unchanged gene sets hash identically before and after
the change; `tests/test_leg_layout.py`; every exporter and analysis, a
simulation and `tune_gait` on a thighless, short-thighed body at scale 0.337
with stand-in lengths. Simulation settings were left as they are (2 ms): that
body neither collapsed, sank nor violated joint limits, but nothing was
re-examined for a 200 mm calf (ADR-052). Not looked at in the web lab, Rhino
or Blender by anyone.

## ADR-057 — A hip-abduction switch per pair of legs (**VERIFY**)

*Context.* The researcher simplified the small prototype to eight motors:
two joints per leg, hip pitch then knee, on all four legs. The generator
gave every leg `leg.<k>.hip` on an abduction joint with its motor;
`front_hip_flex` off removed the wrong joint (it leaves abduction + knee),
and the hind legs could not lose a motor at all.

*Decision.* Genes `front_hip_abd` and `hind_hip_abd` (bool, Form > Legs,
labels "Front legs have hip abduction" / "Hind legs have hip abduction"),
on by default with `absent: true`, not evolvable. Off, for that pair:
no `joint.<k>.hip_abd`, no `act.<k>.hip_abd`, no motor geom, no mass.
`leg.<k>.hip` keeps its ID, its place and its hip block and is a body
without a joint, i.e. fixed to the trunk (as `neck.base` is without neck
yaw, ADR-055). Per pair, not per leg, because that is what the researcher
asked for and a calf with abduction on one side only is not a body anyone
wants. No genome version bump, no migration.

*Why the IDs do not change.* Stable IDs are API (rule 8). The hip-pitch
joint stays `joint.<k>.hip_flex` and the knee `joint.<k>.knee`, so the CPG
drives such a leg on its ordinary three-motor path (it already skips an
abduction index that is missing), speed caps, the torque table, harness,
firmware and both bridges need no change, and solids pushed onto
`leg.<k>.hip` / `.thigh` / `.shank` attach as before. A solid on
`leg.<k>.hip` now moves with the trunk; pushing it onto `trunk` instead is
equivalent.

*Combinations.* All existing leg settings compose with it: own lengths,
knee directions, `front_thigh` off (then a front leg is one pitch joint),
scale. `front_hip_flex` off together with `front_hip_abd` off leaves a front
leg with its knee only; it builds, compiles and is stepped by the knee
sweep, with nothing to lift the hoof. Allowed, described in the tooltip of
the gene, not recommended.

*Consequence to state wherever it matters.* Without abduction every leg
joint turns about the sideways axis of the body. The legs cannot place a
hoof sideways or resist a roll. The open-loop CPG never used abduction for
balance on the default body either (`abduction_amplitude` is 0), so the
loss shows less in these simulations than it will on a floor.

Checked: specs, MJCF and rollout metrics of four unchanged bodies (default,
the 2026-10-09 prototype layout, two-motor front legs, scale 0.33) are
identical before and after, to the last digit;
`tests/test_hip_abduction_switch.py`. Not looked at in Rhino or Blender by
anyone (the build list and the armature plan are tested).

## ADR-058 — What a small body needs from the model: two settings, joint speed in the metrics, and no voltage conversion (**VERIFY**)

*Context.* The researcher asked whether the time step and contact settings,
chosen for a 5 kg, 600 mm calf, were re-examined for a 0.4 kg, 190 mm one
with 0.23 N*m servos, and how the lab treats servos entered at 6 V on a
7.4 V battery. Examining it turned up three things that matter far more
than the time step.

*Found.*

1. **Time step and contact are fine.** On the two-joint body with the
   library values, 2 ms, 1 ms and 0.5 ms give the same speed, stability and
   energy to three digits; hooves sink 0.07 mm when standing (0.22 mm on the
   full-size calf) with the fixed contact time constant of 10 ms. Stiffer
   contact (5 ms, 2 ms) changes nothing either.
2. **Passive joint losses do not scale.** `structure.joint_damping_nms_per_rad`
   (0.05) and `joint_friction_nm` (0.02) in `robot_defaults.yaml` are
   applied to every joint whatever the scale and the motor. Against the
   usable torque of an `scs0009` (0.2256 x 0.6 = 0.135 N*m) friction is
   15 % and damping at 2 rad/s another 74 %.
3. **The default armature decides the result.** `scs0009` gives no
   `armature_kgm2`, so the library default 0.005 kg*m^2 is in use (the
   entries with a value have 0.004 to 0.012, for 55 to 165 g servos). The
   inertia of the whole leg about the hip is of the order 1e-4. With 0.005
   the stall torque of the servo accelerates its own horn at 45 rad/s^2: it
   would need 0.23 s and 69 degrees to reach its no-load speed, where its
   page says 60 degrees take 0.1 s. That figure is a steady speed, so this
   is not a measurement of armature, but any value above about 0.001 kg*m^2
   is incompatible with reaching that speed within one 60 degree move.
4. **The skin model is on by default**: 154 g of skin and its joint
   stiffness on a 378 g bare body.

*Decision.*

* `CompileOptions.joint_loss_scale` and `armature_scale`, both 1.0 by
  default: every existing document, run and test gives the same numbers
  (compiled MJCF is byte-identical at 1.0). They are model settings in
  *Model (terrain, servos, skin)*, stored with each run. They are **not**
  component values: no entry in `config/components` was touched, and the
  right place for the armature of a servo remains its entry (measured, or
  the researcher's guess named in `guessed:`). The settings exist so that
  the dependence of a result on these two assumptions can be seen and
  recorded.
* No automatic scaling with `scale` or with the motor: any rule would be an
  invented one, and it would change saved small-calf results (ADR-052
  bodies must reload identically).
* Metrics: per actuator `speed_peak_deg_s`, `speed_limit_deg_s` (recorded
  no-load speed at the joint, through the transmission), `speed_margin`,
  `torque_saturated` (share of the time at 98 % or more of usable torque);
  overall `speed_margin_min`. The simulator still limits torque only
  (ADR-047); these say when a rollout outran a motor. Runs recorded before
  have no speed limit in their rollout and report `speed_margin_min: null`.
* Voltage: nothing is converted. Torque, speed and current are used as the
  entry gives them (6 V for `scs0009`), the bus voltage is the nominal
  voltage of the battery (7.4 V), battery current is the sum of the motor
  currents at those figures plus board power / bus voltage, and power is
  that current times the bus voltage. `power_budget` now returns
  `voltage_mismatch` and a `voltage_note` when the voltage of a motor
  differs from the bus by more than 15 % (12 V servos on an 11.1 V pack are
  not reported), and the study repeats it. What the wiring of the prototype
  does (servos straight on the 2S pack, where they would be stronger and
  faster than entered, or behind a 6 V regulator, where battery current is
  lower than the sum) is not modelled; entering the figures of the servo at
  the voltage it really gets is the fix.
* With `armature_scale` below 1, results move about 10 % between 2 ms and
  0.5 ms: use 1 ms then. Not made automatic.

*Assumed.* A bare printed prototype has no skin: the project made for the
researcher (`projects/small-calf-two-joint`) has *Include skin* and *Show
skin* off. The defaults of the lab stay on.

## ADR-059 — Proportion study: a table of bodies per gait, not a winner (**VERIFY**)

*Context.* The researcher wants to find good proportions for the two-joint
prototype (segment lengths, trunk, stance), judged by walk, trot and bound
and by what each motor and the battery see, and to see trade-offs. What
existed: *Tune for this body* (one body, trot and walk, one gait out) and
Evolve (MAP-Elites over all evolvable genes within their full slider
ranges, one gait pattern, one fitness number, behaviour descriptors as
axes). Neither takes ranges in millimetres, compares gaits, or reports the
per-joint table for more than the run on the timeline.

*Decision.* `calflab.evolve.study` and `Lab.run_study` (command
`run_study`, a job; panel *Proportions* in Evolve).

* **Dimensions**: thigh, shank, trunk length, stance width, hip drop, each
  with a From/To in real millimetres (ADR-052); 0 to 0 = not varied. Leg
  lengths drive the front/hind length genes of ADR-056, with
  `own_leg_lengths` switched on in the variants (and the four lengths first
  set to what the legs measure now, so the switch alone changes nothing):
  the shared `thigh_length` / `shank_length` stop at 100 mm full size and
  could not reach the 20 mm asked for. Front and hind are tied unless
  *Front and hind legs > Vary separately* is on. A range wider than the range of a
  gene is cut to it and reported, never extended: widening a gene re-scales
  the search space of Evolve and needs a genome migration.
* **Bodies**: a seeded Latin hypercube over the ranges; bodies whose
  standing height (the height readout of the lab,
  `RobotSpec.standing_height_mm`) is outside *Overall height* are left out
  and counted, and sampling repeats until enough are in. The working design
  is always body `b00`.
* **Per body and gait**: the gait numbers of the document with the footfall
  pattern swapped, then CMA-ES over the relevant parameters of the
  controller with the speed caps and penalty of `tune_gait` (ADR-049), then
  one longer check run (15 s or 2.5 x the trial) that every reported number
  comes from. The fitness is the preset of the document. One task per body,
  so the compute backends apply.
* **Works** = did not fall in the check run, forward speed at least
  *Min speed mps* (0.02), at a joint limit at most 2 % of the time, and no
  joint faster than the no-load speed of its motor. A motor at its torque
  limit and a battery over its limit are flags, not failures: with the
  present servo model (position error over 10 degrees saturates) nearly
  every gait of a weak servo touches the limit at some instant, and
  `torque_saturated` says for how long.
* **Trade-offs** are computed in the core (`summarize`): the bodies not
  dominated on (speed, worst torque margin) among those that work are the
  *front*; rank correlations of each varied length with speed, torque
  margin and stability are reported as trends when there are ten or more
  bodies and |rho| >= 0.4. No body is chosen and the document is not
  edited; `adopt_study_body` does that on request (undoable), taking the
  overrides of the run with it as `adopt_candidate` does (ADR-044).
* **Record**: run kind `study`; `run.json` holds settings, dimensions as
  used, model and simulation settings, the mass record, the notes;
  `study.json` holds every body.

*Assumed.* For the study run for the researcher, stance width 40 to 85 mm
and hip drop 0 to 25 mm (they gave ranges for thigh, shank, trunk and height
and said to assume the rest from those proportions; these are nearly the
slider ranges at scale 0.337). The trunk range asked for, 100 to 250 mm, is
cut to 101 to 189 mm at that scale.

*Limits.* The gait search per body is short (10 x 8 by default) and seeded:
rankings between neighbours are noise, groups are not. **Bound** exists as
a footfall pattern of the CPG but the controller is open loop: no flight
phase, no pitch feedback. What the study reports for bound is how far that
pattern shuffles a body forward, not whether it could bound. A bounding
controller (push-off and landing timed from trunk pitch and foot contact)
is not built. Structure masses in a study are the parametric estimates
unless solids were pushed, and pushed solids do not change with the
lengths: a study over a body with pushed solids varies the skeleton under
fixed parts.

## ADR-060 — Rotated servo mounts: mount roll and yaw on every leg part (**VERIFY**)

*Context.* The researcher asked for servos that can be rotated "such that
their affiliated limbs are mounted at an angle". Until now every leg part
sat square on its parent: all leg joints turned about the sideways axis of
the trunk (or the fore-aft one, for abduction), and the only angles were the
standing angles of the joints themselves.

*Read as.* The mount of a servo is turned, and the limb it carries, with its
joint axis, turns with it: legs that lean outward, or swing in a plane that
points outward. Not read as: only the drawn servo box turning while the
joint stays (that would change the picture and nothing else), nor a pitch
offset (leaning a segment fore or aft is what *Knee bend* and the standing
angles already do).

*Decision.* Every leg part (`leg.<k>.hip`, `.thigh`, `.shank`) has two
element parameters, `mount_roll` and `mount_yaw`, in degrees. They rotate
the frame of that body on its parent (yaw about the vertical, then roll
about the fore-aft axis), so its joint, the motor geoms in it and every body
below turn together. Both are mirrored by side: positive roll leans the far
end outward on the left and on the right, positive yaw turns the front
outward on both.

* The hip's two are driven by genes, per pair of legs like the abduction
  switches: `front_leg_splay`, `hind_leg_splay` (-30 to 45 deg) and
  `front_leg_toe`, `hind_leg_toe` (-45 to 45 deg), Form > Legs, default 0,
  `absent: 0`, not evolvable. No genome version bump.
* A thigh's or shank's are 0 and are set per part as an ordinary override
  (Properties, or `add_override target=leg.hl.shank param=mount_roll
  value=12`), within -90 to 90 deg. A hip can be overridden per leg the same
  way. Overrides stay explicit and named (rule 6).
* **Hooves stay on the ground.** A leg with any mount angle is measured by
  forward kinematics through its mounts and standing angles; the trunk
  height follows the leg that reaches furthest down and the hips of the
  others sit lower, as with legs of their own lengths (ADR-056). A leg with
  no mount angle is measured by the old formula, so bodies without mounts
  are bit-identical to before (checked on the same four bodies as ADR-057).
* Nothing else needed to change: MJCF, forward kinematics and both bridges
  already carry a body's rotation (the fixed thigh strut of ADR-048 uses
  it); the CPG commands joint angles and does not know the plane they act
  in.

*Consequences to state.* With splay the hoof no longer stands under the hip:
the body hangs on a sideways lever. On a leg with abduction that load is on
the abduction servo and shows in the torque table. On a leg without, no
motor resists it: it is a bending load on the hip-pitch servo's output shaft
and its bracket, which the simulator carries rigidly and does not report.
The gait's fore-aft sweep is unchanged, so splay buys a wider base, not
sideways control. Measured on the two-joint body (378 g, skin off, the tuned
trot): splay 0 / 10 / 20 / 30 deg gives a hoof track of 78 / 115 / 150 /
182 mm, a height of 187 / 184 / 177 / 168 mm, roll of 0.41 / 0.22 / 0.19 /
0.16 deg RMS and a speed of 0.114 / 0.111 / 0.107 / 0.105 m/s. With toe-out or toe-in, the left and right legs
sweep along diverging lines: part of every stride scrubs the hooves
sideways against each other. The abduction motor, where a leg has one, stays
drawn in the trunk and does not turn with the hip. The envelope shapes may
intersect the trunk at large angles; nothing checks that. The proportion
study does not vary these angles yet.

Checked: `tests/test_rotated_mounts.py` (hooves at ground level for splay,
toe, a part override, a strut thigh and a thighless leg; mirrored signs; the
hip-pitch axis leaning by exactly the splay angle; a simulation of the
two-joint body at 15 deg). Not looked at in the web lab, Rhino or Blender by
anyone.

## ADR-061 — Boards per project: two genes, `elec.<key>` IDs kept (**VERIFY**)

*Context.* The researcher's small prototype has one board, an ESP32. Every
project carried the Teensy 4.1 and the Raspberry Pi 5 named in
`robot_defaults.yaml` (56 g, 6.5 W, unverified): on a calf of a few hundred
grams that placeholder is a seventh of the mass and most of the idle power.
ADR-051 left boards out of the per-project choices because their geom IDs
contain the component key and the harness named the two boards.

*Decision.*

* Two enum genes in the group Mechanism, not evolvable, both
  `choices_from: board`: `board_control` (default `teensy_41`) and
  `board_compute` (default `raspberry_pi_5`, with the extra choice `none`).
  "Only the ESP32" is `board_control: esp_wroom_32`, `board_compute: none`.
  The same board named twice is one board. A genome holds single values, so
  a list of boards is not one gene; two roles are also what the harness
  needs to know (which board the buses run to).
* The defaults are what every existing genome effectively had, so a genome
  that does not mention the genes builds the same body: no genome version
  bump, no migration, no `absent` needed. Checked: spec, MJCF, mass and
  power budget of the default calf and of the genomes of all six projects
  on this machine are identical before and after.
* **Geom IDs stay `elec.<component key>`** (`elec.teensy_41`,
  `elec.esp_wroom_32`). Role IDs (`elec.control`, `elec.compute`) were the
  alternative; they would have renamed two geoms in every saved scene, run
  and Rhino pull for no gain today. The cost of keeping them: a board's ID
  changes when the board does, so nothing may address "the control board"
  by ID; the harness is told the board keys instead.
* Harness: power, servo buses and IMU run to the control board; a second
  board gets `harness.link` to it (still labelled USB, an assumption for
  any pair but Pi and Teensy); with one board there is no link.
* Power budget: unchanged. Boards are found by library kind, their
  `power_w` is added to the motors' power and divided by the battery's
  nominal voltage for battery current. No regulator is modelled, so a board
  behind a linear regulator draws more from the battery than the budget
  says (its full current at battery voltage).
* Runs record the boards: `inputs.boards` in `run.json` for sim, evolve,
  tune and study runs (`calflab.wiring.budget.boards_used`: geom ID,
  component, mass, supply, power, verified, guessed, defaulted), `boards`
  in `study.json`, and the study notes name an unverified or defaulted
  board as they do motors and the battery.
* `robot_defaults.yaml: electronics.boards` is read only for a gene
  definition without the two genes.
* No UI code: Mechanism renders the group from the schema.

*The board entry.* `esp_wroom_32` holds what the researcher gave on
2026-10-10: 7 g (weighed), 3.3 V, "~100 mA". `BoardSpec` has `power_w` and
no current field, so the power is entered as their product, 0.33 W, with
the arithmetic in the comment. Size and cost were not given and are left
blank (default assumed, reported). The current was given as approximate and
is not listed in `guessed:` because the researcher did not call it a guess;
asked in the session report.

*Not done.* More than two boards. Sensors per project (the IMU and
microphone boards, and the foot and touch sensors in the power budget, are
still those of `robot_defaults.yaml`). The firmware skeleton exporter still
writes a Teensy 4.1 + Raspberry Pi project whatever is chosen. A regulator
between battery and board.

*Also fixed.* `calflab components new` rewrote the whole YAML file with
CRLF line endings on Windows; it now keeps LF.

Checked: `tests/test_boards.py` (4). Not looked at in Rhino or Blender; the
Mechanism lists were looked at once in the lab's browser pane.

## ADR-062 — A robot modelled in Rhino is simulated in place of the parametric one (**VERIFY**)

*Context.* The researcher pulled the two-joint calf into Rhino and modelled
the real prototype against it: closed solids, many small parts per body, PLA
at 20 % infill, stainless rods, silicone on the head, joints roughly but not
exactly where the pulled calf's are. `CalflabPush` only replaced one body's
mass properties (ADR-050, 053, 054): the skeleton came from the genome and
the simulator collided the envelope boxes, capsules and hoof spheres. They
asked for joint places and axes, mass and collision from their model, with
the genome, Form, the proportion study and Evolve left as they are. The
conventions below were proposed first and accepted by the researcher on
2026-10-12.

*Decision: one override of kind `model`.* It is layered over the parametric
result like every other override (rules 5 and 6): `set_rhino_model` stores
it, a second push replaces it, switching it off or undoing returns the
parametric calf exactly. Nothing is written to the genome. Its `meta` holds
`joints` (per joint id a point and a direction, world, mm, standing pose) and
`bodies` (per body id its solids, measured in the body frame at the push as
in ADR-053/054, and the collision hulls), so building a design still needs no
file access and a run record carries what it was built from.

*In Rhino: layers, lines, tags.* `CalflabModelSetup` makes `CALFLAB::Model`
with a sublayer per body and `CALFLAB::Model::Joints` with an axis line per
hinge where the parametric skeleton has it. A solid belongs to the body
whose layer it is on or under; `calflab.body` user text is read only for a
solid on no body layer. A joint is the line named with the joint id, else
tagged `calflab.joint`: direction = axis, midpoint = place. (Changed the
same day: at first the user text won. Rhino copies user text with an
object, so mirrored feet all claimed their original's body and a line
copied and renamed kept its original's joint. What is visible in Rhino,
the layer and the object name, now decides, and the push rewrites the
leftover text.)
`calflab.foot = yes` marks ground-contact solids. Layers were chosen over
user text per object because a model of many small parts is organised by
dragging onto layers; lines because the pulled calf already draws its axes
as lines. `CalflabPushModel` takes no selection and sends everything on those
layers; `CalflabTag` writes the tags. The key is `calflab.joint`, not
`calflab.id`, because `CalflabPull` deletes every object carrying
`calflab.id`; the push removes that key from objects on the model layers.

*Skeleton* (`calflab.model.pushed_model.apply_skeleton`). The body a joint
carries gets its origin at the line's midpoint and the joint its axis along
the line, turned to point the way the parametric axis does so a positive
angle means the same turn. Kept: the orientation of every body frame, the
standing angles, the joint ranges, the actuator on each joint, and the IDs
(rule 8). Bodies are processed parents first, so everything below a moved
joint moves with it; a joint without a line keeps its parametric offset from
its parent. Assumed: **the model is drawn in the standing pose** of the
pulled calf, since that is the pose it was modelled against. Library
components (servos, board, battery) keep their place in their body frame, so
a servo moves with its joint; their exact position in the real chassis is not
taken from the model, which has no electronics in it.

*Mass.* Each modelled body is given its solids through the code path of
ADR-053 (one mass geom per solid, own material, infill estimate if tagged,
equivalent box in the simulator). A body without solids stays parametric
and is named in a warning and in `parametric_bodies`.

*Collision.* One convex hull per solid, reduced to at most 32 of its hull's
vertices (the furthest along 32 spread directions, always including the six
axes and straight down in the standing pose, so the lowest point is exact).
The reduced hull lies inside the true one. The envelope geoms of a modelled
body are removed, not kept as collision shapes. All solids tagged as feet on
one body give **one** hull and that is the leg's foot geom
(`<body>.foot`, `foot = true`), so the gait metrics still see four feet in
leg order; the parametric hoof of that leg is removed with its mass (it is
cast silicone the model does not have) and listed in `hooves_removed`. Hulls
are separate massless geoms (`<body>.hull.<n>`, role `collision`,
`Geom.hull`): the solids keep their place in the structure-mass bookkeeping.
MuJoCo collides meshes as convex hulls in any case; a hull fills concavities,
so a concave sole is flat and a foot of several toes is one pad. Robot geoms
still collide only with the ground (as before: `contype 1, conaffinity 0`),
so the cost is one hull-plane test per solid.

*Start height.* A model with hulls starts with its lowest collision point
2 mm above the floor (the parametric calf starts at its root height). Feet
that differ by more than 1 mm in height as modelled are reported.

*All or nothing, with every problem listed.* The push is refused, and
nothing stored, if a solid is open, on no body layer, has no structure
material, has unreadable print tags, or a line names no joint. A check-only
mode reports without storing. Unlike `CalflabPush`, an open solid is not
"shown but not used": a model with a part silently missing from its mass
would be simulated as if it were complete.

*Recorded.* `spec.metadata["geometry"]` and `calflab.app.scene.geometry_record`:
`inputs.geometry` in the run record of sim, tune, evolve and study runs and
`geometry` in the scene. `source` is `parametric` or `rhino_model`; for the
latter the file name, override id, push time, the joint table against the
parametric skeleton (mm, degrees), per body the solids, hulls and the
SHA-256 of each stored mesh, the feet, and what stayed parametric. A sim run
of a model is titled `Simulate (<override name>)`. Designs without a model
have no `geometry` entry in their spec metadata, so their specs and MJCF are
unchanged (the suite's identical-before-and-after checks pass).

*Print settings are asked, not assumed.* The estimate method is ADR-054's.
`CalflabPushModel` asks once per material whether untagged solids are
printed with infill (then for the three values) or fully dense, and writes
the answer onto the objects (`calflab.print.*`, or `calflab.dense = yes`,
which only stops the question being asked again).

*Material.* `silicone_solid` (structure, 1.04 g/cm3 as given by the
researcher on 2026-10-12 from the datasheet; product name and link not
given; unverified).

*Measured on a stand-in* (145 solids with 159,000 faces, joints moved 1 to
4 mm, on a copy of `projects/small-calf-two-joint`): push 4.5 s; 19,000
physics steps per second against 31,000 for the parametric calf; it stands
on its four foot hulls and walks with the project's gait at 0.095 m/s
(parametric: 0.097), no fall in 10 s, stability 0.82 (0.92). The document
grows by about 1 MB (the hull vertices and solid measurements).

*Limits.* Hull vertices are in the document, so a model of several hundred
solids makes every document refresh and undo record large. A proportion
study or evolution with the model on varies genes under fixed geometry and
is not meaningful: not blocked, documented. Evolve's `leg_length` descriptor
reads the hoof's place and misreads a modelled leg. Joint ranges are the
parametric ones; nothing checks that the modelled parts clear each other
through them. `set_part_material` does not reach a modelled body's solids.
A joint that exists in the model but not in the genome (or the reverse)
cannot be expressed: the genome still decides which joints exist.

Checked: `tests/test_pushed_model.py` (10), and `bridge rhino --check` in
Rhino 8.34 on 2026-10-12 with a new step (layers and lines created, lines
moved 5 mm, a trunk box, a shank and a tagged foot pushed whole, the joint
table, mass and foot read back, a pull leaving the model alone, undo). Not
done by anyone: the three commands typed by hand with their prompts, and the
researcher's real model.

## ADR-063 — A belt drive is three catalog references; its centre distance is derived (**VERIFY**)

*Context.* The final feral calf (ADR-066) belts its stifles and hocks 2:1.
On 2026-11-02 the researcher made the belt drives the most important part of
the request. A closed-loop belt comes only in stock lengths, so a design with
a centre distance the shop cannot supply cannot be built. Any continuous
handle on C, or on the servo's place on its segment, would let the lab
produce such designs.

*Decision.*
* A belt drive stores **only** a belt system id, a pulley pair id and a belt
  length entry id (`BeltChoice`, extra fields forbidden). They live in the
  `feral_calf` generator's `belts` parameter.
* C is **derived** from the belt pitch length L and the pitch diameters
  (`D = teeth x pitch / pi`):
  `b = 2L - pi (D1 + D2)`, `C = (b + sqrt(b^2 - 8 (D2 - D1)^2)) / 8`.
  The driver servo's output axis is at C from the driven joint axis, along
  the segment that carries it. The formula is the standard closed form. For
  450 mm with 30T/60T it agrees with the exact open-belt length to 0.1
  micrometre, and the researcher's check values hold: 444 mm gives 176.7 mm,
  450 mm gives 179.7 mm, 460 mm gives 184.8 mm.
* No gene, slider, numeric field, drag handle, IK, fit or optimizer changes C
  or the servo position.
  * The belt choice changes only through the command `set_belt_drive`.
  * `set_node_params` refuses the `belts` parameter.
  * Nothing in the gene file or the generator's numeric parameters names a
    distance; a test checks this.
  * If belts are ever evolved, they become discrete catalog indices.
    (Since ADR-070 the belt choices are catalog-id genes that evolution
    holds fixed.)
* The tensioning slot (`tension_travel_mm`, ±3 mm, PROVISIONAL) is reported
  as `C ± travel`, never used to reach a geometry.
* **Checks** (`calflab.mech.belts.evaluate_drive`), each pass, fail or unknown:
  * the pulleys match the belt pitch;
  * the length's source covers the system's width (ADR-064);
  * the belt goes round both pulleys;
  * C > (D1 + D2)/2 + 3 mm;
  * at least 6 teeth in mesh on the driver, with wrap = pi - 2 asin((D2 - D1)/2C)
    and teeth = driver teeth x wrap / 2 pi;
  * the servo case lies between the joint fittings at both ends of its segment;
  * for the hock, its servo and bracket clear the stifle's driven pulley and
    belt through the **whole** stifle range, sampled every 2.5 deg in the
    tibia's plane.
* **Unknown is not pass.** The position of the output axis on the STS3215
  case is not supplied (`servo.output_axis_offset_mm: null`). A check that
  depends on it passes only if it passes for every position, fails if it
  fails for the most favourable one, and is otherwise "unknown". An unknown
  check does not reject a choice; it is shown in amber.
* **Rejected, not clamped.** `set_belt_drive` builds the design with the
  candidate choice and refuses it with every failed check and its numbers.
  It also refuses a stifle choice that would make the hock check fail. The
  document is then unchanged. Choosing a new system or pulley pair without a
  length re-picks the length by the default rule and says so.
* A drive that **becomes** invalid after a body edit (a gene change, a
  catalog edit) is not silently replaced. The design still builds and is
  shown, with the rejection in its warnings. F5, the load analysis and the
  belt comparison refuse to simulate it until a valid belt is chosen.
* **Defaults.** For each drive, the offered length of the default system and
  pair whose C is closest to a target while passing every check. A drive
  with no stored choice uses this rule; a new project stores its defaults.
  * Stifle: target C 175 within 150-200 (the request's "150-200 mm, servo in
    the hip block") gives 444 mm, C 176.7 mm.
  * Hock: target C 180 gives **400 mm, C 154.7 mm**. The 444/450 mm belts
    (C 176.7/179.7) fail the sweep: the stifle belt reaches the hock servo
    from about 78 deg of stifle flexion, and the stifle range is
    PROVISIONAL -30 to +80 deg. With the range limited to 75 deg, 450 mm
    no longer fails: it is "unknown" (3.7 mm of clearance if the case
    points down the tibia) until the servo's output-axis offset is entered.
    The hock sweep is also "unknown" for 400 mm until the output-axis
    offset is entered (9.9 mm clearance if the case points down the tibia).
  * Carpus (option): target L 680 gives 640 mm, the longest offered in
    10 mm.
* A belted joint's range may not exceed 360 deg / ratio (180 deg at 2:1). A
  wider range in `config/feral_calf.yaml` makes the build fail with that
  message.

*Not modelled.* Belt stretch and compliance (the belt is a rigid ratio in
the simulator, as before: `Transmission` ratio x efficiency); pre-tension;
the stifle servo against the hock belt (they are far apart); clearance
between belts or servos and anything else but the case above.

## ADR-064 — Belt data and their sources; the narrow-belt derating caveat (**VERIFY**)

*Data.* Supplied by the researcher on 2026-11-02 and entered exactly.
`config/belts/*.json` are the templates; each feral project has its own copy
in `<project>/catalog/`, which is what the project uses. Building without a
project folder, as in a worker, falls back to the templates, with a warning.
The catalog's SHA-256 is recorded with designs and runs.

* GT2 2 mm, 10 mm generic: allowable 44 N (111 N per 25.4 mm = 4.37 N/mm x
  10), breaking 860 N (86 N/mm x 10). The **default**.
* GT2 2 mm, 9 mm Gates: 39 N, 774 N.
* GT2 2 mm, 15 mm generic: 66 N, 1290 N. No lengths confirmed in 15 mm, so it
  offers none.
* GT2 3 mm, 9 mm and 15 mm: breaking 1422 N and 2370 N (158 N/mm). Allowable
  working tension **unknown** (null): the sustained check says "unknown".
* Sources: SDP-SI Technical Section Table 3, eBay 335089089074, the Ondrives
  GT2 and 3 mm GT2 catalogs, as cited in each entry.
* **SDP-SI says belts under 1 in wide must be derated**, so 44 N and 39 N are
  optimistic. That note is on every 2 mm entry and is shown in the Belts
  panel.
* Lengths: Source A (eBay, generic 6/9 mm), Source B (Ondrives, Gates
  3/6/9 mm), Source C (10 mm listings: eBay UK 283328995672, an AliExpress
  10 mm listing, Amazon B0G1XTWKCG), and the Ondrives 3GT lengths as Source
  D. Every entry has `purchase_confirmed: false`. An entry that is not a
  whole number of teeth is rejected when the catalog loads; all 192
  supplied lengths are whole.
* Pulley pairs: 30T/60T (default), 36T/72T, 40T/80T, all 2 mm pitch, all
  2:1. Pitch diameters are computed; a file that writes one is rejected.

*Width coverage.* As the researcher gave it, each system names the sources
whose lengths it offers (`length_sources`): 10 mm generic = C, 9 mm Gates =
B. Assumptions:
* "Generic 9 mm = Source A" was stated, but no generic 9 mm **system** was
  listed, so none was created and Source A lengths are offered by no system.
  Adding one needs its values, which follow the same rule (39 N, 774 N);
  ask.
* The 3 mm systems offer Source D because the researcher listed those
  lengths under them. The widths the Ondrives 3GT listing covers were not
  stated (`widths_mm: null`).
* There are no 3 mm pulley pairs in the catalog, so the 3 mm systems cannot
  be built yet. The comparison lists them as "not buildable".

## ADR-065 — Tension springs: pull only, applied every physics step (**VERIFY**)

*Model.* A spring is a `Spring` element of the RobotSpec: two anchors (in the
frames of the segment above and below a joint), a rate k (N/mm) and a free
length.
* Force = k (L - L0) when stretched, **0 when slack**; it never pushes.
* In MuJoCo the two anchors are sites. Before every physics step the runner
  applies the force along the line between them, equal and opposite, to the
  two bodies (`mj_applyFT` into `qfrc_applied`). The anchor positions are
  those of the last kinematics pass, at most one 2 ms step old.
* The torque about the joint is recorded every control step: force x signed
  perpendicular distance from the joint axis to the spring line. Rollouts
  store `spring_force` and `spring_torque`. They stay deterministic (tested).
* The geometry, rate and free length are **genes**: sliders now, evolvable
  later (unlike belts, ADR-063). Anchors are measured from the joint axis,
  `along` the segment and `normal` to it (positive toward the front).

*Defaults (all PROVISIONAL).* Anchor positions were solved for the requested
pull and a 25 mm moment arm in the standing pose. The joint is open (105 deg
at the stifle), so a 25 mm arm on its convex side needs anchors standing off
the tube, like the patella and the point of the hock.
* Stifle (front): k 0.4, L0 64.5, femur and tibia anchors 30 mm along, 55 mm
  forward. Gives 20.0 N, 25.4 mm arm, -0.51 N*m.
* Hock (back): k 0.2, L0 39.5, tibia anchor 80 mm up and 10 mm behind;
  cannon anchor 20 mm *above* the hock and 15 mm behind (a calcaneus-like
  lever). Gives 7.7 N, 24.8 mm, -0.19 N*m.
* Shoulder: k 0.2, L0 43.5, chest anchor 40 mm above and 30 mm behind the
  axle, upper-leg anchor 40 mm down and 25 mm behind. Gives 8.0 N, 24.9 mm,
  +0.20 N*m.

*The shoulder's side was chosen by simulation*, as the request asked for the
side that helps rising from kneeling. Without a shoulder spring, the shoulder
servo's mean torque while the front rises from kneeling is +0.21 N*m: it
swings the leg back. A spring behind the shoulder gives +0.23 N*m there, and
the servo's mean falls to about 0. A spring in front gives -0.03 and works
against it. The cost: kneeling and the standing pose itself load the
shoulder servo more (standing: +0.12 N*m more).

*Side check.* `calflab.mech.statics` estimates, quasi-statically, the torque
the body's weight and the ground put on the segment below each joint in the
standing pose. The ground reactions are vertical, minimum-norm and balance
the weight under the centre of mass (the lever rule for four symmetric
hooves). A spring whose torque has the same sign gets a red "helps collapse"
warning. With the defaults:
* stifle and hock: "resists";
* shoulder: gravity gives only -0.002 N*m at standing, so the side verdict
  there means little; the kneeling result above is the one that counts.

*Relief.* The load analysis runs each scenario again with the springs off
and reports the change in mean and peak servo torque and belt tension.

## ADR-066 — The final feral calf: a body of its own (**VERIFY**)

*Requested 2026-11-02.* A new project `projects/robot-calf-final` (not in git,
like every project), built from the researcher's dimensions.
`projects/small-calf-two-joint` was not touched.

*Decision: a new genome and part generator, `feral_calf`*, not new genes on
the reference calf. The rear leg has three segments with a fixed femur and
no hip pitch; the front legs have two. That is not a variant of the calf's
2-segment, 3-DOF legs, and the calf's genome would have needed a dozen
switches. New projects are made from a template:
`calflab new-project <folder> --template feral_calf`. The template:
* copies the belt catalog into `<project>/catalog`;
* stores the default belt choices;
* uses the controller `feral_motion`;
* sets derating 1 and skin off.

The reference calf and every existing project are unchanged; the full test
suite passed before and after.

*Body.*
* The trunk origin is midway between the hip and shoulder axles, which are
  level and `axle_spacing` (550, PROVISIONAL) apart.
* Rear leg: `joint.<k>.hip_abd` (fore-aft axis) -> `leg.<k>.femur`, fixed
  at 40 deg forward -> `joint.<k>.stifle` -> `leg.<k>.tibia` (35 deg back)
  -> `joint.<k>.hock` -> `leg.<k>.cannon` (10 deg) with the hoof pad.
* Front leg: `joint.<k>.shoulder` -> `leg.<k>.upper` -> `joint.<k>.carpus`
  -> `leg.<k>.cannon`.
* Joint angles are 0 standing. Positive is flexion (stifle, hock, carpus), a
  backward swing (shoulder) and abduction (hip).

*Assumptions in the skeleton (PROVISIONAL unless the researcher said so).*
* The rear cannon leans 10 deg **forward** of vertical, hoof ahead of the hock.
* The front upper leg leans **forward** (carpus ahead of the shoulder axle)
  and the cannon back by the same angle.
* **The back is kept level**: the front angle is solved so the front hooves
  stand at the rear hooves' height. The researcher said "about 5 deg" for
  each front segment, but 340 cos 5 + 245 cos 5 + 30 = 612.8 mm against the
  rear's 610.4. Both front segments are therefore at **7.18 deg**, and the
  lab warns that this differs from the gene by more than 3 deg. Standing
  height: 610.4 mm.
* "Hoof pad 30 mm below the cannon end": vertically, in the standing pose; a
  15 mm sphere (PROVISIONAL radius) whose bottom is 30 mm below.
* No hip pitch: the stifle servo sits in the hip block region at the top of
  the femur, and the femur turns with the hip ab/ad joint. Read that way, no
  belt crosses a joint it does not drive: the stifle belt runs down the
  femur and its servo turns with the femur.
* Legs hang just outside the blocks: lateral offset = rail spacing / 2 +
  20 mm + tube radius + 2 mm.
* The hip ab/ad servo sits in the hip block, the shoulder servo in the chest
  block. The direct carpus servo sits at the carpus, on the upper leg. Every
  servo's case is 45.2 mm along its segment, with the shaft parallel to the
  joint axis.
* The blocks are boxes as long as twice the overhang ((760 - 550) / 2 each),
  rail spacing + 40 mm wide and 80 mm tall. They are drawn, but their mass is
  not entered.
* The rails run axle to axle (550 mm) at axle height.
* The head + neck mass sits 150 mm ahead of the chest block and 150 mm above
  the axles. The batteries hang 50 mm below the rails, 120 mm ahead of the
  hip axle. All PROVISIONAL.

*Servo.* `sts3215_c018` in `config/components/actuators.yaml`, holding only
the researcher's values:
* 2.94 N*m stall and 0.98 N*m rated at 12 V;
* 0.222 s/60 deg, entered as 45.045 rpm (= 10 / 0.222);
* 55 g; 45.2 x 24.7 x 35 mm;
* 4096 steps per revolution; gear 1/345.

The existing `sts3215` entry (recalled from memory) is untouched. **Stall
current was not given**, so ADR-051 changed for it: `stall_current_a` is now
optional with no default. Missing, it is listed as `unknown`; the servo has
no current, power or thermal estimate (its temperature stays ambient), and
the power budget says "Motor current UNKNOWN" and counts only the idle draw.
Armature, idle current, winding resistance and the thermal figures take the
model defaults ("default assumed" in the audit), as for any entry that omits
them. Two new optional fields: `rated_torque_nm`, `encoder_steps_per_rev`.

*Branch.* This work is on `robot-calf-final`, cut from `chassis-mass`.

## ADR-067 — Every PROVISIONAL value in the feral calf (**VERIFY**)

From the researcher (marked PROVISIONAL by them):
* rail spacing 100 mm (80-120);
* hip-shoulder axle distance 550 mm;
* head + neck mass 0.15 kg and its position;
* tube density 1.55 g/cm3, and tube OD/ID 15 x 12 per segment (14x10 and
  16x12 under consideration);
* rail type (two 8 mm CF rods by default, or 1/2 in x 0.049 in aluminium);
* battery position;
* belt efficiency 1.0;
* tension travel ±3 mm;
* sustained = more than 25 % of a gait cycle;
* breaking flag at 0.25 of breaking strength (the researcher's own safety
  factor, not a supplier value);
* every spring value (ADR-065).

Chosen in this session to make the checks computable (`config/feral_calf.yaml
layout`, `joint_ranges_deg`, `servo`):
* joint fitting reach 25 mm and clearance 3 mm, so a servo case may start 28
  mm from a joint axis;
* the hip block may hold the stifle servo up to 40 mm past the hip axle;
* pulley clearance 3 mm;
* bracket margin 3 mm and belt clearance 3 mm in the hock sweep;
* belts and servos assumed in one plane (the sweep is the worst case);
* hoof pad radius 15 mm;
* block height 80 mm and side margin 20 mm;
* the servo case orientation (45.2 mm along the segment, 24.7 across, 35
  sideways);
* joint ranges: hip ab/ad -25..25, stifle -30..80, hock -30..80, shoulder
  -60..60, carpus -10..130 deg;
* the head and battery positions;
* the leg lateral offset, the cannon and front-leg lean directions, and the
  rail length (ADR-066).

All appear in the Belts panel's *Provisional and missing values*, in the
scene and in every load run (`loads.json` `provisional`). Genes carry
`provisional: true`; generator parameters use `P(..., provisional=True)`.
Both show a PROV badge in schema forms.

## ADR-068 — Feral calf masses: what is counted, what is missing (**VERIFY**)

Counted:
* servos, 55 g each, at their mounts (`component`);
* tubes and rods from OD, ID, length (joint centre to joint centre, fittings
  ignored) and density (new source `tube`): 334 g with the defaults;
* the two 3S 2200 mAh packs, 135 g each, and the head + neck lump, 150 g
  (new source `specified`: supplied, not weighed here).

Not entered: horns, bearings, clamp collars, tube plugs, the two blocks,
electronics, skin, hoof pads, belts, springs, neck rods, and the 30T and 60T
pulleys (in `catalog/pulleys.json`). They are **required** values, left
`null`. They count as 0 g, are listed by item and quantity with where to
enter them (`spec.metadata["missing_masses"]`, `mass_breakdown()["missing"]`,
the Mass tab, the Belts panel), and get a mass geom at their place once
entered. Aluminium density is not entered, so an aluminium rail counts 0 g,
with a warning. The request said "placeholder masses flagged PROVISIONAL";
no numbers were given, and no hardware value is invented (rule 4). So the
placeholders are empty required fields rather than guessed grams.

Total as entered: **1304 g**, centre of mass 20 mm ahead of mid-axle, 515 mm
up. The real robot is heavier by everything listed as missing.

## ADR-069 — Load analysis of the feral calf: scenarios, flags, belt comparison (**VERIFY**)

*Motions* (`controller:feral_motion`; joint-space keyframes and phases;
starting points, not tuned):
* **stand** holds the pose.
* **walk** is a lateral-sequence crawl: hind left, front left, hind right,
  front right, 15 % swing, 4 s cycle. The rear ab/ad joints shift the body
  3 deg over the supporting legs before each pair of steps. One leg at a
  time with no shift fell, because with the centre of mass mid-body it lies
  on the diagonal of every support triangle. With 4 deg of shift and a 4 s
  cycle it falls too: the margin is small. Speed is about 17 mm/s, no fall
  in 30 s.
* **lie_rise**:
  * kneel on the carpi (shoulder -20, carpus 110);
  * fold the hind legs (stifle 75, hock 75) and lie, resting on the stifles
    and carpi at 284 mm, since the femur cannot fold;
  * hold;
  * rise hind end first;
  * both front legs reach forward and plant their hooves (shoulder -45,
    carpus 50), then push up.

  One front leg at a time tips this body over: it has no front ab/ad.
  Extending the carpus straight from kneeling somersaulted it forward.

*Runs.* Each scenario is simulated with the servos allowed up to stall
(derating 1), and again without springs. Each is recorded as a `loads` run
with its rollout, so it replays in the viewport, plus three files:
* `loads.csv`, per frame: angle, joint torque, servo torque = joint /
  (ratio x efficiency), spring torque, total, belt tension
  T = servo torque / (D1 / 2), % rated, % stall;
* `loads_summary.csv`: per joint;
* `loads.json`.

*Flags.*
* **Sustained** = in any window of one gait cycle (the walk's 4 s, for every
  scenario), the fraction of frames above the limit exceeds
  `sustained_fraction`.
* **Servo**: sustained above `rated_fraction` (0.6) x rated torque; any
  frame at 0.999 x stall or more.
* **Belt**: sustained above the allowable working tension ("unknown" when
  the system has none); peak above `breaking_fraction` x breaking.

*Belt comparison.* The walk on every system x pulley pair of the catalog,
with everything else fixed. Each drive takes the default-rule length for
that combination, so C and the servo position change with it. That is the
honest comparison: a different pulley needs a different stock belt. It is a
`belts` run with `belt_comparison.json` and `.csv`.

*Results on 2026-11-02* (defaults; masses as entered; servo values
unverified):

| Scenario | Flags | Peaks |
|---|---|---|
| Standing | none | servos at 3-17 % of rated |
| Walk | none | stifle belt 91 N against 44 N allowable (11 % of breaking), not sustained; hip ab/ad up to 105 % of rated |
| Lying down and rising | 8 | stifle belts above 44 N for 60 % of a cycle; hock belts for 28 %; shoulders and carpi above 60 % of rated for 75 % and 54 % of a cycle; shoulders peak at 77 % of stall |

No servo reaches stall. In the comparison, larger pulleys lower the belt
peak in the walk: stifle 91 N (30T), 76 N (36T), 69 N (40T). The 9 mm Gates
belts carry the same tension at a lower allowable (39 N). The 15 mm and 3 mm
systems are not buildable (no lengths; no 3 mm pulleys).

*Limits.* Contact and joint losses are the calf's defaults (ADR-058). The
servo model has no torque-speed curve. The motions are scripted, not
controlled, so peaks depend on their timing.

## ADR-070 — The feral calf evolves; its belt drives do not (**VERIFY**)

*Requested 2026-11-02.* "Get this body to be evolvable. Add the belts to the
catalog index and ensure that their dimensions are unchanged with the
evolution." The researcher accepted that this limits which geometry may be
changed automatically.

*Read as.* The belt choices join the genome as catalog references, so every
candidate, bake and run records them. Evolution never changes them, so each
belt's length, pulleys, C and servo position along its segment are the same
in every candidate. Not read as: letting evolution pick other catalog
entries. That would change the dimensions. If wanted later, it is a
discrete choice among catalog entries with its own ADR.

*Decision.*
* **Belt genes.** `belt_<drive>_system`, `_pulleys`, `_length` for stifle,
  hock and carpus (nine genes). They are enums of a new kind, `open`: the
  value is an id in the project's belt catalog, accepted by the gene and
  checked by the build, which fails with the id's name if the catalog has
  no such entry. They are `hidden` (not in Form or the node editor form) and
  `evolvable: false`. An open gene cannot be evolvable: the definition
  refuses it.
  * `set_genes` refuses them.
  * `set_belt_drive` writes them after its checks (ADR-063).
  * `set_node_params` refuses the generator's belt switches (`auto_belts`,
    `belt_catalog`, `default_*`).
  * Asking MAP-Elites to evolve one is an error naming it.
  * The generator's `belts` parameter is gone. Its defaults equal what the
    project had stored, so no genome version bump was needed.
  * `projects/robot-calf-final` was converted through `set_belt_drive` and
    `set_node_params` (logged, undoable).
* **What evolves.** Segment lengths and angles (femur, tibia, rear cannon,
  upper leg, front cannon), the axle spacing, and all spring genes. Fixed:
  belts, tubes, rails, body length, the front angle (solved for a level
  back), masses and part positions.
* **Belt-bound geometry.** The belt checks depend on these genes, marked
  `belt_bound`:
  * femur length: the stifle servo's room;
  * tibia length: the hock servo's room and its clearance;
  * femur and tibia angles: the hock servo against the stifle belt;
  * upper leg length: the carpus, when belted.

  Before a run each one is scanned (33 values, the others at their starting
  values) and searched only in the stretch around its starting value where
  every belt passes. The run log and `run.json` (`inputs.bounds`) say so.
  With the defaults:
  * femur length 137 mm and up;
  * tibia length 231 mm and up;
  * femur angle up to 43.8 deg;
  * tibia angle up to 39.4 deg.
* **Rejected, never repaired.** A part generator may list in
  `spec.metadata["infeasible"]` why a body cannot be built; the feral calf
  lists failing belts and front legs too short for a level back. Such a
  candidate is not simulated. It is stored with status `infeasible` and its
  reasons, and counted in the Evolve panel. Genes interact, so the narrowed
  ranges cannot exclude every failure; this catches the rest. Only belt
  failures narrow ranges (`infeasible_by.belt`): the front-reach limit is
  left to the front-leg genes, which can fix it.
* **The same catalog everywhere.** Evolution, study and gait-tuning workers
  build away from the project folder. The lab inlines the project's three
  catalog files into their generator parameters (`belt_catalog`), so no
  worker falls back to the repository's template. The inlined copy is
  stripped whenever a run's parameters are put back on a graph, so a
  document never keeps it.
* **Inner loop and archive.** `feral_motion` exposes ten walk numbers to
  CMA-ES: cycle, swing fraction, sway, and the hind and front sweep and
  lift. Their ranges keep one leg in the air at a time. New archive
  descriptors: `standing_height` (450-800 mm) and `step_cycle` (2.5-8 s).
  A gene file may give its evolution defaults (`evolve:`). The feral
  calf's are those two descriptors and 9.5 s rollouts. The lab uses them
  where the Evolve panel sets nothing, and the panel shows them.

*Checked.* `tests/test_feral_evolve.py`, with an evolution of 8 candidates
on varied belt-bound genes: every candidate has the starting belt genes,
one C and one servo position per drive, and its infeasible candidates carry
reasons. A 2 x 4 run on `projects/robot-calf-final` took 41 s, rejected one
candidate (an angle combination the one-at-a-time scan could not foresee),
and kept both belts' C to the micrometre. The fitness preset is still
`walk` (target 0.5 m/s, far above this body's 0.02 m/s), so its scores only
rank candidates against each other.

## ADR-071 — The front carpus is belted by default (**VERIFY**)

*Requested 2026-11-02.* Looking at the evolved body, the researcher said the
front knee (carpus) "should be belt drive as well". In the original request
the belted carpus was an option, off by default (ADR-066).

*Decision.* Gene `carpus_belt` defaults to **on**, with `absent: false`: a
genome saved before this change keeps its direct carpus, as with every
default changed after genomes were saved (ADR-047). `projects/robot-calf-final`
was switched on through the researcher's running lab (`set_genes`, one undo
step).
* With the default body the carpus takes the 640 mm 10 mm belt: the
  longest offered in that width, against the request's target of about
  680 mm. C is 274.8 mm, so the carpus servo rides on the upper leg 65.2 mm
  below the shoulder axle.
* All five checks pass (14.7 teeth in mesh; the case fits for any
  output-axis position).
* The servo's mass moves from the carpus up to near the shoulder: the centre
  of mass rises from 515 to 538 mm and moves 3 mm back. The total is
  unchanged.
* Six belted joints now: six 30T and six 60T pulleys, and four clamp collars
  (hock and carpus servos), all still to be weighed.
* `upper_leg_length` is now an active belt-bound gene in evolution.

*Not re-run.* The load analysis, the belt comparison and the test evolution
of ADR-069/070 were made with a direct carpus. The shoulder servo stays in
the chest block, as requested.

## ADR-072 — Turned-out legs on the feral calf: toe-out and splay as fixed mounts (**VERIFY**)

*Requested 2026-11-02.* "The legs need to be turned out a little ... add
toe-out and splay assuming mounting conditions for the servos, not active
servo engagement to maintain."

*Decision.* Four genes, as on the reference calf (ADR-060):
`hind_leg_toe`, `front_leg_toe` (-30 to 30 deg) and `hind_leg_splay`,
`front_leg_splay` (-15 to 30 deg), in Form under Rear legs and Front legs.
They are 0 by default and not evolvable. A genome that does not mention them
reads 0, so every existing body is unchanged; no version bump.
* Each is a **fixed rotation of the leg's mount**, the servo seat in the hip
  or chest block: yaw about the vertical (toe-out, front of the leg
  outward), then roll about the fore-aft axis (splay, lower end outward),
  mirrored left and right.
  * The whole leg turns with it, joint axes included.
  * The hind ab/ad axis yaws with toe-out; the shoulder axis turns with both
    angles. The ab/ad and shoulder servo boxes in the blocks turn the same
    way.
  * **No joint, servo, range or control changes**: nothing holds the angle
    but the mount. The hind ab/ad servo still has its own range around it.
* **Belts are untouched.** Every belt lies in its leg's plane, which turns
  rigidly with the mount, so C, the servo positions and the clearance sweep
  are exactly the same: tested.
* The shoulder spring's chest anchor turns with the front mount, so the
  spring stays in the leg's plane; the other springs live on leg segments.
* **Hooves stay on the ground, back level.** Toe-out leaves the height
  alone. Splay shortens a leg's height by cos(splay). The hind height sets
  the axle height and the front angle is solved again
  (`(upper + cannon) cos(theta) cos(front splay)`). A front pair too short
  for that is infeasible, as before.

*Checked.* With 10 deg toe-out and 8 deg splay on both pairs:
* the hooves stand 84/82 mm (toe-out only) or 162-166 mm (with splay) off
  the centre line, against 79.5 mm straight;
* the axle height drops from 610.4 to 604.8 mm;
* it stands, and its slow walk covers 320 mm where the straight body covers
  237 mm in the same time (untuned gait);
* the belts' C values are identical.

*Not done.* Toe-out and splay per leg (only per pair). Evolving them.
Clearance between a splayed leg and the blocks: nothing checks it.

## ADR-073 — Behaviors from reference footage: keypoints, retargeting, a stochastic repertoire (**VERIFY**)

*Requested 2026-11-02.* "Start implementing more stochastic behaviors from
reference footage, so that the geometry is capable of more than just
ambulating ... implementing infrastructure to accommodate that."

*Decision: the pipeline, end to end, in the core (`calflab.behave`, the
`behaviors` controller):*

1. **Footage is tracked outside CALFLAB.** Pose tracking needs trained
   networks (DeepLabCut, SLEAP) or a person clicking points; CALFLAB reads
   their output instead of bundling one. `calflab.behave.keypoints` reads
   three CSV layouts:
   * DeepLabCut's (scorer/bodyparts/coords header);
   * long (`frame, keypoint, x, y[, likelihood]`);
   * wide (`frame, <name>_x, <name>_y`).

   Image y is flipped to point up. Points under a likelihood threshold are
   dropped, gaps up to 10 frames are interpolated (longer ones stay
   missing), and a 3-frame moving average smooths the rest. Files go in
   `<project>/footage/`.
2. **Retargeting by a map file** (`config/retarget/<name>.yaml`, or the
   project's `motions/maps/`, which wins).
   * Per robot joint: a `flexion` (the interior angle at a landmark) or a
     `swing` (a segment's direction in the trunk's frame), with sign and
     scale. Landmarks may list alternative names.
   * **Angles are the animal's change from a reference frame** of the
     footage (first, median or a frame), applied to the robot's own standing
     pose. A calf's proportions differ from the robot's, and the camera's
     scale and angle do not matter this way; an absolute retarget would
     need a full-body inverse kinematics nobody has calibrated.
   * A side view sees one side: the far legs copy the near ones, lag half a
     gait period, or hold.
   * Hip ab/adduction cannot be seen from the side and holds its pose.
   * The root path (pitch from the hip-withers line, height scaled to the
     robot's axle height) is stored for previews only; the simulator does
     not follow it.

   `feral_calf_side` is the template map.
3. **A clip is checked against the body, not changed** (`clip_report`):
   * per joint, how much of it lies outside the range (the controller
     clamps those frames);
   * its fastest change against the servo's no-load speed at that joint (a
     2:1 belt halves it), and the slow-down that would make the whole clip
     followable;
   * a verdict: plays, clamped, too fast, or both.

   `preview_clip` poses the body frame by frame (no physics) as a run of
   kind `clip` that replays in the viewport.
4. **Stochastic behaviors** (`controller:behaviors`).
   * A repertoire of `clip`, `idle` and `gait` entries (a gait is any other
     controller, e.g. `feral_motion` walk or trot).
   * The next one is drawn from weights or a transition table (a Markov
     chain), with random speed, amplitude, repeats and left/right mirroring
     within ranges. Switches cross-fade.
   * Commands stay under 90 % of each servo's speed.
   * Seeded, so a rollout is reproducible; the chosen episodes go into the
     rollout (`meta.controller_log`) and the playback payload.
   * Idle sway is an Ornstein-Uhlenbeck process shared by the left and right
     joint of each pair. Independent sway of 2 deg tipped the feral calf
     onto a diagonal and over. Shared, it survived 4 deg on five seeds out
     of six, and the default repertoire (idle, walk, trot) ran 40 s on six
     seeds without a fall.
   * `add_behavior` adds a clip at a speed the servos can follow.
5. **Clips reach workers.** A controller may resolve project data into its
   params (`Controller.resolve_params`): the behaviors controller inlines
   the angles of the clips it names when the graph evaluates it, so
   evolution workers play the same clips; the controller node's cache key
   includes the motion library.
6. **Imitation is a real fitness term** (it was a Phase 2 stub): exp of
   minus the squared ratio of the run's RMS joint tracking error (new
   metric `tracking_rms_deg`, commanded vs achieved) to a scale. With
   clips playing, that rewards a body that can actually perform them. New
   preset `behave` (survival, imitation, stability, joint limits). The
   root path is not compared yet.

*Checked.* Synthetic footage: the feral calf posed by forward kinematics
with a known pawing motion, seen from its left side and written as a
DeepLabCut CSV. Retargeted, it gives back the angles within 0.6 deg
(shoulder, stifle, hock) and 2.3 deg (carpus: the smoothing rounds off a
sharp onset), and the report correctly finds the carpus 37 % too fast for
its belted servo. Tested in `tests/test_behave.py` (13 tests, including
import -> preview -> controller -> simulation in a project) and
`web/e2e/behave.spec.ts`.

*Not done.*
* No real footage has been through it.
* No 3D (multi-camera) keypoints.
* No hip ab/ad from a front view.
* Nothing chooses behaviors from sensors yet: the `touch_response` and
  `puppeteer_blend` behaviors are still stubs.
* No PPO imitation training (Phase 2).
* The behaviors repertoire is edited as JSON in the controller form.
* The feral calf has no neck or head joints, so a head toss or grazing
  dip can only be played by the legs and trunk.

## ADR-074 — The trot is back for the feral calf, and every gait stays within servo speed (**VERIFY**)

*Asked 2026-11-02:* "Where did the trot gait go?" The reference calf's CPG
finds joints by its own names (`hip_flex`, `knee`). It cannot drive the
feral calf, whose project uses `feral_motion` (stand, walk, lie/rise); no
trot was written for it.

*Decision.*
* **The trot** is `feral_motion` mode `trot`. Diagonal pairs (hind left +
  front right, then the other two) swing together half a cycle apart,
  reusing the walk's sweep and lift numbers scaled. There is no body shift,
  and hind ab/ad roll feedback from the IMU is on at 0.5 deg per deg of
  trunk roll. Open-loop trots fell in 3-8 s on this narrow-tracked body
  (hooves 79 mm either side of the centre line) unless the steps were short
  and low.
* **Servo speed.** The simulator limits torque, not speed (ADR-047). Every
  `feral_motion` command now moves no faster than 90 % of the servo's
  no-load speed at its joint (`speed_fraction`). Controllers receive those
  speeds in `ControlInfo.speed_limit`; a 2:1 belt halves them, to 135 deg/s
  from the STS3215's 270 deg/s.
  * Before this, the tuned trot asked the belted carpi for 190 deg/s, and
    even the slow walk exceeded 135 deg/s at the carpus once it was belted
    (ADR-071).
* **Defaults**, tuned with the limit on: cycle 0.6 s, swing 0.45, lift 0.3x
  the walk's, sweep 2x.
  * Result: 0.30 m/s; lowest speed margin 0.18; lowest torque margin 0.81;
    no fall.
  * Also no fall with 8 deg of splay and 10 deg of toe-out (0.14 m/s) and
    with a direct carpus.
* The walk and lie/rise still run, now within servo speed: the walk's
  speed margin is 0.08.
* The load analysis has a `trot` scenario (ramp + 10 cycles).

*Not done.* A torque-speed curve in the servo model. A trot tuned by
evolution; its numbers are not in the CMA-ES vector yet, which is the
walk's.

## ADR-075 — Choosing the controller in the Simulate panel; each keeps its settings

*Requested 2026-11-02.* After trying the stochastic behaviors, the
researcher could not find the trot: the Simulate panel shows the active
controller's form, and only `set_controller` typed on the command line led
back to *Feral calf motions*.

*Decision.*
* **A Controller list** at the top of Simulate > Controller, offering every
  implemented controller.
  * One that cannot drive this body is greyed with "(not for this body)".
    That is decided in the core: `Controller.fits(spec)`, true by default.
    The CPG needs the reference calf's `hip_flex`/`knee` joints;
    `feral_motion` needs stifles or shoulders.
  * The server sends the list with the graph (`controllers`).
* **Switching keeps settings.** The settings of the controller being
  replaced are kept in the document (`settings.controller_params`, by node
  type). A controller used before comes back as it was left (e.g. trot
  mode with a 0.7 s cycle), not reset to defaults; only explicit `params`
  override that.
  * One undo step per switch, the kept settings included.
  * `add_behavior` switches the same way.

*Checked.* `tests/test_behave.py` (switch, change, switch back, undo,
fits), and `web/e2e/behave.spec.ts` drives the list in the browser.

## ADR-076 — A video inbox: from a video in a folder to candidate clips (**VERIFY**)

*Requested 2026-11-03* (session T): "I drop a video of a calf into a folder;
CALFLAB turns it into behavior clips". Before this, footage had to be tracked
outside CALFLAB and imported as a CSV (ADR-073).

*Decision.*
* **The folder** is `<project>/footage/videos/`, created when the lab opens.
  mp4, mov, avi and mkv are picked up.
* **The watcher** is a thread of the lab (`FootageInbox`), started by the
  server, polling every 2 s (`poll_s`). It never runs in the UI. It runs one
  processing job at a time (tracking is CPU/GPU heavy), with progress and
  cancel like any job. Tests and the CLI call `poll()` directly.
* **Status records** in `<project>/footage/inbox.json`, keyed by file name:
  `waiting` -> `queued` -> `tracking` -> `retargeting` -> `needs_review` ->
  `ready`, or `failed` + reason, `cancelled`, `missing`.
  * A new file waits until its size and modification time are the same on
    two polls (still being copied otherwise).
  * The record holds the file's **SHA-256**. It is recomputed only when the
    size or modification time changes. A touched but identical file is not
    processed again; changed content starts over (new record, new
    candidates). Clips already accepted stay in the motion library with the
    old hash.
  * A job never writes into a record whose hash changed meanwhile.
* **Reading video** (`calflab.behave.video`):
  * OpenCV (`opencv-python-headless`, optional extra `video`, Apache-2.0,
    installed with the researcher's approval 2026-11-03) reads every
    format;
  * a built-in reader handles uncompressed and MJPEG AVI, so the synthetic
    footage and its tests need no package.

  The **frame rate is the file's own** (OpenCV `CAP_PROP_FPS`; AVI
  rate/scale), never assumed. OpenCV's frame count can be approximate for
  some containers; tracking reads to the end anyway.
* **Processing** a video: track (ADR-077) -> settle the near side (below)
  -> check the camera view -> retarget the whole video (near legs only) ->
  segment -> candidates. Tracks are kept per hash in
  `footage/tracks/<sha16>.npz` so review and trimming never re-track.
* **Near side.** An animal facing right in the image shows its right side.
  The facing comes from the rear and front trunk landmarks over the whole
  video. With two-sided keypoints (AP-10K), the side tracked more
  confidently is reported as a cross-check (`agree`). A map can be written
  for either side (`joints_side`, `side_names`, `{side}` in landmark names)
  and is mirrored. The inbox always decides the side from the footage
  (`auto_side`, default on).
* **Camera view.** Separation of the left/right hips and shoulders over the
  trunk length = (W/L) tan(yaw). **W/L = 0.35 is an assumption about
  calves**, a map setting (`view.width_over_length`), not measured.
  * The verdict is "side view OK" for a median yaw up to 25 deg, else
    "too oblique".
  * With one side tracked: "unknown (one side tracked)". Frames whose trunk
    looks shorter than cos(25 deg) of its longest are marked turned.
* **Segmentation** (`calflab.behave.segment`):
  * trunk motion in body lengths/s (hip-shoulder distance = 1);
  * limb activity: mean |d angle/dt| of the retargeted joints;
  * periodicity: the first autocorrelation peak of the angles in
    0.3-3 s.

  Still = trunk under 0.05 BL/s and activity under 8 deg/s (0.5 s smoothing,
  edges refined with the unsmoothed signal). Runs under 0.6 s join their
  neighbour. Kinds:
  * still runs of 1 s or more are `idle`;
  * moving runs with a peak of 0.4 or more and at least 2 cycles are
    `gait`, trimmed to whole cycles, with far legs suggested `half_cycle`;
  * other moving runs of 0.6 s or more are `other`.

  A camera that pans with the animal hides travel, so gaits are found by
  periodic limbs, not by trunk motion. **All thresholds are first guesses
  tested only on synthetic footage**; they are settings
  (`set_footage_settings`) and are stored with every clip.
* **Standing reference.** A clip's angles are relative to the middle of the
  video's longest still stretch (the map's `standing` if there is none), not
  to the clip's first frame: a walk cut mid-stride must not be offset.
* **Review** (Behave panel). The server serves frames
  (`/api/footage/<file>/frame/<i>`, JPEG) and tracked points
  (`/api/footage/<file>/points`, image pixels, confidences, skeleton, the
  landmarks the map uses). The browser only draws them.
  * Candidates are previewed on the robot (a kinematic `clip` run), trimmed
    (a trimmed gait keeps whole cycles), renamed, and accepted or rejected.
  * Accepted clips store the video's SHA-256 and info, frame range, tracker
    provenance, the full map with its side settled, the detected side and
    view, standing frame, cleaning and segmentation settings, and the
    retarget report.
* **Commands** (none edits the document, as imports before): `scan_footage`,
  `retry_video`, `cancel_video`, `preview_candidate`, `accept_candidate`,
  `reject_candidate`, `set_footage_settings`.
* **Synthetic footage** (`calflab.behave.synthetic`, `calflab tracker
  synthetic <out.avi>`): the feral calf posed by forward kinematics (stand,
  walk at a known period while travelling, paw), drawn as a stick calf with
  coloured markers, facing left (left legs near), 8-bit paletted AVI.
* **Schema forms**: an optional number (`float | None`) is `nullable` in the
  UI schema and shows "not set" until clicked, with a clear button, so an
  untouched valence stays unset instead of reading 0.

*Checked.* `tests/test_footage.py`:
* synthetic video -> colour-marker tracker -> inbox -> candidates
  idle/gait/idle, period 1.2 s found, near side left;
* angles back within 1.5 deg (measured 0.4-1.0 deg);
* the walk's cuts within 1-3 frames;
* watcher once / touched / changed / missing;
* a failing tracker then retry;
* frames and points;
* segmentation of walk-pause-walk at two periods;
* side and view on two-sided keypoints.

`web/e2e/footage.spec.ts` drives drop -> watcher -> review -> preview ->
tag -> accept in the browser.

*Not done.* Several animals in one video (the tracker follows one). Videos
over about 2 GB in the built-in reader (OpenCV handles them). A per-frame
camera-motion estimate (a panning camera's travel is not measured).

## ADR-077 — Pose tracking as a plugin type; RTMPose AP-10K on this machine (**VERIFY**)

*Requested 2026-11-03.* A plugin type `pose_tracker`; a CSV tracker, a
synthetic one, and one pretrained quadruped model that runs on this AMD,
no-CUDA machine, compared and recommended before installing.

*The comparison put to the researcher (2026-11-03).*
* **A. RTMPose-m AP-10K (ONNX)**: 17 keypoints; ONNX Runtime on CPU or
  DirectML; about 87 MB of weights with the detector; Apache-2.0 code and
  weights, AP-10K data CC-BY-4.0 (read in the AP-10K README).
* **B. DeepLabCut SuperAnimal-Quadruped**: 39 keypoints; PyTorch, about
  1 GB; weights for academic, non-commercial use only; CPU only here;
  slow.
* **C. ViTPose++-s (APT-36K)**: 17 keypoints; about 100 MB; dataset licence
  unclear.

None has separate stifle, hock and fetlock points: three points per leg.
Speeds were estimates; nothing was installed before the answer.

*The researcher chose* A, `onnxruntime-directml`, and `opencv-python-headless`.

*Decision.*
* **Plugin type** `pose_tracker` (`PoseTracker`):
  * `track(video, report, cancelled)` returns `KeypointTracks` in image
    pixels, y up, at the video's frame rate, with a confidence per point;
  * `TrackerCancelled` stops it;
  * `available()` says what is missing without importing anything heavy;
  * `keypoint_names()`;
  * `provenance()` gives tracker, model, version and params, stored in
    `KeypointTracks.model` and on every clip;
  * a contract (tracks a blank AVI when self-contained and available);
  * a `new-plugin pose_tracker` template.
* **`csv`**: the CSV beside the video (same name), at the video's frame rate.
* **`synthetic`**: centres of coloured marker pixels.
* **`rtmpose_ap10k`**:
  * YOLOX-s (COCO; a calf is accepted as cow, horse, sheep or dog) finds
    the animal; between detections the box follows the keypoints;
  * RTMPose-m (AP-10K, 256x256, SimCC) gives 17 keypoints, with pre- and
    post-processing as the model's own `pipeline.json`;
  * runs on DirectML (the AMD GPU) when present, else the CPU.
  * Checked on the model's own sample image: the points match the published
    output.
* **Packages**: optional extras `video` (OpenCV) and `track` (OpenCV +
  `onnxruntime-directml` on Windows, `onnxruntime` elsewhere). Without them
  the lab works and the tracker says what is missing.
* **Weights** are not packages. `calflab tracker download rtmpose_ap10k`
  (or the panel's button) fetches them into `<repo>/models/` (not in git;
  shared by a lab started from the Claude app and one from a terminal),
  checks the recorded SHA-256, and writes a manifest. Nothing downloads
  implicitly. Downloaded 2026-11-03 with the researcher's approval.
* **Keypoint names.** The ONNX file carries none. Its `detail.json` names
  the MMPose config `rtmpose-m_8xb64-210e_ap10k-256x256.py`, whose dataset
  metainfo (mmpose v1.1.0 `configs/_base_/datasets/ap10k.py`) lists them:
  `L_Eye, R_Eye, Nose, Neck, Root of tail, L/R_Shoulder, L/R_Elbow,
  L/R_F_Paw, L/R_Hip, L/R_Knee, L/R_B_Paw`. The count is checked against the
  model's output at load.
* **Map `ap10k_side`.** These choices must be checked against real footage:
  * the hind fold at the AP-10K Knee (hip-knee-hind paw) is split half and
    half between stifle and hock;
  * the shoulder swings with the whole leg (shoulder -> front paw);
  * the carpus takes the fold at the AP-10K Elbow.

  It was not known which anatomical joint AP-10K annotators mark as "Knee"
  on a calf's hind leg, or as "Elbow" on its fore leg. `min_likelihood`
  0.3: SimCC scores are not probabilities; 0.3 is RTMPose's own threshold.
* **Default inbox settings**: tracker `rtmpose_ap10k`, map `ap10k_side`.

*Measured* (2026-11-03): 250 frames of 640 x 360 (10 s at 25 fps), detector
on every frame, pose with a fixed box:
* DirectML (AMD GPU): about 4.9 s (detector 2.8 s, pose 2.1 s);
* CPU: about 32 s (detector 26 s, pose 6 s).

So `detect_every` > 1 mostly saves time on the CPU. Random frames were
used, so this is model time, not accuracy.

*Not verified.* Tracking accuracy on calf footage (no real video has been
through it). Which joints AP-10K's knee and elbow are on a calf. Whether the
YOLOX detector finds a young calf reliably.

## ADR-078 — Affect tags, composition as an expressive instrument, movement features (**VERIFY**)

*Requested 2026-11-03* (session T): accepted clips carry the researcher's affect
tags; the behaviors controller composes them with parameters of clear
kinematic meaning; rollouts are described by movement features, "labelled as
movement features, not emotions"; a composition study compares compositions.

*Decision.*
* **Affect tags** (`MotionClip.affect`):
  * valence -1..+1 (unpleasant..pleasant), arousal 0..1 (calm..agitated),
    free words, a note, and when tagged;
  * set only by the researcher (`accept_candidate`, `tag_clip`); the lab
    never infers or fills them;
  * an untouched valence or arousal stays unset ("not set" in the form),
    not 0;
  * the Behave analysis filters clips by words and value ranges on the
    server and lists the words in use.

  The scales are a choice of convenience (valence and arousal as in
  circumplex models); change them here if another scale is wanted.
* **Clips by tag.** A clip entry may give `select: {words, valence, arousal}`
  instead of an id. `resolve_params` inlines every matching clip and lists
  them in `pools`, so workers play the same set. The entry plays one of them
  each time. An entry whose tags match nothing is an error naming the tags.
* **Modulation parameters** (group "Composition" of the behaviors
  controller; the defaults leave every earlier rollout unchanged, the random
  draws included):
  * `tempo`: clip speed x tempo, the gait's clock x tempo, idle sway time
    constant / tempo;
  * `amplitude`: clip angles and idle sway size;
  * stillness: `idle_share` (the chance the next behavior is idle; -1 = the
    weights decide) and the existing `idle_noise_deg`;
  * smoothness: the existing `blend_s` and `lowpass_hz` (first-order
    low-pass on the commands, before the servo-speed limit);
  * phrasing: `repeat_prob` (play the same behavior again), `pause_prob` and
    `pause_s` (hold the last pose; never two pauses in a row).
* **Affect curve** (`affect_curve`): keyframes at times, each setting any of
  the parameters above (interpolated linearly), with a free `label` (the
  researcher's word for the moment, never interpreted).
  * A keyframe may give `target_valence` / `target_arousal`. Clip choice is
    then weighed by exp(-((tag - target) / target_width)^2) over the
    *researcher's* tags. An untagged clip keeps a small weight (0.05).
  * The lab ships no mapping from affect words to kinematics: what "calm"
    means in tempo or stillness is the researcher's to set in the curve.
* **Logged per episode**: every episode records the composition in effect
  when it began (parameters, targets, label).
* **Required clips** (for ADR-079): an entry may be `required` with an
  `imitation_weight`. `play_required_first` plays each required clip once,
  in a seeded order, before choosing freely.
* **Movement features** (`calflab.behave.descriptors`), each with a unit,
  and a note on every result that they are kinematics, not emotions:
  * quantity of motion (mean joint speed);
  * trunk speed;
  * jerk RMS and smoothness (-log10 jerk);
  * tempo (period of the strongest repetition of joint activity) and its
    regularity;
  * stillness ratio (joints under 5 deg/s);
  * expressive range (spread of 1 s windows of motion);
  * postural height (trunk / standing);
  * openness (foot spread / standing);
  * approach / retreat (net travel along the initial heading).

  Per-clip tracking error comes from the episode log.
* **Composition study** (`run_composition_study`, a job, run kind
  `composition`): each composition (behaviors params over the document's)
  plays with each seed, optionally with friction 0.7-1.1 and mass x0.95-1.05
  randomised.
  * It is compiled with `torque_derating` 1.0, as the load analysis is
    (ADR-069), so a servo can reach stall and the stall constraint means
    something.
  * The table gives mean +/- spread per composition: falls, clip tracking,
    safety margin and violations (ADR-079), and every movement feature.
  * It is stored as `composition_study.json` / `.csv`. The document is not
    changed.

*Checked.* `tests/test_composition.py`:
* selection by tags;
* tempo, amplitude, stillness, pauses and repeats, low-pass;
* the curve's interpolation and its steering toward clips tagged near the
  target;
* seeding;
* features of a known motion;
* a two-composition study.

On a scratch project the "as set" composition of a stick-calf walk fell on
one seed of two (the walk clip moves the legs as the drawing did, without
balance); "still" did not.

*Not done.* Composition parameters are edited in the controller's form
(JSON for the curve and the compositions); a curve editor would be easier.
Movement features are not yet archive axes outside the repertoire run
(ADR-079).

## ADR-079 — Evolving the body to perform a repertoire, consistently and safely (**VERIFY**)

*Requested 2026-11-03* (session T): a fitness preset for a repertoire,
safety as constraints from the load analysis, consistency over seeds and
mild randomisation, an inner loop over per-clip playback limits, archive
axes from movement features, and a cost estimate before running. The
researcher chose the safety policy: **reject breaking and stall, penalise
the rest** (2026-11-03).

*Decision.*
* **Preset `repertoire`** (`config/fitness/repertoire.yaml`):
  * `imitation_required` (scale 8 deg): the weighted mean, over the
    behaviors marked `required`, of exp(-(RMS tracking error while they
    played / scale)^2). A required behavior that never played scores 0.
  * `survival` and `stability`.

  Clips are marked required in the behaviors controller's repertoire
  (`required`, `imitation_weight`). Under this preset the controller plays
  every required clip once, in a seeded order, before choosing freely
  (`play_required_first`), so a short evaluation cannot miss one.
* **A preset may say how candidates are evaluated** (`evaluation:`). A
  preset without it (walk, gentle, behave) evaluates exactly as before. With
  it:
  * **seeds** [0, 1, 2], each compiled with its own floor friction
    (0.7-1.1) and mass scale (x0.95-1.05); torque, stiffness, damping and
    skin are not randomised;
  * **aggregate**: mean minus 1 x spread over seeds (or the worst seed);
  * **every seed recorded** (friction, mass, fitness, penalty, fall, margin,
    violations) in the candidate's `metrics.seeds`;
  * compiled with `torque_derating` 1.0, as the load analysis is, so a servo
    can reach stall and the stall constraint is meaningful (the document's
    default 0.6 caps torque below stall).
* **Safety constraints** (`calflab.evolve.safety`, built on
  `mech.loads.analyse`):

  | Constraint | Violated when | Default action |
  |---|---|---|
  | `servo_sustained` | above `rated_fraction` (0.6) x rated torque for more than `sustained_fraction` (0.25) of a window | penalise |
  | `stall` | any moment at or above stall torque | **reject** |
  | `belt_sustained` | above allowable working tension for more than `sustained_fraction` of a window | penalise |
  | `belt_breaking` | a peak above `breaking_fraction` (0.25) x breaking strength | **reject** |
  | `joint_speed` | a joint faster than its servo's no-load speed at that joint | penalise |
  | `joint_limit` | more than `joint_limit_max` of the time within 1 deg of a limit | penalise |

  * The fractions are the body's own checks (`config/feral_calf.yaml`, ADR-069).
  * **The window is 2 s** (`window_s`): a repertoire has no single gait
    cycle, and 2 s is about one slow walk cycle of this body.
  * **`joint_limit_max` 0.05** is an assumption.
  * A penalised violation costs `weight` (0.5) x the relative excess, at
    most 0.5 per constraint and seed.
  * Loads are judged **up to a fall**: after it they are not the motion's
    loads (ADR-069).
  * A reject in **any** seed rejects that controller setting. Inside the
    inner loop it scores 10 lower, so CMA-ES moves away from it.
  * If the best setting found is still rejected, the candidate is stored with
    status `unsafe` and its reasons, not archived, and counted in the
    history. It is never repaired.
  * `margin` = the smallest 1 - value/limit over known constraints, in the
    worst seed.
* **Inner loop** for the behaviors controller: two numbers per clip entry,
  the top of its speed range (from 0.2 up to `clip_report`'s playable speed
  *on this candidate's body*) and the top of its amplitude range (0.3 to 1,
  the clip as recorded). Each range becomes [0.8 x top, top]. Controllers
  can now give dimensions that depend on their params and the body
  (`vector_dims_for`, `params_from_vector_for`, `vector_from_params_for`;
  the defaults are the old class-level vectors, so `feral_motion` and the
  CPG are unchanged).
* **Archive axes**:
  * `expressive_range` (0-60 deg/s, the spread of 1 s windows of quantity
    of motion);
  * `quantity_of_motion` (0-40 deg/s);
  * `safety_margin` (-1 to 1).

  For example, x = expressive range and y = safety margin shows the
  trade-off rather than one winner. A candidate evaluated without these
  metrics reads 0 on them.
* **Kept from ADR-070**:
  * belts are fixed catalog genes;
  * belt-bound ranges are narrowed before the run;
  * infeasible bodies are rejected before simulation;
  * workers get the project's catalog inlined;
  * clips (and tag-selected pools) are inlined by `resolve_params`.
* **Cost estimate** (`estimate_evolve`, Evolve panel > *Estimate cost*):
  * one 2 s rollout of the working design is timed;
  * rollouts = generations x batch x (1 + inner iterations x popsize) x
    seeds;
  * wall time = generations x ceil(batch / workers) x one candidate's
    rollouts.

  It also offers a small budget (2 x 4, inner 1 x 4) with its own estimate
  and a button to use it.
* **Evolve panel**: the preset's evaluation (seeds, randomisation,
  aggregate, what each constraint does); per candidate, the seeds and the
  worst seed's safety table; an Unsafe counter.

*Checked.* `tests/test_repertoire.py`:
* a carpus slammed through 100 deg in 0.1 s hits stall: rejected. The same
  rollout under a penalise-only policy is kept with a penalty. A gentle
  sway passes.
* Robust evaluation over three seeds, each with its own friction;
  aggregate = mean - spread. A clip that folds both carpi to their limit
  makes the shoulders exceed rated torque for about 70 % of a window and is
  `unsafe` under a stricter policy.
* The inner loop's speed bound equals the clip report's playable speed.
* A 1 x 2 repertoire evolution (slow test): belts identical in every
  candidate, three seeds recorded, axes expressive range x safety margin.

Note: the inner loop slows a clip to what the servos can follow, so a clip
that is only *too fast* becomes safe rather than rejected. That is intended:
the loop tunes playback limits within the clip report.

On the scratch project the cost estimate for the default 6 x 8, inner
3 x 6 run was 2736 rollouts of 9.9 s, about 27 min on 7 workers.

*Not done.*
* The safety policy is set in the preset file, not in the panel.
* Domain randomisation of servo strength is off (`torque_scale` held at 1).
* The archive cannot show more than two axes at once.

## ADR-080 — 3D motion from one camera: the robot's skeleton lifted onto the keypoints (**VERIFY**)

*Requested 2026-11-03* (after the first real video): "Get 3D motion out of
ordinary single-camera videos of calves, not only clean side views ...
recover joint angles in 3D (including hip ab/adduction and the far-side legs)
and the animal's turning, instead of rejecting anything past 25 deg of yaw."

The first real video (7.45 s, 1780 x 990, screen recording, ~30.19 fps)
tracked well with RTMPose AP-10K, but the 2D view check called it "too
oblique" (median yaw 28.4 deg), found no standing frame, and gave one
`other` candidate. The 2D retarget (ADR-073) measures angles in the image, so
foreshortening corrupts them off-axis; the far legs are copied; ab/adduction
holds.

*Decision: a new retarget mode, `3d`, beside the unchanged `2d`.*

1. **Model-based lift** (`calflab.behave.lift`). Per frame the body's own
   skeleton (`RobotSpec` forward kinematics, joint ranges, standing pose;
   vectorised in `Skeleton`, checked against `RobotSpec.world_poses` in a
   test) and a camera are fitted so the projected landmarks match the
   tracked 2D points, weighted by confidence, with a robust (soft L1) loss.
   * **Camera: weak perspective**, `uv = s (R x)[:2] + t`. R = camera roll x
     camera elevation x (level camera at the animal's left side) x heading x
     trunk pitch x trunk roll. Elevation and roll are one pair for the video
     (the camera is assumed fixed); heading, pitch, roll, scale and image
     position are per frame.
   * **Full perspective is not used.** It needs the lens's focal length,
     which one uncalibrated video does not give, and the calf's depth is
     small against its distance. The focal length enters only through
     `camera_hfov_deg` (60, PROVISIONAL), which turns the change of image
     scale into travel toward or away from the camera.
   * **Maps** are YAML files with `kind: lift` in `config/retarget/`:
     landmark name -> a point on a robot body, the origin of a joint, the
     hoof, or a point between two joints (`toward`, `at`). Keys with `{S}`
     are written once for both sides. `ties` make a joint follow another.
     `ap10k_3d` (AP-10K) and `feral_calf_3d` (the robot's own joints, for
     synthetic footage or hand-clicked points) are provided.
2. **Stages**: (A) frame by frame from the previous frame, also trying the
   pose turned the other way and, where the fit fails, a fresh start from
   12 headings; (B) toward or away (below); (C1) proportions, camera
   elevation and roll from up to 120 good frames; a second round of A to C1
   with the fitted proportions; (C2) every frame refined together with a
   smoothness term, in windows of 400 frames; (D) diagnostics.
3. **Ambiguities, explicit and recorded per frame**:
   * *Toward or away (depth flip of the whole body).* In weak perspective a
     symmetric body turned toward the camera with its left side near looks
     the same as one turned away with its right side near, once the
     tracker's L/R labels are exchanged (`mirror_pose`, exact for a level
     camera). Both are kept; a two-state Viterbi chooses by which side is
     tracked more confidently (the far legs are partly hidden; smoothed over
     0.5 s) and charges for a jump in heading. Frames where the cue is under
     `min_cue` (0.03) are marked `ambiguous: depth`. A tracker that labels
     the whole animal the wrong way round is recovered (tested).
   * *Turned the other way with the labels kept* (+yaw vs -yaw): each frame
     is also solved from the opposite heading and judged with the same
     continuity term, so noise cannot flip it.
   * *Limb flips:* every leg's free joints are searched on a grid inside
     their ranges with the trunk held; a second local minimum more than 20
     deg away and nearly as good (within 4 noise units) marks
     `ambiguous: leg <id>`. The chosen solution is the one continuous with
     the previous frame.
   * *Unobservable joints:* a joint whose 10 deg change moves its landmarks
     by less than 2 % of the body length is listed per frame (hip
     ab/adduction in a level side view). It holds near its prior
     (ab/adduction toward standing, sd 15 deg, smoothness 60 deg/s).
   * *Leg labels:* where a frame fits badly, exchanging one leg pair's
     labels is tried and kept if it fits 30 % better (`swapped`).
4. **Proportions.** The calf is not the robot. Per video: trunk length,
   trunk width and front leg as ratios to the robot's, with the hind leg as
   the reference (the per-frame scale absorbs size), held over the clip and
   reported. They start from the tracked segment lengths (90th percentile).
   * **The width is identified only together with the yaw**, and only when
     the animal shows several yaws or the camera looks down. A curvature
     test was not enough: on real footage systematic misfit made a very
     narrow calf (W/L 0.12) turned 50 deg look "pinned". So the width comes
     from the prior `width_over_length` 0.35 (**PROVISIONAL**, an
     assumption about calves, sd 0.2 in log) unless fitting it freely
     lowers the residual of the whole smoothed video by at least 10 %
     (`min_width_gain`) and the footage pins it within 15 %. The result says
     which (`width_source`).
   * **Where the tracker's points sit on the robot can be fitted** too
     (`fit_at: [lo, hi]` on a `toward` landmark; one value per left/right
     pair, held over the video, reported as `landmark_at`).
5. **Noise scale.** Real keypoints are much noisier than synthetic ones (14
   to 22 px RMS on a 300 px calf here). The residuals are scaled by the
   larger of `noise_bl` (1 % of the body) and the frame-by-frame fit's
   median residual, so priors and smoothness keep their weight on real
   footage.
6. **Animal motion vs camera.** Heading (unwrapped, + = turning left),
   trunk pitch and roll, and the trunk's path on the ground (from the image
   position and scale, with the assumed field of view) become part of the
   clip (`root_quat` = heading x pitch x roll, `root_pos`, re-zeroed at the
   clip's start, height from the robot's own feet on the ground). The
   camera is assumed fixed; if the trunk's pitch or roll wander by more
   than 8 deg the result says the camera may tilt or roll. **A camera that
   pans or zooms cannot be told from the animal turning or approaching.**
7. **Per-frame reliability** replaces the "too oblique" verdict: residual
   (px and body lengths), estimated yaw from the nearest side view (+ =
   toward the camera), points used, state `ok` / `ambiguous` / `unreliable`
   / `missing` with reasons. Unreliable: fewer than 6 confident points; a
   residual over 2 x the video's median (at least 0.05) or over 0.12 body
   lengths; more than 70 deg from a side view (head-on / tail-on, where the
   legs' fore-aft angles become depth). Unreliable stretches longer than 10
   frames are gaps for the segmentation; shorter ones are interpolated.
8. **Segmentation on the 3D angles** (`segment(..., trunk_bl_s, gaps)`):
   trunk motion = ground speed and half the turning rate in body lengths/s;
   limb activity from every lifted joint. The standing reference is the
   middle of the longest still stretch; **without one, the robot's own
   standing pose** (the lifted angles are already the robot's), and the
   candidate says so (`reference`). Candidates carry reliable and ambiguous
   fractions, yaw range, turn and per-leg tracking; `far_side: tracked`
   keeps every leg as fitted, and a leg seen in under half the frames takes
   its twin (copy, or half a period later in a gait), recorded in the clip.
9. **Mode per project** (`FootageSettings.mode`, Settings in the Video
   inbox, `set_footage_settings mode=`). 3D for a new project; a project
   that processed videos before, or whose settings were saved before the
   mode existed, stays 2D until switched. `reanalyse_video` (*Analyse
   again*) re-runs the analysis on the stored tracks. Lifts are stored per
   video hash in `footage/lift/<sha16>.json`; the record keeps the summary.
10. **Packages.** None installed. `scipy` (already used by the core through
    `infill` and `pushed_model`, installed with `ribs`/`trimesh`) does the
    least squares. A learned lifter or a mesh quadruped model was not
    needed for this first version; see "Not done".

*Your assumptions, kept as you asked (VERIFY):* the hock tied to the stifle
(ap10k_side's half-and-half split of the hind fold) and AP-10K "Elbow" =
the robot's carpus. **What the first real video shows** (frames 0, 45, 200
drawn with the points): AP-10K "Knee" sits on that calf's **hock** (the fit
places it 0.96 of the way from stifle to hock) and "Elbow" on its
**carpus**; "Hip" and "Shoulder" sit on the thigh and at the point of the
shoulder, well below the top of the back (fitted: Hip 0.60 of the way down
the femur, Shoulder 0.42 down the upper leg). With the Knee at the
hock, untying the hock (two hind angles instead of one) is the natural next
step: your decision.

*Assumptions of this ADR (VERIFY):* weak perspective; a fixed camera; the
trunk level on average (makes elevation and roll identifiable); W/L 0.35;
60 deg field of view for depth travel; Neck, Root of tail and the head not
used; the thresholds above (first guesses tested on synthetic footage and
one real video).

*The first real video in 3D* (`projects/robot-calf-final`, switched to 3D
with `set_footage_settings mode=3d`, then *Analyse again* on its stored
tracks): no "too oblique"; 75 % of frames reliable; median yaw 15 deg; a
side view (10 to 27 deg) for the first 2.6 s, turning toward the camera up
to 84 deg around frames 100 to 140 (the calf at the ball, head-on and
motion-blurred: unreliable, a gap), then a side view again (1 to 17 deg).
Camera elevation 7 deg, judged fixed. Calf against robot: trunk 1.56 x,
front leg 1.12 x the hind leg's ratio, width from the prior. Median
residual 24 px on a 270 px body. No still stretch, so the angles are
relative to the robot's standing pose. Two candidates: 0-108 (`other`,
turns 58 deg left, all four legs tracked) and 156-225. The preview's trunk
turns 0 -> 58 deg. 57 % of frames are `ambiguous`, nearly all one hind or
fore leg whose second basin fits within the noise (24 px). The peak joint
speeds of the preview (up to 870 deg/s) include frame-to-frame tracker
noise.

*Checked* (`tests/test_lift.py`, 9 tests, one slow): synthetic footage of
the robot's own forward kinematics, both sides, seen from yaw 0, 30, 45 and
60 deg at 10 deg elevation, with 8 deg ab/adduction, a 35 deg turn, a calf
1.15 x longer, 1.2 x wider, with 0.9 x front legs, 1 px noise and 5 % of
points dropped. On reliable frames: sagittal joints within 2.5 deg RMS, hip
ab/adduction within 2.5 deg, heading within 1.5 deg, elevation within 1.5
deg, ratios within 3 %; every frame more than 75 deg from a side view is
unreliable. A level side view reports ab/adduction unobservable and uses
the width prior. Labels swapped by the tracker are recovered as the depth
flip. A video through the inbox in 3D (CSV tracker): no "too oblique",
candidates with reliability, a preview with the turn and ab/adduction in
the body report. 2D on the real video: map, side, view verdict,
segmentation and candidates identical to the record made before this
change.

*Not done.*
* Full perspective, camera motion (pan, zoom: they read as turning and
  approaching), several animals.
* The simulator does not steer: the turn is in the clip and the preview;
  playing it in physics needs a controller that follows `root_quat`.
* No learned 2D-to-3D lifter or mesh-based quadruped model (none was
  needed to meet the synthetic tolerances; on real footage the residual,
  14 to 22 px, is dominated by tracker noise and the robot's own skeleton
  differing from a calf's, which a better lifter would not remove).
* Head, neck and tail motion (the robot has no joints there).
* Speed: about 0.23 s per frame on this laptop's CPU (90 real frames in
  21 s; the 225-frame video took about 2 min while the test suite ran
  beside it).

## ADR-081 — A review player that plays: frames from an open reader and a cache

*Reported 2026-11-03.* Play in the Review asked for a new frame every ~33 to
40 ms, but serving one frame of the 1780 x 990 H.264 video took 300 to 500
ms: OpenCV reopened the file and seeked for every request. Each request
cancelled the last and the image never left the first frame.

*Decision.*
* **Server** (`FrameCache` in `calflab.app.footage`, one per lab): one
  reader kept open per video (at most two), the last 600 encoded frames
  kept, keyed by path, modification time, size, frame and width. A request
  starts a read-ahead thread that decodes the next 45 frames in order
  (sequential decoding is fast; seeking is what was slow). Opening a
  candidate in the review prefetches its range
  (`POST /api/footage/<file>/prefetch`).
* **Browser**: Play follows the clock but asks for a new frame only once
  the shown one has loaded; frames that are late are dropped, never
  queued. The tracked points are drawn for the frame actually shown.

*Checked.* `tests/test_lift.py::test_frames_come_from_an_open_reader_and_a_cache`
(cache hit, read-ahead), and Play on the real video in the lab's browser
pane.

## ADR-082 — The hind Knee at the hock, maps compared side by side, and clip smoothing (**VERIFY**)

*Requested 2026-11-03* (session X): "Make a project map from ap10k_3d with
the Knee at the hock and the hock untied from the stifle, re-analyse my
video, and show me side by side (old map / new map): the residual per
landmark, the hind angles, and how often frames are ambiguous. Then add a
clip smoothing setting (in the core, recorded in each clip's provenance) so
the body report's peak speeds reflect the calf rather than tracker noise ...
Do not change the belts."

*Decision.*
* **Project map** `projects/robot-calf-final/motions/maps/ap10k_3d_hock.yaml`
  (projects are not in git; the map is reproduced in
  `tests/test_smoothing.py::_hock_map`): `ap10k_3d` with `{S}_Knee` at the
  origin of `leg.h{s}.cannon` (the hock) and no ties. The Knee sits exactly
  at the hock, not fitted (`ap10k_3d` had fitted it 0.96 of the way from
  stifle to hock). Everything else unchanged: Elbow = carpus, Hip and
  Shoulder fitted along the femur and upper leg. The project's settings use
  it (`map_3d: ap10k_3d_hock`); `config/retarget/ap10k_3d.yaml` is unchanged
  and still the default for new projects.
* **Lifts kept per map**: `footage/lift/<sha16>.<map>.json` beside the
  current `<sha16>.json` (the last lift with each map). `inbox.lift_maps`,
  `load_lift(..., map_name)`. The `ap10k_3d` lift of the first video, made
  before this, was copied to that name by hand.
* **Side by side**: `calflab.behave.lift.compare_lifts` and the command
  `compare_lift_maps` (no UI beyond the command line): per map the reliable,
  ambiguous and unreliable shares, what made frames ambiguous, proportions
  and fitted landmark places; the median residual per landmark (same tracks,
  so the same points); the hind angles over the frames every map calls
  reliable, and the RMS of hock minus stifle.
* **Clip smoothing** (`calflab.behave.smoothing`, `FootageSettings.smoothing`,
  `set_footage_settings clip_smoothing=auto|lowpass|none
  clip_smoothing_hz=<Hz>`):
  * a Butterworth low-pass, order 2, forward and backward (zero lag), with
    Winter's correction for two passes;
  * applied to the whole video's joint angles and root (path, orientation,
    heading/pitch/roll of a lift) before a candidate is cut, in 2D and 3D;
  * the smoothed angles are kept within the range the raw angles covered
    over the video. Without that, ringing at the stifle's -30 deg limit made
    both candidates "clamped", which the raw lift never was;
  * `auto` (default for new projects): Winter's residual analysis on all
    joints pooled. Cutoffs from 1 Hz in 0.5 Hz steps up to 95 % of Nyquist
    after correction (11.4 Hz at 30 fps). A straight line through the top
    40 % of that band gives the noise RMS at 0 Hz; the cutoff is the lowest
    whose residual is down to it;
  * `lowpass`: a fixed cutoff (default 6 Hz, the walking-kinematics
    convention: PROVISIONAL); `none`: as before;
  * every clip records `meta.smoothing`: the setting, whether it applied,
    the cutoff (and for `auto` the noise RMS and residual curve), and each
    joint's peak speed raw and smoothed. `preview_candidate` returns it too;
  * settings saved before this load as `none`, so every other project cuts
    clips as before; accepted clips are never changed. Segmentation, the
    lift itself and CSV imports (ADR-073, their own 3-frame average) are not
    smoothed by it.
* `projects/robot-calf-final` set to `auto` with the researcher's request as
  the reason (the request asked for smoothing; the method is my choice).

*Results on the first video* (`Recording 2026-11-03 111941.mp4`, 225
frames, 30.19 fps; re-analysed in the researcher's running lab):

| | ap10k_3d (tied) | ap10k_3d_hock (untied) |
|---|---|---|
| reliable | 74.7 % | 81.8 % |
| ambiguous | 57.3 % | 70.7 % |
| ambiguous by a hind leg (L / R) | 34 / 21 % | 52 / 56 % |
| ambiguous by a fore leg (L / R) | 21 / 22 % | 14 / 25 % |
| depth (toward/away) | 3.1 % | 3.1 % |
| median residual | 24.2 px | 19.4 px (body 274 px) |
| hind paw residual L / R | 29.4 / 22.3 px | 13.1 / 12.1 px |
| Knee residual L / R | 19.6 / 16.2 px | 19.6 / 12.6 px |
| other landmarks | | the same or up to 3.2 px lower |
| trunk / front leg ratio | 1.56 / 1.12 | 1.47 / 1.00 |
| Hip / Shoulder fitted at | 0.60 / 0.42 | 0.67 / 0.36 |
| hind L stifle / hock, mean +/- sd | 6.5 +/- 18.5 (tied) | 4.1 +/- 19.7 / 9.3 +/- 10.0 |
| hind R stifle / hock | -1.1 +/- 14.1 (tied) | -2.7 +/- 13.9 / 12.7 +/- 13.2 |
| hock - stifle RMS L / R | 0 | 22.9 / 24.9 deg |

(168 frames reliable under both maps; angles in deg from standing.) In both
the stifle reaches its -30 deg limit (5th percentile -30). The hock now
carries its own motion and the hind paw fits twice as well, but more frames
are ambiguous: with the hock free, the hind leg's swing seen at a slant
often has a second bend that fits within the noise. The candidates became
0-109 and 140-225 (were 0-108 and 156-225).

Playable speed (the body report's, `clip_report`) on the same frames:

| map, smoothing (cutoff) | 0-109 | 140-225 (156-225 for the tied map) |
|---|---|---|
| tied, none | 0.29 (left stifle) | 0.17 (left carpus) |
| tied, auto (4.0 Hz) | 0.40 | 0.29 |
| untied, none | 0.16 (left stifle) | 0.14 (left carpus) |
| untied, lowpass 6 Hz | 0.26 | 0.20 |
| untied, auto (3.5 Hz, noise 1.8 deg) | **0.39** (left stifle 351 deg/s) | **0.28** (left carpus 489 deg/s) |

Peak speeds that remain are mostly single-frame jumps of 15-30 deg on
frames marked ambiguous (the fit moving between a leg's two bends; **wrong:
ADR-083 found them to be the screen recording's repeated frames, the
bends unchanged over the window**) and, in
the second candidate, the carpus folding about 80 deg in 0.2 s at the ball,
bridged across unreliable frames. Smoothing cannot remove a jump; a median
filter before the low-pass (3 to 7 frames) raised the playable speeds by
0 to 0.06.

*Assumptions (VERIFY):* the Knee exactly at the hock; Winter's method as the
default with all joints pooled into one cutoff per video; no new extremes;
6 Hz for `lowpass`.

*Checked.* `tests/test_smoothing.py` (4): a 1 Hz + 3 Hz swing with 2 deg of
jitter (auto keeps the harmonic, finds the noise level, peak speed back
within 30 %, no lag, no new extremes; fixed, none and out-of-band
cutoffs); synthetic footage whose hock and stifle move differently, lifted
with both maps (untied within 3 deg RMS; tied hock = stifle; the hind paw
residual lower untied); lifts kept per map. `tests/test_lift.py`: new
projects default to `auto`, older settings to `none`; a clip's provenance
through the inbox; the settings command and view.

*Not done.*
* The limb-flip jumps themselves: a stronger continuity term for legs
  marked ambiguous, or choosing between basins over a window rather than
  frame by frame, would remove what smoothing cannot.
* No panel for the comparison (command line and JSON).
* `ap10k_3d_hock` is not offered as a built-in map for new projects.

## ADR-083 — Each leg's bend chosen over the window; frames the recording repeated (**VERIFY**)

*Requested 2026-11-03* (session X2): "with the map ap10k_3d_hock, 71 % of
frames are ambiguous and the remaining peak speeds are mostly the fit
jumping between a leg's two bends. Make the lift choose each leg's bend over
a window (both basins kept per frame, a Viterbi on fit and continuity, as the
depth flip already does) instead of frame by frame, and show me side by side
(before / after) on my video ... Check it on synthetic footage with a known
bend. Do not change the belts."

*Decision 1: the bend over the window* (`LiftSettings.bend_choice`,
`calflab.behave.lift._choose_bends`, `_chain`).
* After the smoothing over time (C2), per leg and frame (two confident
  landmarks of the leg): the fitted angles and up to `max_bends - 1` (3 - 1)
  other bends: local minima of the leg's grid more than `bend_far_deg` (20)
  from the fitted angles and from each other, refined by least squares on
  that leg's joints (trunk and other legs held), kept if within 25
  chi-square of the fitted one. Each is scored by its fit and its priors
  (chi-square).
* A Viterbi over the frames adds continuity: a step between two kept frames
  costs ((change) / (joint speed sd x frames apart))^2 per joint, the same
  300 deg/s (60 for ab/adduction) as the smoothing over time. Forward and
  backward passes give each frame's **margin**: how much more the best path
  forced through any other bend costs. The best path is applied, frames
  between kept ones follow it, and C2 runs again from there.
* A leg is `ambiguous` where its margin is under `bend_margin` (4
  chi-square, the frame-by-frame test's own 4 units). The frame-alone test
  is kept as `second_bend` and in the summary (`legs.<leg>`:
  `ambiguous_fraction`, `second_bend_fraction` from the refined search,
  `grid_second_bend_fraction` from the old grid test, `bend_changed_frames`);
  per-frame margins are `bend_margin` in the lift (999 = no other bend).
* `frame` is the earlier behaviour exactly: on the first video, frame by
  frame with the new code reproduced the stored lift (70.7 % ambiguous,
  81.8 % reliable, 19.41 px).
* Lifts are kept as `<map>` (frame by frame, as before) and `<map>.window`.
  `compare_lift_maps` now also gives per leg the ambiguous share, the
  second-bend share and the **jumps** (steps between reliable frames moving
  one of its joints more than `jump_deg`, 12), and the **playable speed** of
  the candidates (or `ranges`) raw, smoothed, and smoothed and re-timed.
* New projects choose over the window. Settings saved before this load as
  `frame`; `projects/robot-calf-final` was set to `window` (the request).

*What the first video shows* (`Recording 2026-11-03 111941.mp4`, map
`ap10k_3d_hock`, lifted on a scratch copy of the project through the lab's
own commands; the researcher's running lab has the old code):
* **The window changed no bend on any frame**, and calls no leg ambiguous.
  The old 71 % was mostly the frame test's coarse grid. Of 52 sampled
  "second bends", 5 survive refinement; the rest slide back into the fitted
  bend (within 2-13 deg). The grid had put hip ab/adduction at +-25 deg with
  no prior on it. The few real second bends lose by at least 10 chi-square
  once continuity counts (5th percentile of the margins: 10.6 to 16).
* **The jumps are not bend flips.** They are 2-3 frame ramps that stay where
  they land, with the whole trunk moving 33-54 px in that step (median 6.5).
  **108 of the 225 frames are repeats** of the previous image (mean grey
  difference 0.0-0.4 against a median of 15). The screen recording holds
  the source at about 15 fps in a 30 fps file, so each movement is a single
  step at twice its speed. ADR-082's "jumps between a leg's two bends" was
  wrong.

*Decision 2: frames the recording repeated* (not asked for; the cause found
while doing the above). `calflab.behave.timing`, `FootageSettings.repeated`,
`set_footage_settings repeated_frames=interpolate|keep`.
* Found from the images when a video is analysed: a frame differing from
  the previous by less than 0.15 x the video's 90th-percentile difference
  (grey levels, on a 320 px copy) is a repeat. Not the median: with half the
  steps repeated, the median is one of them. Runs longer than 3 are a still
  scene or a frozen recording and are not counted. Recorded in the lift
  (`repeated`, `summary.repeated_fraction`).
* `interpolate`: clips (and the segmentation's angles) re-timed across
  repeats, a value at a repeat interpolated between the frames around it.
  Each new image is taken to show the animal at the time it first appears.
  The fit itself is unchanged. Clips record `meta.repeated_frames`. `keep`:
  every frame as it is.
* New projects interpolate; settings saved before load as `keep`;
  `robot-calf-final` was set to `interpolate` (my choice, reversible).

*Before / after on the first video* (two candidates, unchanged at 0-109 and
140-225; auto smoothing; playable speed is the body report's):

| | before: frame by frame | after: window | after: window, re-timed |
|---|---|---|---|
| ambiguous, any reason | 70.7 % | 2.2 % (depth only) | 2.2 % |
| ambiguous hind L / R | 52 / 56 % | 0 / 0 % | 0 / 0 % |
| ambiguous fore L / R | 14 / 25 % | 0 / 0 % | 0 / 0 % |
| second bend in one frame, hind L / R, fore L / R | 52 / 56, 14 / 25 % (grid) | 10 / 8, 7 / 7 % (refined) | the same |
| jumps > 12 deg/frame, hind L / R, fore L / R | 20 / 6, 20 / 15 | the same | 15 / 1, 14 / 4 |
| largest step, hind L / fore R | 31.8 / 30.8 deg | the same | 24.9 / 17.6 deg |
| median residual; per landmark | 19.4 px | identical | identical |
| 0-109, raw / auto | 0.16 / 0.39 (left stifle 351 deg/s) | the same | 0.22 / 0.36 (377 deg/s, cutoff 4.0 Hz) |
| 140-225, raw / auto | 0.14 / 0.28 (left carpus 489 deg/s) | the same | 0.14 / 0.28 (487 deg/s) |

* With re-timing, Winter's analysis finds less noise (1.3 vs 1.8 deg) and
  picks 4.0 Hz instead of 3.5. Part of what it had called noise was the
  stutter. At equal cutoffs re-timing raises the playable speed everywhere:
  3.5 Hz 0.385 -> 0.387 and 0.276 -> 0.301; 6 Hz 0.26 -> 0.30 and
  0.20 -> 0.22.
* What still limits the candidates is fast motion as the fit sees it: the
  left stifle swinging about 30 deg between two new images in the first,
  and the left carpus folding at the ball in the second. Whether that is the
  calf or the tracker has to be judged on the frames.

*Checked.* `tests/test_bends.py`:
* the chain's path and margins against brute force;
* known-bend footage: the feral calf with fore carpi allowed to bend either
  way (test only: the robot's own ranges leave no second bend in a side
  view), the carpus point tracked weakly, so one frame cannot tell the bends
  (frame by frame 58-100 % ambiguous):
  * frames put in the other bend (one frame, and a stretch of four) are put
    back, and nothing else changes;
  * end to end, with the first half second misleading: the true bend on
    every frame, none ambiguous, no jump (slow test). Frame by frame also
    holds it there, from its straight-leg start; in no synthetic case tried
    did frame by frame end in the wrong bend;
* repeats found in an AVI (twice, once three times, a still run kept); a
  stuttered joint re-timed to even steps;
* in `test_lift.py` and `test_smoothing.py`: defaults old and new, lifts
  kept per bend choice, the comparison with ranges through the inbox.

*Assumptions (VERIFY):* `bend_margin` 4, `bend_far_deg` 20, 3 bends, 25
chi-square; the continuity cost uses the smoothing's speeds; repeats below
0.15 x the 90th percentile, runs of up to 3; a repeated image shows the
earlier time. A very slow movement can pass for a repeat (interpolating it
changes almost nothing).

*Not done.*
* The fit itself does not use the repeats (its smoothing over time sees the
  stutter).
* 2D mode is not re-timed.
* No panel for the comparison (command line and JSON).
* Frames where a candidate's limiting joint peaks are not marked in the
  Review.

## ADR-084 — Clips judged in physics: a torque-speed servo, shared limits, feasible versions (**VERIFY**)

*Requested 2026-11-03.* Judge footage clips on the hardware's physical limits, not only joint ranges; get the
researcher's two candidates (`Recording 2026-11-03 111941.mp4` c1 = frames 0-109, c2 = 140-225) feasible within
every limit at margin 0.2; expose it as jobs, runs and a Behave panel view. Belts, joint ranges and component
values not changed.

*Decision 1: the servo and the limits* (commit 3fafd3c).
* `CompileOptions.servo_model`: `torque` (default) or `torque_speed`: before every physics step each actuator's
  force range follows `calflab.sim.servo.available_torque`. Stall torque falls linearly to 0 at the library's
  no-load speed when driving; braking is allowed up to stall. Only `stall_torque_nm` and `no_load_speed_rpm` are
  used. An unloaded shoulder step reaches 620 deg/s without it, 258 deg/s against 270 with it.
* **The `torque` model is unchanged bit for bit**: rollouts of the reference calf (CPG) and the feral calf (its
  own controller) hash the same as at b538a0e, before this ADR.
* `calflab.mech.limits`: envelope use per frame (|tau|/stall + |omega|/no-load when driving). Battery current is
  known only with a stall current; otherwise it is a lower bound = mechanical power / 12 V.
* `SafetyPolicy.margin` (every limit x (1 - margin); 0 = as before), constraints `envelope` (penalise) and `fall`
  (report). Preset `repertoire` v2 and the composition study compile with `torque_speed`.

*Decision 2: playing a clip in physics* (`calflab.behave.physics`). The behaviors controller plays the clip once:
1 s lead-in, the clip, 1 s return, 0.5 s standing. Derating 1, torque-speed servos, nothing random. The report
holds:
* per-joint tracking, torque against rated and stall, speed, envelope and belt tension, judged up to a fall
  (the per-joint table now stops at the fall like the constraints; what a falling body does is not the clip's);
* hooves: share on the ground, against the plan when planted;
* battery, fall, the constraint table, a 240-column strip with replay frames and video frames, and events.

*Decision 3: planting* (`calflab.behave.stance.plant`). What changed in this session, and why:
* **The solver did not meet its own goals.** Joints held to 1 deg against hooves to 1 mm let the clip's angles win:
  the centre of mass stayed outside the shrunk polygon in 47 % (c1) and 39 % (c2) of frames, and supporting hooves
  slid up to 32 mm. The weights are now 5 deg and 0.2 mm. On c1 that gives 0 % outside and hooves within 1.3 mm.
* **The lead-in dragged the hooves.** Blending angles from standing into the first pose (whose hooves had been
  anchored elsewhere) left c2 on one or two hooves before the clip began. Now the first frame's supporting hooves
  are anchored where the body stands. `plant` solves a planted way in (standing to the first pose) and a planted
  way back (`meta.stance_paths`, 20 poses each), and the physics playback follows them. The hold keeps the way
  back's last pose. Clips without these paths play exactly as before.
* `StanceSettings.range_margin_deg`: the solved angles stay inside the adaptation's range margin.
* `plant` also returns the solved trunk pose per frame (`trunk_pose`, not stored in clips) and the support per
  frame.

*Decision 4: the search* (`calflab.behave.adapt`).
* Operations are applied in the order amplitude, low-pass, range margin, **plant**, time scale. Planting is cached
  on everything but the time scale.
* `AdaptSettings.plant` (on), `min_support` 3 and `stability_margin_mm` 15 (PROVISIONAL) set the kinematic start.
* Fall remedies: **keep four hooves down**, **a larger stability margin (+10 mm)**, then smaller, slower and
  smoother.
* When no remedy aimed at the worst limit lowers the excess, the round also tries the broad ones (slower,
  smoother, smaller overall).
* The give-back tries faster, larger overall, and **larger at each joint pair** (/0.8).
* Fixed: the "no remedy" step had no `operations` key.

*Why the candidates fell, once planted and slowed* (diagnosed on the scratch copy before adding remedies, from
contacts, the centre of mass against the contact polygon, hoof slip and tracking per frame):
* With three hooves planned down, physics stood on fewer than three in 79-81 % of the clip, mostly diagonal
  pairs.
* The cause is the body's compliance against a tripod's margin. The position servos reach full torque at 10 deg
  of error (`servo_saturation_deg`); under the loads of a three-legged pose they sag 2-13 deg (fl.shoulder up to
  34 deg peak in c1, at stall). That is 4 mm or more per degree at the hoof, more than the 15 mm (or 35 mm)
  balance margin of a calf-width tripod.
* A larger stability margin did not help (c1 still falls at 4.5-5.2 s whatever the margin). Four hooves down did:
  no fall at 2x, 3x or 4x slower, for either candidate.
* **Correction (later the same day): this is about slowed clips, not the body.** An earlier wording said three
  hooves down cannot hold on this robot. That is wrong. The robot's own gaits balance dynamically, by timing, and
  spend most of their time on two or three hooves without falling (10 s, seed 0, scratch copy;
  `tests/test_physics.py::test_own_gaits_stand_under_both_servo_models`):

  | motion | servo model | falls? | speed | time on fewer than 3 hooves | over a limit at margin 0.2 |
  |---|---|---|---|---|---|
  | trot | torque | no | 0.30 m/s | 71 % | sustained torque, sustained belt, joint speed, envelope |
  | trot | torque-speed | no | 0.30 m/s | 74 % | joint speed, envelope |
  | walk | torque | no | 0.026 m/s | 58 % | sustained torque, joint speed, envelope |
  | walk | torque-speed | no | 0.025 m/s | 57 % | sustained torque, joint speed, envelope |

  What fails is a calf clip slowed 3-4x until it must balance statically: each three-legged moment then lasts long
  enough for the sag to tip a narrow tripod. "Four hooves down" is the remedy this search found for slowed clips,
  not a limit of the body. Keeping a clip's timing so the body balances dynamically, as the gaits do, is an
  alternative not yet tried. Also new: judged with margin 0.2 for the first time, both gaits go over joint speed
  and the envelope, and the walk also over sustained torque; they still do not fall.
* What then limited them was sustained hip ab/ad torque (above 48 % of rated in 85 % of a window) and sustained
  belt tension. Shrinking the hip ab/ad alone did not lower it, because planted angles follow the hooves more
  than the clip, so the search shrank everything.

*Results* (scratch copy `projects/_scratch-physics`, through the lab's own commands; margin 0.2; 1.304 kg as
entered; runs `20261104-014201-adapt-7fbe` (c1) and `20261104-014938-adapt-e9f7` (c2)):

| | c1 raw | c1 feasible | c2 raw | c2 feasible |
|---|---|---|---|---|
| verdict | falls at 2.36 s | within limits | falls at 1.52 s | within limits |
| first over a limit | fr.carpus at its limit, 0.74 s (lead-in); hl.stifle at 94 % of stall | nothing | fl.shoulder on its envelope, 0.30 s | nothing |
| operations | | 3.17x slower; amplitude 0.33 (hips/stifles 0.41); low-pass 2.2 Hz; 2 deg inside; planted, 4 down | | 3.64x slower; amplitude 0.51 (fore carpi 1.0); 2 deg inside; planted, 4 down |
| tracking RMS | 8.4 deg | 0.6 deg | 17.8 deg | 0.8 deg |
| smallest margin | | 0.32 | | 0.08 (belt sustained 0.23 / 0.25) |
| busiest servo | hl.stifle: envelope 100 %, 94 % stall | hl.stifle: envelope 40 %, 12 % stall | hl.stifle: envelope 100 % | fl.carpus: envelope 41 %, 11 % stall |
| duration | 3.6 s | 11.4 s | 2.8 s | 10.2 s |
| character kept | 1 | 0.19 | 1 | 0.24 |
| quantity of motion / range / rhythm / shape | | 7 % / 32 % / 13 % / 47 % (13 deg RMS) | | 11 % / 35 % / 24 % / 35 % (15 deg RMS) |
| plays, time | | 55, 7.7 min | | 39, 4.3 min |

**How much character the feasible versions keep: little.** They are quasi-static sways on four planted hooves.
The hooves never leave the ground (on the ground 96-100 % of the clip), at a third to a half of the amplitude and
3-4x slower. What survives is the shape of the trunk's movement, at about 13-15 deg RMS from the raw angles, and
some of its range. Steps, the swing of a leg and the tempo do not survive. Battery: at most about 1 W mechanical,
at least 0.09 A (a lower bound).

*Armature (`armature_scale` 0.2).* The servo's armature is the library default 0.005 kg*m^2 (not on its
datasheet), x4 behind the 2:1 belts.
* Raw: c1 falls at 2.30 s (was 2.36), c2 at 1.54 s (was 1.52); the same first limits.
* The versions found at 1.0, judged at 0.2: c1 stays within limits (margin 0.32 -> 0.44); **c2 goes over sustained
  belt tension (margin 0.08 -> -0.12)**.
* A new search at 0.2 finds versions of the same kind: c1 3.17x, amplitude 0.33-0.51, character 0.22; c2 4.00x,
  amplitude 0.51-0.64, character 0.24.
* So the falls and the kind of remedy do not rest on the armature; c2's exact feasibility does.

*What these results rest on* (each run records it under `basis`):
* the masses as entered, with 14 parts at 0 g (blocks, electronics, skin, plugs, bearings, horns, pads,
  pulleys, belts, springs);
* the STS3215 C018 entry: unverified, no stall current (hence the current lower bound), default armature;
* 62 PROVISIONAL values, among them the joint ranges (the stifle's -30 deg decides when it sits at its limit)
  and the springs (rate, free length, anchors), which carry part of the standing load.

*Exposed.*
* Commands `play_in_physics` and `adapt_clip` (a library clip, or `file`, `candidate`, `start`, `end`,
  `far_side`, `margin`, partial settings), `keep_adapted_clip run=` and `physics_report run=` (or `clip=` /
  `file= candidate=` to list runs). Module `calflab.app.physics_jobs`; commands in
  `calflab.app.physics_commands`, registered like `footage_commands`.
* Runs `physics` (`physics.json`, rollout, scene) and `adapt` (`adapt.json` with both reports, the steps, the
  operations, the comparison and the stance; `adapted_clip.json`; the adapted rollout). The as-retargeted play is
  a child `physics` run, so both replay.
* Provenance: the clip's footage provenance, settings, compile settings, the controller, genome, overrides and
  `basis`; the registry adds the git hash and versions.
* An adapted library clip is saved as `<id>-feasible` (`meta.adapted_from`, operations, margin, stance). The
  original is never changed. A candidate's version stays in the run until `keep_adapted_clip`.
* Behave panel: *Play in physics* and *Make feasible* beside *Preview on robot* and on each clip row. The panel
  renders the stored report only.

*Checked.*
* `tests/test_physics.py`:
  * the envelope at rest and at no-load;
  * the shoulder held to its no-load speed by `torque_speed` and not by `torque`;
  * default = explicit `torque`, bit for bit;
  * the margin scaling every limit in `safety_report`;
  * `plant` on synthetic poses: supporting hooves within 3 mm, the centre of mass inside the polygon, checked
    with the body's kinematics from the solved trunk;
  * a one-round and (slow) a full adaptation;
  * the order of operations;
  * (slow) the jobs, runs, new clip and untouched original.
* `web/e2e/physics.spec.ts`.

*Assumptions (VERIFY):*
* stance weights 5 deg / 0.2 mm, 20 transition poses, lift 15 mm (PROVISIONAL), stability margin 15 mm
  (PROVISIONAL), 3 hooves first;
* braking up to stall;
* "character kept" as defined in `adapt` (not a measure of feeling);
* the greedy search, which is not an optimum: c1's version with the broad fallback kept 0.19, the run without it
  0.20.

*Not done.*
* Moving contact phases in time, or letting a slowed clip step to new places (four hooves down means no steps);
* a trajectory optimisation;
* hoof limits (none in the library);
* sensitivity sweeps as a command (armature, mass, springs were run by script);
* using the feasible clips in the behaviors or the repertoire evolution (they are ordinary clips, so they can be
  added by hand).

## ADR-085 — Interpreting a calf's movement as the robot's own: reading, primitives, interpretation (**VERIFY**)

*Requested 2026-11-03 (session Q).* Between the video and the robot, an interpretation, not a copy: read what the
calf does, then say it in movements this body balances by itself, every step explicit, recorded and in the core.
Belts, joint ranges and component values not changed; `adapt_clip` kept as a diagnostic.

*The footage first (decision 1).*
* **214239: the "exchange" was the lift choosing the mirror, and the tracker's labels flipping early on.** The
  calf stands in a front quarter view facing the camera (both eyes and the nose plainly visible). In such a view
  both sides are seen, so the side-confidence cue of ADR-080 is unreliable, and it chose the turned-away mirror
  for 61 % of frames (yaw -30). Frames 0-~100 also have the tracker's leg labels opposite to its eye labels (the
  legs labelled as if the calf faced away). New: a lift map may name `face` landmarks (`[L_Eye, R_Eye]` in
  `ap10k_3d` and the project's `ap10k_3d_hock`); where all are tracked at 0.6 or more, the hypothesis turned
  toward the camera is favoured, by `face_gain` (1.0) x how far the body is turned beyond `face_min_yaw_deg`
  (20, a calf turns its head on its own). After: median yaw +30.5 (toward), frames 120-310 as tracked, 0-~100 as
  the tracker's labels exchanged (18 %), reliable 92 %, residual 12.2 px (unchanged). **111941 and 213333 lift
  bit for bit as before** (their faces are seen only near side views); 213904 unchanged. Re-analysed in the
  project through `reanalyse_video`: c2 65-310 now turns 36 deg right.
* **213625: unusable, with the reason.** A small dark calf (about 93 px long) bucks and runs toward, away from and
  around a hand-held camera that pans (frames 75-120), with motion blur and a second calf in view: 64 % of frames
  unreliable (fit residual, too few points, head-on/tail-on). Its "364 deg in 0.9 s" was a heading unwrapped
  through those frames: **general fix**: a turn is summed only across steps between reliable frames (the reading
  and the inbox's candidate `turn_deg`). The reading refuses videos under 60 % reliable or under 120 px long
  (`min_reliable`, `min_body_px`, PROVISIONAL) and lists why.
* **Not one calf.** The frames show at least four calves: a Jersey pushing a ball (111941), a dark red calf
  frolicking (213333, 213625), a Hereford cross running at the camera (213904), a tan calf standing (214239). The
  trunk ratios 1.46-1.55 do not make them one animal.
* **The camera moves** in 111941, 213333 and 213904 (hand-held, following): `calflab.behave.camera_motion`
  measures the ground's shift by phase correlation on a band around the hooves with the animal masked (2.2, 5.0,
  2.8 body lengths/s; 214239 0.05). There, the trunk's travel is not read; turns are (weak perspective does not
  mix a pan into heading).

*Decision 2: reading* (`calflab.behave.signals`, `calflab.behave.reading`, `calflab.app.reading_jobs`).
* One reader for the calf and the robot: signals are joint angles relative to standing, trunk heading, pitch,
  roll and path (at the robot's leg length), hoof heights, contact.
* **Contact from the paws, not from lifted hoof heights.** Hoof heights of the lifted skeleton drift by 70-90 mm
  while the paws stand still (214239 frames 24-60: the calf's proportions on the robot's skeleton). A hoof is in
  swing while its tracked paw moves over the ground faster than 0.5 body lengths/s (down under 0.3), its path
  low-passed at 4 Hz with the ground's shift taken out. From a rollout: a hoof carrying 1 N or less, chatter
  under 0.1 s ignored.
* Behaviours by explicit rules (`ReadingSettings`, all PROVISIONAL): stepping bouts split where the share of two
  hooves up or the turn rate changes; *other* (fast) over 40 % two up or 1.5 body lengths/s; *step* at most two
  lifts; *turn* at least 30 deg with under one body length per 90 deg; else *walk*; all hooves down: *weight
  shift* where joints (8 deg/s) or the trunk's tilt (4 deg/s) move, else *stand*; unreliable runs over 10 frames
  are gaps that break the chain. Each stretch keeps its rule, features and a confidence.
* Per behaviour: duration, tempo (stride period or activity repetition), phrasing (bursts, pauses), amplitude per
  joint group, quantity of motion, footfall order and pattern, duty factor, roll, pitch, heave, lateral sway,
  turn, lean, onset (abruptness), head motion (calf only).
* **Semi-Markov model**: transitions between consecutive stretches (no self-transitions), pooled with each
  video's counts kept, alpha 0.5; 90 % Beta intervals; log-normal durations, censored stretches (cut by an end or
  a gap) used only when nothing else is there; one stretch gets a spread of 0.5 (log), said so.
* Stored versioned (`schema_version` 1) in `footage/readings/<id>.json` with provenance (lift files, map, bend
  choice, settings, exclusions); affect tags of accepted clips overlapping a stretch are attached (none exist yet).
  `read_footage synthetic=[[behaviour, seconds], ...]` reads a known sequence posed on the robot (tests, trying).

*What the footage carries* (reading `20261103-230534`): 28.5 s in 5 videos, 4 usable, 21.1 s read. 8 stretches:
other (fast) 5 (11.6 s, 55 %: the three running calves and a hop of the tan calf), stand 2 (6.6 s, 31 %), step 1
(2.9 s, 14 %); no walk, turn or weight shift long enough. 2 transitions (stand -> other, step -> stand); the
others are cut by gaps and the videos' ends. **Enough to say which behaviours occur and their rough character; not enough for
transition probabilities (90 % intervals 0.66 wide), duration distributions, or individual calves.**

*Decision 3: the robot's vocabulary* (new plugin type `motion_primitive`, contract, `new-plugin` template).
A primitive has a few parameters (`Params`, `vector_dims` for the search), a controller that plays it, its period,
safe phases (every hoof down), the read behaviours it may stand for and why it balances. Built in: `stand`
(optionally crouched), `weight_shift` and `step` (poses solved with every hoof planted and the centre of mass
toward the tripod's centroid by `shift`; `calflab.behave.shift_design`, MuJoCo kinematics; 50 mm inside the
tripod at full shift, hooves within 0.25 mm; new controller `weight_shift`), `walk`, `turn` (feral_motion gets
`stride` and `turn`: per-side sweep factors; with 1 and 0 every earlier rollout is unchanged, tested), `trot`
(warm-up 1.5 s: its ramp is played, not judged) and `lie_rise`. **Turning in place: the body hardly allows it**
(stride 0, turn 1: 0.6 deg/s, over sustained torque, belts, speed and the envelope at margin 0.2).

*Decision 4: interpretation* (`calflab.behave.interpret`, `calflab.app.interpret_jobs`, command
`interpret_footage`). Per read behaviour, every primitive that may stand for it: its defaults, then a CMA-ES
(popsize 6, 3 generations; an even grid of 18 for one parameter). Each candidate is played in physics (torque-speed
servos, derating 1, as `play_in_physics`; at least 4 s after the warm-up, two of the 2 s sustained-load windows)
and read back by the same reader. Cost = weighted squared distance of features (log ratios for sizes and rates,
differences over a scale for signed ones) + 10 when it falls or goes over a limit; **within limits = no
violation and a margin of 0.05 beyond the 0.2** (a short play against a minute's performance; PROVISIONAL). The
record per feature: kept (0.8-1.25x), exaggerated, reduced, reversed, dropped, with why: the limits that stopped
closer candidates, a limit close by, or the primitive's range. Evaluations are cached per body on disk
(`.cache/interpret/<spec hash>`).

*Decision 5: performance* (controller `interpreted`). States = behaviours interpreted within limits; durations
drawn from the reading's log-normals (clipped to 0.5-2x what was seen); parameters varied only toward safety
(timing only slower, sizes only smaller, by the calf's own spread); switching only at a safe phase (at most 4 s
late, logged); cross-fade 0.6 s. A behaviour with no interpretation within limits is not performed. 60 s x three
seeds, judged with the physics report (tracking against the commands).

*Results on `projects/robot-calf-final`* (runs `20261104-042001-interpret-4d7f` (the search) and
`20261104-042426-interpret-ef3c` (the same, cached, with transitions played and stays continued); 1.304 kg as
entered; margin 0.2):

| read | as | margin | kept / changed, and why |
|---|---|---|---|
| stand (2, 6.6 s) | weight shift: hind left freed, shift 0.31, 1.5 s over, 1.4 s held | 0.84 | roll and pitch kept; motion (1.9 vs 3.0 deg/s) and heave reduced; amplitude exaggerated (3.7 vs 1.8 deg) |
| step (1, 2.9 s) | step: hind left freed, shift 0.54, 1.5 s over, 0.9 s held, lift 7.7 deg | 0.28 | step rate (0.5 vs 1.4 Hz), amplitude (7.6 vs 15.6 deg), motion and roll reduced: every closer candidate went over sustained servo torque (and most over joint speed and the envelope); 22 % of step candidates within limits, no walk |
| other / fast (5, 11.6 s) | trot: 0.92 s cycle, stride 0.58, lift 0.11 | 0.71 | turn kept; tempo slower (0.92 vs 0.66 s), two hooves up 68 vs 98 %, speed 46 vs 264 mm/s reduced; motion (6 vs 77 deg/s), amplitude (2.4 vs 31 deg), pitch (0.15 vs 19 deg) and heave (1 vs 78 mm) dropped: closer candidates over sustained torque, joint speed, the envelope, belts. 1 of 65 trot candidates within limits; lie/rise none |

* **Search budget matters**: with 6 x 3 the step and the trot had no candidate within limits; 8 x 8 found one each.
  The default is now 8 x 8.
* The gaits as they are, at margin 0.2: walk over sustained torque, sustained belt, joint speed and the envelope
  (margin -2.48); trot over sustained torque, sustained belt and the envelope (-1.2). **What interpretation does
  about that:** it slows the trot (0.92 s cycle), shortens and lowers its stride until it holds with 0.71 in hand,
  and says what that costs (the calf's vigour, pitch and heave dropped). No walk variant held at all.
* **Transitions** (new, decision 6): each primitive is judged from standing, but in a performance it starts from
  wherever the last left the hooves. Played in physics: stand -> fast 0.72, step -> stand 0.28, step -> fast 0.28
  pass; **stand -> step (-0.12), fast -> stand (-0.28) and fast -> step (-3.0) go over sustained shoulder torque**
  (the weight shift and the step are poses solved over the standing hooves; a trot leaves them spread). Those are
  dropped from the performance; a state with no way out carries on (not restarted).
* **Performance**: three seeds, 60 s, **within every limit (margins 0.74, 0.73, 0.32), no fall**, but once
  trotting nothing passes as a way out: the robot trots 95 % of the minute (calf: 55 % fast, 31 % stand, 14 %
  step). Read back by the same reader: 95 % fast. Before the transitions were checked it went 42 / 22 / 36 %
  stand / step / fast and over sustained torque in every seed (-3.0). **The vocabulary lacks a stop: a trot that
  ends on square hooves** (next sessions).
* Cost per body at 8 x 8: 392 evaluations, about 10 minutes of physics uncached (236 new plays took 351 s), 44 s
  when cached (transitions and three minutes of performance included). Inside a repertoire evolution that is a
  once-per-body step on a small budget, not per candidate of a large run.
* For comparison (ADR-084): Make feasible kept character 0.19 and 0.24 of the 111941 clips (scratch project).
* Gaps, never approximated: head and neck (the nose moves 2.0 body lengths/s against the shoulders in the fast
  stretches), tail, hind hip swing (femur fixed), front ab/adduction, spine, fetlock and pastern, airborne
  movement.

*Decision 6: transitions in physics* (`check_transitions`): every pair the performance may take is played (A for
its median duration, then B) and judged with the same limits and buffer; failing pairs are dropped and listed.

*Assumptions (VERIFY):* every threshold of `ReadingSettings`; paw speed as the stance cue; the face cue's gain
and dead zone; feature weights and scales (`MATCH`, `TARGETS`); kept = 0.8-1.25x; the 0.05 buffer; the variation
rule (only slower, only smaller); tempo kept 1:1 (no Froude scaling for the calf's size); the leg freed in a weight
shift from the calf's lean.

*Not done:* steering a walk along the calf's path; a step that moves a hoof to a new place; head motion of any
kind; using the interpretation inside the repertoire evolution; a per-body cost model.

## ADR-086 — Session R: a body for vigorous movement; step 1, what the failures rest on (**VERIFY**)

*Requested 2026-11-04 (session R).* Commitments: the ten STS3215 C018 servos and carbon fibre leg tubes; everything
else may change. Goal: walk, trot and the interpreted performance within every limit at margin 0.2. Six steps, with
a stop for the researcher after each. This ADR covers what was done before the first stop.

*Decision 1: the tube is entered with nothing filled in.* The request gives the tube as "`<outer diameter>` mm,
`<wall>` mm wall, `<g/m or "not weighed">`": placeholders, not values. `config/components/materials.yaml` gets
`carbon_fibre_leg_tube` (`calflab components new material`; `source:` says what was given; `verified: false`;
`density_g_cm3: null`, so the library lists it as incomplete and nothing uses it). Outer diameter, wall and
mass per metre are written as "not given" in its comment. The tube genes (15 x 12 mm everywhere) and
`tube_density` 1.55 g/cm3 stay as they were: PROVISIONAL. The servo entry is not touched.

*Decision 2: the sensitivity study is a script for now* (`docs/studies/sensitivity_r1.py`, results in
`docs/studies/sensitivity_r1.md`). It plays each motion exactly as the interpretation plays a candidate
(`play_primitive` + `judge`, torque-speed servos, derating 1, seed 0, margin 0.2) with one value changed in
memory. Making it a job and a panel is left to session P3: step 1 was asked for as results.

*Assumptions of the study (VERIFY):*
* **Mass x0.9-1.3 is a uniform scale on every geom** (and on a pushed solid's inertia). The missing parts (blocks,
  electronics, skin, horns, bearings, collars, plugs, pads, belts, neck rods) are partly on the trunk and partly
  on the legs, where they are is not known, so they are spread like the mass already there. A trunk-heavy
  distribution would load the hips and shoulders more than this.
* **The servo at another voltage is linear in voltage**: stall torque, rated torque and no-load speed x V / 12 V.
  Feetech gives the C018 only at 12 V (as entered). A DC motor's stall torque and speed scale roughly so; the
  real curve is the datasheet's or a measurement's, not this.
* **The battery voltage**: `config/feral_calf.yaml` has two 3S 2200 mAh packs. How they are connected is not
  entered. Two in series (22.2 V) would be far above the servo's 12 V, so **parallel is assumed**: 11.1 V
  nominal, 12.6 V full, about 10.5 V near empty. The servos then never see their 12 V figures except on a fresh
  charge.
* "Fails first" = the constraint with the lowest margin over the play (the binding one), not the earliest in time.

*Results (1304 g as entered; full tables in `docs/studies/sensitivity_r1.md`):*

| motion | baseline margin, binding limit | what moves it | does a value in range change the verdict? |
|---|---|---|---|
| walk | -2.48, sustained torque hr.hip_abd (above 48 % of rated for 87 % of a window); also stifle belt, fr.carpus speed (122 vs 108 deg/s), fl.carpus envelope (100 %) | rated torque x1.2 -2.24; armature x2 -1.72; mass hardly (-2.40..-2.52); stiffer springs make the belt worse (x1.5: belt -2.60) | **no**: over in every variant. The walk itself is the problem |
| trot | -1.2, sustained torque hr.hip_abd (55 %); stifle belt -0.96; hock envelope -0.01 | mass x1.1 -1.73 (belt); rated x1.2 -1.10; springs x0 -1.32, x3 -2.40 | **no**: over in every variant |
| interpreted trot (fast play) | +0.71, hock envelope (23 %) | mass x1.2 +0.24, x1.3 +0.04 (fr.shoulder sustained); rated x0.8 -0.16; 10.5 V +0.20; springs x1.5 -0.47 (stifle belt) | **yes**: rated torque 20 % lower, or springs 50 % stiffer |
| interpreted step | +0.28, hl.hock joint speed (79 vs 108 deg/s) | **mass x1.1 -0.12; 11.1 V -0.20; rated x0.9 -0.36** (all fr.shoulder sustained); springs x1.5 -1.48, x0 0.00 (stifle belt); armature x2 +0.17 | **yes**: 130 g more, or the servo's figures at 11.1 V, take it over |

What this says:
* **Armature decides nothing** (x0.2-2 keeps every verdict). It is not the first thing to measure.
* **The step's feasibility rests on missing numbers**: the servo's rated torque at the battery's real voltage, and
  the 14 missing masses (130 g, 10 %, is enough). With the electronics, skin and blocks still at 0 g, the step is
  likely out of reach once they are entered, unless the body changes.
* **The springs as they are fight the servos.** Rates above x1 load the stifle belts sharply; at x0 the walk's
  stifle belt is also over (-1.00) and the step's is at its limit. The rate is near a narrow sweet spot for the
  provisional free lengths and anchors: they are not set as gravity compensation. Step 2 looks at that.
* **The gaits as they are fail on the hip ab/ad servos' sustained torque**, which no unknown fixes: it is the
  lateral load of the stance (step 2).
* A lower voltage sometimes *helps* the walk (10.5 V: -2.08): slower servos follow less of the commanded motion,
  so they carry less. A margin does not say how much of the motion was kept.

*Missing numbers that decide a verdict (to measure, not filled in):* the STS3215 C018's rated and stall torque and
no-load speed at 11.1 V (or the curve against voltage); the two packs' connection; the masses of
`config/feral_calf.yaml` `placeholders` (electronics, skin, hip and chest blocks first: the largest); the tubes'
outer diameter, wall and g/m; the springs to be bought (rate, free length) once step 2 says what they should be.

## ADR-087 — Session R step 2: where the load goes, and which levers work (**VERIFY**)

*Requested 2026-11-04 (session R, step 2 of ADR-086).* Per joint, for the walk, the trot and the interpreted fast
play: where sustained torque and belt tension come from (static weight in stance against dynamics), what the
springs carry, and which levers can fix each failure. Scripts and full tables: `docs/studies/load_r2.py`,
`docs/studies/levers_r2.py`, `docs/studies/load_r2.md`. Nothing in the project, genes or library was changed.

*Decision 1: how load is split.* Each recorded frame is rebuilt in MuJoCo; the 3D hoof forces of that instant are
recorded during the play (a study-only hook on `mujoco.mj_kinematics` inside `run_rollout`) and **scaled to sum to
the body's weight**, keeping their directions and their share between hooves. Static = the joint torque that holds
the pose under gravity on those forces; the servo's static share = static minus the springs' torque; dynamics =
what the servo gave minus that share. Checked on quiet standing: within 0.02 N*m on every joint. Vertical-only
reactions (as `calflab.mech.statics` uses for standing) were tried first and **doubled the hip ab/ad's load**:
sideways friction at the hooves matters on splayed legs. Assumptions: the hooves' force directions are those of
the physics play; scaling keeps the static share's pattern but not what an impact would add.

*Decision 2: "springs as gravity compensation" = each spring's rate scaled so that at quiet standing it gives the
torque the weight needs* (stifle x0.55, hock x0.52, shoulder x0.27, free lengths and anchors unchanged). One pose
only; a spring can not be right in every pose of a gait.

*Results* (servo side; limits 0.47 N*m sustained torque, 0.34 N*m = 35.2 N sustained belt):
* **The walk and the trot fail on the weight, not on their dynamics.** The hip ab/ad's sustained torque is static:
  the weight alone would be above the limit for 92 % (walk) and 53-58 % (trot) of the worst window, against 87 % and
  54-55 % measured. The legs are splayed (hind 12, front 10.5 deg in this project): the hooves stand outside the
  ab/ad axes, so the weight twists those servos, and no spring is at the hip.
* **The walk does not walk as planned**: three hooves down at a time is the plan; physics stands on two for 73 % of
  it. Its sway (3 deg hind ab/ad) and the servos' compliance drop a second hoof.
* **The springs over-compensate**: at standing they give 181 % (stifle), 192 % (hock) and 365 % (shoulder) of what
  the weight needs, so the servos pull against them. In the walk's and the step's poses the shoulder needs the
  other sign and its spring adds to the load. The trot's stifle belt is weight + spring excess (+0.1) + dynamics
  (+0.1, RMS 0.35-0.37 N*m).
* The interpreted trot stays clear because it stands on four hooves 35 % of the time and moves little; its binding
  limit is the hock's envelope (dynamics).

*Levers* (played; margins):
* **Stance width (splay) is the strongest**: both splays 0 take the walk from -2.48 to -0.13 and the trot from
  -1.2 to -0.16. Hind and front must change together (hind alone to 0 makes everything worse).
* **Springs as gravity compensation** help the belts (walk belt -0.07 -> +0.28, trot -0.96 -> -0.70) and with
  splay 0 leave the trot over joint speed only (-0.04) and the walk over joint speed and a little torque (-0.13).
* **What is left is the gaits' speed** (carpus fold in the walk, hock in the trot): a gait parameter, for the
  per-candidate gait tuning of step 4. Walk sway 1.5 deg alone: -2.48 -> -1.12.
* **Belt reduction ratio: not available.** The pulley catalog has only 2:1 pairs (30T-60T, 36T-72T, 40T-80T), and
  the hip ab/ad and shoulder are direct drive. A slower, stronger joint needs pulley pairs the researcher adds to
  `catalog/pulleys.json`, and it costs joint speed, which is the next limit.
* **Leg angles and crouch: no.** Straighter legs (femur 30, tibia 25) are worse; more flexed ones (femur 50, tibia
  45) fail the hock belt check (rejected). The walk and trot have no crouch parameter. The front angle is solved
  by the lab for a level back, so it is not a lever.
* Trot roll feedback (0.5 -> 0.25 / 0) changes little.
* The interpreted parameters were found on today's body and break on most other bodies (e.g. both splays 0:
  -0.47): step 4 must re-interpret per body, as planned.

*Consequences for steps 3-4:* the splays are genes but `evolvable: false`; step 4 needs them evolvable (together
or with a bound on their difference), with the spring rates and free lengths, and the gait parameters tuned per
candidate.

## ADR-088 — Session R: the leg tube confirmed, the packs in parallel, joint stops, commercial pulleys (**VERIFY**)

*Context.* Before step 3 the researcher answered four questions (2026-11-04): "The leg tube is correct"; "The two
3s packs are wired in parallel"; they do not know what "real joint stops" means; the belt reduction may change
as long as it is easily available on the market; the legs should splay for stability.

*Decisions.*
* **Tube.** "Correct" is read as confirming the tube the lab already used: 15 mm OD, 12 mm ID (1.5 mm wall),
  1.55 g/cm3. `carbon_fibre_leg_tube` now has `density_g_cm3: 1.55` (still `verified: false`; not a weighed
  value, no g/m given), and the tube genes and `tube_density` lose their PROVISIONAL badge. If the reading is
  wrong, restore `density_g_cm3: null` and the badges.
* **Battery.** Two `lipo_3s_5000` packs in parallel: 11.1 V nominal, 12.6 V full. This is what step 1 assumed;
  the entry's values (one pack) are unchanged. The servo's figures at 11.1 V are still not entered, so the
  servo is judged at its 12 V figures (step 1: at 11.1 V scaled the interpreted step fails, -0.20).
* **Joint stops.** The robot is not built, so there are no measured stops. Step 4 keeps today's joint ranges as
  the outer bounds: evolution may narrow a range, never widen it. The STS3215 turns a full circle, so the stops
  of a built leg come from the printed parts, tubes and belts; they are to be measured on the first leg.
* **Pulleys.** GT2 2 mm pulleys are sold in many tooth counts, so pairs other than 2:1 are allowed in the catalog
  once each tooth count is found in stock for the belt width in use, with the listing as source. Masses stay
  null until weighed.

## ADR-089 — Wide hooves from wider blocks; hip ab/ad springs (**VERIFY**)

*Context.* The researcher wants the legs splayed for stability and chose "wide hips plus springs" (2026-11-04).
Step 2 found that splay puts the hooves outside the hip ab/ad axes, so the weight twists those servos, and no
spring is at the hip.

*Decisions.*
* **Two genes widen the blocks**: `hip_block_widen` and `chest_block_widen` (mm per side, 0-150, default and
  `absent` 0, PROVISIONAL, not evolvable yet). Each block is rail spacing + 2 x margin + 2 x widen, and its legs
  sit just outside it. The rails keep their spacing, and the batteries and the electronics stay where they were.
  Old genomes build exactly as before. The blocks' masses are not entered. If one is, widening keeps the entered
  value and the build warns that it is for the block as weighed. Assumption: a wider block is the same block
  made wider (its height, overhang and servo seats as before), and nothing new is needed to hold a leg further
  out.
* **Hip ab/ad springs** (`spring_hip_abd`, off by default and `absent` false): one tension spring per hind leg,
  from the hip block (forward of, inboard of and below the hip ab/ad axis) to the femur's axis line below the
  joint, like the adductor muscles. The weight pushes a splayed leg out (abduction), and the spring pulls it in.
  Rate, free length and the anchors (block: forward, inward, down; femur: along) are evolvable PROVISIONAL genes
  like the other springs. The defaults (0.2 N/mm, 30 mm, 32 / 40 / 38 mm, 50 mm) are a starting design, not a
  part. They make a horizontal spring about 40 mm long at standing. A spring sits on its joint like the others
  (`Spring.joint`), so the load reports and spring relief count it. The springs-off comparison of the load runs
  turns it off too.
* **Hoof width is the stability measure**, not the leg angle: the distance of the hooves from the centre line,
  standing. Step 3 will score it so evolution cannot buy margin by narrowing the base.

*Results* (`docs/studies/width_r2c.md`; physics, margin 0.2):
* Hooves at today's width with straight legs (blocks +120 / +105 mm per side) take the walk from -2.48 to -0.13.
  Every torque, belt and envelope limit passes, and only joint speed is left (a gait parameter).
* Half splay with half widening and hip springs is as good for the walk and both interpreted motions (walk -0.13,
  interpreted trot +0.73, step +0.28).
* Hip springs alone do not rescue full splay (walk -1.56).
* The trot as it is gets worse on wide blocks (-1.2 to -1.8). Its load moves into the stifles (x2) and
  shoulders (x3): on a diagonal pair, the wider the hooves, the farther the support line passes from the centre
  of mass, which sits ahead of or behind the middle of the body. The trot's parameters were set on the narrow
  body, and step 4 re-tunes them per body.
* Springs that just hold the weight at standing matter for the read motions (interpreted step on wide blocks
  -2.04 -> +0.28).

*Consequences for steps 3-4:* evolve `hip_block_widen`, `chest_block_widen`, both splays, `spring_hip_abd` on
with its rate and anchors, and the other springs, with the gaits tuned per candidate. Keep a floor on hoof width
(stability).

## ADR-090 — Session R step 3: the vigour preset, a body judged on a suite of motions (**VERIFY**)

*Context.* Step 3 asks for a fitness scored on the safety margins (sustained torque, sustained belt, joint speed,
envelope, stall, falls; three seeds; randomisation as in `repertoire`) plus how much of each behaviour is kept
(gait speed for walk and trot; the interpretation's feature distance for the read behaviours, small budget,
cached per body), with archive axes vigour kept x worst margin. The researcher let hoof width evolve freely
(2026-11-04: "Let it evolve"): there is no floor on it, only a `hoof_width` descriptor to look at.

*Decisions.*
* **A preset can score a suite of motions** instead of one controller: `evaluation.suite`
  (`calflab.evolve.vigour.SuiteSettings`). `evaluate_candidate` hands such a preset to `evaluate_body`. The
  MAP-Elites inner loop (iterations x popsize) becomes the per-motion search budget. Preset `vigour@1`: walk,
  trot, and the read behaviours stand, step and other (the fast play).
* **Kept share.** Gait: `min(1, speed / reference)`, where the reference is the gait at its defaults on the
  starting body (walk 32.8 mm/s, trot 186.1 mm/s on today's body). Read behaviour: the weighted mean of
  `exp(-d_k^2)` over the features the interpretation matches, with `d_k` as in its distance. Assumption: this
  stands for "the interpretation's feature distance" as a 0-1 share (1 = every feature as the calf, 2x off
  about 0.62). A read behaviour starts from the primitive and setting the interpretation chose on the starting
  body.
* **Search, then verify.** Each motion is searched on seed 0, nothing random, with every play cached per body in
  the project's `.cache/interpret`. Its best settings within the limits (up to `verify` = 3) are then played on
  the preset's seeds with friction and mass randomised. The first that stays within every limit on every seed
  without falling is kept: its kept share and margin are the worst seed's. A motion with none keeps 0. Stall
  and a belt peak are limits like the others (the motion fails), not a rejection of the whole body.
* **Margins** are those of session R: headroom over every limit lowered by 0.2, so 0 = at margin 0.2.
  Fitness = mean kept share - (how far the worst motion's margin is below 0, at most 1).
* **Simulate candidate** plays the walk as tuned for that body: the candidate's controller parameters are the
  walk's. Every motion's setting is in its metrics (`vigour.motions`).
* **Estimate cost** counts plays for a suite preset (upper bound: every search play uncached, every
  verification to the end) and times them with the usual probe.
* The splays and both block widths are evolvable. The hip ab/ad springs' switch is not (a bool): step 4 turns
  it on in the starting body and lets the rate evolve from 0.

*Results* (`docs/studies/vigour_r3.md`):
* Today's body: vigour 0.315, worst margin -0.44 (trot), fitness -0.125. Walk and trot keep nothing; stand
  0.87, step 0.34, fast play 0.36.
* Wide blocks + half splay + hip springs: vigour 0.517, worst -0.28, fitness +0.237. The walk keeps 0.75 within
  every limit on three seeds, and the step 0.59. The trot is still over sustained torque.
* About 55-60 plays and 64-84 s per body. 6 generations x 8 at 2 x 4: about 0.3 h on 7 workers (1.1 h CPU).

## ADR-091 — Session R step 4: the first evolution with the vigour preset (**VERIFY**)

*Context.* The researcher chose the budget: 6 generations x 8 bodies, per-motion search 2 x 4.

*Decisions.*
* The starting body is the project's, with the hip ab/ad springs switched on (`set_genes spring_hip_abd: true`,
  0.2 N/mm, free to evolve to 0). The fitness node is set to `vigour` (`set_node_params`). Both are undoable
  commands in the project's log.
* Every evolvable gene; belts unchanged; joint ranges unchanged (nothing to narrow without measured stops).
* Archive vigour_kept (10 cells) x worst_margin (8 cells), seed 0.

*Results* (`docs/studies/evolve_r4.md`, run `20261104-162051-evolve-d1b6`, 818 s):
* 48 candidates: 35 evaluated, 13 infeasible. Of these, 11 had front legs that cannot reach the ground with the
  back level and 2 failed the hock belt clearance. None failed to run, none was unsafe.
* Best: fitness +0.228, vigour 0.36, worst margin -0.13. Within limits on three seeds: trot, stand, step and
  fast play, but not the walk. Changes: axle spacing 590, femur 183, tibia 266, hind splay 8.4, stifle springs
  softened, shoulder and hip ab/ad springs to 0.
* No body keeps the walk within limits. The search stayed near the start (block widening at most 18 / 39 mm per
  side), so it never reached the wide-block bodies that do keep it (step 3's body E: vigour 0.517, walk 0.75
  within limits).

*Consequence.* A second run should start from body E, or from a spread wide enough to reach the block widths
`width_r2c.md` found.

## ADR-092 — The wide-block body is the working body; session R turns to behaviour diversity (**VERIFY**)

*Context.* After the first step 4 run (ADR-091) the researcher asked what another body run would add, and whether
the work was losing its focus on new, unprogrammed (sampled, surprising, reconfigured) behaviours. A second run
would mostly refine a body for five fixed motions. They chose (2026-11-04) to take the wide-block body as the
working body and redirect to an evolution of behaviour diversity on it. Steps 5-6 of session R (the stop
primitive, the proof on the best body) are set aside, not done.

*Decision.* `projects/robot-calf-final` now has body E of `docs/studies/width_r2c.md`, set with one undoable
`set_genes` (`docs/studies/body_r5.py`):
* hind / front splay 6 / 5.25 deg;
* hip / chest blocks widened 59.6 / 52.2 mm per side (blocks 259 / 244 mm wide);
* hip ab/ad springs on at 0.178 N/mm;
* stifle 0.197, hock 0.129 and shoulder 0.022 N/mm: rates that just hold the weight at standing.

Belts pass, the body is feasible, and the mass is unchanged (1304 g). The hooves stand where they did before
(203 / 185 mm from the centre line), and the standing height is 607 mm. Step 3 measured this body: vigour 0.517,
worst margin -0.28 (the trot). The walk, stand, step and fast play are within every limit at margin 0.2 on
three seeds.

## ADR-093 — Behaviour diversity on a fixed body: MAP-Elites over a behaviour generator (**VERIFY**)

*Context.* The researcher redirected session R from refining a body for five fixed motions to new, unprogrammed
behaviour: sampled, surprising and reconfigured (ADR-092). They accepted this proposal: the body stays fixed, a
behaviour generator evolves, the archive axes are movement features, every limit at margin 0.2 on three seeds
is required, and within a cell headroom and unpredictability are preferred. Calf-likeness is not scored.

*Decisions* (`calflab.evolve.diversity`, optimizer `map_elites_behaviour`, preset `diversity`):
* **Generator.** One vector in [0, 1]^53 decodes into an `interpreted` controller, a semi-Markov chain that
  switches only where every hoof is down.
  * **Palette:** stand, a weight shift and a step onto either hind leg, walk, trot, turn. A state is kept only
    if its primitive fits the body. Each primitive's parameters are free over its own vector range: the
    interpretation's one-primitive-per-behaviour assignment is gone.
  * **Sequence:** per state a weight, a place and a typical duration (0.8-8 s, log-sd 0.4).
    P(i -> j) ~ w_j exp(-s |p_i - p_j|), with one sharpness gene s (0-8): high s wanders between neighbouring
    states, low s jumps anywhere. One more gene sets the cross-fade (0.2-1.5 s). Assumption: this low-rank form,
    rather than a full transition matrix (56 genes), is enough to reach both wandering and jumping sequences.
* **Evaluation.** 24 s per seed on the preset's three seeds, friction 0.7-1.1, mass x0.95-1.05, torque-speed
  servos, derating 1. Judged with every limit lowered by the margin. A seed over a limit ends the evaluation.
* **Unpredictability** = the chain's entropy rate (stationary distribution) over log2(n - 1).
* **Fitness** = (+1 if safe else -1) + min(1, worst margin) + 0.5 x unpredictability.
  * A safe candidate always displaces an unsafe one.
  * Unsafe candidates may hold a cell until then. Without that, generation 0 is empty and there is nothing to
    vary: 0 of 14 uniformly random generators, and 0 of 14 around the primitives' defaults, were safe.
  * Only safe cells are results, and the archive view marks each cell.
* **Start.** Before generation 0, each state is searched alone (seed 0, 1 + 4 x 2 plays) for a setting within
  the limits as close to its defaults as found. On the working body:
  * stand, both weight shifts, walk and turn have such a setting;
  * the steps and the trot do not. Their weight starts low (0-0.1), and evolution may raise it.
  * Generation 0 is then the sequence genes uniform, and each primitive's parameters around its setting
    (spread 0.1).
* **Commanded joint speed** is capped at 0.95 x (1 - margin) = 0.76 of each servo's speed. The interpreted
  controller's own 0.9 is above the margin-lowered limit (0.8), and joint speed was the limit nearly every
  sampled sequence went over.
* **Axes.** Default quantity of motion (0-15 deg/s; about 1-10 on this body) x tempo regularity (0-1). New
  descriptors: `tempo_regularity`, `stillness_ratio`, `unpredictability`.
* The body's own evolve defaults (ADR-070: body axes, 9.5 s rollouts) are not applied to an optimizer with
  `body_defaults = False`. Estimate cost uses the optimizer's own `duration_s`.

*Trials* (runs `20261104-175905-evolve-8d26`, before the speed cap and the axis fix; and
`20261104-180218-evolve-ce75`, 3 x 14, 180 s):
* After 3 generations, 3 safe cells:
  * a calm stand + weight shift (margin +0.88);
  * shift / stand / turn / walk (+0.03, unpredictability 0.68);
  * shift / stand / step / walk (+0.00, 0.58).
* Several unsafe cells were within 0.01 of the margin.
* Estimate: 10 x 28 is about 9 min on 7 workers (1.0 h CPU), plus about 70 s finding the start settings.

## ADR-094 — The first full behaviour-diversity run on the working body (**VERIFY**)

*Context.* The researcher chose the budget: 20 generations x 28.

*Results* (`docs/studies/diversity_r5.md`, run `20261104-181642-evolve-2650`, 1480 s):
* **Overall:** 560 evaluated, 30 within every limit at margin 0.2 on three seeds. They fill 16 of 58 cells;
  coverage was still rising at the end.
* **The safe region:** quantity of motion 1.3-6.9 deg/s, tempo regularity 0.21-0.80, unpredictability up to
  0.78. Nothing above about 7 deg/s is safe.
* **What stops the rest:** sustained servo torque (472 seed failures), then joint speed (275) and sustained belt
  tension (245). Vigorous movement on this body is bounded by the servos' rated torque. Every active safe cell
  sits within 0.08 of the margin.
* **Movements:** weight shifts, stand, walk and turn become safe in sequences. The steps rarely do (13 of 30 safe
  candidates, briefly). The trot almost never does (1 of 30).

*Assumption kept:* a cell's descriptors are averaged over the seeds it played. An unsafe candidate stops at its
first failing seed, so its descriptors may rest on one seed.

## ADR-095 — A minute of an evolved behaviour; 24 s under-samples a sequence (**VERIFY**)

*Context.* Session R6: play the three picked safe cells of run `20261104-181642-evolve-2650` (ADR-094) for 60 s on
the run's three seeds with a full physics report, and show them in the viewport.

*Decisions / assumptions:*
* The performances are played by a study script (`docs/studies/perform_r6.py`) with the run's own settings:
  its compile options, preset randomisation, margin and the stored candidate genome and generator vector. The
  run's 24 s task is re-run first; the margins must match the stored ones (they did, to the fourth decimal).
* Each performance is stored as a run of kind `sim` (parent: the evolve run, tags `R6` and the label), so the
  existing Runs list replays it. No new command or panel: this is a study, not a lab feature.
* "Closest limit" = the known constraint with the smallest margin over the whole minute (unknowns excluded).
  The minute is also judged over its first 24 s and over 12 s windows, and per episode (0.5 s lead-in).

*Results* (`docs/studies/perform_r6.md`):
* 2 of 9 performances stay within every limit for 60 s (calm seed 0, irregular seed 2); none fell.
* All 9 were within the limits over their first 24 s, as in the run. The 7 that go over do so later, each starting
  in a weight-shift **step**, a state with no safe setting of its own (ADR-093): sustained servo torque at the
  opposite front shoulder (calm: fl, active: fr), or the fr.carpus belt (irregular).
* A 24 s evaluation on three seeds under-samples rare states of a chain: the calm cell never played a step in its
  evaluation and plays one on two seeds of three in a minute.

*Consequence (not acted on, for the researcher):* a cell marked safe in ADR-094 is safe for 24 s, not as a
performance. Options: evaluate at 60 s (2.5x cost), require every state the chain can reach to have been played
within the limits, or leave the steps out of the palette until a safe step exists (Q4).

## ADR-096 — Coverage: every likely state checked before a behaviour counts as safe (**VERIFY**)

*Context.* R6 (ADR-095): a 24 s evaluation on three seeds misses a chain's rarer states, and 7 of 9 one-minute
performances of "safe" cells went over a limit. Session R6b compared (a) 60 s evaluations, (b) a coverage check,
(c) leaving the steps out, on the three R6 behaviours (`docs/studies/options_r6b.py`). (a) and (b) flag all
three, as R6 saw; (c) alone does not (the active behaviour without steps still goes over at 60 s). **The
researcher chose (b) with every state kept.**

*Decisions / assumptions:*
* Optimizer `map_elites_behaviour` gains `coverage` (off by default, so earlier runs mean what they did),
  `performance_s` 60, `coverage_p` 0.05, `coverage_after_s` 6.
* **Which states:** those at least 5 % likely to be played in a 60 s performance (`reach_probability`: switches
  at the chain's mean rate, visits Poisson with the stationary share, plus the initial probability; durations
  log-normal sd 0.4, clipped 0.5-15 s). 5 % per minute and 60 s are PROVISIONAL choices.
* A state counts as played on a seed when an episode of it ended at least 2 s (the sustained window) before the
  end. A state played to its end on every seed is not forced again.
* **The forced play:** from the start if the initial probability is at least half the state's reach; otherwise
  after the predecessor with the largest flow pi_i m_ij among likely states, preferring ones already played to
  the end (the first version took the largest flow over all states and forced paths the chain almost never takes,
  e.g. trot then stand for a calm chain). Predecessor at its typical length (1.5-4 s), the state at its
  90th-percentile length, no draws; then the chain runs 6 s more. On every seed; the first limit over makes the
  candidate unsafe. Coverage margins count toward the worst margin; descriptors come from the seeds only.
* Estimate cost does not count forced plays. Measured: 20 x 28 took 2330 s (R5: 1480 s).

*Results* (`docs/studies/coverage_r6b.md`, run `20261105-024409-evolve-7a63`):
* 6 safe cells (R5: 16), quantity of motion 2.2-5.8 deg/s; R5's calmest and most irregular cells are gone.
* A step (two generators) and the trot (one) are safe in context for the first time.
* **15 of 18 one-minute performances of the six safe cells stay within every limit** (R6: 2 of 9).
* The 3 that go over are all episodes drawn longer than the 90th-percentile length that was checked (z 1.8-2.8):
  rare lengths, not rare states. Not fixed here: the next step caps each state's duration in the controller at
  the checked length.

## ADR-097 — Durations capped at the checked length (**VERIFY**)

*Context.* R6b (ADR-096): the 3 of 18 one-minute performances that went over a limit held a state longer than
coverage had checked it (its 90th-percentile length).

*Decisions / assumptions:*
* Optimizer option `cap_durations` (off by default): every state's `max_s` in the `interpreted` controller is
  its checked length, `checked_duration` = exp(log_mean + 1.2816 x 0.4), within 0.5-15 s. A longer draw is held
  at the cap. One-shot states still round to whole cycles; rounding is monotone, so a capped draw never rounds
  past the checked length.
* With the cap, coverage forces every likely state at exactly the cap, also states the seeds played: a
  typical-length episode does not show the cap is safe.
* What the cap removes: 1 draw in 10 is held at the cap; the longest hold drops from about 2.5x typical
  (99th percentile) to 1.67x; the 99th/1st percentile ratio from 6.5 to 4.2; the mean by 3.5 %. The 90th
  percentile stays PROVISIONAL: a higher quantile keeps more spread and costs more torque headroom.
* `perform_r6.py` plays longer than the 60 s of `SimSettings` (the Simulate panel's slider range) by setting
  the length after validation: a study-only bypass, no core change.

*Results* (`docs/studies/coverage_r6c.md`, run `20261105-053201-evolve-e4c8`, 20 x 28, 1715 s):
* 4 safe cells, quantity of motion 2.1-10.0 deg/s (R5's ceiling 6.9); three of them trot.
* **12 of 12 one-minute performances stay within every limit** (R6 2 of 9, R6b 15 of 18).
* **Over 5 minutes (seed 0), 1 of 4 holds.** The others go over in turns: after a walk or a trot, where coverage
  had checked the turn after a stand or a shift; and a turn 3 % likely per minute, under the threshold. None is a
  long hold. Coverage checks states, not transitions, and only for the performance length it is given.

## ADR-098 — Movement that varies within a state (**VERIFY**)

*Context.* Session R7. The researcher watched the R6c behaviours (ADR-097): the sequences start to look good, but
each movement inside them is the same hand-written primitive every time. Asked: let movement vary below the
primitive level, as evolvable genes of the generator, every variation inside what coverage checks.

*Decisions* (`calflab.control.variation`, the `interpreted` controller's `variation` block, optimizer option
`vary_within`, off by default so every earlier run, layout and controller is unchanged; checked bit for bit):
* **Posture drift and noise.** Fixed joint-offset bases solved on the body with every hoof planted:
  * trunk height: the planted crouch of 15 mm (a drift only lowers the trunk; the standing legs are straight);
  * weight over the hooves: the linear part of the four planted weight shifts of 0.3 (one off each hoof), as a
    lateral and a fore-aft axis (a linear model of a solved pose; the physics judges what it does);
  * head: 8 deg on neck/head pitch and yaw joints. **The feral calf has no neck or head motors**, so on the
    working body the head does not move; the gene is there for bodies that have them.
  * Each axis is a sum of three slow sines (the generator's `drift_hz` x 0.6 / 1.0 / 1.7, seeded phases) plus a
    small noise (three sines at 1.2-2.7 Hz), bounded by construction to +-(drift + noise), at most 1 x the basis.
    One signal per performance, scaled by the current state's `drift` and `noise` (cross-faded at a switch),
    ramped in over the first second. Axis weights (`w_height`, `w_weight`, `w_head`) are generator genes.
* **Cycle to cycle.** Each cycle of a primitive is played at its own tempo, rate exp(tempo x u), and amplitude
  about standing, 1 + amp x v, u and v uniform in [-1, 1]; `tempo`, `amp` 0-0.25 per state. The primitive runs
  on its own clock, so phases stay continuous and switches follow the warped phase.
* **Switches.** A gait may be left up to `switch_slack` (0-0.15) of a cycle before an all-hooves-down window
  opens. One-shot states (shifts, steps) still end on whole cycles. Each cross-fade lasts
  blend_s x exp(blend_var x w), w in [-1, 1], within 0.1-3 s.
* **Durations stay capped.** A gait's planned length is drawn and capped as before (ADR-097). A one-shot plays
  whole cycles at their own tempo, never longer than its cycles at tempo 1 would be (or one cycle).
* **Draws** come from their own random stream (seed, episode), so the chain's own draws are as without variation.
* **Coverage plays the extremes** (`mode = "extremes"` in every forced play): the weight carried to all four
  corners of its square at full drift with the trunk at full crouch (each corner reached in 60 % of a step, the
  step at most a quarter of the forced state's length, so all four fall inside it), the noise at full amplitude
  and its fastest frequency on top; cycles alternating fastest and slowest at the largest amplitude; every switch
  at the earliest phase allowed; cross-fades alternating shortest and longest, the shortest into the forced
  state. The seeds draw. Assumption: these corners and alternations bound what the drawn variation can do; the
  physics only judges what was played.
* **Genes:** 6 for the generator (switch slack, blend variation, drift rate, three axis weights) and 4 per state
  (drift, noise, tempo, amp): 87 genes on the eight-state palette (ADR-093's layout: 53). Generation 0 draws them
  in the lower half of their ranges.
* **Clips from footage were not added** to the palette (optional in the request): the interpretation's feasible
  versions are quasi-static sways (ADR-084) that the weight drift now covers in kind.
* **Replays side by side:** `compare.html?a=<run>&b=<run>` (two lab views) and `?replay=<run>` (view state only).

*Cost:* trial `20261105-221316-evolve-c71d` (2 x 14, 210 s, of which about 70 s finding start settings). The
researcher chose 40 x 28.

*First run* (`20261105-221840-evolve-02e3`, 40 x 28 from random generators, 2780 s): **no safe cell.** 1120
candidates, 29 passed their three seeds, every one went over a limit in a forced play (sustained servo torque
21, joint speed 8, belt 7). What the study found (`docs/studies/variation_r7.md`):
* the forced plays had put *every* state into its extremes, not only the one checked. **Changed:** only the
  forced state plays its extremes (`extremes_state`, faded in and out with the cross-fade); the states before and
  after draw, as in a performance. Re-judged, the 29 are still unsafe (margins mostly better);
* the same 29 without their variation genes are unsafe too: the search had not found sequences whose every
  forced play holds (R6c: 4 of 20 in 53 genes; here 87 genes, each mutated);
* nothing in the fitness rewarded variation. **Added:** `variation_weight` x `variation_amount` (0-1: per state
  the mean of drift x axis weight, noise, tempo and amplitude over their largest values, weighted by the
  stationary share, 3/4; the switch slack and cross-fade variation, 1/4). Default 0, so earlier runs score as
  before;
* R6c's four safe generators with every variation gene at 10 % of its range all stay safe with coverage at the
  extremes; at 30 % all four go over on their seeds. **Added:** `start_vectors` (and `start_within`): a run may
  start from given generators, padded with variation genes.

## ADR-099 — Faster joints: what binds per joint, and which levers buy a 0.6 s trot (**VERIFY**)

*Context.* Session R8. The trot is within the limits only at a 1.2 s cycle (77 mm/s); joint speed is the wall
(ADR-097, `trot_whatif_r6c.py`). Asked: per joint, whether speed or torque binds in the trot, walk and turn; then
in physics, before changing the body, what less reduction, a belted or sprung hip ab/ad and lighter parts buy.

*Decisions / assumptions* (`docs/studies/joints_r8.py`, `joints_r8.md`):
* What-ifs change an in-memory copy of the spec only. No body, belt, catalog, component or `verified` change.
* A changed belt ratio keeps the driver pulley unless stated: joint speed x 2 / ratio, servo torque for the same
  joint torque x 2 / ratio, belt tension per servo torque unchanged. A larger driver (45T/45T against today's
  30T/60T) divides belt tension per servo torque by 1.5. Pulley masses, belt lengths, derived C and fit are not
  re-derived (a real change goes through the catalog and `set_belt_drive`, ADR-063).
* A belted hip ab/ad (2:1) gets the other belts' efficiency and no belt check (no such belt in the catalog).
* Lighter = every geom mass and inertia x 0.9 (optimistic: 14 parts have no mass yet).
* Three seeds with the diversity preset's randomisation (friction 0.7-1.1, mass x 0.95-1.05); without it the
  primitive plays are identical on every seed.

*Results:*
* The front carpi bind on joint speed in every motion (1.1-1.2 x the margin-lowered limit); in a quick trot also
  the hocks (speed, 1.14) and the hip ab/ad (sustained torque, 1.2). The stifles have room in speed and torque.
* Carpi at 1:1 with today's 30T driver move the limit onto the carpus belt (sustained tension).
* **Carpi at 1:1 on 45T/45T and hocks at 1.5:1 (30T/45T): a 0.6 s trot (stride 1.0) within every limit at margin
  0.2 on three seeds, +0.16, 130-137 mm/s**; the walk (+0.12 to +0.18) and the turn (+0.04 to +0.06) pass too.
  The 0.6 s trot at stride 0.5 stays over (hip ab/ad sustained torque, -0.08).
* A 2:1 hip ab/ad belt passes that short-stride trot but makes the walk fail on 2 of 3 seeds. Stiffer hip springs
  make the quick trot worse; 10 % lighter changes little.
* Not added to the catalog: 30T and 45T GT2 pulleys for 10 mm belts are listed commercially; they need the
  researcher's go-ahead (sources, masses null, unverified).
