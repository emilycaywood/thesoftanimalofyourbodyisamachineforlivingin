# CALFLAB session handoff

Everything a new Claude Code session (or a new collaborator) needs to pick up
CALFLAB. Last updated 2026-11-02 on branch `robot-calf-final` (cut from
`chassis-mass`), after the session that built the final feral calf with belt
drives and tension springs (section 4; run `git log --oneline -12` for the
current state). The commits since 2026-10-10 are local: not pushed.

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
working directory `C:\CALFLABHOME`, branch `robot-calf-final` (or
`chassis-mass` / `phase-1-vertical-slice` once the researcher has merged it in).

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

**Tests:** `calflab test` passes: ruff, 291 pytest tests, mypy, web typecheck
and eslint, 14 Vitest tests, 8 Playwright tests (smoke, material / weighed
mass / pushed solid / Mass panel, real-millimetre sliders at scale 0.33,
gumball drag and harness overlay with a
real mouse, runs + journal, evolve from a design, a proportion study on the
two-joint body). After the rotated mounts: 296 pytest tests; after the
boards per project: 300.
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
  `bridges/rhino/validate_in_rhino.py` (run in Rhino on 2026-10-09: passed).
* The researcher added `stainless_304` to
  `config/components/materials.yaml` (7.93 g/cm3; 39.02 USD/kg, from 12
  rods of 3 mm x 12 in for 8 USD) and marked it **verified** on 2026-10-08:
  the first verified entry. `tests/test_morphology.py` keeps the guard with
  an explicit list, `VERIFIED_BY_RESEARCHER`; add a key there only when the
  researcher says so. A value with unit text in it (`7.93 g/cm³`) stops the
  whole library from loading; the loader does not yet report that kindly.

**Added after that (researcher's request of 2026-10-08: PLA parts are
modelled full but printed with infill; ADR-054):**

* A solid tagged `calflab.print.infill`, `calflab.print.perimeters` and
  `calflab.print.line_width` is weighed with an **infill estimate**: a shell
  of perimeters x line width at full density plus the core at the infill
  percentage. Centre of mass and inertia follow the same split. Untagged
  solids are fully dense as before; 100 % equals untagged exactly.
* `calflab.model.infill`: `parse_print_tags` (no defaults; bad tags refuse
  the push), `measure_core` (grid, at the push; a 100 mm cube takes about
  5 s), `printed_solid`, `estimate_info`. Stored in the override as
  `meta.print` / `meta.print_core` (or per entry of `meta.solids`).
* New mass source `infill`, shown as `infill est.` in the web lab and as
  `an INFILL ESTIMATE` in Rhino; `Geom.infill`; `infill_parts` and
  per-solid `infill` in the breakdown and in `inputs.mass` of runs;
  `CalflabPull` writes the print tags back.
* The researcher chose **one wall thickness all round**: top/bottom layers
  and layer height are not used (no print direction is known). Their
  settings: 15 %, 2 perimeters, 0.4 mm (3 top / 3 bottom layers, 0.2 mm).
  These are not defaults anywhere in the code.
* Tests: `tests/test_infill.py` (6), a step in `web/e2e/structure.spec.ts`,
  a step in `bridges/rhino/validate_in_rhino.py`. `bridge rhino --check`
  passed in Rhino 8.34 on 2026-10-09 with that step and with the two-solid
  push of ADR-053.

**Added 2026-10-09 (researcher's request: the prototype has no neck or head
motors; ADR-055):**

* Genes `has_neck_yaw`, `has_neck_pitch`, `has_head_pitch` (Form > Neck and
  head, on by default, `absent: true`). Off = no joint, actuator or motor;
  the parts stay, fixed in the standing pose, IDs unchanged. The neck bus in
  the harness ends at the furthest motor left. No genome version bump.
* `tests/test_neck_switches.py` (9); every exporter and analysis, a
  simulation and undo were run by script on a body with all three off.
  Not looked at in the web lab or Rhino by anyone.

**Added later on 2026-10-09 (researcher's request: the prototype's legs do
not fit the skeleton; ADR-056; and its two servos):**

* `scs0009` and `mg996r` in `config/components/actuators.yaml`, from the
  two documents the researcher supplied; unverified, blanks left blank.
