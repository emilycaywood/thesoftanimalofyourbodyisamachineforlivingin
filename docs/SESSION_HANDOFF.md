# CALFLAB session handoff

Everything a new Claude Code session (or a new collaborator) needs to pick up
CALFLAB. Last updated 2026-11-06 on branch `robot-calf-final` (cut from
`chassis-mass`), after session R9 (up to four STS3250 C002 servos, in simulation only, ADR-100), section 4
"Session R9"; before it sessions R7 (movement that varies within a movement, ADR-098) and R8 (faster joints, ADR-099),
section 4 "Sessions R7 and R8"; before them session R (a body for vigorous movement; steps 1-2 of 6
done, plus wider blocks and hip springs; steps 3-4 done; then redirected to behaviour diversity on the wide-block body: the first full run (ADR-094), session R6, three of its behaviours played for a minute (ADR-095), R6b, a coverage check that makes them hold for a minute (ADR-096), and R6c, durations capped at the checked length (ADR-097); section 4, "Session R", ADR-086..097); before it
session Q: the calf's movement read and interpreted as
the robot's own (section 4, "Added in session Q", ADR-085); before it session
P: clips judged in physics and made feasible
(section 4, "Added after session X2"; before it session X2: each leg's bend
over the window, repeated frames; session X: the hind Knee at the hock, clip
smoothing; the 3D lift and the review player; and session T: video inbox,
pose tracking, composition, repertoire evolution). Run `git log --oneline -12`
for the current state. `robot-calf-final` is pushed to GitHub as a backup (2026-11-05); `projects/*/runs` is not in git and exists only on this machine.

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

**Added after that (ADR-071):** the carpus is belted by default: 640 mm
belt, C 274.8 mm, servo 65 mm below the shoulder. `robot-calf-final` was
switched through the researcher's running lab. Its load runs, belt
comparison and test evolution predate this and were not re-run.

**Added after that (ADR-072):** toe-out and splay per pair of legs on
the feral calf (Form): fixed mount angles, nothing held by a servo; belts
unchanged; hooves regrounded. Default 0. The researcher's running lab needs
a restart to use them (core code changed).

**Added later on 2026-11-02 (researcher's requests: the trot back, and
infrastructure for stochastic behaviors from reference footage; ADR-073,
ADR-074):**

* `feral_motion` mode `trot`: diagonal pairs, IMU roll feedback through the
  hind ab/ad joints, about 0.30 m/s.
* Every feral_motion and behaviors command stays under 90 % of each servo's
  speed at its joint (`ControlInfo.speed_limit`). Before, the trot asked the
  belted carpi for 190 deg/s against 135, and the walk exceeded it too. Load
  analysis has a `trot` scenario.
* `calflab.behave`:
  * keypoint CSVs (DeepLabCut, long, wide) from `<project>/footage/`;
  * cleaning;
  * retargeting by map (`config/retarget/feral_calf_side.yaml`): the
    animal's change from a reference frame applied to the robot's standing
    pose;
  * the per-clip body report (range, servo speed, verdict);
  * a kinematic preview run.
* `controller:behaviors`: a seeded random repertoire (clips, idle sway,
  gaits) with weights or a transition table, random speed, amplitude and
  mirroring, cross-fades. Episodes go into the rollout. Clips are inlined by
  `Controller.resolve_params`, so workers have them.
* Imitation is a real fitness term (metric `tracking_rms_deg`); preset
  `behave`.
* Commands `import_footage`, `preview_clip`, `add_behavior`,
  `set_controller`; analysis `behave`. The Behave workspace is real
  (`LAYOUT_VERSION` 8).
* Checked with synthetic footage (the robot's own forward kinematics seen
  from the side): angles back within 0.6 deg (carpus 2.3).
* **No real footage has been through it yet.**
* `projects/robot-calf-final` is unchanged: its controller is still
  `feral_motion` walk.
* Tests: `tests/test_behave.py` (13), `web/e2e/behave.spec.ts`.

**Added after that (ADR-075):** a Controller list in Simulate (controllers
that cannot drive the body greyed, via `Controller.fits`). Switching
controllers keeps each one's settings in `settings.controller_params`. Asked
for after the trot seemed to vanish under the behaviors controller.

**Added 2026-11-03 (session T, the researcher's request: from a video in a
folder to behaviors an evolved body performs safely; ADR-076 to ADR-079).
All four stop points were built; nothing was handed off unfinished:**

