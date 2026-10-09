"""Printed mass of an infilled solid (ADR-054).

A part modelled as a full solid but printed with infill is lighter than its
volume x the material density. The estimate here is the one a person would
make by hand: a *shell* of the wall thickness (perimeters x line width) all
round the solid at full material density, plus the *core* inside it at the
infill percentage of that density.

The core is the set of points of the solid that are deeper than the wall
thickness below its surface. It is measured once, when the mesh arrives, on a
grid (:func:`measure_core`) and stored beside the solid's own properties, so
building a design needs no file access. Where a feature is thinner than twice
the wall there is no point that deep: the core is simply empty there and the
feature counts as fully dense. The core is a subset of the solid, so the
estimate always lies between the all-infill and the fully dense mass.

What it ignores: the infill pattern, the print direction (top and bottom
layers are taken to be as thick as the walls), the slicer's real tool path,
supports, brims and under- or over-extrusion. A weighed print is better.

Units: mm, mm^3, and mm^5 for unit-density inertia (as in :mod:`calflab.model.solid`).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from calflab.model.solid import WELD_DIGITS, SolidInfo, inertia_matrix
from calflab.model.spec import Inertia6
from calflab.model.xform import Vec3

#: user-text keys on a Rhino object are ``calflab.print.<name>``
TAG_PREFIX = "calflab.print."
#: the tags the estimate needs, and what each is
TAGS: dict[str, str] = {
    "infill": "infill percentage, 0 to 100",
    "perimeters": "number of perimeters (walls), 1 or more",
    "line_width": "line (extrusion) width in mm",
}
MAX_CELLS = 16_000_000  # grid cells the core is measured on; the pitch grows for a larger solid
_JITTER = (0.0137, 0.0291, 0.0173)  # grid offset in pitches, so no grid line runs along a mesh edge
_NEAREST = 6  # triangles (those of the nearest surface samples) a grid point's exact distance is taken over


class PrintSettings(BaseModel):
    """How a solid is printed, as tagged on it. Nothing here has a default."""

    infill_pct: float
    perimeters: int
    line_width_mm: float
    #: other ``calflab.print.*`` tags found on the solid, which the estimate does not use
    ignored: list[str] = Field(default_factory=list)

    @property
    def wall_mm(self) -> float:
        return self.perimeters * self.line_width_mm

    @property
    def fraction(self) -> float:
        return self.infill_pct / 100.0


class PrintCore(BaseModel):
    """The part of a solid deeper than the wall thickness: what is printed as infill."""

    wall_mm: float
    pitch_mm: float = 0.0  # grid pitch it was measured with (0 = no grid was needed)
    volume_mm3: float = 0.0
    com_mm: Vec3 = (0.0, 0.0, 0.0)
    #: inertia about its own centre for density 1 (mm^5), body axes
    inertia_mm5: Inertia6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _number(key: str, text: Any, units: tuple[str, ...]) -> float:
    s = str(text).strip().lower().replace(",", ".")
    for unit in units:
        if s.endswith(unit):
            s = s[: -len(unit)].strip()
    try:
        value = float(s)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise ValueError(f"{TAG_PREFIX}{key} = {str(text)!r} is not a number ({TAGS[key]})")
    return value


def parse_print_tags(tags: dict[str, Any] | None) -> PrintSettings | None:
    """Print settings from a solid's ``calflab.print.*`` user text (keys with or
    without the prefix), or None if it carries none of the three tags: such a
    solid is fully dense.

    Raises ``ValueError`` with a message for the person when a tag is missing
    or cannot be read. No value is ever assumed.
    """
    given: dict[str, Any] = {}
    for key, value in (tags or {}).items():
        name = str(key).strip().lower()
        name = name[len(TAG_PREFIX):] if name.startswith(TAG_PREFIX) else name
        if str(value).strip():
            given[name] = value
    ignored = sorted(f"{TAG_PREFIX}{k}" for k in given if k not in TAGS)
    if not any(k in given for k in TAGS):
        return None
    missing = [f"{TAG_PREFIX}{k}" for k in TAGS if k not in given]
    if missing:
        raise ValueError(
            f"it has print tags but not {', '.join(missing)}. An infill estimate needs all of "
            f"{', '.join(TAG_PREFIX + k for k in TAGS)}; no value is assumed"
        )
    infill = _number("infill", given["infill"], ("%", "percent"))
    if 0 < infill < 1:
        raise ValueError(f"{TAG_PREFIX}infill = {str(given['infill'])!r} looks like a fraction: write the percentage, e.g. 15")
    if not 0 <= infill <= 100:
        raise ValueError(f"{TAG_PREFIX}infill = {str(given['infill'])!r} must be between 0 and 100 (percent)")
    perimeters = _number("perimeters", given["perimeters"], ())
    if perimeters < 1 or perimeters != int(perimeters):
        raise ValueError(f"{TAG_PREFIX}perimeters = {str(given['perimeters'])!r} must be a whole number, 1 or more")
    width = _number("line_width", given["line_width"], ("mm",))
    if width <= 0:
        raise ValueError(f"{TAG_PREFIX}line_width = {str(given['line_width'])!r} must be more than 0 (mm)")
    return PrintSettings(infill_pct=infill, perimeters=int(perimeters), line_width_mm=width, ignored=ignored)


# ---------------------------------------------------------------------- the core, measured on a grid
def _inside_grid(v: np.ndarray, f: np.ndarray, g0: np.ndarray, h: float, n: tuple[int, int, int]) -> np.ndarray:
    """Which grid cell centres are inside the closed mesh (bool, shape ``n``).

    Each triangle is projected along Z onto the grid columns it covers; a cell
    is inside when an odd number of crossings lies below its centre. A column
    exactly on an edge shared by two triangles is given to one of them.
    """
    nx, ny, nz = n
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    lo = np.minimum(np.minimum(a, b), c)[:, :2]
    hi = np.maximum(np.maximum(a, b), c)[:, :2]
    i0 = np.clip(np.ceil((lo - g0[:2]) / h - 0.5), 0, (nx, ny)).astype(np.int64)
    i1 = np.clip(np.floor((hi - g0[:2]) / h - 0.5), -1, (nx - 1, ny - 1)).astype(np.int64)
    span = np.maximum(i1 - i0 + 1, 0)
    columns = span[:, 0] * span[:, 1]
    toggles = np.zeros(nx * ny * (nz + 1), dtype=np.uint8)
    todo = np.nonzero((area2 != 0) & (columns > 0))[0]
    start = 0
    while start < len(todo):
        stop = start + max(int(np.searchsorted(np.cumsum(columns[todo[start:]]), 2_000_000, side="right")), 1)
        t = todo[start:stop]
        start = stop
        count = columns[t]
        rep = np.repeat(np.arange(len(t)), count)
        local = np.arange(int(count.sum())) - (np.cumsum(count) - count)[rep]
        tri = t[rep]
        ix = i0[tri, 0] + local // span[tri, 1]
        iy = i0[tri, 1] + local % span[tri, 1]
        px = g0[0] + (ix + 0.5) * h
        py = g0[1] + (iy + 0.5) * h
        sign = np.sign(area2[tri])
        hit = np.ones(len(tri), dtype=bool)
        z = np.zeros(len(tri))
        for e in range(3):
            ia, ib = f[tri, e], f[tri, (e + 1) % 3]
            swap = ia > ib  # the edge function is evaluated from the same end for both triangles of an edge
            p0, p1 = v[np.where(swap, ib, ia)], v[np.where(swap, ia, ib)]
            w = (p1[:, 0] - p0[:, 0]) * (py - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (px - p0[:, 0])
            w = np.where(swap, -w, w) * sign
            dx, dy = (v[ib, 0] - v[ia, 0]) * sign, (v[ib, 1] - v[ia, 1]) * sign
            hit &= (w > 0) | ((w == 0) & ((dy > 0) | ((dy == 0) & (dx > 0))))
            z += w * v[f[tri, (e + 2) % 3], 2]
        z = z[hit] / np.abs(area2[tri[hit]])
        k = np.clip(np.floor((z - g0[2]) / h - 0.5) + 1, 0, nz).astype(np.int64)
        np.bitwise_xor.at(toggles, (ix[hit] * ny + iy[hit]) * (nz + 1) + k, 1)
    return (np.cumsum(toggles.reshape(nx, ny, nz + 1)[:, :, :nz], axis=2, dtype=np.uint8) & 1).astype(bool)


def _surface_samples(v: np.ndarray, f: np.ndarray, spacing: float) -> tuple[np.ndarray, np.ndarray]:
    """Points on the surface no further apart than ``spacing``, and the triangle each lies on."""
    # a fan from the corner opposite the shortest edge: a long thin triangle gets many steps along, few across
    tri = v[f]
    lengths = np.linalg.norm(tri[:, [2, 0, 1]] - tri[:, [1, 2, 0]], axis=2)  # edge opposite each corner
    apex = lengths.argmin(axis=1)
    rows = np.arange(len(f))
    a, b, c = tri[rows, apex], tri[rows, (apex + 1) % 3], tri[rows, (apex + 2) % 3]
    along = np.maximum(np.ceil(np.delete(lengths, apex + 3 * rows).reshape(-1, 2).max(axis=1) / spacing), 1).astype(np.int64)
    across = np.maximum(np.ceil(lengths[rows, apex] / spacing), 1).astype(np.int64)
    count = (along + 1) * (across + 1)
    owner = np.repeat(rows, count)
    local = np.arange(int(count.sum())) - (np.cumsum(count) - count)[owner]
    t = (local // (across[owner] + 1)) / along[owner]
    s = (local % (across[owner] + 1)) / across[owner]
    base = b[owner] + s[:, None] * (c[owner] - b[owner])
    return a[owner] + t[:, None] * (base - a[owner]), owner


def _closest_on_triangle(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """The point of each triangle nearest to its point (rows of ``p``, ``a``, ``b``, ``c``)."""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
    q = np.empty_like(p)
    done = np.zeros(len(p), dtype=bool)

    def put(region: np.ndarray, value: np.ndarray) -> None:
        m = region & ~done
        q[m] = value[m]
        done[m] = True

    put((d1 <= 0) & (d2 <= 0), a)
    put((d3 >= 0) & (d4 <= d3), b)
    put((d6 >= 0) & (d5 <= d6), c)
    with np.errstate(divide="ignore", invalid="ignore"):
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + (d1 / (d1 - d3))[:, None] * ab)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + (d2 / (d2 - d6))[:, None] * ac)
        put((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), b + ((d4 - d3) / ((d4 - d3) + (d5 - d6)))[:, None] * (c - b))
        total = va + vb + vc
        put(np.ones(len(p), dtype=bool), a + (vb / total)[:, None] * ab + (vc / total)[:, None] * ac)
    return q


def _surface_distance(points: np.ndarray, tree: Any, owner: np.ndarray, v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact distance from each point to the surface and the surface point it is
    measured to, taken over the triangles of the nearest surface samples."""
    k = min(_NEAREST, len(owner))
    dist = np.empty(len(points))
    foot = np.empty((len(points), 3))
    for start in range(0, len(points), 200_000):
        p = points[start:start + 200_000]
        _, hits = tree.query(p, k=k, workers=-1)
        tri = f[owner[np.asarray(hits).reshape(len(p), k)]].reshape(-1, 3)
        rep = np.repeat(p, k, axis=0)
        q = _closest_on_triangle(rep, v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]])
        d = np.linalg.norm(rep - q, axis=1).reshape(len(p), k)
        best = d.argmin(axis=1)
        rows = np.arange(len(p))
        dist[start:start + 200_000] = d[rows, best]
        foot[start:start + 200_000] = q.reshape(len(p), k, 3)[rows, best]
    return dist, foot


