# CLAUDE.md — conventions for every Claude Code session in this repo

CALFLAB is a long-lived research tool. Optimise for **extensibility** and for a
**familiar Rhino/Grasshopper/Blender/Fusion feel**. Read `PLAN.md` for the
architecture and `DECISIONS.md` before changing a convention; add an ADR when
you make a new assumption.

## Golden rules

1. **Never put logic in the UI.** `web/` and `bridges/` render state and send
   commands. Anything that computes, validates, converts units or decides goes
   in `core/calflab` and is exposed by the server. If you are writing math in
   TypeScript or in a Rhino/Blender script, stop and move it to the core.
2. **Core is headless.** `core/calflab` must not import `calflab_server`,
   FastAPI, or anything UI (`calflab.cli` excepted). `tests/test_architecture.py`
   enforces this.
3. **Everything domain-specific is a plugin** with a Pydantic params schema.
   Adding a plugin must never require UI code.
4. **Never invent hardware specs.** Component data lives in
   `config/components/*.yaml` with `source:` and `verified: false`. Do not flip
   `verified` to true; only the researcher does that. Never fill in a missing
   value: leave it `null` (the entry is then incomplete) or, if the researcher
   gives a guess, name the field in `guessed:` (ADR-051).
5. **Edits are commands.** Every document mutation goes through
   `Lab.execute(command, args)` so it is logged, undoable and broadcast.
   Never mutate `lab.state` directly from a route or a plugin.
6. **Overrides are never silent.** A direct edit creates a named override
   record; it does not modify the parametric result or a gene unless the user
   internalizes it.
7. **Units:** mm, g, degrees in files/API/UI; SI inside the simulator.
   Convert only with `calflab.units`.
8. **Stable IDs** (`leg.fl.shank`, `joint.fl.knee`) are API. Do not rename
   them without a genome/spec migration.

## Environment (Windows 11, PowerShell, no CUDA)

* Run everything through `.\calflab.ps1 <cmd>` (or `calflab <cmd>` in the env).
  No bash-only tooling, no `make`.
* The working copy is `C:\CALFLABHOME` (local, unsynced). The venv lives in
  `%LOCALAPPDATA%\calflab\venv`; web dependencies are in-tree at
  `web\node_modules`. Only if the repo is opened from a cloud-synced folder
  does `node_modules` move to `%LOCALAPPDATA%\calflab\web` (ADR-003).
  Python: `& "$env:LOCALAPPDATA\calflab\venv\Scripts\python.exe"`.
* `calflab test` runs ruff, pytest, mypy and the web checks (typecheck,
  eslint, vitest, Playwright). `--py`, `--web`, `--e2e` select subsets. Run it
  after each module.
* When running inside the Claude desktop app, `%LOCALAPPDATA%` is redirected,
  so the environment is separate from the user's own terminal (ADR-033). In
  PowerShell 5.1 do not pipe native stderr with `2>&1`.
* To look at the UI: the `calflab-lab` entry in `.claude/launch.json` starts
  the server on port 8000 serving the built web app (rebuild with `pnpm build`
  via `calflab setup` after changing `web/src`).
* MuJoCo runs on CPU. GPU training goes through a `ComputeBackend`.

## Repository map

```
core/calflab/
  units.py            unit conversion (single place)
  schema.py           P(...) fields + ui_schema()
  plugins/            base classes, registry, discovery, templates, contracts
  model/              RobotSpec, Genome, overrides, Design
  components/         YAML library loader
  morphology/         part generators (reference calf)
  sim/                MJCF/URDF compile, MuJoCo rollouts, metrics, skin
  control/            controllers (CPG)
  fitness/            terms, presets, behavior descriptors
  graph/              typed DAG, cache, node types
  compute/            LocalProcessPool, RemoteSSH (stub), CloudNotebook (stub)
  evolve/             CMA-ES inner loop, MAP-Elites outer loop, lineage
  export/             glTF, STL/3MF, STEP, 3dm, URDF
  wiring/             BOM, power budget, harness, WireViz
  project/            project folder, registry, command log, journal
  app/                Lab session: state, commands, undo, jobs, events
  bridge/             Rhino build list, Blender armature plan (pure functions)
  design.py           build_design(): genome + overrides -> RobotSpec
  config.py, paths.py robot defaults / gene / fitness files; repo and work dirs
  builtin/            built-in plugins (same mechanism as third-party)
  client.py           Python client (notebooks, Grasshopper)
  cli/                Typer CLI
server/calflab_server/ FastAPI app, routes, websocket hub, Hops endpoints
web/src/               React app (see "Web UI conventions")
bridges/               Rhino scripts, Grasshopper components, Blender add-on
plugins/               user plugins, auto-scanned
config/                defaults, gene definitions, components, fitness presets
tests/                 pytest
```