* **Installed with the researcher's approval** (asked first, with
  comparison, sizes and licences):
  * `opencv-python-headless` 4.x and `onnxruntime-directml` 1.24, in the new
    optional extras `video` and `track` of `pyproject.toml`. `calflab.ps1`
    runs with `--all-extras`, so a normal setup installs them;
  * the RTMPose-m AP-10K and YOLOX-s weights (87 MB) in
    `C:\CALFLABHOME\models\`, which is not in git (`calflab tracker
    download`, SHA-256 checked).

  Licences: Apache-2.0 (MMPose, YOLOX), MIT (onnxruntime), AP-10K data
  CC-BY-4.0 (read in its README). The researcher chose option A of three
  (RTMPose AP-10K over DeepLabCut SuperAnimal and ViTPose++).
* **Video inbox** (ADR-076):
  * `<project>/footage/videos/` is created when the lab opens and polled
    every 2 s by a lab thread, which the server starts;
  * one processing job at a time;
  * status records with SHA-256 in `footage/inbox.json`;
  * tracks per hash in `footage/tracks/`;
  * frames and the real fps from the file (OpenCV, or a built-in AVI
    reader).

  Processing: track -> near side from the facing -> camera-view check ->
  retarget against the longest still stretch -> segmentation (idle / gait
  with period, cut to whole cycles / other).

  Review in the Behave panel:
  * the frame with tracked points drawn (served by the server);
  * a preview on the robot and the body report;
  * trim, accept (name + affect tags) or reject.

  Clips carry full provenance. Commands: `scan_footage`, `retry_video`,
  `cancel_video`, `preview_candidate`, `accept_candidate`,
  `reject_candidate`, `set_footage_settings`, `tag_clip`.
* **Pose trackers** (ADR-077):
  * new plugin type `pose_tracker` (contract, `new-plugin` template);
  * `csv` (the file beside the video);
  * `synthetic` (colour markers);
  * `rtmpose_ap10k` (YOLOX-s detector + RTMPose-m, DirectML on the AMD GPU,
    else CPU; checked against the model's own sample output).

  Map `ap10k_side` uses the model's actual names (from MMPose's AP-10K
  metainfo; the ONNX file has none). Maps can be written for either side
  (`{side}`) and are mirrored. CLI: `calflab tracker list | download |
  synthetic <out.avi>`.
* **Composition** (ADR-078):
  * affect tags on clips: valence, arousal, words, note, set only by the
    researcher; "not set" is shown as such, not 0;
  * clips chosen by tag in the behaviors repertoire;
  * composition parameters: tempo, amplitude, idle share, low-pass,
    repeat, pause;
  * an affect curve (keyframes, optional target valence/arousal that
    favours clips the researcher tagged near it), logged per episode;
  * movement features (labelled kinematics, not emotions);
  * a composition study job (run kind `composition`, table in Behave,
    CSV).

  The defaults leave every earlier behaviors rollout unchanged.
* **Repertoire evolution** (ADR-079):
  * preset `repertoire`: `imitation_required` + survival + stability, with
    an `evaluation:` block;
  * three seeds with friction 0.7-1.1 and mass x0.95-1.05, scored as mean
    minus spread;
  * torque derating 1.0;
  * safety constraints from the load analysis. The researcher's policy:
    reject stall and belt breaking, penalise the rest. Judged up to a
    fall; 2 s window;
  * candidates rejected for safety get status `unsafe`;
  * inner loop over per-clip speed and amplitude limits within the clip
    report's playable speed;
  * archive axes `expressive_range`, `quantity_of_motion`,
    `safety_margin`;
  * `estimate_evolve` (Evolve > *Estimate cost*, with *Use the small
    budget*);
  * Evolve shows the preset's evaluation and, per candidate, its seeds and
    safety table.

  Presets without `evaluation:` evolve exactly as before.
* Schema forms: an optional number shows "not set" with a clear button
  (`nullable` in the UI schema).
* Scratch project **`projects/_scratch-footage`** (not in git) holds the
  synthetic stick-calf video, two accepted clips, the behaviors controller
  with the walk clip required, preset `repertoire` and one small evolution
  (2 x 4). Launch entry `calflab-footage` (port 8030).
  `projects/robot-calf-final` and every other project were not touched.
* Tests:
  * `tests/test_footage.py` (10, one slow: RTMPose on a video);
  * `tests/test_composition.py` (6);
  * `tests/test_repertoire.py` (4, one slow: a tiny evolution);
  * `web/e2e/footage.spec.ts` (drop -> watcher -> review -> preview -> tag
    -> accept).

  `calflab test` passes: ruff, 430 pytest tests (default suite 128 s; the new modules add about 20 s), mypy, web typecheck and eslint, 14 Vitest, 11 Playwright tests.

**Added later on 2026-11-03 (the researcher's request after the first real
video: 3D motion from one camera; ADR-080, ADR-081). Nothing installed.**

* **3D lift** (`calflab.behave.lift`, ADR-080): per frame the robot's own
  skeleton (its forward kinematics and joint ranges) and a weak-perspective
  camera are fitted to the 2D keypoints of both sides. Proportions (trunk
  length, width, front leg against the hind leg), camera elevation and roll
  and where the tracker's Hip / Knee / Shoulder sit on the robot are fitted
  per video and reported. Width: the 0.35 W/L prior (PROVISIONAL) unless the
  footage clearly pins it.
* **Ambiguities recorded per frame**: toward/away (the depth flip, a
  two-state Viterbi on near-side confidence and continuity), limb flips (a
  second basin within a leg's ranges), joints the view cannot see, leg
  labels exchanged by the tracker.
* **Per-frame reliability** (residual px and body lengths, yaw, state,
  reasons) replaces "too oblique" in 3D; unreliable stretches over 10 frames
  are gaps for the segmentation.
* **Clips in 3D**: angles relative to the standing frame or, without one,
  the robot's standing pose; heading, pitch, roll and ground path in
  `root_quat` / `root_pos`; far legs `tracked` (a leg hidden most of the
  time takes its twin). The preview shows the turn; **the simulator does
  not steer to follow it**.
* **Mode per project** (`FootageSettings.mode`, Settings in the Video
  inbox): 3D for new projects; a project that processed videos before stays
  2D until switched. *Analyse again* (`reanalyse_video`) re-runs the analysis
  on stored tracks. Lifts in `footage/lift/<sha16>.json`.
* **Review**: a reliability strip with the yaw line under the frame slider,
  the 3D summary line, the body report as a table (ab/adduction included),
  the clip's turn and travel. Routes `/api/footage/<file>/lift` and
  `POST /api/footage/<file>/prefetch`.
* **Player fix** (ADR-081): `FrameCache` (open readers, 600 cached frames,
  read-ahead on a second reader); Play asks for the next frame only when the
  shown one has loaded. Measured in the lab's browser pane on the real
  video: 108 frames in 4 s (30 fps), where before it stayed on frame 0.
* **Maps**: `config/retarget/ap10k_3d.yaml` (AP-10K; your Knee/Elbow
  assumptions kept: hock tied to stifle, Elbow = carpus) and
  `feral_calf_3d.yaml` (the robot's own joints).
* **Synthetic 3D footage**: `synthetic_tracks_3d` (`Camera3D`, `Script3D`):
  the robot's forward kinematics from any camera yaw and elevation, with
  ab/adduction, a turn, proportions, noise and dropped points.
* **`projects/robot-calf-final`**: switched to 3D (the researcher asked for
  the real video in 3D) and its video analysed again: no "too oblique", 75 %
  reliable, yaw following the video (side view, a turn toward the camera up
  to 84 deg at the ball, side view), two candidates (0-108 turning 58 deg
  left; 156-225), camera elevation 7 deg. **2D on the same tracks gives
  exactly the record of before** (map, side, view, segmentation,
  candidates compared field by field). `projects/_scratch-footage` was not
  touched (its settings stay 2D).
* Tests: `tests/test_lift.py` (9, one slow: four camera yaws).
  `tests/test_footage.py` and `web/e2e/footage.spec.ts` now say `mode: 2d`
  (they test the side-view pipeline on fresh projects, which default to
  3D). The new fast tests add about 45 s to the default suite.
  `calflab test` passes: ruff, 440 pytest tests (default suite 223 s, slow
  ones apart; the slow four-yaw test passes on its own), mypy, web typecheck
  and eslint, 14 Vitest, 11 Playwright tests.

**Added at the end of 2026-11-03 (session X: untie the hind leg, smooth
what the tracker adds; ADR-082). Belts not touched:**

* **Project map** `projects/robot-calf-final/motions/maps/ap10k_3d_hock.yaml`:
  AP-10K's hind Knee exactly at the hock, the hock untied from the stifle;
  the rest as `ap10k_3d`. The project's Settings use it (`map_3d`); the
  video was analysed again in your running lab (port 8020) through its own
  commands.
* **Lifts kept per map** (`footage/lift/<sha16>.<map>.json`) and the
  command `compare_lift_maps file=<video>`: reliable/ambiguous shares and
  why, residual per landmark, proportions, hind angles over the frames both
  maps call reliable. Command line only, no panel.
* **On your video**, tied -> untied: reliable 75 -> 82 %, ambiguous 57 ->
  71 % (hind legs 34/21 -> 52/56 %), median residual 24 -> 19 px, hind paw
  residual 29/22 -> 13/12 px, hock now differs from the stifle by 23-25 deg
  RMS. The stifle reaches its -30 deg limit under both maps. Candidates
  are now 0-109 and 140-225 (were 0-108 and 156-225). Full table in
  ADR-082.
* **Clip smoothing** (`calflab.behave.smoothing`, Settings >
  *clip_smoothing*): zero-lag Butterworth on joint angles and the root,
  whole video before cutting, never past the raw range. `auto` (new
  projects) picks the cutoff by Winter's residual analysis; `lowpass` at a
  fixed Hz; `none`. Every clip records the setting, the cutoff and each
  joint's peak speed raw and smoothed (`meta.smoothing`). Older projects'
  settings load as `none`; `robot-calf-final` is set to `auto`, which
  chose **3.5 Hz** (noise 1.8 deg).
* **Playable speed of your two candidates**: 0-109: 0.29 (old map) -> 0.16
  (new map, raw) -> **0.39** (new map, auto); 140-225: 0.17 -> 0.14 ->
  **0.28**. Still limited by the left stifle (351 deg/s) and the left carpus
  (489 deg/s, at the ball). What remains is mostly the fit jumping between
  a leg's two bends on ambiguous frames, which smoothing only spreads out.
* **Your running lab** still runs the old core code: it analysed the video
  with the new map (map files are read when used), but it does not know the
  smoothing until restarted. Restart it before previewing or accepting.
* Tests: `tests/test_smoothing.py` (4) and additions to
  `tests/test_lift.py`. `calflab test` passes: ruff, 445 pytest tests
  (default suite 255 s), mypy, web typecheck and eslint, 14 Vitest, 11
  Playwright tests. (The first full run failed only on ruff's import order
  in the new test file; fixed, and ruff re-run on `core`, `server`, `tests`,
  `plugins`.)
* Not looked at in the browser: the two new fields in the inbox Settings
  form come from the command's schema, with no web code changed.

**Added after session X (session X2: settle the ambiguous legs; ADR-083).
Belts not touched. Nothing installed:**

* **Each leg's bend over the window** (`lift.bend_choice: window`, new
  projects; `frame` = as before):
  * per frame the fitted bend and up to two others (refined) are kept;
  * a Viterbi on fit and continuity chooses them over the whole video;
  * forward-backward margins say where the video cannot decide (then the
    leg is `ambiguous`).

  Lifts are kept as `<map>` (frame by frame) and `<map>.window`.
  `compare_lift_maps` adds per leg ambiguous share, second-bend share, jumps
  over 12 deg/frame, and the candidates' playable speed raw / smoothed /
  smoothed and re-timed (`ranges=`, `jump_deg=`).
* **On your video the window changed no bend.** Ambiguous 70.7 % -> 2.2 %
  (depth only; every leg 0 %). The old figure was mostly the frame test's
  coarse grid: 5 of 52 sampled "second bends" are real, and they lose by at
  least 10 chi-square over the window. The jumps were not bend flips.
* **The cause: 108 of 225 frames are repeats.** Your screen recording holds
  the source at about 15 fps in a 30 fps file. New
  `calflab.behave.timing` finds repeats in the images when a video is
  analysed (`repeated_frames: interpolate`, new projects; `keep` = as
  before), and clips are re-timed across them.
* Before -> window -> window + re-timed:
  * jumps hind L / R, fore L / R: 20 / 6, 20 / 15 (unchanged by the window)
    -> 15 / 1, 14 / 4;
  * residuals identical;
  * playable speed with auto smoothing: 0-109 0.39 -> 0.39 -> 0.36 (Winter
    now picks 4.0 Hz instead of 3.5: part of its "noise" was the stutter);
    140-225 0.28 -> 0.28 -> 0.28;
  * raw 0.16 -> 0.22 and 0.14 -> 0.14.

  Still limited by the left stifle (about 350-380 deg/s) and the left carpus
  at the ball (about 490 deg/s). Full table in ADR-083. ADR-082's diagnosis
  is marked wrong there.
* `projects/robot-calf-final/footage/settings.json` set to `window` and
  `interpolate`. **The video was not analysed again in the project**: your
  lab on port 8020 runs the old code. The numbers come from a scratch copy,
  `projects/_scratch-x2` (not in git; same tracks, document and settings),
  analysed through the lab's own commands. Restart the lab and press
  *Analyse again*: the result is the same (the lift is deterministic), and
  the frame-by-frame lift stays beside it as `ap10k_3d_hock`.
* Tests: `tests/test_bends.py` (5, one slow): chain vs brute force;
  known-bend footage (a test-only carpus that can bend either way, tracked
  weakly) where injected wrong bends are put back and the end-to-end lift
  holds the true bend; repeats in an AVI; re-timing. Additions to
  `tests/test_lift.py` and `tests/test_smoothing.py`.

**Added after session X2 (session P: clips judged in physics; ADR-084, finished). Belts, joint ranges and
component values not touched. Nothing installed:**

* **Play in physics** and **Make feasible**: buttons beside *Preview on robot* in the candidate review and on
  every clip row of the Behave panel. Commands `play_in_physics`, `adapt_clip`, `keep_adapted_clip`,
  `physics_report`. Runs: kind `physics` and kind `adapt`, both replayable.
* **Servo model:** the servos are limited by a torque-speed envelope taken from the library's stall torque and
  no-load speed. `torque` stays the default everywhere else, unchanged bit for bit.
* **The report:**
  * per joint: tracking, torque against rated and stall, speed, envelope, belt tension;
  * the constraints with your margin;
  * hooves on the ground against the plan;
  * the battery (a lower bound: no stall current);
  * a clickable time strip (it seeks the replay and the review frame);
  * what the numbers rest on.
* **Make feasible** plants the clip: supporting hooves still, at least three down (four if three falls), the
  centre of mass over them, planted ways in and out. It then slows, shrinks and smooths until every limit
  holds, and gives back what still holds.
* **Saved versions:** a library clip's version is saved as `<id>-feasible`; the original is never changed. A
  candidate's version stays in the run (*Keep adapted clip*).
* **Your two candidates are feasible at margin 0.2** (scratch copy `projects/_scratch-physics`, through the
  lab's commands). They are quasi-static sways that keep little character:

  | | c1 | c2 |
  |---|---|---|
  | as retargeted | falls at 2.4 s | falls at 1.5 s |
  | feasible version | 3.2x slower, a third of the amplitude | 3.6x slower, half the amplitude |
  | hooves | all four always down | all four always down |
  | character kept | 0.19 | 0.24 |
  | search | 7.7 min | 4.3 min |

  Full table in ADR-084.
* **Why three hooves were not enough for slowed clips:** slowed 3-4x, a clip must balance statically, and under a
  three-legged pose the position servos sag 2-13 deg, more than the tripod's balance margin. A larger margin did
  not help; four hooves down did. **This is not a limit of the body:** the robot's own trot and walk balance by
  timing and still run under the torque-speed servos, on fewer than three hooves 57-74 % of the time, without
  falling. Judged with margin 0.2 (for the first time), both gaits go over joint speed and the envelope, and the
  walk also over sustained torque. Table in ADR-084.
* **Armature x0.2:** the falls barely move. c1's version still holds; **c2's goes over sustained belt tension**
  (margin 0.08 -> -0.12).
* **Tests:**
  * `tests/test_physics.py` (9, two slow);
  * `web/e2e/physics.spec.ts`;
  * the torque model checked bit for bit against b538a0e.

  `calflab test` passes: ruff, 463 pytest tests (slow ones included, 8 min), mypy, web typecheck and eslint, 14 Vitest, 12 Playwright tests.
* `projects/robot-calf-final` was not touched. **Your lab on port 8020 runs older code**: restart it before
  using the new buttons.

**Added after session P: four more videos.** `Recording 2026-11-03 213333.mp4`, `213625.mp4`, `213904.mp4` and
`214239.mp4` were processed through the inbox in `projects/robot-calf-final` (3D, the project's settings; the lab
on port 8020 was not running). All need review; `213625` has a broken fit and `214239` legs exchanged by the
tracker in 61 % of frames. Details in next session Q (section 7).

**Added in session Q (interpretation, not copy; ADR-085). Belts, joint ranges and component values not touched.
Nothing installed. `adapt_clip` kept as a diagnostic:**

* **The footage, looked at on the frames:**
  * **214239**: the calf faces the camera in a front quarter view; the lift had chosen the turned-away mirror (the
    side-confidence cue fails when both sides are visible). Lift maps may now name `face` landmarks (the eyes; in
    `ap10k_3d` and your `ap10k_3d_hock`): a seen face favours "toward" beyond 20 deg of yaw. Now yaw +30, frames
    0-~100 read as the tracker's leg labels exchanged (they are: opposite to its eye labels). 111941, 213333 and
    213904 lift **bit for bit as before**. Re-analysed in the project (`reanalyse_video`, 214239 and 213625).
  * **213625: unusable**, with the reason recorded: a ~93 px calf bucking at a panning hand-held camera, 64 %
    unreliable. Its 364 deg "turn" was a heading unwrapped through unreliable frames: turns are now summed only
    between reliable frames (reading and inbox candidates).
  * **At least four different calves** (Jersey with a ball; dark red calf; Hereford cross; tan calf).
  * **The camera moves** in 111941, 213333, 213904 (2-5 body lengths/s of ground shift, measured): travel is not
    read there, turns are.
* **Reading** (`read_footage`, `reading_report`; `footage/readings/<id>.json`, schema version 1): stand, weight
  shift, step, walk, turn, other (fast), each stretch with rule, features, confidence; contact from the paws'
  speed over the ground (lifted hoof heights drift 70-90 mm while the paws stand still); character per behaviour;
  a semi-Markov model with per-video counts; a support statement; the gaps. `read_footage synthetic=[...]` reads a
  known sequence (no footage needed).
* **What your 28.5 s carry:** 21.1 s read; 8 stretches: other/fast 5 (55 %), stand 2 (31 %), step 1 (14 %); 2
  transitions. Enough for which behaviours and their rough character; not for transition probabilities or
  duration distributions.
* **Vocabulary**: new plugin type `motion_primitive` (contract, template): `stand`, `weight_shift`, `step` (poses
  solved with every hoof planted, centre of mass inside the tripod; controller `weight_shift`), `walk`, `turn`
  (feral_motion `stride`/`turn`, defaults unchanged bit for bit), `trot`, `lie_rise`. **Turning in place hardly
  works on this body** (0.6 deg/s, over several limits).
* **Interpretation** (`interpret_footage`, `interpretation_report`, run kind `interpret`): per behaviour a CMA-ES
  (8 x 8) over each candidate primitive, played in physics with torque-speed servos and read back by the same
  reader; the closest within every limit with margin 0.2 + 0.05. Record per feature: kept / exaggerated / reduced /
  reversed / dropped, with the limit that stopped it. Cached per body (`.cache/interpret`).
* **Performance**: controller `interpreted` draws behaviours, durations and parameters (only slower and smaller)
  from the model; switches only at safe phases.
* **Results on robot-calf-final** (runs `20261104-042001-interpret-4d7f` and `-042426-interpret-ef3c`, margin 0.2;
  table in ADR-085):
  * stand -> a small weight shift (margin 0.84): roll and pitch kept;
  * step -> a slow step on three hooves (0.28): rate, amplitude and sway reduced, held back by sustained servo torque;
  * fast play -> a slow trot (0.71): turn kept, tempo slower; vigour, pitch and heave dropped (closer candidates over
    sustained torque, joint speed, envelope, belts). With the first, smaller budget (6 x 3) neither step nor trot had a
    candidate within limits: the default is now 8 x 8;
  * the gaits as they are: walk margin -2.48, trot -1.2; no walk variant held;
  * **transitions played in physics**: stand -> step, trot -> stand and trot -> step go over sustained shoulder torque
    (the shift and step poses are solved over standing hooves; a trot leaves them spread): dropped;
  * **performance**: 3 x 60 s within every limit, no fall, but once trotting there is no way out: 95 % trot (calf 55 %
    fast, 31 % stand, 14 % step). Before transitions were checked: 42 / 22 / 36 % and over sustained torque in every
    seed. **The vocabulary lacks a trot that stops on square hooves** (Q4).
  * Cost per body at 8 x 8: about 10 min of physics uncached, 44 s cached.
* **Behave panel**: section *Interpretation* (Read footage, Interpret) shows the stored report: support, a time strip
  (calf stretches per video, click opens the frames in the Review; robot episodes and limits per seed, click seeks
  the replay), shares, durations, transitions, features, the records, the gaits as they are and interpreted, the
  performances, the gaps, ADR-084's character scores.
* Tests: `tests/test_reading.py` (7), `tests/test_primitives.py` (12), `tests/test_interpret.py` (4),
  `web/e2e/interpret.spec.ts`. `calflab test` passes: ruff, 502 pytest tests (7.6 min), mypy, web typecheck and eslint, 14 Vitest, 13 Playwright tests.
* Launch entry `calflab-q`: scratch copy `projects/_scratch-q` (not in git).

**Session R (a body for vigorous movement within margin 0.2; ADR-086). In progress: steps 1-3 of 6 done, plus
wider blocks and hip springs (ADR-089); step 4's first run done (ADR-091); stopped for the researcher.** Belts, joint ranges and the servo's
values not touched; nothing installed.

* The request (six steps, a stop after each) commits the body to the ten STS3215 C018 servos and carbon fibre leg
  tubes. **The tube's outer diameter, wall and g/m were placeholders in the message**: `carbon_fibre_leg_tube` is
  in `config/components/materials.yaml`. **Later the researcher confirmed the tube already in use** ("The leg
  tube is correct", ADR-088): 15 x 12 mm, 1.55 g/cm3 entered (unverified, not weighed); tube genes no longer
  PROVISIONAL. The two 3S packs are **in parallel** (confirmed). Joint stops: the researcher did not know the term;
  the robot is unbuilt, so evolution may only narrow today's ranges (ADR-088). Pulley pairs: anything easily
  bought is allowed; I found GT2 10 mm pulleys listed from 20T to 120T (ADR-088), none added to the catalog yet.
* **Step 1 (what the failures rest on)**: `docs/studies/sensitivity_r1.md` (script `sensitivity_r1.py`, scratch
  copy `projects/_scratch-r`, about 2 min of physics). Summary in ADR-086:
  * walk (-2.48) and trot (-1.2) fail on sustained hip ab/ad torque whatever mass, armature, springs or servo
    torque within the ranges: the gaits/stance, not the unknowns;
  * the interpreted trot (+0.71) holds up to mass x1.2 and 10.5 V; fails at rated torque x0.8 or springs x1.5;
  * **the interpreted step (+0.28) fails with 130 g more mass, or with the servo's figures scaled to 11.1 V**
    (fr.shoulder sustained): its verdict rests on the missing masses and the servo at the battery's voltage;
  * armature decides nothing; stiffer springs load the stifle belts (the springs are not gravity compensation).
* Assumed (ADR-086): uniform mass scaling, servo figures linear in voltage, the two 3S packs in parallel.
* **Step 2 (where the load goes)**: `docs/studies/load_r2.md` (scripts `load_r2.py`, `levers_r2.py`). ADR-087:
  * the gaits fail on **the weight**: the hip ab/ad's sustained torque is static, because the legs are splayed
    (hind 12, front 10.5 deg) and nothing at the hip carries it; the walk stands on two hooves 73 % of the time;
  * **the springs over-compensate** (181 / 192 / 365 % of the weight at stifle / hock / shoulder);
  * **both splays 0** take the walk to -0.13 and the trot to -0.16; with springs as gravity compensation the trot is
    over joint speed only (-0.04); what is left is the gaits' speed (per-candidate tuning in step 4);
  * belt ratio: the catalog has only 2:1 pulley pairs; leg angles and crouch do not help; front angle is solved.
* **Wider blocks and hip springs (ADR-089)**, the researcher's choice to keep the hooves wide for stability:
  genes `hip_block_widen` / `chest_block_widen` (mm per side) and `spring_hip_abd` (+ rate, free length, anchors;
  off by default). Old genomes build as before. `docs/studies/width_r2c.md`: with hooves at today's width on
  straight legs the walk passes every torque/belt/envelope limit (-2.48 -> -0.13, joint speed only); half splay +
  half widening + hip springs equally good; hip springs alone do not rescue full splay (-1.56); **the trot as it is
  gets worse on wide blocks** (-1.8: stifles x2, shoulders x3; the diagonal support line moves off the centre of
  mass) and needs re-tuning per body.
* Hoof width: the researcher chose "Let it evolve" (no floor; descriptor `hoof_width` to look at it).
* **Step 3 (vigour preset)**, ADR-090, `docs/studies/vigour_r3.md`: `config/fitness/vigour.yaml` +
  `calflab.evolve.vigour`: a body plays walk, trot and the interpretation's stand, step and fast play, each
  searched for it (CMA-ES 4 x 2, cached per body), the best within limits verified on 3 randomised seeds. Fitness
  = mean kept share - shortfall of the worst margin below 0 (limits already x0.8). Archive axes `vigour_kept` x
  `worst_margin`. Splays and block widths now evolvable. Today's body: vigour 0.315, worst -0.44, fitness -0.125;
  wide blocks + half splay + hip springs: 0.517, -0.28, +0.237 (walk keeps 0.75 within limits, trot still over
  torque). About 60 plays, 64-84 s per body; 6 x 8 at 2 x 4 = about 0.3 h on 7 workers.
* **Step 4, first run** (ADR-091, `docs/studies/evolve_r4.md`, run `20261104-162051-evolve-d1b6`, 6 x 8, 2 x 4,
  818 s). The project document now has `spring_hip_abd: true` and fitness preset `vigour` (both undoable
  commands). 13 / 48 were infeasible (11 front legs too short for a level back, 2 hock belt clearance). Best:
  fitness +0.228, vigour 0.36, worst -0.13; trot, stand, step and fast play within limits on 3 seeds, the walk
  not. No body keeps the walk. The search stayed near the start (blocks widened at most 18 / 39 mm), so step 3's
  hand-made body E (vigour 0.517) is still better.
* **Redirected (ADR-092)**: the researcher asked whether the work was losing its focus on new, unprogrammed
  behaviour. The wide-block body (E) is now the project's working body (one `set_genes`), and steps 5-6 are set
  aside.
* **Behaviour diversity (ADR-093)**: `calflab.evolve.diversity`, optimizer `map_elites_behaviour`, preset
  `diversity`.
  * Body fixed. A 53-gene generator decodes into an `interpreted` chain over a palette: stand, weight shifts,
    steps, walk, trot, turn, parameters free.
  * 24 s on 3 randomised seeds at margin 0.2. Axes: quantity of motion (0-15 deg/s) x tempo regularity.
  * Safe always beats unsafe; within that, headroom + 0.5 x unpredictability.
  * Each state is first searched alone for a setting within the limits. The steps and the trot have none on
    this body.
  * Joint speed commanded at 0.76 of the servo's.
  * Trial 3 x 14 (180 s): 3 safe cells. The project's fitness node is now `diversity` (`set_node_params`).
* **First full run (ADR-094, `docs/studies/diversity_r5.md`, run `20261104-181642-evolve-2650`, 20 x 28,
  1480 s).** 30 of 560 safe, 16 safe cells of 58.
  * Safe region: QoM 1.3-6.9 deg/s, regularity 0.21-0.80, unpredictability up to 0.78.
  * Bounded by sustained servo torque. Trot and steps almost never safe.
  * Three cells picked to play at 60 s: (0,5) calm, (2,2) irregular, (4,6) active.
* **Assessment (2026-11-04, with the researcher): how organic is it?** Partly successful.
  * Works: unscripted sequences, judged in full physics, within the limits, varied from still to ambling.
  * Falls short:
    1. Vigour: the most active safe behaviour is 6.9 deg/s; the calf stands at 3.0, steps at 18.3 and plays at
       76.8. The ceiling is the servos' sustained torque.
    2. The primitives themselves are hand-written: nothing within a movement evolves.
    3. Switches come only at all-hooves-down moments, with a fixed cross-fade.
    4. "Organic" is so far only kinematic proxies. Nothing has been watched yet.
    5. The body was fixed during the run.
  * Next, in order: R6 (watch three performances); then R7 (movement quality, software) or R8 (vigour,
    hardware), depending on what the researcher sees.
* **Session R6 (ADR-095, `docs/studies/perform_r6.md`, script `perform_r6.py`): the three picked cells played
  for 60 s on three seeds.** The run's 24 s evaluation re-runs to the fourth decimal.
  * **2 of 9 minutes stay within every limit** (calm seed 0, closest limit joint speed at the hl.hock, +0.76;
    irregular seed 2, sustained belt tension at the fr.carpus, +0.08). None fell.
  * **60 s does not stay within what 24 s did.** All nine were within the limits over their first 24 s. Seven go
    over later, each starting in a **step** (no safe setting of its own, ADR-093): sustained servo torque at the
    opposite front shoulder, or the fr.carpus belt. A 24 s evaluation under-samples a chain's rare states.
  * The nine minutes are runs of kind `sim` titled `R6 ...` (Journal or Simulate > Runs; click to replay).
* **Session R6b (ADR-096, `docs/studies/coverage_r6b.md`): coverage.** Optimizer option `coverage`: a candidate
  that passes its seeds also plays, forced, every state at least 5 % likely in a minute that its seeds did not
  finish, on every seed. Tried against 60 s evaluations and dropping the steps on the R6 behaviours; the
  researcher chose coverage with every state kept.
  * Run `20261105-024409-evolve-7a63` (20 x 28, 2330 s): **6 safe cells** (R5: 16), QoM 2.2-5.8 deg/s. A step
    and the trot are safe in context for the first time.
  * **15 of 18 one-minute performances of them stay within every limit** (R6: 2 of 9). Runs `R6 <label> ...`
    for calm, irregular, stepping, trotting, walking, active.
  * The 3 that go over are episodes drawn longer than the length coverage checked (its 90th percentile).
    Next: cap durations at the checked length (R6c).
* **Session R6c (ADR-097, `docs/studies/coverage_r6c.md`): durations capped at the checked length.** Option
  `cap_durations`: no state is held longer than coverage checks it (its 90th percentile, 1.67x typical), and
  coverage then forces every likely state at the cap.
  * Run `20261105-053201-evolve-e4c8` (20 x 28, 1715 s): **4 safe cells**, quantity of motion 2.1-10.0 deg/s,
    above R5's 6.9; three trot. (A first start, `20261105-044708-evolve-e577`, stopped after 9 generations when
    the session ended: marked cancelled.)
  * **12 of 12 one-minute performances hold.** Over 5 minutes (seed 0) **1 of 4 holds** (lively): the others go
    over in turns entered from a walk or trot, where coverage checked the turn from a stand or shift, or in a turn
    too rare for a one-minute check. Next: cover transitions (R6d).
  * Runs `R6c <label> ...`: 12 of 60 s, 4 of 300 s.
* Next: R7, then R8 (the researcher's order, 2026-11-05), in section 7; R6d later.

**Sessions R7 and R8 (2026-11-05; ADR-098, ADR-099). Body, belts, catalogs and component values not changed;
nothing installed.**

* Tests: `calflab test` after R7/R8: ruff, mypy, web typecheck and eslint, 14 Vitest, 13 Playwright pass; pytest 533
  passed and 1 failed (an architecture rule: a degree conversion outside `calflab.units`), fixed and re-run
  (`tests/test_architecture.py`, `tests/test_variation.py`, 9 new tests); the full pytest was not re-run after it.

* **R7, variation within a movement** (`docs/studies/variation_r7.md`): `calflab.control.variation` and the
  `interpreted` controller's `variation` block; optimizer options `vary_within`, `variation_weight`,
  `start_vectors`, `start_within`. Posture drift and noise (trunk height, weight over the hooves; head only with
  neck motors, which the feral calf lacks), per-cycle tempo and amplitude, switches before all hooves are down,
  varying cross-fades; coverage plays the checked state's extremes. Off by default; old runs replay bit for bit.
  * Run `20261105-221840-evolve-02e3` (the chosen 40 x 28, from random generators): **no safe cell**. Diagnosed:
    every state played its extremes (now only the checked one), the sequences themselves did not hold, and nothing
    rewarded variation (now `variation_weight`).
  * Run `20261105-232649-evolve-4237` (15 x 28, seeded from R6c's four safe generators): **7 safe cells** (R6c 4).
    The variation that holds is small (about 8 % of its ranges: +-2.5 % tempo and amplitude per cycle; posture
    invisible).
  * **20 of 21 one-minute performances hold** (the one over plays a step coverage never checked, 1.4 % likely).
    Means unchanged; **repeats of a walk or trot now differ** (repeat dissimilarity 0.007-0.03 -> 0.12-1.46),
    mostly in timing.
  * **5 minutes: 3 of 7 hold** (R6c 1 of 4); like for like the same. The variation neither closes nor widens R6d.
  * **Side by side:** `http://localhost:8020/compare.html?a=<run>&b=<run>`; `?replay=<run>` opens the lab replaying
    a run. A table of 21 ready links (R6c left, R7 right) is in `variation_r7.md`. Runs `R7 <label> ...`.
