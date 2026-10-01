"""Harness -> WireViz YAML and a diagram.

The harness routes of the RobotSpec (with real cable lengths from the routed
path) become a WireViz document. If the ``wireviz`` package and Graphviz
``dot`` are installed, WireViz renders the diagram; otherwise a simple built-in
SVG renderer is used so there is always something to look at (ADR-022).
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

import yaml

from calflab.model.spec import RobotSpec

_COLOR_HEX = {"RD": "#d23b3b", "BK": "#222222", "YE": "#e0c21b", "BU": "#3b6fd2", "GN": "#3ba55d", "WH": "#eeeeee"}


def _conn_name(element_id: str) -> str:
    return element_id.replace(".motor", "").replace(".board", "").replace(".", "_")


def wireviz_document(spec: RobotSpec) -> dict[str, Any]:
    """WireViz data structure (connectors, cables, connections) for the harness."""
    connectors: dict[str, Any] = {}
    cables: dict[str, Any] = {}
    connections: list[Any] = []
    for route in spec.harness_routes:
        n = len(route.wires)
        pins = [w.signal for w in route.wires]
        for end in (route.src, route.dst):
            name = _conn_name(end)
            c = connectors.setdefault(name, {"type": route.connector, "pinlabels": [], "notes": end})
            for sig in pins:
                if sig not in c["pinlabels"]:
                    c["pinlabels"].append(sig)
        cable = route.id.replace(".", "_")
        cables[cable] = {
            "wirecount": n,
            "length": round(route.length_mm / 1000.0, 3),
            "gauge": f"{route.wires[0].gauge_awg} AWG" if route.wires else "",
            "colors": [w.color for w in route.wires],
            "wirelabels": pins,
            "notes": f"{route.length_mm:.0f} mm via {', '.join(route.via_bodies) or 'trunk'}",
        }
        src, dst = _conn_name(route.src), _conn_name(route.dst)
        connections.append(
            [
                {src: [connectors[src]["pinlabels"].index(s) + 1 for s in pins]},
                {cable: list(range(1, n + 1))},
                {dst: [connectors[dst]["pinlabels"].index(s) + 1 for s in pins]},
            ]
        )
    return {"connectors": connectors, "cables": cables, "connections": connections}


def wireviz_yaml(spec: RobotSpec) -> str:
    return yaml.safe_dump(wireviz_document(spec), sort_keys=False)


def fallback_svg(spec: RobotSpec) -> str:
    """Minimal harness diagram: one row per cable, wires coloured, lengths labelled."""
    routes = spec.harness_routes
    row_h, pad, width = 26, 16, 760
    y = pad + 30
    parts: list[str] = []
    for r in routes:
        block_h = max(len(r.wires), 1) * row_h + 26
        src, dst = html.escape(_conn_name(r.src)), html.escape(_conn_name(r.dst))
        parts.append(f'<text x="{width / 2}" y="{y + 12}" text-anchor="middle" class="t">'
                     f'{html.escape(r.id)} · {r.length_mm:.0f} mm · {html.escape(r.connector)}</text>')
        for bx, name in ((pad, src), (width - pad - 170, dst)):
            parts.append(f'<rect x="{bx}" y="{y + 18}" width="170" height="{block_h - 22}" rx="4" class="c"/>')
            parts.append(f'<text x="{bx + 85}" y="{y + 33}" text-anchor="middle" class="n">{name}</text>')
        for i, w in enumerate(r.wires):
            wy = y + 48 + i * row_h
            color = _COLOR_HEX.get(w.color, "#888888")
            parts.append(f'<line x1="{pad + 170}" y1="{wy}" x2="{width - pad - 170}" y2="{wy}" stroke="{color}" stroke-width="3"/>')
            parts.append(f'<text x="{pad + 162}" y="{wy + 4}" text-anchor="end" class="p">{html.escape(w.signal)}</text>')
            parts.append(f'<text x="{width - pad - 162}" y="{wy + 4}" class="p">{html.escape(w.signal)}</text>')
            parts.append(f'<text x="{width / 2}" y="{wy - 5}" text-anchor="middle" class="g">{w.gauge_awg} AWG</text>')
        y += block_h + 24
    height = y + pad
    style = (
        ".t{font:600 12px sans-serif;fill:#333}.n{font:600 11px sans-serif;fill:#222}"
        ".p{font:10px monospace;fill:#333}.g{font:9px sans-serif;fill:#777}"
        ".c{fill:#f4f4f4;stroke:#555}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f"<style>{style}</style><rect width='100%' height='100%' fill='white'/>"
        f'<text x="{pad}" y="{pad + 10}" class="t">Harness (built-in renderer; install wireviz + Graphviz for the full diagram)</text>'
        + "".join(parts)
        + "</svg>"
    )


def wireviz_available() -> tuple[bool, str]:
    try:
        import wireviz  # noqa: F401
    except ImportError:
        return False, "the wireviz package is not installed"
    if shutil.which("dot") is None:
        return False, "Graphviz 'dot' is not on PATH (winget install Graphviz.Graphviz)"
    return True, "ok"


def render(spec: RobotSpec, out_dir: Path, name: str = "harness") -> dict[str, Any]:
    """Write ``<name>.yml`` and ``<name>.svg``. Returns paths and which renderer was used."""
    out_dir.mkdir(parents=True, exist_ok=True)
    yml = out_dir / f"{name}.yml"
    yml.write_text(wireviz_yaml(spec), encoding="utf-8")
    svg = out_dir / f"{name}.svg"
    ok, reason = wireviz_available()
    renderer = "fallback"
    if ok:
        try:
            from wireviz import wireviz as wv

            wv.parse(wireviz_document(spec), output_formats=("svg",), output_dir=out_dir, output_name=name)
            renderer = "wireviz"
        except Exception as exc:  # fall back rather than fail the export
            reason = f"wireviz failed: {exc}"
    if renderer == "fallback":
        svg.write_text(fallback_svg(spec), encoding="utf-8")
    return {"yaml": yml, "svg": svg, "renderer": renderer, "reason": reason}
