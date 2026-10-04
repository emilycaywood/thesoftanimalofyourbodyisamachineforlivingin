# CALFLAB — Plan

CALFLAB is a research platform and design environment for the co-design of a
~610 mm tall autonomous quadruped modelled on a calf: form, mechanism, control,
behavior, sensing and fabrication in one project, one scene and one research
record.

Two qualities outrank everything else:

1. **Extensibility and modularity** — everything domain-specific is a plugin
   with a schema; the UI is generated from schemas.
2. **Familiar UI/UX** — Rhino/Grasshopper/Blender/Fusion conventions for
   modeling, slicer/pattern-making conventions for fabrication.

## 1. Architecture

```
            ┌────────── clients (no domain logic) ──────────┐
            │ web/ (React)  bridges/rhino  bridges/blender  │
            │ CLI (calflab)  notebooks (calflab.client)     │
            └───────────────┬───────────────────────────────┘
                 REST + WS  │  one project, one event stream
            ┌───────────────▼───────────────┐
            │ server/calflab_server (FastAPI)│  thin: routing, serialisation,
            └───────────────┬───────────────┘  websocket fan-out
                            │ in-process calls
            ┌───────────────▼───────────────────────────────────────────┐
            │ core/calflab  (headless; importable with no server)        │
            │                                                           │
            │  app.Lab ── commands (event-sourced undo) ── event bus    │
            │     │                                                     │
            │  graph engine (typed DAG, content-hash cache, async jobs) │
            │     │                                                     │
            │  plugins: genes · part generators · components ·          │
            │   controllers · fitness · descriptors · optimizers ·      │
            │   simulators · compute backends · exporters · analyses ·  │
            │   panels · commands                                       │
            │     │                                                     │
            │  project store (JSON + JSONL + SQLite index) · registry   │
            └───────────────────────────────────────────────────────────┘
```

### Module boundaries (`core/calflab/`)

| Module | Responsibility | May import |
|---|---|---|
| `units` | The **only** place mm/g/deg ↔ SI conversion happens | — |
| `schema` | `P(...)` parameter fields with units/ranges/UI hints; `ui_schema()` | pydantic |
| `plugins` | Plugin base classes, registry, discovery (entry points + `plugins/` scan + hot reload), templates for `new-plugin`, contract checks | schema |
| `model` | `RobotSpec`, `Genome`/gene definitions/migrations, element params, overrides, `Design` | schema, units |
| `components` | YAML component library (actuators, sensors, boards, batteries, materials) with `source`/`verified` | model |
| `morphology` | Part generators: genome → element params → `RobotSpec` | model, components |
| `sim` | MJCF/URDF compiler, MuJoCo runner, skin model, domain randomization, metrics | model, units |
| `control` | Controllers (CPG now; policies later) | schema |
| `fitness` | Fitness terms, named versioned presets, behavior descriptors | sim metrics |
| `graph` | Node types, graph model, cached evaluator, clusters | plugins |
| `compute` | `ComputeBackend`s: LocalProcessPool, RemoteSSH (stub), CloudNotebook (stub) | — |
| `evolve` | Optimizers (CMA-ES inner loop, MAP-Elites outer loop), lineage | sim, compute |
| `export` | Exporters: glTF, STL/3MF, STEP, 3dm, URDF, WireViz, BOM | model |
| `wiring` | BOM, power budget, harness | components |
| `project` | Project folder, SQLite registry, command log, journal, designs | model |
| `app` | `Lab`: the session object — state, commands, undo/redo, jobs, events | everything above |
| `bridge` | Pure "build instructions" for Rhino and Blender (testable without either) | model |
| `client` | HTTP/WS Python client for notebooks, Grasshopper, scripts | httpx only |
| `cli` | Typer CLI `calflab` | app, server (lazy) |
| `builtin` | Built-in plugins, registered through the same mechanism as third-party ones | plugins |

`server/calflab_server` contains no domain logic: it maps HTTP/WS onto `Lab`.
`web/` contains no domain logic: it renders server state and sends commands.

## 2. Data flow