* **R8, faster joints** (`docs/studies/joints_r8.md`, simulation only, what-ifs on an in-memory spec):
  * The front carpi bind on joint speed in every motion; in a quick trot also the hocks (speed) and the hip ab/ad
    (sustained torque). The stifles have room.
  * **Carpi at 1:1 on a 45T/45T pair and hocks at 1.5:1 (30T/45T): a 0.6 s trot within every limit at margin 0.2
    on three randomised seeds** (+0.16, 130-137 mm/s; today 77 mm/s at 1.2 s), and the walk and turn pass too.
  * 1:1 with today's 30T driver moves the carpus onto belt tension; a 2:1 hip ab/ad belt costs the walk; stiffer
    hip springs and 10 % less mass do not help.
  * Not added to the catalog (needs your go-ahead): 30T and 45T GT2 10 mm pulleys are listed commercially.
    Belt lengths, derived C, fit and pulley masses for those pairs are not checked; nor is `lie_rise`.

**Session R9 (2026-11-06; ADR-100): up to four STS3250 C002 servos, simulation only.** The working body, belts,
catalogs, other component values and `verified` flags were not changed; nothing installed.

* **New library entry `sts3250_c002`** (`config/components/actuators.yaml`, unverified), with only the
  researcher's 12 V values:
  * 74.5 g; 4.9 / 1.57 N*m stall / rated; 4.2 A; 0.133 s / 60 deg; 1/345;
  * armature, idle current, winding resistance, thermal values, encoder and cost null ("default assumed" /
    "unknown");
  * voltage range, spline, dual shaft and the third-party 0.129 s in `notes`.

  It is on no body. `tests/test_sts3250.py` (2).
