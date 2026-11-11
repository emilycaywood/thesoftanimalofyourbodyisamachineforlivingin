# R15 — Behaviour from outcomes, body and behaviour together (design study and pilot)

Session R15, 2026-11-11, ADR-110. The working body (document), catalog values, library entries and `verified` flags
were not changed; nothing installed. Code: `calflab.fitness.outcomes` (measures, gates, terms),
`calflab.control.outcome` (controller family), `calflab.sim.scene` (block, contact probes), `calflab.evolve.outcomes`
(per-body search); preset `config/fitness/outcomes_r15.yaml`; script `docs/studies/outcomes_r15.py`
(pilot / store / report / estimate); tables `outcomes_r15_tables.md`, data `outcomes_r15.json`.

**Mass model: explicit_v2** (ADR-109: the real parts, the Flywoo P45B pack, 300 g PROVISIONAL headroom; g007-002
2040 g, g012-009 2076 g). The request as first sent said explicit_v1; Emily corrected it to explicit_v2 during the
session, and a pilot started at v1 was stopped and discarded (its plays stay in the cache, keyed by the body, unused).

## 1. The four objectives and their limits

Every play is judged twice:

* **Limits** (hard), as the R11c suite judges every play since Stage B: servo torque-speed envelope, sustained torque
  (above 60 % of rated for more than 25 % of a 2 s window), stall, belt tension (allowable and breaking), joint
  ranges and joint speed, all at **margin 0.2**; three seeds with friction 0.7–1.1 and mass ×0.95–1.05; the worst
  seed counts. Unchanged code: `hardware.judge_play`.
* **Outcome** (`calflab.fitness.outcomes`): a score (higher is better) and named **gates**. A version **holds** when
  every gate passes and it is within every limit on every judging seed.

The search plays short, the judging plays long (same seeds): what is optimised in 12 s must hold for a minute.

| behaviour | score | gates (all PROVISIONAL) | search / judged |
|---|---|---|---|
| **suckle** | 20th percentile of the forward head force on the block over the press window (from 6 s), as a share of body weight | pressing ≥ 90 % of the window (> 0.5 N); steady: std/mean ≤ 0.25; no hoof slides more than 10 mm while loaded; centre of mass ≥ 10 mm inside the loaded hooves' support polygon; head not leaning down on the block (≤ 0.1 body weight, 80th pct); nothing but the head touches the block (≤ 1 N); trunk tilt ≤ 30° | 14 s / 30 s |
| **trot** | the slowest 5 s window's forward speed (mm/s), less 0.5 × sideways drift (mm/s) | slowest window ≥ 100 mm/s; trunk never under 0.8 of standing height; heading within 30°; hoof sliding while loaded ≤ 150 mm per metre travelled; tilt ≤ 30° | 12 s / 60 s |
| **stand** | −(mean + worst)/2 of each servo's mean \|torque\| / rated torque, from 4 s | mean trunk height ≥ 0.85 of standing; nothing but hooves on the floor (≤ 1 N); trunk travel ≤ 20 mm; tilt ≤ 10° | 12 s / 120 s |
| **lie** | 1 − 0.5 × peak descent speed / 300 mm/s − 0.5 × peak body-floor force / 2 body weights (+0.5 if it stands again) | trunk at ≤ 0.5 of standing for ≥ 2 s; tilt ≤ 30° throughout (no tipping); peak trunk descent ≤ 300 mm/s (over 0.1 s); peak force of non-hoof parts on the floor ≤ 2 body weights | its own length + 3.5 s, judged as searched |

New measurements the old suite could not make: a **block** in the world and **contact probes** (`calflab.sim.scene`):
the force of the block on the head, of the block on any other part, and of the floor on any part but the hooves.
The runner records them only when a model asks; every other rollout is unchanged.

### How each could be cheated, and what stops it

