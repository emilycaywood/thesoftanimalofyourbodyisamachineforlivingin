"""Session R11c step 0 (ADR-103): add the sourced single pulleys, the 15 mm length source and its lengths to a belt
catalog folder. Existing entries are not changed; the 15 mm system's empty ``length_sources`` gains source E.

Run once per folder:  python docs/studies/catalog_r11c.py config/belts projects/robot-calf-final/catalog
Every entry is unverified (``verified: false``, ``purchase_confirmed: false``). ``listed_mass_g`` is what a listing
says; ``mass_g`` stays null until the researcher verifies it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

NA3D = {"url": "https://www.na3d.eu/p/3228/gt2-10-pulley", "label": "na3D GT2-10 pulley (for a 10 mm wide belt)",
        "read": True, "note": "page read 2026-11-06: 20/30/36/40/60/80/100/120/140T; bores 5 mm (20T) or 5/8 mm; "
                              "marked sold out; no mass"}
B30 = {"url": "https://bulkman3d.com/product/gt0002-30/", "label": "Bulkman3D GT2 30T, belt width 6/10 mm", "read": True,
       "note": "page read: 10 mm version bores 5/6/6.35 mm; OD 22, H 17.5 mm; 0.018 kg (one weight for both widths)"}
B48 = {"url": "https://bulkman3d.com/product/gt2-48-teeth-timing-belt-pulley-belt-width-6mm-10mm/",
       "label": "Bulkman3D GT2 48T, belt width 6/10 mm", "read": True,
       "note": "page read: 10 mm version bore 5 mm; OD 28 as listed (a 48T GT2 pitch diameter is 30.6 mm, so the "
               "listed OD looks wrong); 0.04 kg"}
B60 = {"url": "https://bulkman3d.com/product/gt0002-60/", "label": "Bulkman3D GT2 60T, belt width 6/10/15 mm", "read": True,
       "note": "page read: bores 5-14 mm (15 mm bore with 15 mm width only); OD 42, H 18 mm; 0.08 kg (one weight for "
               "every width)"}
EB10 = {"url": "https://www.ebay.com/itm/283328996026",
        "label": "eBay 283328996026 'GT2 10mm ... Pulley 16 20 30 36 40 60 Bore 3 5 8'", "read": False,
        "note": "search-result title only (the page refused automated reading)"}
EB15 = {"url": "https://www.ebay.de/itm/284184103238", "label": "eBay.de 284184103238 'GT2 15mm Riemenbreite Riemenscheibe'",
        "read": False, "note": "search-result snippet only: 20/40/60 tooth, belt 15 mm, bores from 5 mm; some variants "
                               "out of stock"}
ONE = "one listing only"


def p(id_: str, teeth: int, widths: list[float], bores: list[float], listings: list[dict[str, Any]],
      listed: float | None = None, note: str = "", notes: str = "") -> dict[str, Any]:
    return {"id": id_, "teeth": teeth, "pitch_mm": 2, "belt_widths_mm": widths, "bores_mm": bores, "mass_g": None,
            "listed_mass_g": listed, "listed_mass_note": note, "listings": listings, "verified": False, "notes": notes}


PULLEYS = [
    p("GT2-20T-10", 20, [10], [5, 8], [NA3D, {
        "url": "https://www.bitsandparts.nl/en/gt2-timing-drive-pulley-20t-5mm-for-10mm-belt-p1914624",
        "label": "Bits and Parts 'GT2 Timing drive pulley 20T 5mm for 10mm belt'", "read": False,
        "note": "search-result title"}, {
        "url": "https://sigmanortec.ro/en/2gt-timing-pulley-20-teeth-8mm-10mm-belt",
        "label": "Sigmanortec '2GT timing pulley 20 teeth, 8mm, 10mm belt'", "read": False,
        "note": "search-result title"}]),
    p("GT2-30T-10", 30, [10], [5, 6, 6.35, 8], [NA3D, B30], 18, "Bulkman3D listing, one weight for 6 and 10 mm"),
    p("GT2-36T-10", 36, [10], [5, 8], [NA3D, EB10]),
    p("GT2-40T-10", 40, [10], [5, 8], [NA3D, EB10]),
    p("GT2-45T-10", 45, [10], [7], [{
        "url": "https://www.fruugo.us/gt2-timing-pulley-45-teeth-for-3d-printer-belt-width-610mm-bore-7mm-bore-options-4-15mm/p-403436352",
        "label": "Fruugo 'GT2 Timing Pulley 45 Teeth ... Belt Width 6/10mm, Bore 7mm, Bore Options 4-15mm'",
        "read": False, "note": "search-result title and snippet only (the page refused automated reading)"}],
      notes=ONE + "; bore options 4-15 mm stated, only 7 mm confirmed"),
    p("GT2-48T-10", 48, [10], [5], [B48], 40, "Bulkman3D listing", notes=ONE),
    p("GT2-60T-10", 60, [10], [5, 6, 6.35, 8, 10, 12, 14], [NA3D, B60, {
        "url": "https://www.multanelectronics.com/?p=43285",
        "label": "Multan Electronics 'GT2 60 Teeth 10mm Belt Synchronous Pulley Bore 5mm & 8mm'", "read": False,
        "note": "search-result title"}], 80, "Bulkman3D listing, one weight for 6/10/15 mm"),
    p("GT2-80T-10", 80, [10], [5, 8], [NA3D], notes=ONE + " (marked sold out when read)"),
    p("GT2-20T-15", 20, [15], [5, 6, 6.35, 8], [EB15], notes=ONE),
    p("GT2-40T-15", 40, [15], [5, 6, 6.35, 8, 10, 12], [EB15], notes=ONE),
    p("GT2-60T-15", 60, [15], [5, 6, 6.35, 8, 10, 12, 14, 15], [EB15, B60], 80,
      "Bulkman3D listing, one weight for 6/10/15 mm"),
    p("GT2-80T-15", 80, [15], [8, 12], [{
        "url": "https://www.fruugo.us/80-teeth-gt2-timing-pulley-bore-8mm12mm-15mm-width-2gt-belt-compatible-80t-1-pc/p-376962330",
        "label": "Fruugo US '80 Teeth GT2 Timing Pulley Bore 8mm/12mm, 15mm Width'", "read": False,
        "note": "search-result title"}, {
        "url": "https://www.fruugo.ca/80-teeth-gt2-timing-pulley-8mm-12mm-bore-for-15mm-belt-width-linear-motion-80t-pully-compatible-with-2gt-systems/p-366557887",
        "label": "Fruugo CA '80 Teeth GT2 Timing Pulley 8mm 12mm Bore for 15mm Belt Width'", "read": False,
        "note": "search-result title; possibly the same seller as the US listing"}]),
]
SOURCE_E = {"id": "E", "label": "Amazon B0DPV1912G 'GT2/2M Closed Loop ... Length 300mm 310mm, Width 6/9/10/12/15mm'",
            "pitch_mm": 2, "widths_mm": [6, 9, 10, 12, 15], "construction": "generic rubber",
            "url": "https://www.amazon.com/clp/B0DPV1912G",
            "range_note": "R11c (ADR-103): search-result title only; offered for the 15 mm system only. A wider 15 mm "
                          "range seen elsewhere (homediyer, 50T-175T) names no exact lengths, so none is entered."}
OLD_NOTE = ("REQUIRED: no lengths are listed in 15 mm width yet; add a source to belt_lengths.json and name it in "
            "length_sources.")
NEW_NOTE = ("R11c (ADR-103): lengths from source E (300 and 310 mm; listing title only, unverified). Matching 15 mm "
            "pulleys are in pulleys.json 'pulleys'.")


def main() -> None:
    for d in (Path(a) for a in sys.argv[1:]):
        t = (d / "pulleys.json").read_text(encoding="utf-8").rstrip()
        assert '"pulleys"' not in t and t.endswith("}")
        body = ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in PULLEYS)
        t = t[:-1].rstrip() + ',\n  "pulleys": [\n' + body + "\n  ]\n}\n"
        json.loads(t)
        (d / "pulleys.json").write_bytes(t.encode("utf-8"))

        t = (d / "belt_lengths.json").read_text(encoding="utf-8")
        assert all(s["id"] != "E" for s in json.loads(t)["sources"])
        k = t.index('"lengths"')
        end = t.rindex("]", 0, k)
        t = t[:end].rstrip() + ",\n    " + json.dumps(SOURCE_E, ensure_ascii=False) + "\n  " + t[end:]
        lens = [{"id": f"GT2-2mm-{L}-E", "pitch_mm": 2, "pitch_length_mm": L, "teeth": L // 2, "source": "E",
                 "purchase_confirmed": False} for L in (300, 310)]
        end = t.rindex("]")
        t = t[:end].rstrip() + ",\n" + ",\n".join("    " + json.dumps(x) for x in lens) + "\n  " + t[end:]
        json.loads(t)
        (d / "belt_lengths.json").write_bytes(t.encode("utf-8"))

        t = (d / "belt_systems.json").read_text(encoding="utf-8")
        i = t.index('"id": "GT2-2mm-15mm-generic"')
        a = t.index('"length_sources": []', i)
        t = t[:a] + '"length_sources": ["E"]' + t[a + len('"length_sources": []'):]
        assert OLD_NOTE in t
        t = t.replace(OLD_NOTE, NEW_NOTE)
        json.loads(t)
        (d / "belt_systems.json").write_bytes(t.encode("utf-8"))
        print("updated", d)


if __name__ == "__main__":
    main()