* Tests: `calflab test` passes (ruff; 536 pytest in 457 s, slower than the usual budget, while the researcher's lab
  was running on port 8020; mypy; web typecheck and eslint; 14 Vitest; 13 Playwright).
* Study `docs/studies/servos_r9.md`. Scripts:
  * `servos_r9.py`: what-if bodies, the trot grid, walk and turn on three seeds, belt peaks, current;
  * `belts_r9.py`: which catalog belts fit each catalog pulley pair;
  * `perform_r9.py`: R6c/R7 behaviours on a what-if body;
  * `*_table.py`: the tables.
* **Servos alone on today's belts: a 1.0 s trot at best** (new carpi). Then the 30T carpus belt binds on sustained
  tension. Stifles + carpi is the only assignment whose walk and turn pass on every seed. That does not beat R8.
* **R8's body is better than R8 reported**: re-run down to 0.4 s, it trots within every limit at 0.5 s / 1.0,
  208 mm/s.
* **Best body: new servos on hip ab/ad and hocks; carpi 1:1 on 45T/45T (old servo); stifles and hocks on the
  catalog's 40T/80T** (444 mm, C 161.5; 400 mm, C 139.4; every belt check passes).
  * 0.5 s / stride 2.0 trot at 394 mm/s, and 0.4 s at 283-286 mm/s, within every limit on three seeds; walk and
    turn pass with more margin than R8's body.
  * It needs one new pulley size (45T, four pulleys), not R8's hock pair.
  * Without new pulleys the best is a 0.8 s trot at 46-70 mm/s.