| behaviour | cheat | stopped by |
|---|---|---|
| suckle | **a lunge** counted as pushing: a peak, then nothing | the score is the 20th percentile over 8 s (search) / 24 s (judged), not the peak; *pressing*, *steady* |
| suckle | **leaning on the block**: falling forward and being held up by it | *not propped*: the centre of mass must stay inside the loaded hooves' support polygon, so the push is held by the legs (take the block away and it still stands) |
| suckle | resting the head **on top** of the block (the block carrying weight) | only the horizontal force scores; *not leaning down* |
| suckle | pushing with the **chest or a leg** | only the head's force scores; *head only* |
| suckle | sliding the hooves backward (a push that is really a slip) | *no slip* |
| suckle | a high-friction seed only | worst of three seeds (friction 0.7–1.1) |
| trot | **a lunge or a fall forward** counted as travel | the slowest 5 s window, not the mean; a play that stops at the simulator's fall check ranks −5; *stays up*, *tilt* |
| trot | **shuffling** (hooves sliding along the floor) | *no shuffle* |
| trot | **a crawl** (trunk low, crawling on the knees) | *stays up* (≥ 0.8 standing height) |
| trot | running in a **circle** (long path, little distance) | the score is net displacement along x; *heading*; drift subtracted |
| trot | a fast first seconds, then a stall | judged 60 s, slowest window |
| stand | **lying down** or **kneeling** (no servo effort) | *standing* (≥ 0.85 height), *hooves only* |
| stand | **hanging on the joint stops** (the simulator's limits carry load for free) | the joint-limit check (within 1° of a range end is a violation, at margin 0.2) |
| stand | a posture that only holds for 12 s (creep, heating) | judged 120 s, *no drift* |
| lie | **a crouch** counted as lying | *lay down*: trunk ≤ 0.5 of standing for ≥ 2 s (a crouch at 0.6 fails; tested) |
| lie | **dropping** (collapsing onto the belly) | *slow descent*, *soft landing* (tested with a drop) |
| lie | **rolling onto the side** or a somersault (R13's first search found one) | *not tipped* (≤ 30° tilt at any time; tested) |
| lie | lying "within limits" by switching the servos off | not possible here: position servos always hold; the sustained limits apply over the whole play |

What the gates do **not** catch: a gait that is a pace or a bound (allowed: the gait is not prescribed, only
recorded); a stand on a crouch above 0.85; a suckling push whose force line is not where a calf pushes (the head is a
point, see 2); a lying pose the real robot could not rise from (rising is a bonus only).

### The controller family and why (`outcome_motion`)

One small parametric controller for all four, chosen to be cheap enough to search inside a body search on this CPU
(no GPU; a policy would need training per body):

* **Posture keyframes** (up to three; five angles each, the same on both sides: hip ab/ad, stifle, hock, shoulder,
  carpus; and a time to reach each). Standing is one keyframe, suckling a brace then a press, lying a kneel then a lie.
* **A rhythm** whose four leg phases are free numbers (hind-left at 0; the other three searched), with cycle, swing
  fraction, sweep and lift per joint and a hind ab/ad sway. A diagonal trot, a pace, a bound or a walk can emerge;
  the footfall is recorded and labelled (`footfall`), never required.
* **Reflexes** on the IMU only: roll → hind ab/ad, pitch → shoulders and stifles, heading → a left/right stride
  difference. No foot-contact reflex: it needs a phase-reset rule (more numbers to search) and the harness has no foot
  sensors yet (ADR-043).

Old motions are **starting points only**: `feral_motion`'s trot is exactly expressible (`from_feral_trot`; tested
against `feral_motion` frame by frame) and four of R11c's trot-grid corners start the trot search; R13's evolved
lie_rise kneel and lie poses start the lying search; standing starts from the standing pose. The search is free to
leave them, and the gates, not the old motions, say what counts.

Search per behaviour: CMA-ES on its own dims scaled 0..1 (stand 7, suckle 15, trot 20, lie 13), popsize 12,
20 generations, every candidate on three seeds (stopped after the first if hopeless), worst seed ranks; the best
three distinct versions are re-judged at the judging length. Ranking: normalised score (250 mm/s, 0.2 body weights,
2 × effort, lie as is), less 2 per failed gate (a version failing a gate never outranks one that passes on score), less 5
for a fall, plus the margin when negative; the best is chosen lexicographically: holds, within, rank.

## 2. Suckling: what the model lacks

The feral calf's head is a **lumped mass** (150 g PROVISIONAL, a 25 mm sphere 150 mm ahead of the chest block and
150 mm above the axles), rigid on the trunk, and **not a collision shape**. For suckling only, the scene makes that
sphere solid and puts a rigid 40 × 120 × 80 mm block (default friction) with its face 10 mm ahead of it, centred at
the head's standing height (PROVISIONAL: the udder height relative to this body is not known).

**Can the body push with its head as it is? Yes, as a whole-body push.** With no neck the head moves only with the
trunk: the legs lean the trunk forward and the ground's friction carries the force. Two bounds from geometry
(standing pose, explicit_v2):

| body | weight | head height | tipping back about the hind hooves, centre of mass where it stands | ... centre of mass moved to the front hooves (the *not propped* limit) | friction, μ 0.7 / 1.1 |
|---|---|---|---|---|---|
| g007-002 | 20.0 N | 761 mm | 7.3 N (0.37 bw) | 14.0 N (0.70 bw) | 14.0 / 22.0 N |
| g012-009 | 20.4 N | 754 mm | 7.8 N (0.38 bw) | 14.7 N (0.72 bw) | 14.3 / 22.4 N |

So a steady push of up to about 0.7 body weight is physically available without a neck; the pilot (section 3) shows
how much the servos can hold for 24 s.

**What a neck pitch joint would add** (and so when it is needed):

1. **Reach without changing stance.** The head's height is set by the trunk posture. A block above or below the
   head's standing height (the udder height is not given) costs a crouch or a stretch held by the leg servos for the
   whole press. A neck pitch joint aims the muzzle instead.
2. **The direction of the push.** Calves butt upward into the udder. Without a neck the force line is fixed by the
   trunk's pitch; an upward bunt also loads the hooves (more friction available) and lowers the tipping moment.
3. **Butting and rooting** (repeated head movements while the body braces): impossible without a joint.
4. **Holding force independently of posture**: the push is set by how far the posture is commanded past the block
   (servo stiffness × position error) and drifts with the legs; a neck servo would carry it locally.

Also missing, independent of a neck: no **force sensing** in the model (the STS servos report load; the simulator does
not model that reading), so the controller presses open-loop; a **rigid, fixed** block (a real udder is soft and
moves); the **head geometry** (a sphere, no muzzle shape or material); the head's mass and position are PROVISIONAL.

**Hardware, if you want a neck: I have added nothing.** It would be one servo at the neck base pitching the head
(the library's STS3215 C018 or STS3250 C002; a C002 counts against the six-servo budget), a horn and bracket, a neck
of some length, and a decision whether the 150 g lump becomes a head mass at the end of that neck. I need from you:
whether to add it, which servo, the neck length and where its pivot sits on the chest block, the bracket mass (or
leave it null, ADR-051), and the udder height you want the block at. The feral genome would gain a switch
(`has_neck_pitch`, off for every stored genome) as the reference calf has (ADR-055).

## 3. Pilot: four behaviours on g007-002 and g012-009 at explicit_v2

(filled in below from `outcomes_r15.json`)