def measure_core(vertices: Any, faces: Any, wall_mm: float, max_cells: int = MAX_CELLS) -> PrintCore:
    """Volume, centre and unit-density inertia of the region of a closed mesh
    that is deeper than ``wall_mm`` below its surface.

    Measured on a grid of pitch ``wall_mm / 2`` (coarser for a solid too large
    for :data:`MAX_CELLS`). A cell well inside counts whole; a cell within half
    a pitch of the wall depth counts in proportion to its exact distance from
    the surface, so a flat wall is measured exactly whatever the pitch. The
    mesh must be a closed solid (see :func:`calflab.model.solid.analyze_mesh`).
    """
    import trimesh
    from scipy.ndimage import maximum_filter1d
    from scipy.spatial import cKDTree

    core = PrintCore(wall_mm=wall_mm)
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, dtype=float), faces=np.asarray(faces, dtype=int), process=False)
    mesh.merge_vertices(digits_vertex=WELD_DIGITS)
    mesh.update_faces(mesh.nondegenerate_faces())
    v, f = np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=np.int64)
    if len(f) < 4:
        return core
    room = (v.max(axis=0) - v.min(axis=0)) - 2.0 * wall_mm  # the box the core must lie in
    if wall_mm <= 0 or float(room.min()) <= 0:
        return core  # thinner than two walls everywhere: no core
    ref = (v.max(axis=0) + v.min(axis=0)) / 2.0  # sums are taken about the middle of the solid
    v = v - ref
    h = wall_mm / 2.0
    while float(np.prod(np.ceil(room / h) + 4)) > max_cells:
        h *= 1.05
    g0 = v.min(axis=0) + wall_mm - h * (1.5 + np.asarray(_JITTER))
    dims = np.ceil((room + 3.0 * h) / h).astype(int) + 1
    n = (int(dims[0]), int(dims[1]), int(dims[2]))
    inside = _inside_grid(v, f, g0, h, n)

    # cells near the surface need their distance from it; the rest of the inside is core for certain
    samples, owner = _surface_samples(v, f, h)
    cells = np.clip(np.floor((samples - g0) / h).astype(np.int64), 0, np.asarray(n) - 1)
    near = np.zeros(n, dtype=np.uint8)
    near[cells[:, 0], cells[:, 1], cells[:, 2]] = 1
    ramp = min(h, 2.0 * wall_mm)  # depth over which a cell goes from shell to core
    reach = int((wall_mm + ramp / 2.0 + h) / h) + 2
    for axis in range(3):
        near = maximum_filter1d(near, size=2 * reach + 1, axis=axis, mode="constant")
    band = inside & (near > 0)
    deep = inside & ~band
    index = np.argwhere(band)
    points = g0 + (index + 0.5) * h
    weight = np.zeros(len(points))
    if len(points):
        tree = cKDTree(samples)
        nearest, _ = tree.query(points, k=1, workers=-1)
        weight[nearest >= wall_mm + ramp / 2.0 + h] = 1.0  # the surface is at most one spacing nearer than a sample
        unsure = np.nonzero((nearest > wall_mm - ramp / 2.0) & (nearest < wall_mm + ramp / 2.0 + h))[0]
        dist, foot = _surface_distance(points[unsure], tree, owner, v, f)
        part = np.clip(0.5 + (dist - wall_mm) / ramp, 0.0, 1.0)
        # A cell a little short of the wall depth counts in part only if the solid does get that deep just
        # beyond it. In a feature thinner than two walls it does not (the far wall comes first): no core there.
        short = np.nonzero((part > 0) & (dist < wall_mm) & (dist > 0))[0]
        if len(short):
            inward = (points[unsure][short] - foot[short]) / dist[short, None]
            beyond, _ = _surface_distance(points[unsure][short] + inward * (wall_mm - dist[short, None]), tree, owner, v, f)
            part[short[beyond < wall_mm - 0.05 * h]] = 0.0
        weight[unsure] = part

    cell = h**3
    axes = [g0[i] + (np.arange(n[i]) + 0.5) * h for i in range(3)]
    volume = cell * (float(deep.sum()) + float(weight.sum()))
    if volume <= 0:
        return core
    first = np.array([float((deep.sum(axis=tuple(j for j in range(3) if j != i)) * axes[i]).sum()) for i in range(3)])
    first += (points * weight[:, None]).sum(axis=0)
    second = (points * weight[:, None]).T @ points
    for i in range(3):
        second[i, i] += float((deep.sum(axis=tuple(j for j in range(3) if j != i)) * axes[i] ** 2).sum())
        for j in range(i + 1, 3):
            pair = deep.sum(axis=3 - i - j)  # counts over the remaining axis, shape (n_i, n_j)
            second[i, j] += float(axes[i] @ pair @ axes[j])
            second[j, i] = second[i, j]
    com = cell * first / volume
    central = cell * second - volume * np.outer(com, com) + np.eye(3) * volume * h * h / 12.0  # + each cell's own extent
    inertia = np.trace(central) * np.eye(3) - central
    core.pitch_mm = h
    core.volume_mm3 = volume
    centre = com + ref
    core.com_mm = (float(centre[0]), float(centre[1]), float(centre[2]))
    core.inertia_mm5 = (float(inertia[0, 0]), float(inertia[1, 1]), float(inertia[2, 2]),
                        float(inertia[0, 1]), float(inertia[0, 2]), float(inertia[1, 2]))
    return core