* Belt peaks within limits up to 79 N (breaking check 172 N). The new servos draw up to 2.1 A peak. The C018s'
  current and the packs' rating are not entered: the packs' load is unknown.
* At 11.1 V the best body keeps 0.5 s / 1.5 at 300 mm/s and the walk; its turn is -0.01 on one seed.
* **R6c's and R7's behaviours on the best body: 20 of 33 minutes hold** (today 32 of 33). Calm ones go over on the
  1:1 carpus's sustained torque. Where they hold, headroom rises from about +0.02 to +0.4. They need evolving again
  on such a body.
* 66 replayable runs `R9 what-if (...) <label> ...`: 33 on the best body, 33 on it without the hock 40T/80T. Their
  stored genome builds the working body (USER_GUIDE, "What-if runs").
* **Found:** the feral calf has one `actuator` gene for all ten servos, so a mixed body cannot be built yet. It
  needs a servo choice per pair: a genome change with a migration (next session R10).

**Scaffolded only (interfaces + tests, no behaviour):** PPO training, MJX
simulator, RemoteSSH and CloudNotebook transports (job bundling is real),
imitation reward, interactive selection, molds, skin patterns, nesting,
system ID, touch response, puppeteering blend, ball joints. UI placeholders:
the Deploy workspace, reference images, inertia / heat-map /
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

**The researcher must verify (new in session R9, ADR-100):**

