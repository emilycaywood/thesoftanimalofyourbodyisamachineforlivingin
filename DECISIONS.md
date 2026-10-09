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
multiplies every gene whose unit is mm and the generator's fixed millimetre
constants (motor offsets, ear and tail radius, the belt). Length genes stay
written at full size; element parameters, overrides, the gumball and
everything pulled into Rhino are in real millimetres, and *Internalize*
converts back. `scale = 0.33` gives a calf 200.6 mm tall.

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
