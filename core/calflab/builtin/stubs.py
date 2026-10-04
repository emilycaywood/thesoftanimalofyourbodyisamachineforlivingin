"""Later-phase features, scaffolded as plugins with real interfaces.

Each class documents the intended design, declares its parameters (so the UI
already shows them), and raises ``NotImplementedError`` with a clear message.
``stub = True`` makes the UI show a "planned" badge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from calflab.plugins import Analysis, Behavior, ExportContext, Exporter, register
from calflab.schema import P


# ====================================================================== fabrication (Phase 4)
@register
class MoldExporter(Exporter):
    """Phase 4: two-part (or multi-part) molds for cast silicone parts.

    Plan: take the skin surface of a region (head, muzzle, hooves), offset by
    the skin thickness for the core, build a bounding block, split along a
    parting surface derived from the silhouette, add registration keys, pour
    spout and vents, check minimum wall thickness, export each half as
    STEP/3MF plus a parting-line preview for the mold view.
    """

    key = "mold"
    label = "Silicone mold"
    description = "Mold halves with parting line, keys, pour spout and vents (Phase 4)."
    formats = ["step", "3mf"]
    category = "fabrication"
    stub = True

    class Params(BaseModel):
        region: str = P("skin.head", desc="Skin region to mold.")
        wall: float = P(6.0, unit="mm", ge=2, le=20, desc="Minimum mold wall thickness.")
        keys: int = P(4, ge=2, le=12, desc="Number of registration keys.")
        pour_diameter: float = P(12.0, unit="mm", ge=4, le=40, desc="Pour spout diameter.")
        vent_diameter: float = P(2.0, unit="mm", ge=0.5, le=6, desc="Vent diameter.")

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        raise NotImplementedError("Mold generation is planned for Phase 4.")


@register
class SkinPatternExporter(Exporter):
    """Phase 4: flatten skin regions into sewing patterns.

    Plan: mesh each skin region, cut along its seams, flatten with libigl
    (LSCM for the initial map, ARAP to reduce distortion), compute the
    per-triangle distortion map, add seam allowance, notches, match marks and
    grainline, lay pieces out on the fabric width, export DXF/SVG and a tiled
    1:1 PDF.
    """

    key = "skin_pattern"
    label = "Skin pattern"
    description = "Flattened skin pieces with seam allowance, notches and grainline (Phase 4)."
    formats = ["dxf", "svg", "pdf"]
    category = "fabrication"
    stub = True

    class Params(BaseModel):
        seam_allowance: float = P(8.0, unit="mm", ge=0, le=30, desc="Seam allowance.")
        fabric_width: float = P(1500.0, unit="mm", ge=300, le=3000, desc="Fabric width for the layout.")
        method: Literal["lscm", "arap"] = P("arap", desc="Flattening method.")
        paper: Literal["A4", "Letter", "A3"] = P("Letter", desc="Paper size for the tiled 1:1 PDF.")

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        raise NotImplementedError("Skin flattening is planned for Phase 4 (libigl ARAP/LSCM).")


@register
class NestingExporter(Exporter):
    """Phase 2+: build-plate nesting of printable parts for a printer profile."""

    key = "nesting"
    label = "Build-plate nesting"
    description = "Arrange parts on a printer's build plate with orientation and spacing (planned)."
    formats = ["3mf"]
    category = "fabrication"
    stub = True

    class Params(BaseModel):
        plate_x: float = P(256.0, unit="mm", ge=100, le=600, desc="Build plate X.")
        plate_y: float = P(256.0, unit="mm", ge=100, le=600, desc="Build plate Y.")
        spacing: float = P(5.0, unit="mm", ge=1, le=30, desc="Gap between parts.")

    def export(self, ctx: ExportContext, out_dir: Path) -> list[Path]:
        raise NotImplementedError("Nesting is planned; export parts individually for now.")


# ====================================================================== behavior (Phase 4)
@register
class Idle(Behavior):
    """Stand and breathe: the default behavior of the performance mode."""

    key = "idle"
    label = "Idle"
    description = "Stand still with small breathing and weight-shift motions."

    class Params(BaseModel):
        breathing_rate: float = P(0.25, unit="Hz", ge=0.05, le=1, step=0.05, desc="Breathing frequency.")

    def tick(self, t: float, sensors: dict[str, Any]) -> dict[str, Any]:
        return {"gait": None, "pose": "stand", "breathing_rate": self.params.breathing_rate}  # type: ignore[attr-defined]


@register
class TouchResponse(Behavior):
    """Phase 4: react to capacitive touch (head, muzzle, flank) and sound."""

    key = "touch_response"
    label = "Touch response"
    description = "Turn the head toward touch; lean into a flank stroke (Phase 4)."
    stub = True

    class Params(BaseModel):
        sensitivity: float = P(0.5, ge=0, le=1, step=0.05, desc="How readily touch triggers a response.")

    def tick(self, t: float, sensors: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("The behavior layer with touch/audio sensing is planned for Phase 4.")


@register
class PuppeteerBlend(Behavior):
    """Phase 4: an operator blends authored animation clips with autonomous behavior."""

    key = "puppeteer_blend"
    label = "Puppeteering blend"
    description = "Blend operator-triggered animation clips with autonomy (Phase 4 performance mode)."
    stub = True

    class Params(BaseModel):
        clip: str = P("", desc="Motion-library clip to blend in.")
        weight: float = P(0.5, ge=0, le=1, step=0.05, desc="0 = autonomous, 1 = authored clip.")

    def tick(self, t: float, sensors: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Performance mode is planned for Phase 4.")


# ====================================================================== sim-to-real (Phase 3)
@register
class SystemId(Analysis):
    """Phase 3: fit actuator and skin parameters from single-leg bench logs.

    Plan: import a CSV of commanded/measured joint angle, current and
    temperature; replay the commands in simulation; fit kp/kd, friction,
    torque constant, thermal constants and skin stiffness/damping by least
    squares; write the fitted values back to the component YAML as a proposal
    (never setting ``verified`` automatically).
    """

    key = "system_id"
    label = "Single-leg system ID"
    description = "Fit actuator and skin parameters from bench logs (Phase 3)."
    stub = True

    class Params(BaseModel):
        log: str = P("", desc="Project-relative path of the bench log CSV.")
        joint: str = P("joint.fl.knee", desc="Joint that was tested.")

    def run(self, lab: Any) -> dict[str, Any]:
        raise NotImplementedError("System identification is planned for Phase 3.")