* **The `sts3250_c002` entry** against the datasheet: every value; whether 4.9 N*m (50 kg.cm) and 1.57 N*m are
  at the output at 12 V; idle current, armature and thermal values if you have them; stall current of the C018
  (without it the packs' load stays unknown); the packs' discharge rating.
* **Whether the real servo is stiffer**: the simulator sets a servo's position gain from its stall torque, so the
  STS3250 acts 1.67x stiffer, which raises belt peaks. Its firmware P gain decides that on the robot.
* **Watch the best body** (Journal > Runs, `R9 what-if (new: hip_abd+hock | carpus 1:1 45T | stifle 40T-80T |
  hock 40T-80T 400) ...`): lively, ambling, trot-walk and trotting hold. Calm goes over at the carpus.
* **Pulleys**: whether to add 45T GT2 10 mm pulleys (with sources) for a 1:1 carpus. Whether an 80T pulley
  (50.9 mm) fits at the stifle and hock, and a 45T at the carpus, clear of the leg and the other belt. Pulley masses.
* **The trade at the carpus**: 1:1 doubles its speed but halves its torque, and the calm behaviours and probably
  `lie_rise` need that torque. Decide whether the carpus may change, and to what (1:1, 1.5:1, or 2:1 with new
  carpi and different servos elsewhere).
* **The 66 what-if runs** (about 100 MB in `projects/robot-calf-final/runs`): keep, or delete the 33 without the
  hock pair.

**The researcher must verify (new in sessions R7 and R8, ADR-098, ADR-099):**

* **Watch R7 against R6c side by side** (start the lab on port 8020, open the links in
  `docs/studies/variation_r7.md`). For calm, lively and trotting both sides play the same states in the same
  order; only the movement within them differs. Is the timing variation visible, and does it read as organic?
* Whether the variation should be allowed to be larger at the cost of margin, or checked differently: within
  margin 0.2 and coverage at the extremes, it stayed at about 8 % of its ranges.
* The variation's ranges (PROVISIONAL): crouch 15 mm, weight shift 0.3, head 8 deg, tempo and amplitude 25 %,
  switch slack 15 % of a cycle, cross-fade x / 2.2.
* **R8:** whether to add GT2 10 mm pulleys to the catalog for a 1:1 carpus (45T/45T) and a 1.5:1 hock (30T/45T),
  with sources; then the belt lengths that fit them, their masses, and whether a 45T pulley fits at the carpus.

**The researcher must verify (new in session R6c, ADR-097):**

* **Watch the four R6c behaviours** (Journal > Runs, `R6c calm`, `R6c lively`, `R6c walking`, `R6c trotting`;
  60 s and 300 s): the first safe trotting at about 10 deg/s. Does the capped timing still look organic?
* The cap at the 90th percentile (1.67x typical): keep, or check at a higher quantile (more spread, more cost).

**The researcher must verify (new in session R6b, ADR-096):**

* **Watch the six new behaviours** (Journal > Runs, `R6 calm (1, 4)`, `R6 irregular (1, 2)`, `R6 stepping`,
  `R6 trotting`, `R6 walking`, `R6 active`): the calm one steps, the trotting one trots on seed 1.
* The coverage choices: 5 % per minute, 60 s, the 90th-percentile hold, the path into a state.
* The cost of strictness: R5's calmest (1.3 deg/s) and most irregular (0.21) cells are gone.

**The researcher must verify (new in session R6, ADR-095):**

* **Watch the nine minutes** (lab on port 8020, Journal > Runs, rows `R6 ...`): do the calm, irregular and active
  behaviours look organic? Which falls short: the movement within a primitive (R7) or vigour (R8)?
* The finding that the steps make a minute unsafe: decide whether the archive should be judged at 60 s, require
  every reachable state to have been played, or leave steps out until Q4 gives a safe step (R6b).

**The researcher must verify (new in session Q, ADR-085):**

* **Restart the lab on port 8020**, open Behave > *Interpretation*: the stored report of run `20261104-042426-interpret-ef3c` is there. Click a
  calf stretch: the Review should open at its first frame.
* **The reading against what you see**: the 8 stretches (time strip). Are 111941, 213333, 213904 really fast play
  (other), 214239 a stand, a hop, a step and a stand? Tell me where a stretch really starts and ends: the thresholds
  are first guesses (`ReadingSettings`).
* **214239 frames 0-100**: the tracker labels the legs opposite to the eyes there (the lift now reads them as
  exchanged). Look at frames 0 and 112 with points drawn.
* **213625 left out**: say if you would rather keep its few reliable frames.
* **The four calves**: is any pair the same animal?
* **The interpretation's choices**: feature weights, kept = 0.8-1.25x, the 0.05 buffer, parameters varied only
  slower and smaller, tempo 1:1 (no scaling for size), the freed leg from the calf's lean.
* **Watch the performance** (replay of the run, seed 0): a slow trot for the whole minute, within every limit.
  With these servos (unverified, 1.3 kg as entered) and margin 0.2 the calf's vigour, pitch and heave are out of
  reach and the trot cannot yet stop (Q4). P3 (sensitivity) tells which missing value would change that most.

**The researcher must verify (new in session P, ADR-084):**

* **Restart the lab on port 8020**, open Behave, and on c1 and c2 press *Play in physics* and *Make feasible*.
  The results should match ADR-084: the search is deterministic; each takes 4-8 minutes.
* **Watch the feasible versions in the viewport** and judge the character yourself. The lab's "character kept"
  (0.19 / 0.24) is a movement measure, not a reading of the calf's mood. Say whether a quasi-static sway on four
  planted hooves is worth keeping, or whether stepping (next session P2) should come first.
* **The values the results rest on:**
  * the missing masses (14 parts at 0 g; 1.30 kg as entered);
  * the STS3215 C018's stall current (none: battery current is a lower bound);
  * its armature (the library default 0.005 kg*m^2, x4 behind a 2:1 belt). c2's version fails at x0.2;
  * the PROVISIONAL joint ranges and springs.
* **The search's choices:**
  * stance weights 5 deg / 0.2 mm;
  * the 15 mm stability margin and 15 mm lift threshold (PROVISIONAL);
  * braking allowed up to stall;
  * the definition of character kept;
  * greedy steps (not an optimum).
* The Behave panel by hand: a Playwright test and nobody else has clicked it.

**The researcher must verify (new in session X2, ADR-083):**

* **Restart the lab on port 8020 and press *Analyse again*** on your video;
  then `compare_lift_maps file="Recording 2026-11-03 111941.mp4"
  ranges=[[0,109],[140,225]]` should give the table of ADR-083.
* **The repeats**: step through frames 40-46 in Review. 41, 42, 43 and 44
  should be one image, then the calf jumps. If your original video (not the
  screen recording) is at hand, drop that instead: it has no repeats.
* **The fast frames**: whether the left stifle's swing in 0-109 and the left
  carpus folding at the ball in 140-225 are the calf or the tracker. These
  now set the playable speed.
* **Re-timing as the default**: with auto smoothing it lowered the first
  candidate's playable speed (0.39 -> 0.36, because Winter's cutoff rose).
  It is the honest timing; say if you would rather keep every frame
  (`set_footage_settings repeated_frames=keep`).
* The thresholds: `bend_margin` 4 chi-square, other bends more than 20 deg
  away; repeats below 0.15 x the 90th-percentile frame difference, runs of
  up to 3.

**The researcher must verify (new in session X, ADR-082):**

* **The Knee exactly at the hock** on a few frames of your video (Review:
  the orange L/R_Knee points against the calf's hocks).
* **The hind angles** of the untied map against what you see: the hock now
  bends on its own (mean 9-13 deg flexed, sd 10-13 deg), the stifle swings
  -30..+30 deg and sits at its PROVISIONAL -30 deg limit in about 5 % of
  reliable frames.
* **More frames are ambiguous** with the hock free (71 %, mostly hind legs).
  Say whether a stronger continuity choice for ambiguous legs is the next
  step (session X2 below).
* **The smoothing method**: `auto` (Winter, one cutoff per video, all
  joints pooled) and "no new extremes" are my choices; 6 Hz for `lowpass` is
  the human-gait convention, not a calf measurement.
* Restart the lab on port 8020 before previewing or accepting candidates.

**The researcher must verify (new with the 3D lift, ADR-080):**

* **The yaw strip against what you see** in Review for your video (the lab
  says a side view for the first 2.6 s, a turn toward the camera up to 84
  deg around frames 100-140, a side view at the end).
* **Knee and Elbow**: on your first video AP-10K's "Knee" sits on the
  calf's **hock** and "Elbow" on its **carpus**. Done in session X for this
  project (`ap10k_3d_hock`); `ap10k_3d` itself keeps the tie.
* **Hip and Shoulder sit well down the leg** on a calf (fitted 0.60 down
  the femur, 0.42 down the upper leg); check on a few frames.
* The PROVISIONAL values: width/length 0.35 (used for your video), 60 deg
  field of view (travel toward/away only), and the thresholds (70 deg from
  a side view, residual 2 x the video's median or 0.12 body lengths, 6
  points, 10-frame gaps, the 4-unit limb ambiguity test).
* **"Ambiguous" is frequent on real footage** (57 % of your frames, mostly
  a leg whose other bend fits within the 24 px noise). Say if you want it
  stricter.
* **Peak joint speeds** of real clips include tracker noise: clip
  smoothing (session X) removes the jitter, not limb-flip jumps.
* The camera must stay still: a pan or zoom reads as the calf turning or
  approaching (your screen recording shows some of both, frames 120-160).

**The researcher must verify (new on 2026-11-03):**

* **Tracker accuracy on your own footage.** No real video has been through
  RTMPose here; it was checked only on the model's sample image (a person)
  and on the synthetic stick calf (where it finds no animal, as expected).
  Look at the points drawn on your frames in the review.
* **Which joints AP-10K means on a calf**: its "Knee" on the hind leg
  (stifle or hock?) and "Elbow" on the fore leg. The map `ap10k_side`
  splits the hind fold half and half between stifle and hock and takes the
  carpus from the fore "Elbow": edit it once you have seen your footage.
* **The segmentation's cuts** on real video. Thresholds (still under
  0.05 body lengths/s and 8 deg/s, periodicity 0.4, 2 cycles, 0.6 s runs)
  are first guesses tested only on synthetic footage.
* **The camera-view check** assumes a calf's trunk is 0.35 times as wide as
  it is long.
* **Licences**: the AP-10K README says CC-BY-4.0 (attribution: cite Yu et
  al., NeurIPS 2021); MMPose and YOLOX are Apache-2.0.
* **The speed** of RTMPose on a real 10 s clip on DirectML and on the CPU
  (measured on random 640 x 360 frames: about 5 s per 10 s clip at 25 fps on DirectML, about 32 s on the CPU; model time only, not accuracy).
* **The safety thresholds not taken from the body**: the 2 s window and
  `joint_limit_max` 0.05. Also the penalty weight 0.5 per constraint.
* The affect scales (valence -1..1, arousal 0..1): change them if you use
  another instrument.
* The composition study and the repertoire evolution on the stick-calf
  clips: every seed fell within a second with the walk clip required, so
  the scores there say little; real clips will tell more.

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
| `DECISIONS.md` | ADR log: every assumption (100 so far) |
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