* Form > Legs: `own_leg_lengths` (off) with `front_thigh_length`,
  `front_shank_length`, `hind_thigh_length`, `hind_shank_length` (thigh
  down to 5 mm full size), and `front_thigh` (on; off = no front thigh body,
  the shank hangs from the hip on `joint.f*.knee`, named Shoulder pitch).
  With either in use the shorter legs' hips sit lower so all hooves stand.
  None is evolvable; no genome version bump. This supersedes next session G
  for the lengths (the default body was not changed).
* The request's three leg measurements were placeholders: the body was
  tested with stand-in lengths. With scs0009 on the pitch joints and the
  full-size battery and boards it stands but hardly walks (servos at their
  limit); with mg996r everywhere it trots at 0.09 m/s. A small battery and
  board are still not in the library.
* `tests/test_leg_layout.py` (6).

**Added 2026-10-10 (the researcher simplified the prototype to eight
motors, two joints per leg, and wants to compare proportions; ADR-057,
ADR-058, ADR-059):**

* Genes `front_hip_abd`, `hind_hip_abd` (Form > Legs, "Front legs have hip
  abduction" / "Hind legs have hip abduction", on by default,
  `absent: true`). Off = no abduction joint, actuator or motor on that pair;
  `leg.<k>.hip` keeps its ID and is fixed to the trunk; the leg is
  `joint.<k>.hip_flex` then `joint.<k>.knee`. No genome version bump.
  Specs, MJCF and rollout metrics of the default calf, the 2026-10-09
  layout, two-motor front legs and scale 0.33 are identical before and
  after.
* Metrics: per actuator `speed_peak_deg_s`, `speed_limit_deg_s`,
  `speed_margin`, `torque_saturated`; overall `speed_margin_min`. The
  simulator still limits torque only.
* MJCF compile: `joint_loss_scale`, `armature_scale` (both 1 = unchanged
  results). `power_budget` returns `voltage_mismatch` / `voltage_note`;
  nothing is converted between a 6 V servo entry and a 7.4 V battery.
* **Proportion study**: `calflab.evolve.study`, `Lab.run_study`, commands
  `run_study`, `simulate_study_body`, `adopt_study_body`, route
  `/api/study/<run>`, panel **Proportions** in Evolve (centre, beside
  Archive). Run kind `study`, artifact `runs/<id>/study.json`.
  `LAYOUT_VERSION` is 6 (dock layouts reset once).
* New project **`projects/small-calf-two-joint`** (not in git, like every
  project): scale 0.337, both abduction switches off, front knees forward,
  hind backward, no neck/head/tail/ear motors, `scs0009` on all eight
  joints, `lipo_2s_1100`, *Include skin* and *Show skin* off. It holds a
  tune run, a sim run and two studies. `projects/small-calf` was not
  touched.
* What the examination of the small body found (ADR-058): time step and
  contact are fine at 2 ms. The passive joint friction/damping of
  `robot_defaults.yaml` and the library default armature (0.005 kg*m^2,
  used because `scs0009` gives none) are sized for the 5 kg calf and decide
  how fast the small one walks.
