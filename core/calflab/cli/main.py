"""The ``calflab`` command line. Everything works from PowerShell; no make/bash.

    calflab setup | doctor | lab | test | demo <name> | new-plugin <type> <name>
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from calflab import __version__
from calflab.paths import default_project, home_dir, plugins_dir, repo_root

app = typer.Typer(
    help="CALFLAB: co-design lab for a calf-scale quadruped.",
    no_args_is_help=True,
    add_completion=False,
)
registry_app = typer.Typer(help="Experiment registry maintenance.", no_args_is_help=True)
bridge_app = typer.Typer(help="Rhino and Blender bridges.", no_args_is_help=True)
components_app = typer.Typer(help="Component library: verification worksheet and audit.", no_args_is_help=True)
app.add_typer(registry_app, name="registry")
app.add_typer(components_app, name="components")
app.add_typer(bridge_app, name="bridge")
console = Console()

ProjectOpt = typer.Option(None, "--project", "-p", help="Project folder (default: projects/sample-calf).")


def _project(path: Path | None) -> Path:
    return (path or default_project()).resolve()


def _open_lab(path: Path | None):  # type: ignore[no-untyped-def]
    from calflab.app import Lab

    return Lab.open(_project(path))


# ====================================================================== setup / doctor
@app.command()
def setup(
    skip_web: bool = typer.Option(False, help="Do not install/build the web app."),
    skip_browsers: bool = typer.Option(False, help="Do not download the Playwright test browser."),
    project: Path | None = ProjectOpt,
) -> None:
    """Install web dependencies, build the web app, create the sample project."""
    from calflab.cli import webenv

    console.rule("CALFLAB setup")
    console.print(f"Python environment: [bold]{sys.prefix}[/bold] (calflab {__version__})")
    console.print(f"Local work directory: [bold]{home_dir()}[/bold]")

    if not skip_web:
        if webenv.pnpm() is None:
            console.print("[red]pnpm not found.[/red] Install Node LTS, then: npm install -g pnpm")
            raise typer.Exit(1)
        work = webenv.workdir()
        where = "in the repo" if work == repo_root() / "web" else f"out of tree at {work} (ADR-003)"
        console.print(f"Web app: {where}")
        webenv.run_pnpm(["install"], cwd=work)
        webenv.save_lockfile(work)
        webenv.run_pnpm(["build"], cwd=work)
        if not skip_browsers:
            webenv.run_pnpm(["exec", "playwright", "install", "chromium"], cwd=work, check=False)

    p = _project(project)
    lab = _open_lab(project)
    if not lab.journal.list():
        lab.journal.save(
            "Welcome to CALFLAB",
            "This is the sample project with the reference calf.\n\n"
            "- Press **F5** (or type `Simulate` in the command line) to watch it walk.\n"
            "- Drag a slider in **Form** to change its proportions.\n"
            "- Press **B** to bake a design you want to keep and cite.\n\n"
            "Every number in the component library is *unverified* until you check it.",
            tags=["getting-started"],
        )
    lab.close()
    console.print(f"Project ready: [bold]{p}[/bold]")
    try:
        z = build_blender_addon()
        console.print(f"Blender add-on: [bold]{z}[/bold]")
    except Exception as exc:  # the add-on is optional
        console.print(f"[yellow]Blender add-on not built: {exc}[/yellow]")
    console.rule("Done")
    console.print("Next: [bold].\\calflab.ps1 doctor[/bold] then [bold].\\calflab.ps1 lab[/bold]")


@app.command()
def doctor(project: Path | None = ProjectOpt) -> None:
    """Check the environment: tools, Rhino/Blender paths, ports, project."""
    from calflab.cli.doctor import run_checks

    table = Table(title=f"calflab doctor ({__version__})", show_lines=False)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    table.add_column("How to fix", overflow="fold")
    colors = {"ok": "green", "warn": "yellow", "fail": "red"}
    checks = run_checks(_project(project))
    for c in checks:
        table.add_row(c.name, f"[{colors[c.status]}]{c.status.upper()}[/]", c.detail, c.fix)
    console.print(table)
    failed = [c for c in checks if c.status == "fail"]
    if failed:
        console.print(f"[red]{len(failed)} problem(s) need attention.[/red]")
        raise typer.Exit(1)
    console.print("[green]Environment is usable.[/green] Warnings are optional features.")


# ====================================================================== lab
@app.command()
def lab(
    project: Path | None = ProjectOpt,
    port: int = typer.Option(8000, help="Server port."),
    dev: bool = typer.Option(False, help="Run the Vite dev server with hot reload (for UI development)."),
    web_port: int = typer.Option(5173, help="Vite dev server port (with --dev)."),
    browser: bool = typer.Option(True, "--browser/--no-browser", help="Open the browser."),
) -> None:
    """Start the server and the web app, and open the browser."""
    from calflab_server.main import serve

    from calflab.cli import webenv
    from calflab.cli.doctor import port_free

    if not port_free(port):
        console.print(f"[red]Port {port} is in use.[/red] Is CALFLAB already running? Try --port {port + 1}.")
        raise typer.Exit(1)
    p = _project(project)
    vite: subprocess.Popen[bytes] | None = None
    web_dist: Path | None = None
    url = f"http://127.0.0.1:{port}"
    if dev:
        work = webenv.workdir()
        if not (work / "node_modules").is_dir():
            console.print("[red]Web dependencies are missing.[/red] Run: calflab setup")
            raise typer.Exit(1)
        exe = webenv.pnpm()
        assert exe is not None
        env = {**os.environ, "CALFLAB_API": f"http://127.0.0.1:{port}"}
        vite = subprocess.Popen([exe, "dev", "--port", str(web_port), "--strictPort"], cwd=str(work), env=env)
        url = f"http://127.0.0.1:{web_port}"
    else:
        web_dist = webenv.dist_dir()
        if not (web_dist / "index.html").is_file():
            console.print("[yellow]The web app is not built yet.[/yellow] Run: calflab setup  (or use --dev)")
            raise typer.Exit(1)

    console.print(f"CALFLAB lab: project [bold]{p}[/bold]")
    console.print(f"Open [bold]{url}[/bold]   (Ctrl+C to stop)")
    if browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        serve(p, port=port, web_dist=web_dist, log_level="warning")
    finally:
        if vite is not None:
            vite.terminate()


# ====================================================================== test
@app.command()
def test(
    py: bool = typer.Option(False, "--py", help="Python: ruff, pytest, mypy."),
    web: bool = typer.Option(False, "--web", help="Web: typecheck, eslint, vitest."),
    e2e: bool = typer.Option(False, "--e2e", help="Playwright UI smoke test."),
    fast: bool = typer.Option(False, help="Skip tests marked slow."),
    types: bool = typer.Option(False, "--types", help="Only relevant with --web/--e2e: also run mypy."),
) -> None:
    """Run the test suites (all of them when no flag is given)."""
    from calflab.cli import webenv

    run_all = not (py or web or e2e)
    root = repo_root()
    cache = home_dir()
    failures: list[str] = []

    def step(name: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        console.rule(name)
        code = subprocess.run(cmd, cwd=str(cwd), env={**os.environ, **(env or {})}, check=False).returncode
        if code != 0:
            failures.append(name)

    if py or run_all:
        step("ruff", [sys.executable, "-m", "ruff", "check", "core", "server", "tests", "plugins",
                      "--cache-dir", str(cache / "ruff_cache")], root)
        cmd = [sys.executable, "-W", "ignore::UserWarning", "-m", "pytest"]
        if fast:
            cmd += ["-m", "not slow"]
        step("pytest", cmd, root)
        if types or run_all or py:
            step("mypy (lenient)", [sys.executable, "-m", "mypy", "--cache-dir", str(cache / "mypy_cache")], root)
    if web or e2e or run_all:
        work = webenv.workdir()
        exe = webenv.pnpm()
        if exe is None or not (work / "node_modules").is_dir():
            console.print("[red]Web dependencies are missing.[/red] Run: calflab setup")
            failures.append("web setup")
        else:
            if web or run_all:
                step("web: typecheck", [exe, "typecheck"], work)
                step("web: eslint", [exe, "lint"], work)
                step("web: vitest", [exe, "test"], work)
            if e2e or run_all:
                if not (webenv.dist_dir() / "index.html").is_file():
                    step("web: build", [exe, "build"], work)
                step(
                    "web: playwright smoke",
                    [exe, "e2e"],
                    work,
                    {"CALFLAB_PYTHON": sys.executable, "CALFLAB_REPO": str(root), "CALFLAB_WEB_DIST": str(webenv.dist_dir())},
                )
    console.rule("Summary")
    if failures:
        console.print(f"[red]FAILED:[/red] {', '.join(failures)}")
        raise typer.Exit(1)
    console.print("[green]All test suites passed.[/green]")


# ====================================================================== demo
DEMOS = ("walk", "override", "evolve", "export", "wire", "bridges", "all")


@app.command()
def demo(
    name: str = typer.Argument(..., help=f"One of: {', '.join(DEMOS)}"),
    project: Path | None = ProjectOpt,
) -> None:
    """Run a headless smoke demo against the project (no browser needed)."""
    if name not in DEMOS:
        console.print(f"[red]Unknown demo {name!r}.[/red] Choose one of: {', '.join(DEMOS)}")
        raise typer.Exit(2)
    lab_ = _open_lab(project)
    try:
        for d in DEMOS[:-1] if name == "all" else (name,):
            console.rule(f"demo {d}")
            globals()[f"_demo_{d}"](lab_)
    finally:
        from calflab.compute.local import LocalProcessPool

        LocalProcessPool.shutdown_all()
        lab_.close()


def _demo_walk(lab_) -> None:  # type: ignore[no-untyped-def]
    s = lab_.scene()
    console.print(f"Design: {len(s['bodies'])} bodies, {len(s['joints'])} joints, {s['mass']['total_g']:.0f} g "
                  f"(target {s['mass']['target_g']:.0f} g), height {s['extents']['height_mm']:.0f} mm")
    job = lab_.jobs.wait(lab_.run_sim().id)
    if job.status != "done":
        raise RuntimeError(job.error)
    m = job.result["metrics"]
    console.print(f"Run {job.result['run_id']} ({'cached' if job.result['cached'] else 'new'}): "
                  f"speed {m['speed_mps']:.3f} m/s, CoT {m['cost_of_transport']:.2f}, "
                  f"stability {m['stability']:.2f}, fell: {m['fell']}")


def _demo_override(lab_) -> None:  # type: ignore[no-untyped-def]
    r = lab_.execute("add_override", {"target": "leg.fl.shank", "param": "length", "value": 190}, client="cli")
    pv = lab_.scene()["elements"]["leg.fl.shank"]["params"]["length"]
    console.print(f"Override {r['result']['override']}: leg.fl.shank length {pv['parametric']} -> {pv['value']} mm")
    lab_.undo("cli")
    console.print("Undone (the override is gone, the command log remembers it).")


def _demo_evolve(lab_) -> None:  # type: ignore[no-untyped-def]
    job = lab_.run_evolve(params={"generations": 3, "batch_size": 8, "inner_iterations": 2},
                          sim={"duration_s": 3.0, "record_hz": 25})
    while job.status in ("queued", "running"):
        time.sleep(0.5)
        console.print(f"  {job.progress * 100:5.1f}%  {job.message}", end="\r")
    console.print()
    if job.status != "done":
        raise RuntimeError(job.error)
    view = lab_.evolve_view(job.result["run_id"])
    last = view["history"][-1]
    console.print(f"Run {job.result['run_id']}: {last['elites']} elites, best fitness {last['best']:.3f}, "
                  f"{last['evals']} rollouts, best candidate {job.result['best_candidate']}")


def _demo_export(lab_) -> None:  # type: ignore[no-untyped-def]
    for exporter in ("leg_segment_cad", "rhino_3dm", "gltf"):
        job = lab_.jobs.wait(lab_.export(exporter).id)
        if job.status != "done":
            console.print(f"[yellow]{exporter}: {job.error}[/yellow]")
            continue
        for rel in job.result["files"].values():
            console.print(f"  {exporter}: {rel}")


def _demo_wire(lab_) -> None:  # type: ignore[no-untyped-def]
    bom = lab_.analysis("bom")
    console.print(f"BOM: {len(bom['lines'])} lines, ${bom['total_cost_usd']:.0f}, {bom['unverified']} unverified")
    pb = lab_.analysis("power_budget")
    src = f"run {pb['run_id']}" if pb["from_run"] else "idle only (no sim run yet)"
    rt = pb["battery"]["runtime_min"] if pb["battery"] else None
    console.print(f"Power ({src}): mean {pb['mean_power_w']:.1f} W, peak {pb['peak_power_w']:.1f} W, runtime ~{rt} min")
    h = lab_.analysis("harness")
    console.print(f"Harness: {len(h['routes'])} cables, {h['total_length_mm']:.0f} mm, diagram {h['svg']} ({h['renderer']})")


def _demo_bridges(lab_) -> None:  # type: ignore[no-untyped-def]
    from calflab.bridge import armature_plan, rhino_build_list

    rb = rhino_build_list(lab_.design(), lab_.revision)
    console.print(f"Rhino build list: {len(rb['layers'])} layers, {len(rb['blocks'])} blocks, {len(rb['objects'])} objects")
    ap = armature_plan(lab_.design().spec)
    console.print(f"Blender armature: {len(ap['bones'])} bones, {len(ap['meshes'])} meshes")


# ====================================================================== plugins
@app.command("new-plugin")
def new_plugin(
    ptype: str = typer.Argument(..., metavar="TYPE", help="Plugin type (e.g. fitness_term, controller, exporter)."),
    name: str = typer.Argument(..., help="snake_case name; becomes the plugin key and file name."),
    force: bool = typer.Option(False, help="Overwrite existing files."),
) -> None:
    """Generate a plugin template in plugins/ plus a contract test."""
    from calflab.plugins.templates import create

    try:
        plugin_path, test_path = create(ptype, name, plugins_dir(), repo_root() / "tests" / "plugins", force)
    except (ValueError, FileExistsError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"Created [bold]{plugin_path.relative_to(repo_root())}[/bold]")
    console.print(f"Created [bold]{test_path.relative_to(repo_root())}[/bold]")
    console.print("The running lab picks it up automatically. Check it with: calflab test --py")


@app.command()
def plugins() -> None:
    """List registered plugins."""
    from calflab.plugins import load_plugins, registry

    load_plugins()
    table = Table(title="Plugins")
    for col in ("Type", "Key", "Label", "State", "Module"):
        table.add_column(col)
    for cls in registry.everything():
        table.add_row(cls.plugin_type, cls.key, cls.label, "planned" if cls.stub else "ready", cls.__module__)
    console.print(table)
    for src, err in registry.errors.items():
        console.print(f"[red]{src}: {err}[/red]")


# ====================================================================== registry
@registry_app.command("check")
def registry_check(project: Path | None = ProjectOpt) -> None:
    """Verify that the index, run files and artifacts agree."""
    lab_ = _open_lab(project)
    problems = lab_.registry.check()
    lab_.close()
    for p in problems:
        console.print(f"[yellow]{p}[/yellow]")
    console.print("[green]Registry is consistent.[/green]" if not problems else f"{len(problems)} problem(s).")
    if problems:
        raise typer.Exit(1)


@registry_app.command("rebuild")
def registry_rebuild(project: Path | None = ProjectOpt) -> None:
    """Rebuild index.sqlite from runs/*/run.json and designs/*/design.json."""
    lab_ = _open_lab(project)
    counts = lab_.registry.rebuild()
    lab_.close()
    console.print(f"Indexed {counts['runs']} runs, {counts['candidates']} candidates, {counts['designs']} designs.")


# ====================================================================== components
@components_app.command("audit")
def components_audit(
    project: Path | None = ProjectOpt,
    run_id: str = typer.Option("", "--run", help="Sim run to read torques from (default: latest sim run)."),
    simulate: bool = typer.Option(False, "--simulate", help="Simulate the current design first."),
) -> None:
    """List unverified components, the results that depend on them, and saturated actuators."""
    lab_ = _open_lab(project)
    try:
        if simulate:
            job = lab_.jobs.wait(lab_.run_sim().id)
            if job.status != "done":
                raise RuntimeError(job.error)
        rep = lab_.analysis("component_audit", {"run_id": run_id})
    finally:
        lab_.close()

    table = Table(title=f"Components: {rep['unverified']} of {rep['total']} unverified "
                        f"({rep['in_design_unverified']} used by this design)")
    for col in ("Component", "Kind", "Verified", "Quantity", "Cost USD", "Mass g"):
        table.add_column(col, no_wrap=True)
    for c in rep["components"]:
        qty = f"{c['qty']:g} {c['qty_unit']}".strip() if c["in_design"] else "not used"
        table.add_row(c["key"], c["kind"], "[green]yes[/]" if c["verified"] else "[yellow]no[/]", qty,
                      f"{c['cost_usd']:.0f}" if c["in_design"] else "", f"{c['mass_g']:.0f}" if c["in_design"] else "")
    console.print(table)

    table = Table(title="Results that rest on unverified components")
    for col in ("Result", "Value", "Unverified components it depends on"):
        table.add_column(col, overflow="fold")
    for r in rep["results"]:
        if r["value"] is None:
            value = "no sim run"
        elif r["key"] == "torque_margin":
            value = f"{max(0.0, r['value']) * 100:.0f}%"
        else:
            value = f"{r['value']:g} {r['unit']}".strip()
        if r["from_run"] is False and r["value"] is not None:
            value += " (idle only: no sim run)"
        table.add_row(r["label"], value, ", ".join(r["depends_on_unverified"]) or "-")
    console.print(table)

    if not rep["from_run"]:
        console.print("[yellow]No sim run yet, so there are no torque margins.[/yellow] "
                      "Run: calflab components audit --simulate")
        return
    table = Table(title=f"Torque margins from run {rep['run_id']} (lowest first)")
    for col in ("Joint", "Actuator", "Stall", "Usable", "Peak", "RMS", "Margin"):
        table.add_column(col, no_wrap=True)
    for r in sorted(rep["torque"], key=lambda x: x["margin"]):
        style = "red" if r["at_limit"] else ("yellow" if r["margin"] < 0.25 else "green")
        table.add_row(r["joint"], r["component"], f"{r['stall_nm']:.2f}", f"{r['available_nm']:.2f}",
                      f"{r['required_peak_nm']:.2f}", f"{r['required_rms_nm']:.2f}",
                      f"[{style}]{max(0.0, r['margin']) * 100:.0f}%[/]")
    console.print(table)
    console.print("Torques in N*m. Usable = stall x derating (simulation.torque_derating).")
    if rep["at_limit"]:
        console.print(f"[red]{len(rep['at_limit'])} actuator(s) reach their usable torque limit:[/red] "
                      + ", ".join(rep["at_limit"]))
    console.print(rep["note"])


@components_app.command("worksheet")
def components_worksheet(
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV to write (default: docs/component_verification.csv)."),
    force: bool = typer.Option(False, help="Overwrite an existing worksheet (your filled-in columns are lost)."),
) -> None:
    """Write a CSV with every recorded spec value and blank columns for the datasheet value."""
    from calflab.components import library
    from calflab.wiring import component_worksheet, component_worksheet_csv

    path = (out or repo_root() / "docs" / "component_verification.csv").resolve()
    if path.exists() and not force:
        console.print(f"[red]{path} already exists.[/red] Use --force to overwrite it, or --out for another file.")
        raise typer.Exit(2)
    lib = library()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(component_worksheet_csv(lib), encoding="utf-8-sig", newline="")
    console.print(f"Wrote [bold]{path}[/bold]: {len(component_worksheet(lib))} values across {len(lib.all())} components.")
    console.print("Fill in datasheet_value, datasheet_reference and ok; then correct config/components/*.yaml "
                  "and set verified: true yourself.")


# ====================================================================== bridges
def build_blender_addon() -> Path:
    """Zip bridges/blender/calflab_blender as a Blender extension (4.2+).

    Extensions keep ``blender_manifest.toml`` and ``__init__.py`` at the root
    of the zip (no wrapping folder).
    """
    src = repo_root() / "bridges" / "blender" / "calflab_blender"
    if not (src / "blender_manifest.toml").is_file():
        raise FileNotFoundError(src / "blender_manifest.toml")
    out = repo_root() / "bridges" / "blender" / "dist" / "calflab_blender.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(src))
    return out


@bridge_app.command("blender")
def bridge_blender(
    install: bool = typer.Option(False, "--install", help="Also install and enable it in Blender."),
    check: bool = typer.Option(False, "--check", help="Run the numerical bridge check in Blender (lab must be running)."),
    url: str = typer.Option("http://127.0.0.1:8000", help="Lab URL for --check."),
) -> None:
    """Build the Blender extension zip (and optionally install or check it)."""
    import json

    from calflab.cli.doctor import find_blender

    z = build_blender_addon()
    console.print(f"Built [bold]{z}[/bold]")
    if check:
        exe = find_blender()
        if exe is None:
            console.print("[red]Blender was not found.[/red]")
            raise typer.Exit(1)
        script = repo_root() / "bridges" / "blender" / "validate_in_blender.py"
        proc = subprocess.run(
            [str(exe), "--background", "--factory-startup", "--python", str(script)],
            capture_output=True, text=True, env={**os.environ, "CALFLAB_URL": url}, check=False,
        )
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("CALFLAB_BLENDER_CHECK ")), None)
        if line is None:
            console.print("[red]Blender produced no report.[/red]")
            console.print(proc.stdout[-1500:] + proc.stderr[-1500:])
            raise typer.Exit(1)
        rep = json.loads(line.split(" ", 1)[1])
        if rep.get("error"):
            console.print(f"[red]{rep['error']}[/red]")
        for key in ("blender", "hinges", "rollout", "clip"):
            if key in rep:
                console.print(f"{key}: {rep[key]}")
        console.print("[green]Blender bridge check passed.[/green]" if rep["ok"] else "[red]Blender bridge check FAILED.[/red]")
        if not rep["ok"]:
            raise typer.Exit(1)
        if not install:
            return
    if not install:
        console.print("Install it with: calflab bridge blender --install")
        console.print("or in Blender: Edit > Preferences > Get Extensions > (arrow menu) Install from Disk...")
        return
    exe = find_blender()
    if exe is None:
        console.print("[red]Blender was not found.[/red] Install Blender 4.2+ or add blender.exe to PATH.")
        raise typer.Exit(1)
    cmd = [str(exe), "--command", "extension", "install-file", "-r", "user_default", "-e", str(z)]
    code = subprocess.run(cmd, check=False).returncode
    if code != 0:
        console.print(f"[red]Blender could not install the extension (exit code {code}).[/red]")
        raise typer.Exit(1)
    console.print(f"Installed and enabled in {exe.parent.name}. Open the 3D viewport sidebar (N) > CALFLAB.")


@bridge_app.command("rhino")
def bridge_rhino() -> None:
    """Show how to install the Rhino 8 commands."""
    scripts = repo_root() / "bridges" / "rhino" / "scripts"
    console.print("In Rhino 8, run this once (it registers the Calflab* aliases):")
    console.print(f'  [bold]_-ScriptEditor _Run "{scripts / "CalflabInstall.py"}"[/bold]')
    console.print("Then type CalflabConnect, CalflabPull, CalflabPush or CalflabLiveSync in the Rhino command line.")


@app.command()
def version() -> None:
    """Print the CALFLAB version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