**R10. A body with two servo models, in the genome** (recommended next; written after R9, ADR-100.)
> In projects/robot-calf-final, R9 (`docs/studies/servos_r9.md`, ADR-100) found the best body with at most four
> STS3250 C002s:
> * new servos on the hip ab/ad and the hocks;
> * carpi 1:1 on 45T/45T with the old servo;
> * stifles and hocks on the catalog's 40T/80T.
>
> It trots at 0.5 s / 394 mm/s within every limit, but the calm behaviours go over on the 1:1 carpus's torque.
> The feral calf cannot be built that way yet: `morphology/feral.py` reads one `actuator` gene for all ten servos.
>
> Part 1, the genome:
> * Replace `actuator` in `config/genes/feral_calf.yaml` with one servo gene per joint pair (hip ab/ad, stifle,
>   hock, shoulder, carpus): `choices_from: actuator`, default `sts3215_c018`, not evolvable, group Mechanism.
> * Bump the version to 2 and add a v1 -> v2 migration in `calflab/model/migrations.py`. It copies `actuator` into
>   each pair gene with setdefault, so values already set are kept, then drops `actuator`.
> * Note that a document's genome node params carry no version: `GenomeNode` stamps the current one. So also make
>   an open v1 document (params with `actuator`, without the pair genes) build with its own servo, not the
>   defaults, and migrate when its params are next cleaned or saved.
> * Tests in `tests/test_genome.py` and `tests/test_feral_calf.py`: specs, MJCF and masses are bit-identical for
>   the default body, for a v1 genome with a non-default `actuator`, for a run candidate and baked design from
>   `projects/robot-calf-final`, and for the project document itself. A mixed body builds with the right component
>   and servo mass on each joint. Mass sums still add up (ADR-050).
> * Show each joint's servo in the lab: the Mass tab rows, and per-joint speed and torque limits by servo (server
>   payload, no logic in the web).
> * Do not change the working body.
>
> Part 2, still in memory (`docs/studies/servos_r9.py` / `perform_r9.py`, now able to build mixed bodies through the
> genes): find the carpus drive that keeps the calm behaviours and `lie_rise` within limits while the trot stays
> fast. Try 1:1 and 1.5:1 (45T/45T and 30T/45T what-ifs), and 2:1 on 30T/60T or the catalog's 40T/80T, with an old
> or a new carpus servo, at most four new servos in all. For each, play:
> * the quick trot grid, the walk and the turn on three seeds at margin 0.2;
> * `lie_rise`;
> * R6c's and R7's safe behaviours for 60 s on three seeds.
>
> Report belt peaks and the new servos' current. Judge at 12 V and say what changes at 11.1 V. Store the best
> body's plays with `docs/studies/play_r9.py` and give me compare.html links against today's body.
>
> Do not change component values or `verified` flags. Ask me before any catalog change (45T pulleys need sources)
> or any change to the working body.

**R11. Behaviours evolved for the faster body** (after R10, once the researcher has chosen a body.)
> In projects/robot-calf-final, R9 showed that R6c's and R7's behaviours keep their old pace on a faster body:
> where they hold, they have about +0.4 headroom. Once I have changed the body (servos per pair, pulleys), run
> behaviour diversity (`calflab.evolve.diversity`) on it with coverage, capped durations and variation as in R7,
> seeded from R7's safe generators. Compare the archive's quantity of motion, tempo and vigour with run
> `20261105-232649-evolve-4237`, play every safe cell for 60 s on three seeds, and set up side-by-side replays with
> R7's. Estimate the cost and let me choose the budget. Do not change component values or `verified` flags.

**R9 (as first written; superseded by session R9's servo study and R10).** Pulleys for faster joints, in the catalog
and the body (written after R8, ADR-099.)
> In projects/robot-calf-final, R8 (`docs/studies/joints_r8.md`) found that carpi at 1:1 on a 45T/45T GT2 10 mm pair
> and hocks at 1.5:1 (30T/45T) give a 0.6 s trot within every limit at margin 0.2 on three seeds, and the walk and
> turn too. Add these pulleys to the catalog from these listings <links>, masses null, unverified. Then show me,
> for each new pair, which catalog belt lengths fit (derived C, every belt check, the servo on its segment, a 45T
> pulley's clearance at the carpus), and only then change the working body with `set_belt_drive` (undoable). Re-run
> `joints_r8.py` on the real body, play `lie_rise`, and re-run R6c's and R7's safe behaviours on it: what is now
> possible that was not? Do not change component values or `verified` flags.

**R7b. How far can each behaviour vary?** (written after R7, ADR-098.)
> In projects/robot-calf-final the variation within movements that holds at margin 0.2 stayed at about 8 % of its
> ranges (`docs/studies/variation_r7.md`). Keep the sequence and primitive genes of the safe cells of run
> `20261105-232649-evolve-4237` fixed and evolve only the variation genes (with variation weight), so each behaviour
> shows how far its posture, tempo, amplitude, switches and cross-fades can vary within every limit. Report per
> gene which limit stops it and play the most varied safe versions for 60 s on three seeds, side by side with
> R6c's. Estimate the cost and let me choose the budget. Do not change the body, belts or component values.

*(R7, movement that varies within a movement, and R8, faster joints, were done 2026-11-05: ADR-098, ADR-099,
`docs/studies/variation_r7.md`, `docs/studies/joints_r8.md`. R9, up to four STS3250 C002s, was done 2026-11-06:
ADR-100, `docs/studies/servos_r9.md`.)*

**R7. Organic movement within a movement** (done 2026-11-05, ADR-098; kept for reference.)
> In projects/robot-calf-final, behaviour diversity (`calflab.evolve.diversity`) with coverage and capped durations
> (ADR-096, ADR-097) gives behaviours that hold every limit for a minute: run `20261105-053201-evolve-e4c8`, studied
> in `docs/studies/coverage_r6c.md`. I watched them: the sequences are starting to look good, but each movement
> inside them is the same hand-written primitive every time. Let movement vary below the primitive level, as
> evolvable genes of the generator:
> * posture drift and small noise within a movement (head, trunk height, weight over the hooves);
> * cycle-to-cycle variation in timing and amplitude;
> * switches not only where every hoof is down, and a cross-fade that varies.
>
> Every variation must stay inside what coverage checks: the forced plays must play the variation's extremes, and
> durations stay capped. Keep every limit at margin 0.2 on three seeds; leave R6d's transition gap (5-minute
> performances) as it is, but say whether the variation makes it better or worse. Optionally add clips retargeted
> from my footage to the palette, as their own states. Estimate the cost and let me choose the budget. Then run it,
> play every safe cell for 60 s on three seeds with `docs/studies/perform_r6.py`, compare the archive and the
> movement features with run `20261105-053201-evolve-e4c8`, and set up the replays so I can watch them side by
> side with the R6c ones. Do not change the body, belts or component values.

**R8. Faster joints: lifting the vigour ceiling** (done 2026-11-05, ADR-099; kept for reference.)
> In projects/robot-calf-final the trot is within the limits only at a 1.2 s cycle (77 mm/s, against the default
> 0.6 s): joint speed is the wall, the STS3215 C018's 270 deg/s halved by the 2:1 belts. Even at margin 0.1, or
> with the sustained check at full rated torque, no 0.6-0.8 s cycle passes; relaxing torque only moves long strides
> onto belt tension (`docs/studies/coverage_r6c.md`, `trot_whatif_r6c.py`). Find, per joint, whether speed or
> torque binds in the trot, walk and turn (the front carpi bind on speed first). Then show in physics, before
> changing the body, what each of these buys:
> * less reduction where a joint has torque to spare (for example 1.5:1 or 1:1 at the carpi): search commercial
>   GT2 10 mm pulley listings, but ask me before adding any to the catalog (sources, masses null, unverified);
> * belting the hip ab/ad, or springs that carry its static load;
> * lighter parts where the missing masses allow it.
>
> Re-run the trot grid with `docs/studies/trot_r6c.py` for each, and say which combination gives a 0.6-0.8 s trot
> within every limit at margin 0.2. Do not change component values or `verified` flags.

**R6d. Transitions checked, for the real performance length** (later; written 2026-11-05 after R6c, ADR-097.)
> In projects/robot-calf-final, with coverage and capped durations (ADR-097) every safe cell holds for a minute,
> but over 5 minutes 3 of 4 go over, in turns entered from a walk or a trot (coverage had checked the turn from a
> stand or shift) or in a turn too rare for a one-minute check. Extend coverage in `calflab.evolve.diversity` to
> transitions: every pair (A then B) likely at least once in a performance of `performance_s`, forced at the
> capped lengths, rather than each state along one path. Estimate the cost per passing candidate and for a
> 20 x 28 run at performance_s 60 and 300, and let me choose. Then re-run and play every safe cell for 5 minutes
> on three seeds with `docs/studies/perform_r6.py --seconds=300`. Do not change the body, belts or component values.

*(R6c, durations capped at the checked length, was done 2026-11-05: ADR-097, `docs/studies/coverage_r6c.md`.)*

*(R6b, the coverage check, was done 2026-11-05: ADR-096, `docs/studies/coverage_r6b.md`.)*

*(R6, watching three evolved behaviours for a minute, was done 2026-11-04: ADR-095, `docs/studies/perform_r6.md`.)*

**Q2. Interpretation inside the repertoire evolution** (written after session Q, ADR-085.)
> In projects/robot-calf-final, interpretation (run `20261104-042426-interpret-ef3c`) found how this body can say the calf's stand, step and
> fast play within every limit at margin 0.2, at about 10 minutes per body uncached. Make that a fitness: per candidate
> body, interpret the reading on a small budget (reuse the cache when the body is unchanged), score how many
> features are kept and how close (the distance), and require the performance to stay within limits over three
> seeds. Run Estimate cost first and show me the budget. Then a small evolution (proportions within the belts,
> springs) on archive axes "features kept" x "safety margin": does another body keep more of the fast play? Do not
> change the belts, joint ranges or component values.

**Q3. The reading against my own labels**
> The reading's thresholds (paw swing speed, stillness, step/walk/turn/fast rules) are first guesses. Let me mark
> stretches by hand in the Review (start, end, behaviour; stored beside the reading, never mixed with it), then
> compare the reader's stretches with mine per video (agreement, boundary error), and tune the thresholds on the
> videos I marked, keeping one video out to check. Show which threshold mattered. If I drop calmer videos (walking,
> grazing, weight shifting) read them too, and say how the model and the interpretation change.

**Q4. A trot that stops, steps that go somewhere**
> In projects/robot-calf-final the interpreted performance (ADR-085) gets stuck trotting: played in physics, trot ->
> stand and trot -> step go over sustained shoulder torque, because the weight shift and step poses are solved over
> the standing hooves and a trot leaves them spread. Add the missing primitives: a stop that ends a trot (or walk)
> with the hooves back under the body (the last cycles shortened onto square hooves, judged in physics), and a step
> that places a hoof somewhere (forward, back or sideways by a few cm, solved over the tripod). Re-run the
> interpretation of my reading with transitions checked: what share of the minute is then stand / step / fast, and
> are the margins still 0.2? Do not change the belts, joint ranges or component values.

*(Q, interpreting the calf's movement as the robot's own, was done in session Q: ADR-085.)*

**P2. Feasible versions that step**
(written 2026-11-03 after session P, ADR-084.)
> In projects/robot-calf-final (lab restarted), Make feasible turns my candidates c1 and c2 into quasi-static
> sways on four planted hooves that keep little character (0.19 and 0.24): slowed 3-4x, a clip must balance
> statically, and three hooves down falls because the servos sag more than a tripod's balance margin. The body
> itself is not the problem: its own trot and walk balance by timing on two or three hooves. Try two routes and
> compare them. First, let a slowed clip step:
> * keep the clip's footfalls as contact phases, moved in time if needed;
> * shift the body over the three supporting hooves before each lift (as a slow walk does), and re-place each
>   hoof where the clip puts it;
> * solve it with the stance solver in the core and judge it in physics with the same limits and margin 0.2.
>
> Second, keep more of the clip's own timing so the body balances dynamically, as the gaits do, and adjust the
> poses (not the rhythm) until it stands within the limits.
>
> Compare character kept, duration and margins with the four-hooves-down versions side by side in the Behave
> report. If the servo's compliance is the limit, say how much a stiffer servo_saturation_deg would change (as a
> what-if only, not a new default). Do not change the belts, the joint ranges or component values.