* Results in that project, 378 g as simulated (parametric structure
  estimate, the lab's Teensy + Pi 5, no solids pushed):
  * Tune for this body (library values): trot 0.12 m/s, no fall, no joint
    limit, trunk never under 96 % of standing height. Hip-pitch servos at
    their torque limit 55 to 59 % of the time; knees have 60 to 69 % margin.
  * Study `20261010-155806-study-1075` (library values, 41 bodies, thigh and
    shank 20 to 100 mm, trunk 101 to 189, stance 40 to 85, hip drop 0 to 25,
    height 100 to 250): trot works on all 41 at 0.10 to 0.12 m/s whatever
    the proportions; walk on 22 (up to 0.08 m/s; shorter shanks walk
    faster); bound on none. Battery peak about 5.4 A, mean 4.6 A.
  * Study `20261010-160303-study-b3c8` (a **what-if**: joint loss scale
    0.02, armature scale 0.2, 1 ms): trot on 31 (up to 0.33 m/s), walk on
    30 (up to 0.25), bound on 6 (up to 0.09). Shorter shanks trot faster and
    steadier. The what-if values are assumptions, not data; the document was
    put back to 1 / 1 / 2 ms.
* **Rotated servo mounts (ADR-060):** every leg part has `mount_roll` and
  `mount_yaw` (deg, mirrored by side); the hip's are the genes
  `front_leg_splay`, `hind_leg_splay`, `front_leg_toe`, `hind_leg_toe`
  (Form > Legs, 0 by default, `absent: 0`), a thigh's or shank's are set by
  an override. The body frame turns, so joint axis, motor and everything
  below turn with it; hooves are regrounded by forward kinematics. Bodies
  without mount angles are bit-identical. `tests/test_rotated_mounts.py`
  (5). The request was one sentence; this is my reading of it (the mount
  turns and the limb with it), recorded in the ADR. Not looked at in the
  web lab, Rhino or Blender; not a dimension of the proportion study.
* Rotor inertia of the SCS0009: the researcher supplied gear ratio 1:416
  (not entered in the library; ask). It cannot be calculated from the
  listing. Reflected inertia = rotor inertia x 416^2; a geometric guess with
  assumed rotor sizes gives 0.0002 to 0.001 kg*m^2 at the output (Armature
  scale 0.04 to 0.2). A timed no-load step read from the servo's bus gives
  it: armature = time to 63 % of no-load speed x 0.0215.
* Not done: a bounding controller (the CPG "bound" is an open-loop footfall
  pattern); a torque-speed curve in the servo model (next session F).

**Added later on 2026-10-10 (researcher's request: the prototype's only
board is an ESP32; ADR-061):**

* `esp_wroom_32` in `config/components/electronics.yaml`: 7 g (weighed by
  the researcher), 3.3 V, 0.33 W (= 3.3 V x the "~100 mA" given). Size and
  cost not given, left blank. Unverified. Open question put to the
  researcher: whether the approximate current belongs in `guessed:`.
* Genes `board_control` (default `teensy_41`) and `board_compute` (default
  `raspberry_pi_5`, extra choice `none`), group Mechanism, `choices_from:
  board`, not evolvable. They show as **Control board** and **Second
  board** at the end of Mechanism > *Actuators and transmission*; no web
  code changed. "Only the ESP32" = `esp_wroom_32` + `none`. No genome
  version bump: the defaults are what every genome had. Geom IDs stay
  `elec.<component key>`.
* Spec, MJCF, mass and power budget of the default calf and of the genomes
  of all six projects in `projects/` are identical before and after.
* Runs record `inputs.boards` (sim, evolve, tune, study) and `study.json`
  has `boards`; study notes name the boards.
* On a scratch copy of `projects/small-calf-two-joint` with only the ESP32:
  378.2 g -> 329.2 g, idle budget 2.09 A -> 1.26 A at 7.4 V. Seen in the
  lab's browser pane (Mechanism lists, trunk row of the Mass tab, Ctrl+Z
  twice). The researcher's message named `projects/small-calf`, whose
  document is a different body (scale 0.5, `mg996r` abduction,
  `lipo_3s_5000`); asked, they confirmed they meant the two-joint project.
* Then, at the researcher's request, in `projects/small-calf-two-joint`
  itself: ESP32 chosen as the only board (two undo steps) and *Tune for
  this body* re-run with the first tune's settings (run
  `20261010-172610-tune-fd7c`, then sim `20261010-172610-sim-7dac`).
  329 g: trot 0.117 m/s (was 0.111 at 378 g), no fall, hip-pitch servos at
  their torque limit 54 to 60 % of the time (was 55 to 59 %), knee margins
  54 to 62 %. So 49 g less changes almost nothing, as ADR-058 would
  predict. The two studies there are still the 378 g ones; not re-run.
  `projects/small-calf` was not touched.
* `calflab components new` no longer turns the YAML file's line endings
  into CRLF.
* Not done: sensors per project (the IMU and microphone boards and the
  sensor loads of `robot_defaults.yaml` are still on every body); more
  than two boards; a regulator in the power budget; the firmware skeleton
  export is still Teensy 4.1 + Raspberry Pi whatever is chosen.
* `tests/test_boards.py` (4). 300 pytest tests.
* Not verified by anyone by hand: the Proportions panel beyond one look in
  the lab's browser pane and its Playwright test; `CalflabPull` of a
  two-joint body in Rhino (the build list and armature plan are tested).

**Added 2026-10-12 (researcher's request: simulate the prototype as
modelled in Rhino instead of the parametric calf; ADR-062):**

* Before: `CalflabPush` replaced one body's mass properties; the skeleton
  came from the sliders and collision from the envelope shapes.