## How to add a plugin

```powershell
.\calflab.ps1 new-plugin <type> <name>     # e.g. new-plugin fitness_term quiet_feet
```

This writes `plugins/<name>.py` from a template plus
`tests/plugins/test_<name>.py` (a contract test). Then edit the template.
Types and what to implement:

| Type (`new-plugin` key) | Base class | Implement |
|---|---|---|
| `gene_definition` | `GeneDefinition` | `definition()` → `GenomeDefinition` (or add a YAML file in `config/genes/`) |
| `part_generator` | `PartGenerator` | `element_params(genome)`, `build(params, ctx)` |
| `joint_type` | `JointType` | `mjcf(joint)`, `dof` |
| `component` | `ComponentProvider` | `components()` (prefer YAML in `config/components/`) |
| `controller` | `Controller` | `Params`, `reset()`, `act(t, obs)`; `param_vector`/`from_vector` if optimisable |
| `behavior` | `Behavior` | `Params`, `tick(t, sensors)` |
| `fitness_term` | `FitnessTerm` | `Params`, `evaluate(metrics, rollout)` → float (higher is better) |
| `behavior_descriptor` | `BehaviorDescriptor` | `range`, `describe(spec, metrics)` |
| `optimizer` | `Optimizer` | `Params`, `run(problem, backend, report)` |
| `simulator` | `Simulator` | `rollout(model, controller, settings)` |
| `compute_backend` | `ComputeBackend` | `map(tasks, on_result)`, `cancel()` |
| `exporter` | `Exporter` | `Params`, `formats`, `export(spec, out_dir, params)` |
| `analysis` | `Analysis` | `Params`, `run(lab, params)` → JSON-able result |
| `panel` | `Panel` | declarative layout (`widgets`) — no code runs in the browser |
| `command` | `Command` | `Params`, `run(lab, params)`; set `mutates=True` for document edits |

Rules for all plugins:

* Class attribute `key` (snake_case, unique per type), `label`, `description`.
* Parameters are a nested `Params(BaseModel)` whose fields use
  `calflab.schema.P(default, unit=..., ge=..., le=..., ui="slider", desc=...)`.
  The UI builds panels, node sockets, tooltips and validation from this.
* Register with the decorator `@register` from `calflab.plugins`.
* Plugins must be import-safe (no side effects, no heavy imports at module
  top level — import MuJoCo/OCP inside functions).
* Every plugin type has a contract in `calflab/plugins/contracts.py`;
  `tests/test_plugins.py` runs it over every registered plugin.

To add a **node type** to the graph: subclass `NodeType` in
`calflab/graph/nodes.py` (or in a plugin), declare `inputs`, `outputs`,
`Params`, and `evaluate`. Set `expensive = True` to run it as a job.

To add a **component**: `calflab components new <kind> <key>` appends a blank
entry to the YAML in `config/components/` (`source:`, `verified: false`,
every value `null`). Actuators and batteries are then selectable through
`choices_from` in the gene file.

**Mass** (ADR-050): every `Geom` carries `mass_source`; a new geom that
represents a library part must set `mass_source="component"`, and anything
that changes mass must keep `calflab.model.mass.mass_breakdown` adding up to
`RobotSpec.total_mass_g()`. Lengths in a part generator follow the `scale`
gene (ADR-052): multiply fixed millimetre constants by it.

To change the **genome**: edit/add `config/genes/<name>.yaml`, bump
`version`, and add a migration in `calflab/model/migrations.py` plus a test in
`tests/test_genome.py`. Old runs must always reload.