**P3. How much the physics rests on what is unverified**
> Make a sensitivity study a job and a panel: for a physics or adapt run, re-judge the stored clip with the
> armature scale, the total mass (x0.9-1.2, for the parts with no mass), floor friction and spring rates varied
> one at a time. Show which limit moves and whether the verdict changes. Run it on my two feasible versions (c2
> fails sustained belt tension at armature x0.2). List which missing value would most change each result, so I
> know what to measure first. Do not change any component values.

**P4. Feasible clips in the repertoire**
> Use the feasible versions of my clips in the stochastic behaviors and in the repertoire evolution (preset
> repertoire, torque-speed servos, margin 0.2): add them by tag, check that every episode stays within limits in
> the composition study, and run a small evolution to see whether a body with other proportions keeps more of
> the raw clips' character within the same limits (adapt each clip per candidate body, or judge the raw clips
> with the search's operations). Report the cost first (estimate_evolve).

**X3. The fast frames: the calf or the tracker?**
(written 2026-11-03 after session X2, ADR-083.)
> In projects/robot-calf-final (lab restarted, video analysed again with
> bends over the window and repeated frames re-timed), the playable speed
> of my candidates is set by the left stifle in 0-109 and the left carpus at
> the ball in 140-225. Mark in the Review strip the frames where each
> candidate's limiting joint peaks (computed in the core), show me those
> frames with the tracked points and the fitted skeleton drawn, and tell me
> which points move how far there. If the tracker is the cause (a point
> jumping to another leg or the ball), add a per-landmark outlier test on
> the 2D tracks before the lift (in the core, recorded per frame), re-run
> the comparison side by side, and say what then limits the speed. Do not
> change the belts.

**X4. A panel for comparing lifts**
> compare_lift_maps (maps, bend choices, ambiguity per leg, jumps, residual
> per landmark, playable speed raw / smoothed / re-timed) is command-line
> JSON only. Make it a panel in the Behave workspace (schema-driven, no
> logic in the UI): pick the lifts of a video, see the tables, click a
> range to open it in the Review. Extend the Playwright footage test.

**Y. A robot that turns as the calf did**
> Clips from the 3D lift carry the calf's heading (root_quat) and ground
> path, but the simulator does not steer: the behaviors controller plays
> the joints only. Give the feral calf's walk and trot a turn rate (from
> the hind ab/ad and stride length left/right, as the body allows), and
> make the behaviors controller follow a clip's heading with it, measured
> in simulation against the clip (heading error over time). Show me my
> 61 deg turning candidate (frames 0-109) in physics, and say what limits the turn rate
> (servo speed, ab/ad range, stability). Do not change the belts.

**Z. More of my videos in 3D, and the camera that moves**
> I dropped <videos> into projects/robot-calf-final/footage/videos (some
> hand-held). Go through the 3D results with me: the yaw strip against
> what I see, the camera elevation and whether it was judged fixed, the
> proportions per video (are they consistent across videos of the same
> calf?), and the candidates. If a camera pans or zooms, add a camera
> motion estimate from the background (OpenCV, already installed) so that
> panning is not read as turning, and report where it was removed. If a
> learned lifter or mesh model would clearly help, stop and compare
> options with sizes and licences before installing anything.

**U. My first real calf video through the inbox**
(written 2026-11-03 after session T built the video inbox, RTMPose AP-10K
tracking, composition and repertoire evolution, ADR-076 to ADR-079. Its
first video went through the 3D lift on 2026-11-03; what remains is the 2D
map and segmentation tuning.)
> I dropped <video file(s), what the calf does, which side faces the camera>
> into projects/robot-calf-final/footage/videos. Go through what the inbox
> made of it with me: the tracker's points on a few frames where you think
> it is wrong (zoom the review frames), the near side and the camera-view
> verdict, and every candidate cut. Tell me which AP-10K points land on
> which joints of a calf (is "Knee" the stifle or the hock? "Elbow" the
> elbow or the carpus?), then make a project map from ap10k_side that
> matches, and tune the segmentation thresholds until the cuts match what I
> see (I will tell you where stretches really start and end). Measure the
> tracker's speed on DirectML and on the CPU for one 10 s clip and record it
> in ADR-077. Do not change the belts.

**V. Composing a performance: a curve editor and a timeline of episodes**
> Composing behaviors works but the affect curve and the compositions are
> JSON. Make a curve editor in the Behave panel (keyframes on a time axis,
> drag to move, a row per parameter: tempo, amplitude, idle share, low-pass,
> repeat, pause, target valence and arousal), and show the episodes of a
> simulated run as a coloured strip on the timeline (clip, idle, gait,
> pause, with the label in effect), so I can scrub and see which clip played
> under which setting. Save named compositions in the project and pick them
> in the composition study instead of typing JSON. No logic in the UI: the
> curve's interpolation and the episode strip come from the server.

**W. A real repertoire evolution on robot-calf-final**
> In projects/robot-calf-final, with my accepted clips <names>, required
> <which, with weights>, run Estimate cost, then the small budget with the
> repertoire preset (archive: expressive range x safety margin). Show me the
> archive, which constraints rejected or penalised candidates and why, how
> far each belt-bound gene moved, and the spread over seeds. Then propose a
> budget for an overnight run from the estimate, and let me choose before
> starting it. Let me set the safety policy in the Evolve panel (reject /
> penalise per constraint, the window, the joint-limit share) instead of
> editing the preset file. Do not change the belts.

*(T, from a video in a folder to behaviors an evolved body performs safely, was done on 2026-11-03: ADR-076 to ADR-079. 3D motion from one camera and the review player were done later the same day: ADR-080, ADR-081. X, the hind Knee at the hock and clip smoothing, at the end of that day: ADR-082. X2, bends over the window and repeated frames, after it: ADR-083.)*

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

**S. My first footage through the behavior pipeline**
> I tracked <video, behavior, side> with <DeepLabCut / SLEAP / by hand>;
> the CSV is in projects/robot-calf-final/footage/<file> at <fps> fps, and my
> labels are <list>. Make a retarget map for my labels (copy
> feral_calf_side), import it, and show me what the body can play of it
> (range, servo speed) and the preview. Then put it in the stochastic
> behaviors with idle and walk, simulate a minute with three seeds, and tell
> me where it falls or clamps and what in the body (ranges, belts, springs)
> limits it most. Do not change the belts.

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
