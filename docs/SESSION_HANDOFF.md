# CALFLAB session handoff

Everything a new Claude Code session (or a new collaborator) needs to pick up
CALFLAB. Last updated 2026-10-08 on branch `chassis-mass` (on top of
`phase-1-vertical-slice`, pushed to GitHub), after the session that made mass come from solids
pushed from Rhino, per-part materials and weighed parts, and added a scale
gene for a small test calf (section 4; run `git log --oneline -12` for the
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
working directory `C:\CALFLABHOME`, branch `chassis-mass` (or
`phase-1-vertical-slice` once the researcher has merged it in).

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
researcher merges. The 2026-10-08 work is on the branch `chassis-mass`,
branched from `phase-1-vertical-slice`, pushed to GitHub and open as a pull
request into `phase-1-vertical-slice` (so it joins pull request #1 when the
researcher merges it).

**Tests:** `calflab test` passes: ruff, 249 pytest tests, mypy, web typecheck
and eslint, 14 Vitest tests, 7 Playwright tests (smoke, material / weighed
mass / pushed solid / Mass panel, real-millimetre sliders at scale 0.33,
gumball drag and harness overlay with a
real mouse, runs + journal, evolve from a design).
`calflab doctor` is clean apart from three optional warnings (Graphviz, no
CUDA, unverified components). It used to warn "uv not found" as well: that
was a false alarm, fixed 2026-10-03. uv is installed and is what
`calflab.ps1` runs everything through; nothing needs installing.

**Built and working (Phase 1 vertical slice):**

* Core: plugin system (15 types, hot reload, contract tests, `new-plugin`),
  cached dataflow graph with clusters, versioned YAML genome with migrations,
  explicit overrides (toggle / remove / internalize), event-sourced undo/redo
  shared by all clients, Bake to immutable versioned Designs, run registry
  with lineage, journal with captures.
* Simulation: genome -> RobotSpec -> MJCF -> MuJoCo (CPU) with a CPG gait,
  skin model, domain-randomization hooks, metrics. The reference calf is
  5.0 kg, 608 mm tall, has forward front knees and backward hind knees, and
  trots at 0.51 m/s in simulation (since 2026-10-04, ADR-047).
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

**Added 2026-10-03, after the researcher's first walkthrough by hand:**

* `front_knee_forward` gene (Form > Legs), the counterpart of
  `hind_knee_forward`.
* Gumball: an arrow per handle parameter, visible and draggable (was a
  one-pixel line hidden inside the part). The bar follows the drag.
* Harness routes are drawn over the body in the web viewport (on by default
  in the Wire workspace) and pulled into Rhino as polylines on
  `CALFLAB::Harness`. `calflab.wiring.harness_paths` is the one source.
* Baked designs: **Load** into the working document (`load_design`,
  undoable) and **Evolve from** (`run_evolve design=<id>`); the Designs panel
  is also in the Evolve workspace. Runs record what they started from.
* Archive: a gene table for the clicked candidate (vs current design, vs
  parent, vs a pinned candidate), computed by `Lab.candidate_genes`.
* Runs rows replay visibly (they did work, but in the Journal workspace the
  viewport was a hidden tab); the Journal has run and design pickers and the
  viewport beside the editor.
* Overrides and evolution: the starting point's enabled overrides are built
  into every candidate and never vary; candidates are shown, replayed and
  adopted with the overrides of their run (ADR-044).

**Added 2026-10-04 (researcher's decision: the final body has forward front
knees; no extra leg joint is wanted):**

* `front_knee_forward` defaults to **on** for new projects. Anything saved
  before the gene existed (documents, undo records, runs, candidates, baked
  designs) keeps backward front knees: the gene definition carries
  `absent: false`, the value of a genome that does not mention it (ADR-047).
  No genome version bump, no migration.
* The default CPG trot was re-tuned for that body: 2.0 Hz, hip 10.5 deg,
  knee 10.5 deg, swing 0.55, hip offset -3 deg, crouch -7 deg. In simulation:
  0.51 m/s, stability 0.93, 6.2 W, lowest leg torque margin 0.41, no fall in
  60 s. One shared set of numbers was enough; no front/hind gait parameters.
* `reset_node_params` command and a *Reset to defaults* button on the
  Controller section, so an existing document can take the new gait.
* Found while tuning: **the simulator does not limit joint speed**, only
  torque. The default gait was tuned with commanded joint speed capped at
  120 deg/s (two thirds of the XH540-W270's recorded, unverified 30 rpm).
  Gaits from Evolve are not capped and can be faster than the servos.
* The three-segment leg proposal is set aside (kept in `docs/proposals/`).

**Added later on 2026-10-04 (researcher's revision: the front joint should
work as a high, backward-facing elbow, and the front legs should have two
motors):**

* Gene `front_hip_flex` (Form > Legs, on by default). Off = two-motor front
  legs: no front hip-flexion joint, actuator or motor; the thigh is a fixed
  strut; IDs unchanged (ADR-048). All exporters, analyses, the Rhino build
  list and the Blender armature plan were run on such a body by script.
* The CPG steps two-motor legs with the knee (sweep) and hip abduction
  (lift): new parameters `elbow_amplitude`, `elbow_offset`,
  `swing_abduction`.
* `tune_gait`: a job that tunes the gait for the working design as it is,
  with joint speeds capped, and writes it into the document (ADR-049).
  Button *Tune for this body* on the Controller section.
* Not changed: the default body (front knees forward, three motors). The
  researcher is exploring the elbow proportions with overrides in
  `projects/forward-knees` (front thighs 100 mm; thigh and shank genes 152
  and 250, which leaves the front hooves 46 mm off the ground when
  standing). Once the proportions settle, the natural next step is
  front-specific length genes and a new default body (next session G).
* The forward-knee default of the morning is therefore likely to be
  superseded; it is still what a new project gets.

**Added 2026-10-08 (researcher's request: model the chassis in Rhino and
get real mass, at a smaller scale; ADR-050, ADR-051, ADR-052):**

* Before: a solid pushed onto `Structure` was display only (it replaced
  nothing, weighed nothing, and was a 5 mm sphere in the simulator).
* Every geom has a `mass_source` (`parametric`, `component`, `geometry`,
  `measured`). `calflab.model.mass.mass_breakdown` sums them; it is in
  `scene.mass.breakdown`, in the new **Mass** panel (Form, Mechanism) and in
  `inputs.mass` of sim, evolve and tune runs.
* A pushed mesh is measured on arrival (`calflab.model.solid`): closed?,
  volume, centre of mass, inertia, stored in the override's `meta.solid`.
  Closed + Structure = mass from volume x material density; the simulator
  gets the box with the same mass, centre and inertia tensor; the envelope
  stays as a massless collision shape. Open = shown, not used, warned about.
* Override kinds `material` and `mass` (weighed part); commands
  `set_part_material`, `set_measured_mass`, `set_mass_target`.
  Properties > *Material and mass*.
* Rhino: `CalflabPush` asks for a material on Structure and prints the
  resulting mass or a warning; `CalflabPull` writes `calflab.material`,
  `calflab.mass_g`, `calflab.mass_source`. `bridge rhino --check` now also
  pushes a box, a sphere and an open box (passed in Rhino 8.34).
* Gene `scale` (0.25-1.25): 0.33 gives a 200.6 mm calf. Length genes are
  marked `scale_by: scale`, stored at full size and shown in real
  millimetres everywhere a person reads them (`Lab.genome_form`,
  `set_genes real=true`; the researcher chose this on 2026-10-08 over
  lowering the gene minimums). Gene `battery`.
  Actuator and battery choices come from the library (`choices_from`).
* Component entries never take a value silently: incomplete entries,
  `guessed:`, "default assumed"; `calflab components new <kind> <key>`.
* **No component or material was added.** The researcher's request had
  placeholders where the list of small servos, board, battery and materials
  should be. Ask for it; do not invent one.
* Side effects to know: hooves are booked as cast silicone in the BOM (they
  were printed PETG by mistake), BOM total 5253 -> 5256 USD; the worksheet
  has a `flag` column (the committed CSV was not regenerated);
  `LAYOUT_VERSION` is 5 (dock layouts reset once); a body can carry one
  geometry override per layer instead of one in all.

**Added later on 2026-10-08 (researcher's request: parts of printed PLA
with stainless steel rods; ADR-053):**

* Before: `CalflabPush` joined the selection into one mesh with one
  material; an object's own `calflab.material` was only the prompt default.
* Now, on Structure, each selected object is sent, measured, stored and
  weighed as its own solid with its own `calflab.material` (else the prompt
  material, else the part's). One override per part still; its
  `meta.solids` lists them; the design gets one mass geom per solid
  (`<body>.override.<id>.<n>`). A single-object push is stored as before.
* Breakdown structure rows carry `materials`, `material_label`, `solids`,
  `com_mm`; the push reply carries `solids` and `com_world_mm`; runs record
  `materials` (and `solids`) per part. Properties and the Mass panel show
  them. If one solid of a push is open, none is used for mass.
* `set_part_material` refuses a part whose solids have different materials.
* Tests: three new ones in `tests/test_mass.py` (the first is the
  researcher's two-box check and reads `stainless_304` from the library), a
  step in `web/e2e/structure.spec.ts`, a two-solid push in
  `bridges/rhino/validate_in_rhino.py` (**not yet run in Rhino**).
* The researcher added `stainless_304` to
  `config/components/materials.yaml` (7.93 g/cm3; 39.02 USD/kg, from 12
  rods of 3 mm x 12 in for 8 USD) and marked it **verified** on 2026-10-08:
  the first verified entry. `tests/test_morphology.py` keeps the guard with
  an explicit list, `VERIFIED_BY_RESEARCHER`; add a key there only when the
  researcher says so. A value with unit text in it (`7.93 g/cm³`) stops the
  whole library from loading; the loader does not yet report that kindly.

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
* Grasshopper by hand: opening `calflab_example.gh` on the canvas, dragging
  the slider, pressing the buttons. Rhino by hand: pushing a SubD; looking
  at the harness curves now pulled onto `CALFLAB::Harness`.
* Blender by hand: posing in Pose Mode, typing in the panel's fields;
  Blender 4.2-4.5.
* Web viewport by hand: the new gumball arrows and harness overlay (checked
  with a real mouse by Playwright, not yet by the researcher),
  window/crossing selection, four-view, Rendered mode, mouse navigation
  presets.

**Checked by hand by the researcher (2026-10-03: web lab, Evolve, Wire,
Journal, Rhino bridge):**

* `CalflabConnect` typed as a command: works.
* `CalflabPull`: the model looks right on first inspection (the Harness
  layer was empty; fixed since, see above).
* `CalflabPush` with a Brep (two boolean-unioned spheres, 2810 faces): works.
  It shows in the web lab only while the Skin layer is visible there, which
  is easy to miss: a pushed sculpt replaces the Skin geometry of its part.
* `CalflabLiveSync`: works, follows override toggles and gene edits.
* Typing a value in the gumball bar + *Override this part*: works (badge in
  Properties, entry in Overrides).
* `doctor` warned "uv not found" on top of the three expected warnings:
  false alarm, fixed (see Tests above).

**The researcher must verify (new on 2026-10-08):**

* `CalflabPush` by hand with the new material prompt (a script exercised the
  bridge function with real Breps, not the typed prompts), and the look of
  Properties > *Material and mass* and the Mass panel (a browser test drives
  them; nobody has looked).
* That weighing a pushed solid as fully dense is what is wanted; a printed
  part with infill needs a measured effective density or a weighed mass.
* The small calf in use: the sliders in real millimetres (chosen by the
  researcher, checked by a browser test, not yet used by hand); simulation
  settings and the default gait were
  not re-examined for a 200 mm body, and no real small servo has been tried.
* Whether the `guessed:` lists added to the existing entries match what the
  files meant (only values the files already called guesses were listed).

**The researcher must verify:**

* Every component spec (`verified: false`, written from memory of
  datasheets): fill in `docs/component_verification.csv`, correct the YAML,
  set `verified: true`. All 14 components the design uses are unverified, so
  the $5,253 BOM, 5.0 kg mass and ~25 min runtime all rest on them.
* Torque: with the default trot of 2026-10-04 no leg actuator is near its
  limit (lowest margin 41 %, hip flexion); the neck pitch servo (STS3215) has
  16 %. The earlier finding that `act.fr.hip_abd` saturates belonged to the
  old gait; it can return with other gaits, so re-read the torque table
  after changing the gait.
* Joint speed: the 120 deg/s cap behind the default gait rests on the
  XH540-W270's no-load speed (30 rpm), which is unverified like every other
  component value. A torque-speed curve in the servo model is the proper
  fix (next session F).
* The default trot veers when left running (open loop): 0.15 m sideways in
  20 s, 2.6 m in 60 s.
* Proportions and mass model (ADR-015, ADR-017); skin, servo and thermal
  coefficients (ADR-018, ADR-019); the two-segment leg simplification.
* Harness: only battery, leg buses, neck bus, IMU and Pi link are routed.
  Foot, touch and microphone sensors have no cables in the model; adding
  them needs connector and wire choices (ADR-043).
* Adopting a candidate now replaces the document's overrides when they
  differ from the run's (ADR-044). Say if you would rather be asked first.
* Known UX gaps: in a new Blender file the default cube hides the calf. In
  the Evolve workspace the Archive and the Viewport are tabs of one group,
  so the replay of a clicked cell is behind the Archive tab. A sculpt pushed
  from Rhino is invisible in the web lab while the Skin layer is off.

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
| `DECISIONS.md` | ADR log: every assumption (53 so far) |
| `docs/proposals/anatomical-leg.md` | Proposal for a three-segment leg (set aside 2026-10-04; not built) |
| `docs/USER_GUIDE.md` | How to use the lab |
| `docs/CHAT_GUIDE_PROMPT.md` | Prompt that makes a chat assistant a guide to the whole lab |
| `docs/CHAT_GUIDE_CHASSIS.md` | The same for one workflow: chassis parts from Rhino, real mass, own components, the small calf |
| `docs/CHAT_GUIDE_PROTOTYPE.md` | The same for one job: a small prototype already modelled in Rhino (PLA and steel rods) into the simulator; covers ADR-053, which `CHAT_GUIDE_CHASSIS.md` does not yet |
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
> Check window/crossing selection, four-view, Rendered mode and all three
> navigation presets in the web viewport with Playwright (real mouse, as
> web/e2e/viewport.spec.ts does for the gumball); fix defects. Put the
> Archive beside the Viewport in the Evolve workspace so a clicked cell's
> replay is visible. Then implement reference images on view planes (the
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

**E. The sample project on the new default**
> My working document in projects/sample-calf still has backward front knees
> and an adopted evolved gait. Tell me what it would change, then (after I
> say yes) bake the current state as a design so nothing is lost, switch
> front_knee_forward on, reset the gait to the default, simulate, and show
> me the torque-margin table and speed before and after.

**F. Motor speed in the simulator**
> The servo model limits torque but not speed (ADR-047). Add a torque-speed
> curve to the servo model in core/calflab/sim (available torque falling
> linearly to zero at the actuator's no_load_speed_rpm), a "speed margin"
> metric beside the torque margin, and a column for it in the Mechanism
> table. Show how the default trot and my evolved gaits fare with it, and
> whether the 120 deg/s cap used for the default was too cautious or not
> cautious enough. Do not change component values; flag which results rest
> on unverified speeds.

**H. Enter my small components and tune the small calf**
> Here are my parts for the 200 mm test calf: <servo models with datasheet
> links, board, battery, materials with densities>. For each, run
> `calflab components new`, enter only the values I give or that are on the
> linked datasheet, leave everything else blank or in `guessed:` as I say,
> and keep `verified: false`. Then in a new project set scale 0.33, choose
> them in Mechanism, set a mass target, run *Tune for this body*, and show me
> the mass breakdown, the torque-margin table and the speed. Tell me which
> results rest on guessed or defaulted values, and whether the simulator's
> time step and contact settings still make sense for a body this small.

**I. Boards and sensors per project; skin mass from sculpted skin**
> Boards and sensors are still chosen for all projects in
> config/robot_defaults.yaml because their geom IDs contain the component key
> (ADR-051). Propose stable IDs (e.g. `elec.control`, `elec.compute`), make
> them genes with `choices_from`, migrate, and keep old runs loading. Then
> give a sculpted Skin push a mass from its own area x skin thickness, with
> the same open/closed honesty as structure solids (ADR-050).

**G. Make the elbow body the default**
> I have settled the front leg: joint facing backward, upper segment <N> mm,
> lower segment <N> mm, standing bend <N> deg, two motors (front_hip_flex
> off). Add front-specific genes for those three values (allowing an upper
> segment shorter than 100 mm if I asked for it), keep the hooves on the
> ground automatically, make this the default body for new projects with
> existing work unchanged (the `absent` mechanism of ADR-047), tune the
> default gait for it with tune_gait, and tell me speed, drift and the
> torque margins of the front abduction motors, which carry the lift.