## Python style

* Python 3.12, type hints everywhere, Pydantic v2 models for all data that
  crosses a boundary (file, API, process).
* ruff (line length 100) and lenient mypy must pass. No `print` in the core;
  use `logging.getLogger(__name__)`.
* Pure functions where possible; side effects live in `project/` and `app/`.
* Determinism: any randomness takes an explicit `seed`; rollouts with the same
  inputs and seed must be bit-identical (there is a test).
* Docstrings state units for every physical quantity.
* Stubs for later phases: real interface + docstring + `TODO(phaseN)` +
  `raise NotImplementedError` with a helpful message + one test.

## Testing rules

* Every module gets tests in `tests/`; every plugin type has a contract test.
* Keep the default suite fast (< ~90 s). Mark long tests `@pytest.mark.slow`.
* Required coverage areas: genome validity, migrations, MJCF compile,
  deterministic rollouts, registry integrity, plugin contracts, command
  undo/redo, architecture boundaries, one Playwright smoke test.
* After each module: `.\calflab.ps1 test --py`, then a smoke demo
  (`.\calflab.ps1 demo walk`).

## Web UI conventions

* Stack (pinned, ADR-020): React 18 + TypeScript strict, Vite 6, React Three
  Fiber 8 + drei 9, @xyflow/react 12, dockview 4, Zustand 5, Tailwind 4, visx 3.
* Layout of `web/src/`: `api/` (the only code that talks to the server),
  `store/` (`lab.ts` server mirror, `view.ts` view state, `playback.ts`),
  `commands/` (registry + shortcuts), `components/` (`SchemaForm`, `ui.tsx`),
  `viewport/`, `panels/`, `shell/`, `workspaces.ts`.
* Stores never compute domain results. If the UI needs a number, add it to
  the scene/rollout payload on the server (see ADR-028, ADR-029).
* **Schema-driven forms:** render parameters with `<SchemaForm>` from the
  schema the server sends. Do not hand-write a form for a plugin.
* **Every UI action is a command**: client commands in
  `web/src/commands/registry.ts`, document commands in
  `core/calflab/app/commands.py`. Menus, buttons, shortcuts and the command
  line all call `execute(name)`.
* **Panels**: add the component, register it in `web/src/panels/registry.tsx`
  and add its id to `web/src/panels/ids.ts`; add it to a workspace in
  `web/src/workspaces.ts`. Bump `LAYOUT_VERSION` in `shell/Dock.tsx` when a
  default layout changes.
* **Effects must not return values.** Write `useEffect(() => { el.scrollIntoView(); }, [])`
  with braces: some DOM methods return Promises, and React calls whatever an
  effect returns as its cleanup.
* The web app is run from a work directory (`calflab.cli.webenv`), which may
  be outside the repo; never hard-code `web/node_modules`. `nodeLinker:
  hoisted` and `preserveSymlinks` must stay (ADR-027).
* Rhino conventions: RMB orbit, Shift+RMB pan, wheel zoom; L→R window
  selection, R→L crossing; Enter/Space repeats the last command; Esc cancels.
* Grasshopper conventions in the node editor: orange = warning, red = error,
  grey = disabled; wire colour = data type.
* Empty states teach: say what the panel is for and the one action that
  fills it.
* Long operations are jobs with progress and cancel. Never block the UI.
* Scene is Z-up, units mm. Objects are keyed by stable ID.

## Git

* Small, coherent commits; imperative subject, body explains why.
* Do not commit generated data (`runs/`, `exports/`, SQLite, `node_modules`).
* Work on a branch; `main` is merged by the researcher.

## When you start a session

Read `docs/SESSION_HANDOFF.md` (current state, machine quirks, the
researcher's working rules, next sessions) and confirm the working directory
is `C:\CALFLABHOME`.

## When you finish a session

Update `docs/USER_GUIDE.md` for any user-visible change, add ADRs for new
assumptions, run `.\calflab.ps1 test`, list what is real vs. stubbed, and
bring `docs/SESSION_HANDOFF.md` up to date (state, verified/unverified, next
sessions).