```
genes (YAML definition, versioned)
  └─ Genome values ──► PartGenerator.element_params()  ─┐  per-element parametric values,
                                                        │  each bound to the gene that drives it
                 explicit Overrides (named records) ────┤
                                                        ▼
                                   PartGenerator.build() ──► RobotSpec (mm, g, deg, stable IDs)
                                                        │
                    ┌───────────────────────────────────┼──────────────────────────┐
                    ▼                                   ▼                          ▼
          scene JSON / glTF (viewport)        MJCF (SI) + skin model       exporters (3MF/STL/STEP/
          Rhino build list, Blender                    │                    3dm/URDF/WireViz/BOM)
          armature plan                    Controller ─┤
                                                       ▼
                                          MuJoCo rollout (body poses, torques, contacts)
                                                       ▼
                                          metrics ──► fitness preset ──► optimizer
                                                       ▼
                              registry (run.json + SQLite index) · lineage · journal
```

The same pipeline is the **default graph** shown in the node editor:
`genome → morphology → mjcf → simulate (← controller) → metrics → fitness`.
Each node's output is cached under `hash(node type, code version, params, input
hashes)`, so dragging a slider recomputes only what is downstream of it.

### State and editing model

* The **document** (`project.calflab.json`) = graph (incl. genome and controller
  params on their nodes) + overrides + fitness preset + layer settings.
* Every edit is a **command** appended to `commands.jsonl` with its inverse
  patch. Undo/redo moves a cursor on that log; all clients share it.
* **Overrides** are records layered over the parametric result
  (`target element`, `param`, `value`, `enabled`). They can be listed, toggled,
  removed, or *internalized* (written back into the gene that drives the param).
* **Bake** freezes document + evaluated spec + code version into an immutable
  `designs/<name>-vNNN/` folder.
* Every sim/optimization/bake/export writes `runs/<id>/run.json` (inputs,
  genome, fitness definition, seed, git hash, package versions, backend,
  metrics, artifacts, duration). SQLite is only an index, rebuildable from the
  text files.

### Conventions

* World frame: **X forward, Y left, Z up** (MuJoCo, Rhino). The web scene is Z-up.
* Files and UI: **mm, g, degrees**. Simulation: SI. Conversion only in `calflab.units`.
* Stable IDs are dotted paths: `leg.fl.shank`, `joint.fl.knee`, `act.fl.knee`.

## 3. Phases and milestones

### Phase 1 — vertical slice (this session)

| # | Milestone | Proof |
|---|---|---|
| M1 | `calflab setup` / `doctor` / `lab` | commands run in PowerShell |
| M2 | Plugin registry, schema-driven panels, `new-plugin`, contract tests | `tests/test_plugins.py` |
| M3 | Graph engine with caching; default graph editable in node editor | `tests/test_graph.py` |
| M4 | Reference calf: genome → spec → MJCF + scene/glTF; viewport with display modes, layers, views, Rhino navigation, selection, properties, CoM/joint-axis/support-polygon overlays | `tests/test_morphology.py`, UI |
| M5 | Gumball edit → override; remove / internalize; undo/redo; Bake | `tests/test_commands.py`, UI |
| M6 | CPG controller; streamed rollout, scrubbing, synced plot | `tests/test_sim.py`, UI |
| M7 | CMA-ES inner + MAP-Elites outer on LocalProcessPool; clickable heatmap; lineage; registry | `tests/test_evolve.py`, UI |
| M8 | build123d leg segment with actuator mount → 3MF/STL/.3dm with part label | `tests/test_export.py` |
| M9 | Rhino `CalflabPull` (layers, blocks, user text); Blender armature | `tests/test_bridges.py` + scripts |
| M10 | BOM + power budget from a run; WireViz harness | `tests/test_wiring.py` |
| M11 | Test suite + Playwright smoke | `calflab test` |

### Phase 2 — learning at scale
PPO training plugin with imitation rewards from Blender clips; RemoteSSH and
CloudNotebook backends completed; domain randomization presets.

### Phase 3 — sim-to-real
Single-leg system ID from bench logs; thermal- and impact-noise-aware rewards;
skin parameters fitted from physical tests; Deploy telemetry.

### Phase 4 — skin, molds, performance
Mold generation; skin flattening (libigl ARAP/LSCM) with seam editing and
distortion maps; behavior layer with touch/audio; puppeteering + autonomy
performance mode.

Later-phase features exist now as plugin stubs with interfaces, docstrings,
TODOs and a contract test each.

### Status after the Phase 1 session (2026-10-01)

All eleven milestones are met and covered by tests (`calflab test`: pytest,
mypy, web typecheck/eslint/vitest, Playwright smoke). Verified outside the
test suite: `CalflabPull` inside Rhino 8.34; the web lab driven by hand
(simulate, override, evolve, click-to-load candidate).

Added later the same day, once Blender 5.2.2 was installed: the Blender
extension was run headless against a live server and checked numerically
(every hinge on its true axis, imported rollout within 0.02 mm of the
simulator, clip round trip exact); see `bridges/blender/README.md`. That
check exposed and fixed three defects: the trunk trajectory was applied about
the world origin, bones were not perpendicular to their joint axes, and
recorded body poses lagged joint angles by one physics step.

A later session the same day pushed the branch (pull request #1), added the
component audit and verification worksheet (`calflab components audit` /
`worksheet`, ADR-037), and checked the remaining bridges inside the real
applications (ADR-038): `CalflabInstall`, `CalflabPush` and `CalflabLiveSync`
in Rhino 8.34, the five GH Python components (with a generated
`calflab_example.gh`), and the Blender sidebar panel with simulated mouse
clicks. Those checks fixed three Rhino defects: the installer crashed on a
second run, leg capsules could vanish after a gene edit (ADR-039), and a
live-sync error could escape into Rhino's idle loop.

The researcher's first walkthrough by hand (2026-10-03) found six problems,
fixed in the session that followed: a front knee direction gene (ADR-041), a
gumball that can be seen and dragged and harness routes that are drawn, in
the web viewport and in Rhino (ADR-042, ADR-043), loading a baked design and
evolving from one (ADR-044), a gene table for archive candidates (ADR-045),
and run rows / journal links that replay visibly (ADR-046). A three-segment
leg was proposed and set aside: `docs/proposals/anatomical-leg.md`. On
2026-10-04 forward front knees became the default body, with a default trot
re-tuned for it (ADR-047); earlier work keeps backward knees.

Not verified on real software: Hops against a live Grasshopper (Hops is not
installed), and most things done by hand with the mouse in Grasshopper and
Blender's Pose Mode. `docs/SESSION_HANDOFF.md` lists what the researcher has
checked by hand in Rhino and the web lab.

Scaffolded as stubs with interfaces and contract tests: PPO training, MJX
simulator, RemoteSSH and CloudNotebook transports (job bundling and the
notebook export are real), imitation reward, interactive selection, molds,
skin patterns, nesting, system ID, touch response, puppeteering blend, ball
joints. UI placeholders: Behave and Deploy workspaces, reference images,
inertia / heat-map / range-of-motion overlays, endpoint/midpoint/axis snaps,
angle and clearance measurement, run comparison, Pareto / parallel
coordinates.

## 4. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Working copy placed in a cloud-synced folder (Google Drive, OneDrive): sync races with `.git` and SQLite, tens of thousands of small files uploaded | Broken `node_modules`, corrupt git/SQLite | Resolved 2026-10-01: the working copy is `C:\CALFLABHOME` (local NTFS). The code still detects synced folders and keeps environments out of them (ADR-003). GitHub is the backup; nothing has been pushed yet. |
| Actuator/sensor specs are recalled, not measured | Wrong torque margins, mass budget | Every component is `verified: false` with a `source`; UI shows "unverified" badges |
| No CUDA locally | No large-scale RL on the laptop | CPU MuJoCo + process pool locally; remote backends for MJX/PPO |
| Rhino/Blender cannot be driven in CI | Bridges regress silently | Bridges are thin; all geometry/armature logic is in `calflab.bridge` and tested headlessly |
| Reduced-order skin model (stiffness/damping/added mass) | Sim optimism about skin drag | Parameters live in material YAML; Phase 3 fits them from physical tests |
| Sim-to-real gap of CPG gaits | Evolved gaits fail on hardware | Domain randomization hooks now; system ID in Phase 3 |
| Scope: the UI spec is far larger than one slice | Shallow features everywhere | Vertical slice first; other workspaces are honest empty states that teach |
| build123d/OCP is a ~200 MB wheel | Slow setup | Optional `cad` extra; exporter degrades with a clear message |