* Three new Rhino commands (run `CalflabInstall` again to get them):
  `CalflabModelSetup` (layers `CALFLAB::Model::<body id>` and an axis line
  per joint on `CALFLAB::Model::Joints`), `CalflabTag` (material, foot,
  print settings onto the selection) and `CalflabPushModel` (sends
  everything on the model layers, no selection; Check or Push).
* One override of kind `model` ("Rhino model"), command `set_rhino_model`,
  route `/api/bridge/rhino/model` (GET = the layout, POST = the push).
  Joints go to the axis lines (direction = axis, midpoint = place); each
  body's solids give mass as in ADR-053/054; collision is a convex hull per
  solid (32 points at most), one hull round the solids tagged
  `calflab.foot` per leg; envelope shapes and that leg's hoof sphere are
  removed. Off / undo = the parametric calf. Genome, Form, study and Evolve
  untouched.
* All solids of a body are one rigid piece (the researcher asked): the
  printout and `tests/test_pushed_model.py` state one free body plus the
  hinges and zero loose solids.
* Refused whole, with every problem listed, if a solid is open, on no body
  layer or without a structure material.
* `run.json`: `inputs.geometry` (source, file, joints against the
  parametric ones in mm and degrees, solids and mesh hashes per body, feet)
  on sim, tune, evolve and study runs; the scene has `geometry`; a sim run
  of a model is titled `Simulate (Rhino model)`.
* `silicone_solid` in `config/components/materials.yaml`: 1.04 g/cm3 as the
  researcher gave it from the datasheet; product name and link not given;
  unverified.
* Conventions the researcher accepted before the build: layers for bodies,
  lines for joints, a tag for feet. Their answers: feet are PLA; print
  settings are the existing ADR-054 tags (20 % infill, 2 mm walls: the
  perimeters and line width that make 2 mm are asked at the push, not
  assumed).
* Tried on a scratch copy of `projects/small-calf-two-joint` with a
  stand-in model (145 detailed solids, joints moved 1 to 4 mm): pushed in
  4.5 s, stands on its foot hulls, walks at 0.095 m/s with the project's
  gait (parametric 0.097), 19,000 steps/s against 31,000.
  **The researcher's real model has not been pushed**: the project itself
  was not touched and has no overrides.
* `bridge rhino --check` passed in Rhino 8.34 with a new model step
  (2026-10-12). It was run against a scratch project on port 8010
  (`calflab-scratch` in `.claude/launch.json`, project
  `projects/_scratch-check`), and it rewrites
  `%APPDATA%\calflab\rhino_bridge.json`: that file was put back to
  `http://127.0.0.1:8000` afterwards (it had pointed at port 8011, left by
  an earlier check).
* `projects/small-calf-two-joint` holds about 50 runs, three bakes and
  three studies made by the researcher after the 2026-10-10 handoff; they
  are not described here.
* 314 pytest tests.
* Fixed after the researcher's first try the same day: an open Rhino kept
  the old `calflab_rhino` module in memory (the command scripts now reload
  it when its file changes); a copied or mirrored solid kept its
  original's `calflab.body`, and a hand-drawn or renamed axis line was not
  read by its name (the layer and the object name now decide);
  `CalflabTag` threw away its answers when a later prompt was cancelled;
  `CalflabPushModel` lists the joints and foot solids it found before it
  sends. `bridge rhino --check` no longer rewrites
  `%APPDATA%\calflab\rhino_bridge.json`: it passes the lab address to its
  own Rhino through `CALFLAB_RHINO_URL`.
* Not done: the model's solids are stored with their hull vertices in the
  document (about 1 MB for 145 solids); a web view of the joint table (it
  is in the scene payload and the Rhino printout only); self-collision;
  servo, board and battery positions from the model; a check that parts
  clear each other through the joint ranges.

**Added 2026-11-02 (researcher's request: the final feral calf, belt drives
and tension springs; ADR-063 to ADR-069). Branch `robot-calf-final`:**

* New project **`projects/robot-calf-final`** made with
  `calflab new-project projects\robot-calf-final --template feral_calf`.
  `projects/small-calf-two-joint` was not touched. The lab for it:
  `.\calflab.ps1 lab --project projects\robot-calf-final` (or the
  `calflab-feral` entry in `.claude/launch.json`, port 8020).
