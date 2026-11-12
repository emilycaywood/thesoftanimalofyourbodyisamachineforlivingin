"""R18 (ADR-115): the McMaster-Carr timing belt parts, the only ones offered to the body's belt drives from now on.

Adds to a belt catalog folder (``config/belts`` and a project's ``catalog``), idempotently:

* two belt systems, ``MM-2MGT-6`` and ``MM-3MGT-9`` (closed-loop neoprene GT belts, fiberglass cord, nylon-coated
  teeth). Breaking strength = the RESEARCHER'S ASSUMPTION of 2026-11-12, 51 lbf per 1/8 in of width (named in
  ``guessed``); allowable working tension null (not published, not supplied, never derived);
* two length sources (McMaster 2MGT closed, McMaster 3MGT closed) and every listed closed length with its part number;
* the single pulleys with a finished 1/4 in bore (2MGT 60T and 72T; 3MGT 16T-45T). Any driver x driven pair of one
  pitch is the pair ``<driver id>+<driven id>`` (ADR-103), so no pair entry is written;
* every earlier system, pair, pulley, length source and length is marked ``not_sourceable`` with the evidence. Nothing
  is deleted: stored bodies still build.

The part list, prices and listed pulley PDs were supplied by the researcher from mcmaster.com on 2026-11-12. What the
part pages themselves list (hub diameter, OD, widths, flanges, mount; belt prices) is in ``PAGES``, read in the
built-in browser in session R18; a value a page does not list is not entered. No mass is entered: no page read lists
one. Every entry: ``verified: false``, ``purchase_confirmed: false``.

Run:  python docs/studies/catalog_r18.py <catalog dir> [<catalog dir> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DATE = "2026-11-12"
VENDOR = "McMaster-Carr"
URL = "https://www.mcmaster.com/{}/"

# --------------------------------------------------------------------- supplied by the researcher (2026-11-12)
#: teeth: (part number, listed pitch diameter mm, flanges, price USD each); 1/4 in finished bore, set screw
PULLEYS_2 = {60: ("3764N118", 38.2, 2, 20.33), 72: ("3764N119", 45.8, 0, 23.13)}
PULLEYS_3 = {16: ("3764N125", 15.3, 1, 16.96), 17: ("3764N126", 16.2, 1, 16.31), 18: ("3764N127", 17.2, 2, 16.37),
             20: ("3764N128", 19.1, 2, 11.06), 22: ("3764N129", 21.0, 2, 16.96), 24: ("3764N13", 22.9, 2, 17.37),
             25: ("3764N131", 23.9, 2, 17.58), 26: ("3764N132", 24.8, 2, 17.58), 28: ("3764N133", 26.7, 2, 14.31),
             30: ("3764N134", 28.7, 2, 19.38), 32: ("3764N135", 30.6, 2, 14.50), 34: ("3764N136", 32.5, 2, 21.19),
             36: ("3764N137", 34.4, 2, 22.08), 40: ("3764N139", 38.2, 2, 16.44), 44: ("3764N14", 42.0, 2, 22.33),
             45: ("3764N141", 43.0, 2, 16.71)}
#: belt teeth: part number suffix (7947K...)
BELTS_2 = {50: 711, 56: 712, 62: 713, 63: 714, 67: 715, 68: 716, 70: 717, 76: 718, 79: 719, 80: 721, 82: 722, 86: 725,
           90: 726, 93: 727, 96: 728, 100: 729, 101: 731, 106: 732, 110: 733, 116: 734, 118: 735, 120: 736, 125: 737,
           126: 738, 129: 739, 140: 741, 150: 742, 160: 743, 166: 744, 175: 745, 185: 746, 190: 747, 200: 748,
           210: 749, 228: 751, 244: 753, 252: 754, 264: 755, 276: 756, 288: 757, 300: 758, 320: 759, 348: 761,
           372: 762, 424: 763, 582: 764}
BELTS_3 = {33: 765, 41: 767, 55: 769, 60: 771, 61: 772, 63: 773, 67: 774, 73: 775, 75: 776, 80: 777, 81: 778, 85: 779,
           89: 781, 94: 782, 97: 783, 100: 784, 113: 785, 116: 786, 119: 787, 120: 788, 125: 789, 131: 791, 138: 792,
           140: 793, 150: 795, 158: 796, 160: 797, 161: 798, 168: 811, 179: 812, 184: 813, 188: 814, 200: 815,
           210: 816, 228: 817, 245: 818, 280: 822, 315: 823, 350: 824, 360: 825, 512: 826, 687: 828}

#: what each part's own page listed when read in R18 (built-in browser); absent = not read or not listed
PAGES: dict[str, dict[str, Any]] = {
    "3764N118": {"read": DATE, "title": "High-Strength Gt Timing Belt Pulley, Press-Fit Mount, for 6 mm Maximum Belt "
                 "Width, 60 Teeth", "price_usd": 20.33, "for_belt_trade_size": "2MGT", "max_belt_width_mm": 6,
                 "bore": "finished, for 1/4 in round shaft", "pitch_diameter_mm": 38.2, "flanges": 2,
                 "hub_type": "standard", "hub_diameter_mm": 31.04, "inside_width_mm": 7.37, "od_mm": 44,
                 "outside_width_mm": 10.41, "overall_width_mm": 18.26, "shaft_mount": "set screw",
                 "material": "aluminum, anodized"},
    "3764N119": {"read": DATE, "title": "High-Strength Gt Timing Belt Pulley, Press-Fit Mount, for 6 mm Maximum Belt "
                 "Width, 72 Teeth", "price_usd": 23.13, "for_belt_trade_size": "2MGT", "max_belt_width_mm": 6,
                 "bore": "finished, for 1/4 in shaft", "pitch_diameter_mm": 45.8, "hub_type": "standard",
                 "hub_diameter_mm": 30.35, "od_mm": 45, "outside_width_mm": 9.65, "overall_width_mm": 19.05,
                 "shaft_mount": "set screw"},
    "3764N125": {"read": DATE, "title": "High-Strength Gt Timing Belt Pulley, Press-Fit Mount, 9 mm Maximum Belt Width "
                 "& 1/4 Shaft, 16 Teeth", "price_usd": 16.96, "for_belt_trade_size": "3MGT", "max_belt_width_mm": 9,
                 "bore": "finished, for 1/4 in shaft", "pitch_diameter_mm": 15.3, "flanges": 1, "hub_type": "standard",
                 "hub_diameter_mm": 18.03, "inside_width_mm": 10.16, "od_mm": 18, "outside_width_mm": 11.43,
                 "overall_width_mm": 17.55, "shaft_mount": "set screw"},
}
#: the other 3MGT pages read in R18 (9 mm max belt width, 1/4 in finished bore, set screw, standard hub; no weight,
#: no set-screw size listed): part number -> (price USD, listed PD, flanges, hub diameter, inside width, OD, outside
#: width, overall width), mm
_PAGES_3 = {
    "3764N126": (16.31, 16.2, 1, 18.8, 10.16, 19, 11.43, 17.55),
    "3764N127": (16.37, 17.2, 2, 11.23, 10.16, 20, 12.95, 20.62),
    "3764N128": (11.06, 19.1, 2, 12.7, 10.16, 23, 12.95, 20.62),
    "3764N129": (16.96, 21.0, 2, 14.27, 10.16, 24, 12.95, 20.62),
    "3764N13": (17.37, 22.9, 2, 15.88, 10.16, 26, 12.95, 20.62),
    "3764N131": (17.58, 23.9, 2, 15.88, 10.16, 27, 12.95, 20.62),
    "3764N132": (17.58, 24.8, 2, 15.88, 10.16, 28, 12.95, 20.62),
    "3764N133": (14.31, 26.7, 2, 17.81, 10.16, 30, 12.95, 20.62),
    "3764N134": (19.38, 28.7, 2, 19.71, 10.16, 32, 12.95, 20.62),
    "3764N135": (14.50, 30.6, 2, 21.62, 10.16, 34, 12.95, 20.62),
    "3764N136": (21.19, 32.5, 2, 23.39, 10.16, 36, 13.46, 21.16),
    "3764N137": (22.08, 34.4, 2, 25.4, 10.16, 37, 13.46, 21.16),
    "3764N139": (16.44, 38.2, 2, 29.21, 10.16, 41, 13.46, 21.16),
    "3764N14": (22.33, 42.0, 2, 33.02, 10.16, 45, 13.46, 21.16),
    "3764N141": (16.71, 43.0, 2, 31.75, 10.16, 45, 13.46, 21.16),
}
for _pn, (_pr, _pd, _fl, _hub, _iw, _od, _ow, _all) in _PAGES_3.items():
    PAGES[_pn] = {"read": DATE, "title": "High-Strength Gt Timing Belt Pulley, Press-Fit Mount, for 9 mm Maximum Belt "
                  "Width", "price_usd": _pr, "for_belt_trade_size": "3MGT", "max_belt_width_mm": 9,
                  "bore": "finished, for 1/4 in shaft", "pitch_diameter_mm": _pd, "flanges": _fl,
                  "hub_type": "standard", "hub_diameter_mm": _hub, "inside_width_mm": _iw, "od_mm": _od,
                  "outside_width_mm": _ow, "overall_width_mm": _all, "shaft_mount": "set screw"}

RULE = (f"researcher's rule {DATE} (session R18, ADR-115): every pulley and belt of this body comes from McMaster-Carr "
        "only (GT pulleys with a finished 1/4 in bore; closed neoprene GT belts); this entry is not a McMaster part")
EVIDENCE = {
    "GT2-80T-10": "one listing found, marked sold out (na3D, read 2026-11-06)",
    "GT2-40T-10": "its only listing read (na3D, 2026-11-06) is marked sold out; the other is a search-result title",
    "GT2-2mm-640-C": "one unconfirmed listing (source C)",
    "GT2-2mm-444-C": "one unconfirmed listing (source C)",
}
BREAK_PER_MM = 51.0 * 4.4482216152605 / 3.175  # N per mm of width, the researcher's assumption (71.45)
BREAK_DERIVATION = ("researcher's assumption 2026-11-12: 51 lbf per 1/8 in of width (71.4 N/mm) x width; not published "
                    "by McMaster")


def _sys(pitch: int, width: int, belts: dict[int, int], pulleys: dict[int, Any], brk: float) -> dict[str, Any]:
    sid = f"MM-{pitch}MGT-{width}"
    lo, hi = min(belts), max(belts)
    return {
        "id": sid, "profile": f"GT ({pitch}MGT)", "pitch_mm": pitch, "width_mm": width,
        "construction": "Neoprene, fiberglass cord, nylon-coated teeth; one-sided teeth; -30 to 180 F (McMaster-Carr)",
        "allowable_working_tension_n": None,
        "allowable_working_tension_derivation": "not published by McMaster-Carr and not supplied: unknown. Never "
                                                "derived from the breaking strength or any other figure.",
        "breaking_strength_n": brk,
        "breaking_strength_derivation": f"{BREAK_DERIVATION} = {BREAK_PER_MM * width:.1f} N for {width} mm, entered as "
                                        f"{brk:g} N as supplied",
        "length_sources": [f"MM-{pitch}MGT"],
        "sources": [f"McMaster-Carr closed-loop GT timing belts {pitch}MGT {width} mm wide, 7947K{belts[lo]} to "
                    f"7947K{belts[hi]} ({lo}-{hi} teeth); pulleys "
                    + ", ".join(v[0] for v in pulleys.values()) + f"; part list read from mcmaster.com {DATE}"],
        "notes": "Breaking strength is the researcher's assumption (guessed): every result that uses it says "
                 "'breaking strength assumed'. The sustained belt-tension check is unknown until an allowable working "
                 "tension is supplied.",
        "vendor": VENDOR,
        "source": f"https://www.mcmaster.com/ ({pitch}MGT closed belts 7947K{belts[lo]}-7947K{belts[hi]}) {DATE}",
        "guessed": ["breaking_strength_n"], "verified": False, "purchase_confirmed": False, "not_sourceable": "",
    }


def _pulley(pitch: int, width: int, teeth: int, row: Any) -> dict[str, Any]:
    pn, pd, flanges, price = row
    page = PAGES.get(pn, {})
    listed: dict[str, Any] = {"pitch_diameter_mm": pd, "flanges": flanges, "bore": "finished, 1/4 in",
                              "shaft_mount": "set screw", "hub": "standard", "price_usd": price,
                              "from": f"researcher's part list {DATE}"}
    if page:
        listed = {**listed, **{k: v for k, v in page.items() if k not in ("title",)}, "from": f"part page read {DATE}"}
    return {
        "id": f"MM-{pitch}MGT-{teeth}T", "teeth": teeth, "pitch_mm": pitch, "belt_widths_mm": [width],
        "bores_mm": [6.35], "mass_g": None, "listed_mass_g": None,
        "listed_mass_note": "no weight listed" if page else "", "listings": [
            {"url": URL.format(pn), "label": f"McMaster-Carr {pn} ({teeth}T {pitch}MGT, 1/4 in bore)",
             "read": bool(page), "note": (f"page read {DATE}: " + page.get("title", "")) if page
             else f"part list supplied by the researcher {DATE}; page not read"}],
        "verified": False,
        "notes": f"Aluminium, finished 1/4 in bore, set screw, standard hub, {flanges} flange(s); for belts up to "
                 f"{width} mm wide. Hub OD, overall width and set-screw size: see 'listed' (absent = not listed/read).",
        "vendor": VENDOR, "part_number": pn, "price_usd": price,
        "source": f"{URL.format(pn)} ({pn}) {DATE}", "purchase_confirmed": False, "listed": listed,
        "not_sourceable": "",
    }


def _source(pitch: int, width: int, belts: dict[int, int]) -> dict[str, Any]:
    return {"id": f"MM-{pitch}MGT", "label": f"McMaster-Carr {pitch}MGT closed-loop belts, {width} mm wide",
            "pitch_mm": pitch, "widths_mm": [width],
            "construction": "neoprene, fiberglass cord, nylon-coated teeth",
            "url": "https://www.mcmaster.com/",
            "range_note": f"{min(belts)}-{max(belts)} teeth, closed loops only (no cut-to-length); part list read from "
                          f"mcmaster.com {DATE}",
            "listings": [f"7947K{belts[t]}" for t in sorted(belts)], "vendor": VENDOR, "not_sourceable": ""}


def _lengths(pitch: int, width: int, belts: dict[int, int], prices: dict[str, float]) -> list[dict[str, Any]]:
    out = []
    for t in sorted(belts):
        pn = f"7947K{belts[t]}"
        out.append({"id": f"MM-{pitch}MGT-{t * pitch}", "pitch_mm": pitch, "pitch_length_mm": t * pitch, "teeth": t,
                    "source": f"MM-{pitch}MGT",
                    "listings": [f"{URL.format(pn)} ({pn}; {t} teeth, {t * pitch} mm pitch length, {width} mm wide; "
                                 + (f"page read {DATE}: price and Gates number listed, no weight)" if pn in prices
                                    else f"part list supplied by the researcher {DATE}; page not read)")],
                    "purchase_confirmed": False, "part_number": pn, "price_usd": prices.get(pn), "mass_g": None,
                    "verified": False, "not_sourceable": ""})
    return out


#: belt prices read from their part pages (R18: Gates 450-3P-09, 414-3P-09, 600-3P-09; "Outer Circle" = the pitch
#: length; no weight listed); a belt not read has no price
BELT_PRICES: dict[str, float] = {"7947K795": 14.43, "7947K792": 14.18, "7947K815": 16.47}


def _mark(entry: dict[str, Any], key: str) -> None:
    if entry.get("vendor") == VENDOR:
        return
    why = EVIDENCE.get(key)
    entry["not_sourceable"] = (f"{why}; " if why else "") + RULE


def apply(directory: Path) -> None:
    d = Path(directory)
    systems = json.loads((d / "belt_systems.json").read_text(encoding="utf-8"))
    lengths = json.loads((d / "belt_lengths.json").read_text(encoding="utf-8"))
    pulleys = json.loads((d / "pulleys.json").read_text(encoding="utf-8"))
    for s in systems["systems"]:
        _mark(s, s["id"])
    for src in lengths["sources"]:
        _mark(src, src["id"])
    for e in lengths["lengths"]:
        _mark(e, e["id"])
    for p in pulleys["pairs"]:
        _mark(p, p["id"])
    for p in pulleys.get("pulleys", []):
        _mark(p, p["id"])
    new_sys = [_sys(2, 6, BELTS_2, PULLEYS_2, 429.0), _sys(3, 9, BELTS_3, PULLEYS_3, 643.0)]
    systems["systems"] = [s for s in systems["systems"] if s.get("vendor") != VENDOR] + new_sys
    lengths["sources"] = [s for s in lengths["sources"] if s.get("vendor") != VENDOR] + [
        _source(2, 6, BELTS_2), _source(3, 9, BELTS_3)]
    lengths["lengths"] = ([e for e in lengths["lengths"] if not str(e["source"]).startswith("MM-")]
                          + _lengths(2, 6, BELTS_2, BELT_PRICES) + _lengths(3, 9, BELTS_3, BELT_PRICES))
    pulleys["pulleys"] = ([p for p in pulleys.get("pulleys", []) if p.get("vendor") != VENDOR]
                          + [_pulley(2, 6, t, r) for t, r in sorted(PULLEYS_2.items())]
                          + [_pulley(3, 9, t, r) for t, r in sorted(PULLEYS_3.items())])
    # the default rule (new projects, the belt comparison) chooses from McMaster parts only
    systems["default"] = DEFAULT_SYSTEM
    pulleys["default"] = DEFAULT_PAIR
    systems["_about"] = _about(systems["_about"])
    (d / "belt_systems.json").write_bytes(json.dumps(systems, indent=2).encode("utf-8"))
    (d / "belt_lengths.json").write_bytes(json.dumps(lengths, indent=2).encode("utf-8"))
    (d / "pulleys.json").write_bytes(_fmt(pulleys).encode("utf-8"))
    print("updated", d)


DEFAULT_SYSTEM = "MM-3MGT-9"
DEFAULT_PAIR = "MM-3MGT-30T+MM-3MGT-45T"
ABOUT_R18 = (" R18 (ADR-115): from 2026-11-12 only the McMaster-Carr entries (vendor McMaster-Carr) are offered for a "
             "new choice; every earlier entry is marked not_sourceable with its evidence and still builds stored bodies.")


def _about(text: str) -> str:
    return text if ABOUT_R18.strip() in text else text + ABOUT_R18


def _fmt(d: dict[str, Any]) -> str:
    out = ["{"]
    items = list(d.items())
    for i, (k, v) in enumerate(items):
        end = "," if i < len(items) - 1 else ""
        if isinstance(v, list):
            out.append("  " + json.dumps(k) + ": [")
            out.append(",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in v))
            out.append("  ]" + end)
        else:
            out.append("  " + json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False) + end)
    return "\n".join(out) + "\n}\n"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        apply(Path(arg))
