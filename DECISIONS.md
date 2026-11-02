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