* New genome and part generator **`feral_calf`**
  (`config/genes/feral_calf.yaml`, `core/calflab/morphology/feral.py`) with
  the researcher's dimensions:
  * rear: femur 200 mm at 40 deg, fixed (no hip pitch); tibia 245 mm at 35
    deg; cannon 230 mm at 10 deg;
  * front: upper leg 340 mm and cannon 245 mm, solved to 7.2 deg so the
    back is level;
  * hoof pad 30 mm; standing height 610.4 mm;
  * axles 550 mm apart, rails 100 mm apart.

  Ten `sts3215_c018` servos (new library entry, only the supplied values;
  stall current not given, so its current is "unknown"). Stifles and hocks
  are belted 2:1; the carpus belt is an option, off. Values that are not
  genes live in `config/feral_calf.yaml`.
* **Belt drives** (ADR-063, ADR-064, `core/calflab/mech/belts.py`):
  * a drive is three catalog ids, nothing else, and C is derived;
  * catalog in `<project>/catalog/*.json`, copied from `config/belts/`;
  * checks: servo on its segment, pulleys apart, at least 6 teeth in mesh,
    and the hock servo against the stifle pulley and belt through the whole
    stifle range;
  * `set_belt_drive` rejects a failing choice with the reason, and
    `set_node_params` cannot touch belts; a design with a failing drive
    builds but is not simulated.
  * Defaults: stifle 444 mm (C 176.7) and **hock 400 mm (C 154.7)**. The
    450 mm hock near the 180 mm target fails: the stifle belt reaches the
    hock servo from about 78 deg of flexion, and the provisional stifle
    range is 80 deg.
* **Springs** (ADR-065): `Spring` spec elements, forces applied at their
  anchor sites every physics step, pull only, torque recorded per step. The
  genes are sliders and evolvable. Defaults at standing:
  * stifle 20 N at 25.4 mm (front);
  * hock 7.7 N at 24.8 mm (back);
  * shoulder 8 N at 24.9 mm, **behind**: in simulation that side helps
    rising from kneeling.

  A side check warns when a spring helps gravity fold its joint.
* **Motions and loads** (ADR-069): `controller:feral_motion` (stand, a
  slow lateral-sequence walk, lie down and rise hind end first then front
  from kneeling). Commands `run_loads` and `run_belt_comparison` write runs
  of kind `loads` (rollout + `loads.csv`, `loads_summary.csv`,
  `loads.json`) and `belts` (`belt_comparison.json` / `.csv`). Results on
  the defaults (masses as entered, unverified servo):
  * standing: no flags;
  * walk: no flags (stifle belt peaks at 91 N against 44 N allowable,
    briefly);
  * lying down and rising: stifle belts above 44 N for 60 % of a cycle,
    hocks 28 %; shoulders and carpi above 60 % of rated for most of a
    cycle; peak 77 % of stall at the shoulders.

  Larger pulleys lower the belt peak (91 / 76 / 69 N for 30T / 36T / 40T).
  These runs are in the project (`20261102-1455*-loads-*`,
  `20261102-1456*-belts-*`).
* **Masses** (ADR-068): servos, tubes and rods, batteries and the head lump
  are counted. Every other part is a required `null` value (0 g, listed in
  the Mass tab and the Belts panel). **1304 g as entered.**
* **UI**:
  * new **Belts and springs** panel in Mechanism, with three dropdowns per
    drive and every derived value read-only;
  * spring sliders and a standing-pose table;
  * load and comparison tables;
  * a provisional/missing list;
  * PROV badges in schema forms;
  * springs drawn as lines that follow playback;
  * belts and pulleys as Transmission geoms;
  * `LAYOUT_VERSION` 7 (dock layouts reset once).
* Tests: `tests/test_belts.py` (20), `tests/test_feral_calf.py` (17, one
  slow), `web/e2e/belts.spec.ts` (runs on a second lab started by
  `playwright.config.ts` on a fresh feral project).
* Changed for everyone:
  * `stall_current_a` is optional (ADR-051's required list shrank by one;
    `tests/test_mass.py` updated);
  * `Component.unknown`;
  * `ActuatorSpec.rated_torque_nm` and `encoder_steps_per_rev`;
  * mass sources `tube` and `specified`;
  * `mass_breakdown()["missing"]`;
  * `RobotSpec.springs`;
  * `BuildContext.project_dir`;
  * `calflab new-project`.

  The reference calf and every existing project build exactly as before.
