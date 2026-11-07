"""Session R11c-B: the report on Stage B run 20261107-043030-evolve-c02e in docs/studies/production_r11c.md (fronts
over minutes / trot / cost, rejections, gene movement, lineage, belt loads). Read-only; prints markdown.

Run from the repo root:  python docs/studies/report_r11cb.py
"""
import json
import re
from collections import Counter, defaultdict

RID = "20261107-043030-evolve-c02e"
with open(f"projects/robot-calf-final/runs/{RID}/candidates.jsonl") as fh:
    L = [json.loads(x) for x in fh]
J = [c for c in L if (c.get("metrics") or {}).get("hardware")]
X = [c for c in L if c.get("status") == "infeasible"]
by = {c["id"].replace(RID + "-", ""): c for c in L}
W = by["g000-000"]["genome"]["values"]


def SH(i):
    return i.replace(RID + "-", "")


REFS = {"g000-000": "working body", "g000-012": "A012", "g000-013": "A013", "g001-006-r05": "B1 g001-006-r05"}
SERVO = {"servo_hip_abd": "hip ab/ad", "servo_stifle": "stifles", "servo_hock": "hocks", "servo_shoulder": "shoulders",
         "servo_carpus": "carpi"}
SITES = ["hip_abd", "stifle", "hock", "shoulder", "carpus"]
out = []
P = out.append


def hw(c):
    return c["metrics"]["hardware"]


def key(c):
    h = hw(c)
    return h["minutes_held"], round(h["trot_speed_mm_s"]), round(h["costs"]["cost_index"], 3)


def pul(s):
    if "+" in s:
        a, b = s.split("+")
        return a.split("-")[1] + "/" + b.split("-")[1]
    return s.replace("-", "/")


def length(s):
    m = re.search(r"-(\d+)-[A-Z]$", s)
    return m.group(1) if m else s


def active(g, v):
    """genes that matter for this genome (shoulder belt genes only when belted; spring values only when on)"""
    if g.startswith("belt_shoulder_") and not v.get("shoulder_belt"):
        return False
    return all(not (g.startswith(f"spring_{s}_") and not v.get(f"spring_{s}")) for s in SITES)


def describe(c):
    v = c["genome"]["values"]
    parts = []
    new = [n for g, n in SERVO.items() if v.get(g) == "sts3250_c002"]
    parts.append("C002 on " + (" + ".join(new) if new else "none"))
    d = []
    for dr in ("stifle", "hock", "carpus") + (("shoulder",) if v.get("shoulder_belt") else ()):
        sysw = "15 mm " if "15mm" in str(v.get(f"belt_{dr}_system")) else ""
        d.append(f"{dr} {sysw}{pul(v[f'belt_{dr}_pulleys'])} {length(v[f'belt_{dr}_length'])}")
    parts.append("; ".join(d))
    if not v.get("shoulder_belt"):
        parts.append("shoulder direct")
    sp = []
    for s in SITES:
        on, won = v.get(f"spring_{s}"), W.get(f"spring_{s}")
        if on != won:
            sp.append(("+" if on else "no ") + s.replace("hip_abd", "hip ab/ad") + " spring")
        elif on:
            ch = [g.split(f"spring_{s}_")[1] for g in v if g.startswith(f"spring_{s}_") and not g.endswith("free_length") and v[g] != W.get(g)]
            if "k" in ch:
                sp.append(f"{s.replace('hip_abd', 'hip ab/ad')} rate x{v[f'spring_{s}_k'] / W[f'spring_{s}_k']:.2g}")
                ch.remove("k")
            if ch:
                sp.append(f"{s.replace('hip_abd', 'hip ab/ad')} spring {', '.join(ch)} moved")
    if sp:
        parts.append(", ".join(sp))
    ln = []
    for g, n in (("femur_length", "femur"), ("tibia_length", "tibia"), ("rear_cannon_length", "rear cannon"),
                 ("upper_leg_length", "upper leg"), ("front_cannon_length", "front cannon")):
        if v[g] != W[g]:
            ln.append(f"{n} {v[g]:.0f}")
    parts.append(", ".join(ln) if ln else "lengths as today")
    return "; ".join(parts)


def row(c, tag=""):
    h = hw(c)
    m, t, k = key(c)
    s = h["screen"]
    st = ", ".join(f"{a} {b} ({n})" for a, b, n in h["stoppers"][:2])
    name = SH(c["id"])
    if name in REFS:
        name = f"{name} ({REFS[name]})"
    return (f"| {tag}{name} | {describe(c)} | {m} | {t} {('(' + h['fastest_trot'] + ')') if h.get('fastest_trot') else ''} | "
            f"{s['walk']['worst_margin']:+.2f} | {s['turn']['worst_margin']:+.2f} | {s['lie_rise']['worst_margin']:+.2f} | "
            f"{k:.2f} | {h['costs']['mass_g']:.0f} | {st} |")


