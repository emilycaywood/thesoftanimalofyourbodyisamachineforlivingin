# CALFLAB chat guide: sourcing a battery for the feral calf

Paste everything below the line into a new chat. It is a snapshot of `projects/robot-calf-final` as of 2026-11-11
(branch `robot-calf-final`, after session R13, ADR-107) and stands on its own. It gives the loads the simulation
puts on the servos, what is known and unknown about the servos and the packs, and asks for a sourcing study. The
numbers come from stored simulation runs (the R12 compare set, seed 0); the script that summarised them is not in the
repo. Regenerate this file if the body, the servos or the battery change.

---

You are helping me choose and source the battery for a robot calf I am designing with my research tool, CALFLAB
(M.Arch thesis research). We have a first choice, but I do not want to assume it is the best one: I want you to work
out what the robot actually needs, then find and compare real products, including our current choice. Everything you
know about the project is in this message; you cannot see my files or the simulations.

## How I want you to answer

- I am an architecture researcher, fluent in Rhino, Grasshopper and fabrication; I have built small robots but I am
  not an electrical engineer. Explain the electrical reasoning (C-rating, voltage sag, holding current, why two packs
  in parallel) in plain language when it matters, without talking down.
- **Keep three kinds of statement apart**: numbers from my project (all load figures below are *simulated*; nothing
  has been built or measured), assumptions (marked ASSUMPTION) and values nobody knows yet (marked UNKNOWN). When you
  use a typical value from your own knowledge, say so and say how sure you are. **Never present a guess as a spec.**
- **For every product, give where you read each figure** (the listing or datasheet, with its URL), and say which
  figures you could not find. A figure you did not read on a page is not a spec. If you cannot browse, say so and
  give me search terms and what to check on each listing instead of inventing products.
- Where the decision is mine, lay out options and trade-offs and recommend one with reasons, but do not decide for me.
- Use short paragraphs and tables.

## 1. The robot

A four-legged robot calf, about 600 mm tall at the back (standing trunk height 596-607 mm in simulation), built from
carbon-fibre leg tubes, printed parts, belts and pulleys. Ten serial-bus servos: per leg pair, hip ab/ad and stifle
and hock (hind legs), shoulder and carpus (front legs); several joints are driven through GT2 timing belts (2:1 or
1.5:1). Its behaviour is generated (evolved sequences of calm, lively, walking and trotting movement), and every
behaviour is judged in physics on three randomised seeds with a 20 % safety margin on every limit.

Mass as simulated: **1304-1421 g** depending on the body (below), *including* two battery packs at 135 g each, but
with 14-15 parts still counted as 0 g because their masses are not entered: the electronics, skin, hip and chest
blocks, servo horns, bearings, collars, tube plugs, hoof pads, belts. The real robot will be heavier (UNKNOWN by how
much), and heavier means more holding torque, so more current.

Four candidate bodies are still in play (the build is not decided):