* Not done:
  * Rhino/Blender bridges for springs: pulleys and belt spans are ordinary
    geoms, so `CalflabPull` gets them, but no spring curves;
  * a Rhino model of this body (ADR-062 needs `CalflabModelSetup` on it,
    not tried);
  * the proportion study on this genome (not tried);
  * a harness or power budget for it;
  * clearance checks other than the hock sweep.

**Added later on 2026-11-02 (researcher's request: make the feral calf
evolvable with its belts unchanged; ADR-070):**

* The belt choices are genes now: `belt_<drive>_system`, `_pulleys`,
  `_length`, catalog ids ("open" enums), hidden from Form, never evolvable.
  Only `set_belt_drive` writes them. The generator's `belts` parameter is
  gone. `projects/robot-calf-final` was converted through the lab's own
  commands (two undoable steps).
* Evolvable: segment lengths and angles, axle spacing, springs. Belt-bound
  genes (femur and tibia length and angle, upper leg) are searched only
  where every belt passes: femur 137 mm and up, tibia 231 mm and up, femur
  angle up to 43.8 deg, tibia angle up to 39.4 deg, with the defaults.
* Candidates that cannot be built are rejected before simulation
  (`spec.metadata["infeasible"]`, status `infeasible`, counted in the
  Evolve panel).
* Workers get the project's catalog inlined (`belt_catalog`), never stored
  in a document.
* `feral_motion` has a CMA-ES vector (ten walk numbers). New descriptors
  `standing_height` and `step_cycle`. Gene files may carry `evolve:`
  defaults, which the lab applies and the Evolve panel shows.
* A 2 x 4 evolution on the project ran in 41 s; every candidate kept both
  belts at the same C. Not done: a fitness preset for this body (`walk`
  targets 0.5 m/s; it walks at about 0.02 m/s); the proportion study on it.
* Tests: `tests/test_feral_evolve.py` (7, one slow); `web/e2e/belts.spec.ts`
  also checks that Form hides the belt genes and that Evolve shows the
  body's defaults. 369 pytest tests.

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

**The researcher must verify (new on 2026-11-02):**

* Every PROVISIONAL value (ADR-067; listed in the Belts panel), and above
  all the ones chosen in this session:
  * joint ranges (stifle -30..80 decides the hock belt);
  * fitting reach 25 mm;
  * hip block reach 40 mm;
  * servo orientation on the tubes;
  * belts and servos in one plane;
  * leg lateral offset;
  * the cannon and front-leg lean directions;
  * the front angle solved to 7.2 deg for a level back.
* The STS3215 C018's output-axis position on its case
  (`config/feral_calf.yaml` `servo.output_axis_offset_mm`): until entered,
  the hock sweep and the servo-on-segment checks of long belts say
  "unknown".
* The missing masses (horns, bearings, collars, plugs, blocks, electronics,
  skin, hoof pads, belts, springs, pulleys, neck rods), the aluminium
  density if that rail is used, and the servo's stall current.
* Whether 450 mm (C 179.7) at the hock is worth a stifle limited to 75 deg,
  or the 400 mm default (C 154.7) is acceptable.
* `purchase_confirmed` for the belts you can order.
* Whether a generic 9 mm belt system (Source A lengths) should exist, and
  3 mm pulley pairs plus the 3 mm allowable tension.
* The motions: the walk is slow (17 mm/s) with a small stability margin; the
  lie/rise script is one way that worked in simulation.
* The Belts panel by hand: a browser test and one look in the lab's browser
  pane, nobody else.

**The researcher must verify (new on 2026-10-12):**

* `CalflabModelSetup`, `CalflabTag` and `CalflabPushModel` typed by hand, with
  the real model: a script drove the functions behind them in Rhino 8.34,
  nobody has answered the prompts.