def scale_core(core: PrintCore, factor: float) -> None:
    """Scale the core with its solid when the sender's exact volume replaces the mesh volume."""
    core.volume_mm3 *= factor
    i = core.inertia_mm5
    core.inertia_mm5 = (i[0] * factor, i[1] * factor, i[2] * factor, i[3] * factor, i[4] * factor, i[5] * factor)


# ---------------------------------------------------------------------- shell + core
def printed_solid(solid: SolidInfo, core: PrintCore, fraction: float) -> tuple[float, Vec3, Inertia6]:
    """The solid as printed: its shell at full density and its core at
    ``fraction`` (0..1) of it. Returns the equivalent dense volume (mm^3; times
    the material density it is the mass), the centre of mass (mm) and the
    inertia about it for density 1 (mm^5).

    The printed solid is the dense solid minus ``1 - fraction`` of the core, so
    mass, centre and inertia all follow the real distribution: a part with a
    thick end and a thin end has its centre of mass towards the thin, denser end.
    """
    lighter = 1.0 - fraction
    core_volume = min(core.volume_mm3, solid.volume_mm3)
    if lighter <= 0 or core_volume <= 0:
        return solid.volume_mm3, solid.com_mm, solid.inertia_mm5
    volume = solid.volume_mm3 - lighter * core_volume
    c_solid, c_core = np.asarray(solid.com_mm), np.asarray(core.com_mm)
    com = (solid.volume_mm3 * c_solid - lighter * core_volume * c_core) / volume

    def about_com(i6: Inertia6, vol: float, centre: np.ndarray) -> np.ndarray:
        d = centre - com
        return inertia_matrix(i6) + vol * (float(d @ d) * np.eye(3) - np.outer(d, d))

    scale = core_volume / core.volume_mm3
    core_i = (core.inertia_mm5[0] * scale, core.inertia_mm5[1] * scale, core.inertia_mm5[2] * scale,
              core.inertia_mm5[3] * scale, core.inertia_mm5[4] * scale, core.inertia_mm5[5] * scale)
    i = about_com(solid.inertia_mm5, solid.volume_mm3, c_solid) - lighter * about_com(core_i, core_volume, c_core)
    return (
        volume,
        (float(com[0]), float(com[1]), float(com[2])),
        (float(i[0, 0]), float(i[1, 1]), float(i[2, 2]), float(i[0, 1]), float(i[0, 2]), float(i[1, 2])),
    )