HDR = ("| Body | Hardware and geometry (changes from the working body) | Min /33 | Trot mm/s | Walk | Turn | lie_rise | "
       "Cost | Mass g | Stopped most by |\n|---|---|---|---|---|---|---|---|---|---|")


def dom(a, b):
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a != b


def front(cs):
    seen, u = set(), []
    for c in cs:
        g = json.dumps(c["genome"]["values"], sort_keys=True)
        if g not in seen:
            seen.add(g)
            u.append(c)
    return [c for c in u if not any(dom(key(o), key(c)) for o in u)]


fronts = {}
for cut in (5, 10, 15, 20):
    cs = [c for c in J if c["generation"] <= cut]
    f = sorted(front(cs), key=lambda c: (-key(c)[0], -key(c)[1], key(c)[2]))
    fronts[cut] = f
    newc = [c for c in f if c["generation"] > cut - 5]
    P(f"\n### Front after generation {cut} ({len(f)} bodies of {len(cs)} judged; {len(newc)} new in generations "
      f"{max(1, cut - 4)}-{cut})\n")
    P(HDR)
    for c in f:
        P(row(c, "**new** " if c["generation"] > cut - 5 and cut > 5 else ""))
    off = [by[r] for r in REFS if by[r] not in f]
    for c in off:
        P(row(c, "(off the front) "))

# rejections
P("\n### Rejections per block\n")
P("| Generations | Draws | Rejected | Share | Reasons (a draw can have several) |\n|---|---|---|---|---|")
gens = defaultdict(lambda: [0, 0])
for c in L:
    gens[c["generation"]][0] += 1
    if c.get("status") == "infeasible":
        gens[c["generation"]][1] += 1


def cls(p):
    if "too short to reach the ground" in p:
        return "front legs too short for a level back"
    if "servo budget" in p:
        return "servo budget > 6 C002"
    if "servo travel" in p or re.search(r"is \d+(\.\d+)?:\d", p):
        return "pulley ratio needs > 360 deg servo travel"
    if p.startswith("ratio"):
        return "segment ratio outside +-5 %"
    if "spring" in p:
        return "spring anchor / free length off its range"
    if "feasible" in p or "length" in p:
        return "no feasible listed belt length"
    return p[:60]


for lo, hi in ((1, 5), (6, 10), (11, 15), (16, 20)):
    rs = [c for c in X if lo <= c["generation"] <= hi]
    draws = sum(gens[g][0] for g in range(lo, hi + 1))
    cnt = Counter()
    for c in rs:
        for k in {cls(p.strip()) for p in (c.get("error") or "").split(";") if p.strip()}:
            cnt[k] += 1
    P(f"| {lo}-{hi} | {draws} | {len(rs)} | {100 * len(rs) / draws:.0f} % | "
      + "; ".join(f"{k} {n}" for k, n in cnt.most_common()) + " |")
worst = max(range(1, 21), key=lambda g: gens[g][1] / gens[g][0])
P(f"\nHighest share in one generation: {worst} ({gens[worst][1]} of {gens[worst][0]}, "
  f"{100 * gens[worst][1] / gens[worst][0]:.0f} %); the stop is 50 %.")
other = Counter()
for c in X:
    for p in (c.get("error") or "").split(";"):
        if cls(p.strip()) == p.strip()[:60]:
            other[p.strip()[:100]] += 1
if other:
    P("Unclassified: " + "; ".join(f"{k} ({n})" for k, n in other.items()))

# gene movement: share of judged bodies whose active gene differs from the working body, per block, + front
P("\n### Which genes move (share of judged bodies whose gene differs from the working body; inert genes left out)\n")
groups = {
    "femur": ["femur_length"], "tibia": ["tibia_length"], "rear cannon": ["rear_cannon_length"],
    "upper leg": ["upper_leg_length"], "front cannon": ["front_cannon_length"],
    **{f"servo {n}": [g] for g, n in SERVO.items()},
    **{f"{d} pulleys": [f"belt_{d}_pulleys"] for d in ("stifle", "hock", "carpus")},
    **{f"{d} belt length": [f"belt_{d}_length"] for d in ("stifle", "hock", "carpus")},
    **{f"{d} belt system": [f"belt_{d}_system"] for d in ("stifle", "hock", "carpus")},
    "shoulder belted": ["shoulder_belt"],
    **{f"{s} spring on/off": [f"spring_{s}"] for s in SITES},
    **{f"{s} spring rate/anchors": [g for g in W if g.startswith(f"spring_{s}_") and not g.endswith("free_length")] for s in SITES},
}
sets = {f"gen {lo}-{hi}": [c for c in J if lo <= c["generation"] <= hi and SH(c["id"]) not in REFS]
        for lo, hi in ((1, 5), (6, 10), (11, 15), (16, 20))}