| body | servos | mass as simulated |
|---|---|---|
| working body (today's) | 10 x Feetech STS3215 C018 | 1304 g |
| g009-000 | 4 x STS3250 C002 (hocks, carpi) + 6 x STS3215 C018 | 1380 g |
| g007-002 | 4 x STS3250 C002 (shoulders, hocks) + 6 x STS3215 C018 | 1383 g |
| g012-009 | 6 x STS3250 C002 (shoulders, hocks, carpi) + 4 x STS3215 C018 | 1421 g |

## 2. The servos (figures supplied by me from the maker's specs; none verified)

| | STS3215 C018 | STS3250 C002 |
|---|---|---|
| operating voltage | 6-12 V | 6-12 V |
| figures given at | 12 V | 12 V |
| stall torque | 2.94 N*m (30 kg.cm) | 4.9 N*m (50 kg.cm) |
| rated torque | 0.98 N*m (10 kg.cm) | 1.57 N*m (16 kg.cm) |
| no-load speed | 0.222 s / 60 deg (45 rpm) | 0.133 s / 60 deg (75 rpm) |
| **stall current** | **UNKNOWN** (not supplied) | 4.2 A at 12 V |
| idle current | UNKNOWN | UNKNOWN |
| mass | 55 g | 74.5 g |

The STS3215 C018's stall current is the biggest gap: without it the current of 4 to 10 of the ten servos is unknown.
Please find it (and the idle current of both) from Feetech's own documentation or a reliable test, with the source.

## 3. The battery as it stands (inconsistent; please help me resolve it)

- The body model carries **two "3S 2200 mAh LiPo" packs, 135 g each** (what I supplied on 2026-11-02; mass only; no
  maker, C-rating or dimensions entered).
- A later decision record (ADR-088, 2026-11-04) says **"two 3S packs wired in parallel"**, and the component library
  has a generic entry **"3S LiPo 5000 mAh", 400 g, 50 A, 138 x 44 x 26 mm, 45 USD** marked *typical figures for hobby
  packs, not verified*. Which of the two is the real first choice is UNKNOWN: ask me.
- ASSUMPTION used in the simulation: the two packs in parallel feed the servos directly: 12.6 V full, 11.1 V nominal,
  about 10.5 V near empty. The servos' figures are at 12 V, so on a 3S pack they are a little weaker and slower except
  on a fresh charge. The simulation assumes torque and speed scale linearly with voltage (ASSUMPTION; at 11.1 V one of
  the delicate movements went from within its limits to just over).
- Above 12 V is outside the servos' 6-12 V range, so a 4S pack straight onto the servos is out; anything other than
  3S would need a regulator able to carry the servo current (see section 4).

## 4. The loads (simulated)

The robot spends most of its time standing, shifting weight, walking slowly and occasionally trotting. The motion
itself needs little power: **mechanical power is 0.1-0.4 W on average** over a minute of behaviour. What draws current
in a servo is **holding torque**: a DC motor's current rises with the torque it holds, even when nothing moves.

Per body, the sum over its servos of the torque each servo holds (at the servo, after the belts), split by model:

| body | play | C018 torque, mean / peak (N*m) | C002 torque, mean / peak (N*m) | C002 current, mean / peak (A) | mech. power, mean / peak (W) |
|---|---|---|---|---|---|
| working | 11 behaviours, 60 s each | 0.72-1.02 / 1.59-2.95 | - | - | 0.1-0.3 / 0.5-2.1 |
| working | quick trot | 1.90 / 3.37 | - | - | 2.6 / 5.7 |
| working | lying down and rising | 1.73 / 4.99 | - | - | 1.2 / 8.4 |
| g009-000 | 11 behaviours | 0.52-0.74 / 1.27-1.96 | 0.33-0.44 / 0.84-1.15 | 0.28-0.38 / 0.72-0.98 | 0.1-0.4 / 0.6-4.3 |
| g009-000 | quick trot | 0.91 / 2.01 | 1.01 / 1.50 | 0.86 / 1.28 | 4.0 / 7.6 |
| g009-000 | lying down and rising | 1.28 / 3.80 | 0.65 / 2.23 | 0.56 / 1.91 | 0.6 / 3.0 |
| g007-002 | 11 behaviours | 0.49-0.71 / 1.18-1.75 | 0.29-0.48 / 0.97-2.13 | 0.25-0.41 / 0.83-1.82 | 0.1-0.3 / 0.6-4.1 |
| g007-002 | quick trot | 1.03 / 1.87 | 1.12 / 2.40 | 0.96 / 2.06 | 3.1 / 8.5 |
| g007-002 | lying down and rising | 0.76 / 2.32 | 1.19 / 5.26 | 1.02 / 4.51 | 1.0 / 12.1 |
| g012-009 | 11 behaviours | 0.33-0.54 / 0.98-1.54 | 0.54-0.81 / 1.34-2.41 | 0.47-0.70 / 1.15-2.06 | 0.1-0.3 / 0.9-4.4 |
| g012-009 | quick trot | 0.64 / 1.28 | 1.32 / 1.87 | 1.13 / 1.60 | 3.0 / 5.6 |
| g012-009 | lying down and rising | 0.73 / 2.57 | 1.87 / 7.90 | 1.60 / 6.77 | 1.9 / 17.5 |

How to read it:
- "mean" is over the whole play; "peak" is the highest instant (a sample every 20 ms). Each behaviour range covers
  the 11 behaviours. The quick trot (0.4 s cycle) and lying down and rising go over at least one limit on these
  bodies, so they are upper bounds of what the robot will be asked to do, not routine.
- **C002 current** is computed by the lab as torque x (4.2 A / 4.9 N*m) per servo (ASSUMPTION: current proportional
  to torque, no idle current). Once the C018's stall current is known, its current can be estimated the same way:
  C018 torque x (C018 stall current / 2.94 N*m). Please do that estimate with me, and say how a real servo differs
  from this linear model (idle current, the controller's own draw, current when it fights its position gain,
  efficiency at low torque).
- For a DC motor the current for a given torque is roughly independent of the supply voltage, so these estimates
  hold at 11.1 V (ASSUMPTION; check against the datasheet if it gives a curve).
- Not in the table: the electronics. They are not chosen; the library has a Teensy 4.1 (5 V, 0.5 W), a Raspberry Pi 5
  (5 V, 6 W, a guess) and an ESP32 (3.3 V, about 0.33 W), plus an IMU and possibly foot sensors and a depth camera. A
  5 V / 3.3 V regulator from the pack is assumed.

## 5. What I don't know yet (ask me before you size anything)

1. How long one charge should last (minutes of performance), and whether I can swap packs during a session.
2. Which packs I actually have, if any, and their maker, C-rating and dimensions.
3. The mass I can afford for the battery and the space for it. In the model the two packs hang one on each side of
   the body's two rails (100 mm apart), 120 mm ahead of the hip axle and 50 mm below it (PROVISIONAL placement; their
   size is not modelled). Moving mass forward or back changes which legs carry it; ask me what is possible.
