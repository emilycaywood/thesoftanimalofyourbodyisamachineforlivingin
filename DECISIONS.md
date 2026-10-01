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
they are not derived from calf gait data. The simulated speed (~0.36 m/s for
the default, up to ~0.8 m/s after evolution) says nothing about the real robot
until actuator and skin parameters are identified (Phase 3).

## ADR-033 — Environment built during Phase 1 is inside the Claude app sandbox
The Phase 1 build ran inside the Claude desktop app, whose `%LOCALAPPDATA%` is
redirected to a per-app location. The venv and `node_modules` created there are
not the ones a normal PowerShell session sees: run `.\calflab.ps1 setup` once
in your own terminal.