sets["front at 20"] = [c for c in fronts[20] if SH(c["id"]) != "g000-000"]
P("| Gene | " + " | ".join(sets) + " |\n|---|" + "---|" * len(sets))
for name, gs in groups.items():
    cells = []
    for cs in sets.values():
        n = sum(1 for c in cs if any(active(g, c["genome"]["values"]) and c["genome"]["values"].get(g) != W.get(g)
                                    for g in gs))
        cells.append(f"{100 * n / max(1, len(cs)):.0f} %")
    P(f"| {name} | " + " | ".join(cells) + " |")
P("| (bodies) | " + " | ".join(str(len(cs)) for cs in sets.values()) + " |")

# choice frequencies on the front at 20
P("\n### Choices on the final front\n")
f20 = sets["front at 20"]
for d in ("stifle", "hock", "carpus"):
    P(f"* {d}: " + ", ".join(f"{pul(k)} x{n}" for k, n in Counter(c["genome"]["values"][f"belt_{d}_pulleys"]
                                                                       for c in f20).most_common()))
P("* servos on C002: " + ", ".join(f"{n} x{k}" for n, k in Counter(
    s for c in f20 for g, s in SERVO.items() if c["genome"]["values"][g] == "sts3250_c002").most_common()))
P("* shoulder belted: " + str(sum(1 for c in f20 if c["genome"]["values"].get("shoulder_belt"))) + f" of {len(f20)}")
for s in SITES:
    P(f"* {s} spring on: {sum(1 for c in f20 if c['genome']['values'].get('spring_' + s))} of {len(f20)}")
for g in ("femur_length", "tibia_length", "rear_cannon_length", "upper_leg_length", "front_cannon_length"):
    vs = sorted(c["genome"]["values"][g] for c in f20)
    P(f"* {g}: today {W[g]:.0f}; front {vs[0]:.0f}-{vs[-1]:.0f}, median {vs[len(vs) // 2]:.0f}")


# lineage of the best
def lineage(cid, depth=0, seen=None):
    seen = seen or set()
    c = by[cid]
    P("  " * depth + f"* {cid}: {key(c) if (c.get('metrics') or {}).get('hardware') else c.get('status')}")
    if depth > 6:
        return
    for p in c.get("parents") or []:
        p = SH(p)
        if p in by and p not in seen:
            seen.add(p)
            lineage(p, depth + 1, seen)


P("\n### Lineage of the best (minutes, trot, cost)\n")
lineage("g020-008-r01")
P("\n### Belt loads, top bodies (peak / largest mean, N)\n")
for cid in ("g020-008-r01", "g012-009", "g011-003", "g009-000", "g007-002", "g001-006-r05", "g000-000"):
    bl = hw(by[cid]).get("belt_loads") or {}
    P(f"* {cid}: " + ", ".join(f"{k} {v['peak_n']:.0f}/{v['mean_n']:.0f}" for k, v in bl.items())
      + f"; springs sim {hw(by[cid]).get('spring_peaks_sim_n')}")

print("\n".join(out))


# ---- compact fronts per five generations
REFS_SHORT = {"g000-000": "working", "g000-012": "A012", "g000-013": "A013", "g001-006-r05": "B1-r05"}
out = []
prev = set()
for cut in (5, 10, 15, 20):
    cs, seen = [], set()
    for c in J:
        if c["generation"] <= cut:
            g = json.dumps(c["genome"]["values"], sort_keys=True)
            if g not in seen:
                seen.add(g)
                cs.append(c)
    f = sorted([c for c in cs if not any(dom(key(o), key(c)) for o in cs)], key=lambda c: (-key(c)[0], -key(c)[1]))
    ids = {SH(c["id"]) for c in f}
    out.append(f"\n**After generation {cut}** ({len(f)} on the front of {len(cs)} distinct bodies; "
               f"entered: {', '.join(sorted(ids - prev)) or 'none'}; left: {', '.join(sorted(prev - ids)) or 'none'})\n")
    out.append("| Body | Min /33 | Trot mm/s | Cost | Walk | Turn | lie_rise |\n|---|---|---|---|---|---|---|")
    for c in f + [x for x in J if SH(x["id"]) in REFS and SH(x["id"]) not in ids and x["generation"] <= 1]:
        h = c["metrics"]["hardware"]
        s = h["screen"]
        m, t, k = key(c)
        n = SH(c["id"])
        n = f"{n} ({REFS_SHORT[n]})" if n in REFS_SHORT else n
        if SH(c["id"]) not in ids:
            n += ", off the front"
        out.append(f"| {n} | {m} | {t} | {k:.2f} | {s['walk']['worst_margin']:+.2f} | {s['turn']['worst_margin']:+.2f} | "
                   f"{s['lie_rise']['worst_margin']:+.2f} |")
    prev = ids
print("\n".join(out))