* The joint table of the push against a measurement in Rhino (pick one
  joint, measure from the pulled calf's axis line to yours).
* Whether the model is drawn in the standing pose the lab assumes, and
  whether the feet are level (the push reports their lowest points).
* The body masses of the push against the real parts on a scale.
* `silicone_solid`: product name and datasheet link for `source:` and
  `url:`, then `verified` if it is right.

**The researcher must verify (new on 2026-10-08):**

* `CalflabPush` by hand with the new material prompt (a script exercised the
  bridge function with real Breps, not the typed prompts), and the look of
  Properties > *Material and mass* and the Mass panel (a browser test drives
  them; nobody has looked).
* The infill estimate against reality: compare two or three real parts with
  the slicer's filament weight at the same settings, and with a scale. Tag
  a solid in Rhino by hand (Attribute User Text) and read the printout and
  Properties: a script did both, nobody has by hand.
* The small calf in use: the sliders in real millimetres (chosen by the
  researcher, checked by a browser test, not yet used by hand). Simulation
  settings were re-examined on 2026-10-10 (ADR-058). What only the
  researcher can supply: the armature of the `scs0009` (measured, or a
  guess in `guessed:`), the servo figures at the voltage the servos really
  get, the size and cost of the board (`esp_wroom_32` has neither) and how
  it is fed from the battery, and the weight of the real prototype.
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
| `DECISIONS.md` | ADR log: every assumption (70 so far) |
| `docs/proposals/anatomical-leg.md` | Proposal for a three-segment leg (set aside 2026-10-04; not built) |
| `docs/USER_GUIDE.md` | How to use the lab |
| `docs/CHAT_GUIDE_PROMPT.md` | Prompt that makes a chat assistant a guide to the whole lab |
| `docs/CHAT_GUIDE_CHASSIS.md` | The same for one workflow: chassis parts from Rhino, real mass, own components, the small calf |
| `docs/CHAT_GUIDE_PROTOTYPE.md` | The same for one job: a small prototype already modelled in Rhino (PLA and steel rods) into the simulator; covers ADR-053 and the infill estimate of ADR-054, which `CHAT_GUIDE_CHASSIS.md` only points to |
| `docs/component_verification.csv` | Datasheet verification worksheet (the researcher fills it in) |
| `bridges/rhino/README.md`, `bridges/blender/README.md` | Bridge install, conventions, what is verified |
| `docs/notebooks/quickstart.ipynb` | Driving the lab from Python |

---

## 7. Recommended next sessions

Prefix each with the opening message from section 1.

**O. The feral calf: enter what I measured and re-check the belts**
> In projects/robot-calf-final: the STS3215 C018 output axis is <N> mm from
> the nearer end of the case; the parts weigh <horn, bearing, collar, plug,
> blocks, electronics, skin, hoof pad, belt, spring, 30T and 60T pulleys, or
> "not yet">; my joint ranges are <stifle, hock, shoulder, carpus, hip>.
> Enter them in config/feral_calf.yaml and catalog/pulleys.json (only what I
> give), rebuild, and show me every belt check that changed from unknown or
> fail. Say whether the hock can now take the 450 mm belt (C 179.7). Then
> re-run the load analysis and the belt comparison, and tell me in a table
> which belt system and pulley pair to buy, with the tension margins and
> which numbers still rest on PROVISIONAL or missing values.

**P. Model the feral calf in Rhino and simulate it**
> Pull projects/robot-calf-final into Rhino (CalflabPull), set up the model
> layers for its bodies (CalflabModelSetup), and make sure the belts,
> pulleys and the spring anchor points come across (draw the springs as
> curves on a layer of their own, read back from the scene's `springs`). I
> will model the blocks, fittings and collars. When I push with
> CalflabPushModel, the belt drives must keep their catalog C: if my joint
> lines put a joint elsewhere, tell me which belt no longer fits and refuse
> the push, rather than moving the servo. Extend bridges/rhino and its check
> script; update the user guide.

**R. A fitness for the feral calf and a first real evolution**
> The feral calf evolves with its belts fixed (ADR-070), but it is scored
> with the `walk` preset, made for the 5 kg calf (target 0.5 m/s). Write a
> preset for this body: slow steady walking without a fall, low servo load
> against rated torque, and belt tension under the allowable for most of
> the cycle (from the load analysis's numbers, computed in the core). Then
> run an evolution of a size you think worth it on projects/robot-calf-final
> and show me the archive: which proportions walk best, how far each
> belt-bound gene moved inside its allowed range, and how many candidates
> were infeasible and why. Do not change the belts.

**Q. Walking and rising that a real feral calf can do**
> The feral_motion walk is a slow open-loop crawl (17 mm/s, small stability
> margin) and lie/rise is a fixed script. Make the walk use the IMU (shift
> the body until the centre of mass is inside the support triangle before
> lifting a leg), add a slow trot, and make the rise from kneeling adapt to
> the body's pitch. Keep every joint inside its range and the belted joints
> inside 180 deg. Re-run the load analysis and tell me how belt tension and
> servo load change, and whether the spring settings should change with it.

**L. My real model in the simulator: read the result with me**
> I pushed my prototype with CalflabPushModel into
> projects/small-calf-two-joint (override "Rhino model") and pressed F5.
> Read the latest run's run.json and the push report (scene `geometry`):
> show me the joint table against the pulled calf's, the mass per body
> against what I weighed (<weights, or "not weighed yet">), where the centre
> of mass sits over the feet, and whether it stands, walks or falls with the
> current gait, in plain language. Then run *Tune for this body* on it and
> show before and after. Tell me which numbers rest on infill estimates,
> unverified components or the default armature.

**M. See the modelled robot in the web lab**
> The joint table and body list of a pushed model (ADR-062) are only in the
> Rhino printout and the scene payload. Add a Model panel to Form and
> Simulate (schema-driven, no logic in the UI): joints against the
> parametric skeleton, bodies with solids, materials, mass and hull count,
> feet, warnings; and draw the collision hulls and the foot contact points
> with the collision overlay. Move the hull vertices out of the document
> into the project's assets so the document stays small, with old documents
> still loading. Extend the Playwright test.

**N. Servos and electronics where they really are; joint ranges from the model**
> My model has no electronics, so servos, board and battery sit where the
> lab puts them (ADR-062). Let me place them: blocks or points on
> CALFLAB::Model tagged with the component's stable ID, used for the
> position of that component's mass. Then check my modelled parts against
> each other through each joint's range (which angle do they first touch
> at?) and offer those angles as the joint ranges, as overrides I can
> accept or not.

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

**J. Make the small servo honest in the simulator**
> For my SCS0009 I measured / decided: <armature in kg*m^2 or "time for an
> unloaded 60 degree step from rest: N s">, and the servos are wired
> <straight to the 2S pack / behind a 6 V regulator>. Enter what I give in
> config/components/actuators.yaml (a guess goes in `guessed:`; if I gave
> figures for 7.4 V make a second entry, do not edit the 6 V one), keep
> `verified: false`. Then decide with me whether the passive joint damping
> and friction of robot_defaults.yaml should become per-actuator values in
> the component entry instead of one number for every joint (ADR-058), with
> the default calf unchanged. Re-run *Tune for this body* and the
> proportion study in projects/small-calf-two-joint with Joint loss scale
> and Armature scale back at 1, and show me how the tables changed against
> studies 20261010-155806-study-1075 and 20261010-160303-study-b3c8.

**K. A controller that can bound, and one that holds a line**
> The CPG "bound" is an open-loop footfall pattern (ADR-059). Add a
> controller plugin (`calflab new-plugin controller ...`) that bounds with a
> flight phase: push-off and landing timed from trunk pitch and foot
> contact, parameters optimisable so *Tune for this body* and the
> proportion study can use it. Tell me first what it needs from the body
> (torque, speed) and whether eight SCS0009 can supply it at 378 g. Also
> give the CPG an optional yaw/roll correction from the IMU that works
> without hip abduction (stride length left/right), and show sideways drift
> with and without it for the two-joint body.

**I. Sensors per project; firmware for the chosen board; skin mass from sculpted skin**
> Boards are chosen per project (ADR-061); sensors are still those of
> config/robot_defaults.yaml for every project. My prototype has these
> sensors: <list, or "none">. Make the sensor set a per-project choice the
> way the boards are, with existing projects unchanged, and make the
> firmware skeleton export follow the chosen control board (tell me what you
> need from me for an ESP32 before writing anything). Then give a sculpted
> Skin push a mass from its own area x skin thickness, with the same
> open/closed honesty as structure solids (ADR-050).

**G. Make the elbow body the default**
> I have settled the front leg: joint facing backward, upper segment <N> mm,
> lower segment <N> mm, standing bend <N> deg, two motors (front_hip_flex
> off). Add front-specific genes for those three values (allowing an upper
> segment shorter than 100 mm if I asked for it), keep the hooves on the
> ground automatically, make this the default body for new projects with
> existing work unchanged (the `absent` mechanism of ADR-047), tune the
> default gait for it with tune_gait, and tell me speed, drift and the
> torque margins of the front abduction motors, which carry the lift.
