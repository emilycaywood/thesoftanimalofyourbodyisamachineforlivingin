# CALFLAB session handoff

Everything a new Claude Code session (or a new collaborator) needs to pick up
CALFLAB. Last updated 2026-10-01 on branch `phase-1-vertical-slice`, after the session
that pushed the branch, added the component audit and checked the bridges
inside Rhino, Grasshopper and Blender (run `git log --oneline -8` for the
current state).

---

## 1. Start a session in the right place

The one and only working copy is **`C:\CALFLABHOME`** (local disk, not synced).
The earlier copies on Google Drive and OneDrive were deleted; do not recreate
them, and never move the repo into a cloud-synced folder.

**Claude desktop app (Code tab):** start a *new* session and choose
`C:\CALFLABHOME` as its folder. Do not continue the original session: it was
started in the old Google Drive folder and stays tied to it.

**Terminal:**

```powershell
cd C:\CALFLABHOME
claude
```

Check you are in the right place: the first thing the session should report is
working directory `C:\CALFLABHOME`, branch `phase-1-vertical-slice`.

### Paste this as the first message of a new session

> We are working on CALFLAB in `C:\CALFLABHOME`. Before doing anything, read
> `docs/SESSION_HANDOFF.md`, `CLAUDE.md`, `PLAN.md` and `DECISIONS.md`, confirm
> your working directory is `C:\CALFLABHOME` and tell me the current branch,
> last commit and whether the tree is clean. Follow the working rules in the
> handoff: do not ask clarifying questions, log assumptions as ADRs, never
> invent hardware specs, commit incrementally on the branch, and finish with
> what works, what is stubbed, what I must verify, and the next three sessions
> as ready-to-paste prompts. Then: <your task here>

---

## 2. One-time setup on this machine

The Python environment built during the first session lives in the Claude
app's private `%LOCALAPPDATA%`, which a normal terminal does not see. Run this
once in your own PowerShell:

```powershell
cd C:\CALFLABHOME
.\calflab.ps1 setup
.\calflab.ps1 doctor
```

Daily use:

```powershell
.\calflab.ps1 lab        # server + web app, opens the browser
.\calflab.ps1 test       # everything; --py, --web, --e2e, --fast for subsets
```

Full command list and UI guide: `docs/USER_GUIDE.md`.

---

## 3. Who this is for and how to work

The researcher is an architecture-school (M.Arch thesis) researcher, fluent in
Rhino 8, Grasshopper, 3D modeling, digital fabrication and sewing, with
experience building small robots; not primarily a software engineer. CALFLAB
is long-term research across architecture, design, engineering, theater and
critical humanities, used daily and extended with Claude Code.

Two qualities outrank everything else: **extensibility/modularity**, and a
**familiar UI/UX** following Rhino / Grasshopper / Blender / Fusion and
fabrication-craft conventions.

Working rules (from the original brief):

1. Do not ask clarifying questions. Make reasonable assumptions and record
   each one as an ADR in `DECISIONS.md`.
2. Never invent hardware specs. Component data lives in
   `config/components/*.yaml` with `source:` and `verified: false`; only the
   researcher sets `verified: true`.
3. Never put logic in the UI (web, Rhino, Blender). It goes in `core/calflab`.
4. After each module: run tests and a smoke demo, fix failures, then move on.
5. Commit incrementally on a branch with clear messages; `main` is merged by
   the researcher.
6. End every session with: what works, what is stubbed, what the researcher
   must verify, known UX gaps, and the next three sessions as ready-to-paste
   prompts. Update `docs/USER_GUIDE.md` and this file.

`CLAUDE.md` holds the detailed coding conventions and is loaded automatically.

---

## 4. Current state