def estimate_info(solid: SolidInfo, core: PrintCore, settings: PrintSettings, density_g_cm3: float) -> dict[str, Any]:
    """What an infill estimate was made from, for the breakdown, the run record
    and the printouts: the settings, the outer, shell and core volumes, the
    fully dense mass, and one line of text saying all of it."""
    core_volume = min(core.volume_mm3, solid.volume_mm3)
    shell = solid.volume_mm3 - core_volume
    dense = solid.volume_mm3 * density_g_cm3 / 1000.0
    wall = f"{settings.infill_pct:g} % infill, {settings.perimeters} perimeter{'s' if settings.perimeters != 1 else ''} x " \
           f"{settings.line_width_mm:g} mm = {settings.wall_mm:g} mm wall"
    if core_volume > 0:
        label = (f"infill estimate: {wall}; shell {shell / 1000.0:.1f} cm3 at full density + core "
                 f"{core_volume / 1000.0:.1f} cm3 at {settings.infill_pct:g} %; fully dense it would be {dense:.1f} g")
    else:
        label = (f"infill estimate: {wall}; no core (nowhere thicker than two walls), so all "
                 f"{solid.volume_mm3 / 1000.0:.1f} cm3 count at full density")
    return {
        "infill_pct": settings.infill_pct,
        "perimeters": settings.perimeters,
        "line_width_mm": settings.line_width_mm,
        "wall_mm": round(settings.wall_mm, 4),
        "volume_mm3": round(solid.volume_mm3, 2),
        "shell_volume_mm3": round(shell, 2),
        "core_volume_mm3": round(core_volume, 2),
        "pitch_mm": round(core.pitch_mm, 4),
        "dense_g": round(dense, 2),
        "ignored": list(settings.ignored),
        "label": label,
    }