4. The electronics I end up with.
5. Where the robot runs: a studio, an exhibition, a theatre stage, near people? Safety and charging rules may decide
   the chemistry.
6. My budget.

## 6. What I want from you

1. **Sizing method.** With my numbers (and the C018 stall current you find, clearly sourced), estimate the current
   the robot draws: typical, worst sustained, and peak, for each body. Add the electronics with a range. Then the
   energy per minute and the capacity for my runtime (when I give it), with a margin you justify. Show the arithmetic.
   Say what would change the answer most.
2. **Requirements**, from that: voltage window (the servos take 6-12 V), continuous and burst discharge current, capacity,
   mass and size limits, connector and wire gauge, protection (BMS, fuse, low-voltage cut-off), charging.
3. **Options with trade-offs**: chemistry (LiPo, Li-ion cells such as 18650/21700 in a pack, LiFePO4, others), cell
   count (3S directly, or another voltage through a regulator able to carry the servo current), one pack or two in
   parallel, ready-made packs or a custom pack. Include what each means for safety near people, mass, runtime and
   servo strength (3S sags from 12.6 V to about 10.5 V; a regulated 12 V would keep the servos at their rated figures:
   is that worth a regulator's mass, cost and losses?).
4. **Candidate products**, including our current choice for comparison, in a table: maker and model, chemistry and
   cell count, nominal and full voltage, capacity, continuous and burst current (or C-ratings), mass, dimensions,
   connector, price, where sold, URL; and which figures you read on the page and which you could not find.
5. **For the shortlist**, give each candidate as a YAML entry I can paste into my component library, with these
   fields and units, values only from a listing or datasheet, `null` where not found:

   ```yaml
   - key: <snake_case_id>
     kind: battery
     name: "<as listed>"
     manufacturer: "<maker>"
     mass_g: <g>
     dims_mm: [<l>, <w>, <h>]
     voltage_v: <nominal V>
     capacity_mah: <mAh>
     max_current_a: <continuous A>
     cost_usd: <USD>
     url: "<listing>"
     source: "<where each value was read, and when>"
     guessed: []          # names of fields whose value is NOT from the listing
     verified: false      # I set this myself after checking
     notes: "<burst current, connector, BMS, anything with no field>"
   ```

6. **Questions to settle before I buy**, and what I should measure on the first assembled leg (current at standing,
   for example) to check your estimate.