**Git:** branch `phase-1-vertical-slice`, pushed to GitHub and open as
pull request #1 into `main`
(https://github.com/emilycaywood/thesoftanimalofyourbodyisamachineforlivingin/pull/1).
The repository is **public**. `main` still has only the initial commit; the
researcher merges.

**Tests:** `calflab test` passes: ruff, 209 pytest tests, mypy, web typecheck
and eslint, 13 Vitest tests, 1 Playwright smoke test. `calflab doctor` is
clean apart from optional warnings (Graphviz, no CUDA, unverified components).

**Built and working (Phase 1 vertical slice):**

* Core: plugin system (15 types, hot reload, contract tests, `new-plugin`),
  cached dataflow graph with clusters, versioned YAML genome with migrations,
  explicit overrides (toggle / remove / internalize), event-sourced undo/redo
  shared by all clients, Bake to immutable versioned Designs, run registry
  with lineage, journal with captures.
* Simulation: genome -> RobotSpec -> MJCF -> MuJoCo (CPU) with a CPG gait,
  skin model, domain-randomization hooks, metrics. The reference calf is
  5.0 kg, 608 mm tall and trots at 0.36 m/s in simulation.
* Evolve: MAP-Elites (pyribs) + CMA-ES inner loop on the local process pool.
* Web lab: Form, Mechanism, Simulate, Evolve, Fabricate, Wire, Journal
  workspaces; viewport, schema-driven panels, node editor, command line.
* Fabricate / Wire: build123d leg segment with actuator mount and embossed ID
  (STEP/STL/3MF/.3dm), glTF, URDF, MJCF, firmware skeleton, BOM, power budget,
  harness YAML and diagram.
* Component verification: `calflab components audit` (unverified components,
  the results that rest on them, actuators at their torque limit) and
  `docs/component_verification.csv`, a worksheet with one row per recorded
  spec value and blank columns for the datasheet value.
* Rhino 8.34 (`calflab bridge rhino --check`): CalflabInstall, CalflabPull,
  CalflabPush (typed as a command) and CalflabLiveSync verified against a
  live server.
* Grasshopper (`calflab bridge rhino --grasshopper`): the five GH Python 3
  components verified; `bridges/rhino/grasshopper/calflab_example.gh` is
  generated and committed.
* Blender 5.2.2: armature build, clip export and rollout import verified
  numerically (`bridge blender --check`), and the sidebar panel clicked with
  simulated mouse events (`bridge blender --check-ui`).

**Scaffolded only (interfaces + tests, no behaviour):** PPO training, MJX
simulator, RemoteSSH and CloudNotebook transports (job bundling is real),
imitation reward, interactive selection, molds, skin patterns, nesting,
system ID, touch response, puppeteering blend, ball joints. UI placeholders:
Behave and Deploy workspaces, reference images, inertia / heat-map /
range-of-motion overlays, endpoint/midpoint/axis snaps, angle and clearance
measurement, run comparison, Pareto / parallel coordinates. The component
audit has no panel in the web lab yet (CLI and `lab.analysis` only).

**Not yet verified on real software:**

* Hops endpoints against Grasshopper: Hops is not installed on this machine
  (Rhino `PackageManager` > Hops).
* Rhino and Grasshopper by hand: how the pulled model looks, opening
  `calflab_example.gh` on the canvas, dragging the slider, pressing the
  buttons; `CalflabConnect` as a typed command; pushing a Brep or SubD.
* Blender by hand: posing in Pose Mode, typing in the panel's fields;
  Blender 4.2-4.5.
* Web viewport by hand: dragging the gumball handle, window/crossing
  selection, four-view, Rendered mode, mouse navigation presets.

**The researcher must verify:**

* Every component spec (`verified: false`, written from memory of
  datasheets): fill in `docs/component_verification.csv`, correct the YAML,
  set `verified: true`. All 14 components the design uses are unverified, so
  the $5,253 BOM, 5.0 kg mass and ~25 min runtime all rest on them.
* Torque: in the default trot `act.fr.hip_abd` (XM430-W350) reaches its
  usable torque (2.46 N*m = stall x 0.6) and the neck pitch servo (STS3215)
  has 3 % margin. Either the hip-abduction actuator is undersized, the 0.6
  derating is too cautious, or the gait is too wide: a design decision.
* Proportions and mass model (ADR-015, ADR-017); skin, servo and thermal
  coefficients (ADR-018, ADR-019); the two-segment leg simplification.
* Known UX gap: in a new Blender file the default cube hides the calf.

---
## 5. Things about this machine that are not obvious

* Windows 11, PowerShell 5.1, AMD GPU (no CUDA): MuJoCo runs on CPU; GPU
  training is meant for a remote backend.
* Only Python 3.14 is installed system-wide; `uv` manages Python 3.12 for the
  project. `uv` is not on PATH: it is reached as `python -m uv`, which
  `calflab.ps1` handles. Always run tools through `.\calflab.ps1`.
* The venv is in `%LOCALAPPDATA%\calflab\venv`; web dependencies are in
  `C:\CALFLABHOME\web\node_modules`.
* **Inside the Claude desktop app `%LOCALAPPDATA%` is redirected** to a
  per-app folder, so an environment built by a Claude session is separate
  from the one your terminal uses. Both work; each needs `setup` once.
* In PowerShell 5.1, do not pipe a native program's stderr with `2>&1`.
* Rhino 8.34: `C:\Program Files\Rhino 8\System\Rhino.exe`. A script can be run
  with `Rhino.exe /nosplash /runscript="_-ScriptEditor _Run <path without spaces>"`.
* Blender 5.2.2: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`.
* To re-check a bridge, start the lab on a scratch project
  (`.\calflab.ps1 lab --project <folder> --no-browser`) and run
  `bridge rhino --check`, `bridge rhino --grasshopper`, `bridge blender --check`,
  `bridge blender --check-ui`. Rhino and Blender open a window and close it again.
* Graphviz is not installed, so harness diagrams use the built-in renderer
  (`winget install Graphviz.Graphviz` enables full WireViz drawings).
* The web stack is deliberately pinned to older major versions (ADR-020).
* To look at the UI from a Claude session: the `calflab-lab` entry in
  `.claude/launch.json` starts the server on port 8000 with the built web app.
  Changes in `core/` need a server restart; changes in `web/src` need a
  rebuild (`.\calflab.ps1 setup`, or `.\calflab.ps1 lab --dev` for hot reload).

---

## 6. Where to read

| File | Purpose |
|---|---|
| `CLAUDE.md` | Conventions for every session (loaded automatically) |
| `PLAN.md` | Architecture, module boundaries, data flow, phases, risks, status |
| `DECISIONS.md` | ADR log: every assumption (40 so far) |
| `docs/USER_GUIDE.md` | How to use the lab |
| `docs/component_verification.csv` | Datasheet verification worksheet (the researcher fills it in) |
| `bridges/rhino/README.md`, `bridges/blender/README.md` | Bridge install, conventions, what is verified |
| `docs/notebooks/quickstart.ipynb` | Driving the lab from Python |

---

## 7. Recommended next sessions

Prefix each with the opening message from section 1.

**A. Use the verified data**
> I have filled in docs/component_verification.csv. Read it, list every row
> where my datasheet value differs from the recorded value, and update
> config/components/*.yaml to my values (keep `verified` as I set it; do not
> flip it yourself). Re-run `calflab components audit --simulate` and tell me
> how the BOM, mass, torque margins and runtime changed. Then resolve the
> saturated hip-abduction actuator: show me the torque-margin table for the
> alternatives already in the library and for a narrower gait, and add a
> Component audit panel to the Wire workspace (schema-driven, no logic in the
> UI). Update docs/USER_GUIDE.md.

**B. Viewport and Form polish**
> Exercise the web viewport by hand: gumball dragging, window/crossing
> selection, four-view, Rendered mode and all three navigation presets; fix
> defects. Then implement reference images on view planes (the
> `set_reference` command and `/api/assets` exist), endpoint/midpoint/axis
> snaps, the angle measurement tool, and side-by-side run comparison in
> Simulate. Keep all logic in the core, extend the Playwright smoke test, and
> update docs/USER_GUIDE.md.

**C. Remote compute and PPO (Phase 2 start)**
> Read core/calflab/compute/remote.py. Implement the RemoteSSH transport
> (package, scp, run, poll, fetch, with cancel) using the existing bundle
> format, tested against localhost or a mock. Finish the CloudNotebook flow so
> a Colab notebook trains a MuJoCo Playground/MJX PPO policy on the exported
> MJCF and imports the ONNX policy as a Controller plugin. Add domain
> randomization presets and the imitation reward using motion-library clips
> exported from Blender.

**D. Hops (after installing it: Rhino `PackageManager` > Hops)**
> Hops is now installed in Rhino 8. Extend bridges/rhino/grasshopper/
> build_example.py (or add a sibling script) to place Hops components pointed
> at the five /hops endpoints, solve them against the live lab like the GH
> Python components, fix whatever breaks in server/calflab_server/hops.py,
> and update bridges/rhino/README.md.