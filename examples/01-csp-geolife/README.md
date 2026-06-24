# Worked Example 01 — Constraint-Satisfaction Alibi Consistency on GeoLife GPS

> A fully runnable Digital-Forensics + AI worked example. It parses a **real**
> Microsoft GeoLife GPS trajectory, builds a **Constraint-Satisfaction Problem
> (CSP)** with Google OR-Tools **CP-SAT**, and uses the solver to test whether a
> suspect's alibi is *physically consistent* with independent evidence. All
> numbers in [Verified output](#verified-output) are genuine solver output
> captured in [`output.txt`](./output.txt).

---

## Overview

**Technique.** Constraint Satisfaction. We discretise a one-hour window into
seven time slots and model the suspect's location at each slot as a variable
ranging over four city regions. Pieces of evidence (a phone-provider record, a
CCTV hit) and a physics rule (you cannot move faster than 120 km/h) become
constraints. We then ask a CP-SAT solver a yes/no question: *does any sequence
of locations satisfy every constraint at once?*

**Dataset.** Microsoft **GeoLife GPS Trajectories v1.3** — 17,621 real GPS
trajectories from 182 users in Beijing, recorded 2007–2012. We parse one real
trajectory (user `010`) to (a) demonstrate genuine `.plt` parsing and (b)
*ground* the region grid in authentic Beijing coordinates.

**Forensic question.** A suspect's phone places them at home (HOME_NORTH) at
14:00 and 15:00. A CCTV camera reportedly places them at the crime scene
(CRIME_SCENE_SOUTH), ~67 km away, at 14:30. **Can both be true?** The solver
answers: **no** — and returns the *minimal set of contradicting evidence*. It
never outputs "guilty"; it outputs *inconsistency*. That distinction is the
whole pedagogical point.

---

## Dataset & download

| Field | Value |
|---|---|
| Name | Geolife Trajectories 1.3 |
| Provider | Microsoft Research |
| URL | `https://download.microsoft.com/download/f/4/8/f4894aa5-fdbc-481e-9285-d5f8c4c4f039/Geolife%20Trajectories%201.3.zip` |
| Size | ~298 MB zipped (~1.6 GB extracted) |
| License | Microsoft Research License Agreement (free for research/education; see the `User Guide-1.3.pdf` inside the archive) |
| Format | `.plt` files: **6 header lines**, then CSV rows `lat,lon,0,alt,days,date,time` |

A real `.plt` header + first data rows (user `010`, file `20070804033032.plt`):

```
Geolife trajectory
WGS 84
Altitude is in Feet
Reserved 3
0,2,255,My Track,0,0,2,8421376
0
39.921712,116.472343,0,13,39298.1462037037,2007-08-04,03:30:32
39.921705,116.472343,0,13,39298.1462152778,2007-08-04,03:30:33
```

Download command:

```bash
mkdir -p data
wget -q -O data/geolife.zip "https://download.microsoft.com/download/f/4/8/f4894aa5-fdbc-481e-9285-d5f8c4c4f039/Geolife%20Trajectories%201.3.zip" \
  && unzip -q data/geolife.zip -d data
# the chosen trajectory then lives at:
#   data/Geolife Trajectories 1.3/Data/010/Trajectory/*.plt
```

> The archive is large. Keep it under `data/` (gitignored). After extraction you
> can delete `data/geolife.zip` to reclaim ~298 MB; `run.py` only needs the
> extracted `.plt` files.

---

## How to run

Copy-paste runnable from this folder. The venv inherits system `numpy` etc.
(`--system-site-packages`) to avoid the local py3.10/pip-3.11 mismatch, then adds
OR-Tools:

```bash
cd examples/01-csp-geolife

# 1. environment
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --quiet ortools

# 2. data (see "Dataset & download" above)
mkdir -p data
wget -q -O data/geolife.zip "https://download.microsoft.com/download/f/4/8/f4894aa5-fdbc-481e-9285-d5f8c4c4f039/Geolife%20Trajectories%201.3.zip" \
  && unzip -q data/geolife.zip -d data

# 3. run and capture the real output
python3 run.py | tee output.txt
```

---

## Workflow

```
download  ->  parse  ->  encode  ->  build CSP  ->  solve  ->  interpret
```

1. **Download** the GeoLife archive; extract to `data/`.
2. **Parse** one real `.plt` (skip 6 header lines) into `(lat, lon, alt, date, time)` points.
3. **Encode** the forensic scenario: a 4-region grid anchored on a real GPS
   point, and a haversine distance matrix between region centroids.
4. **Build CSP**: one location variable per time slot, plus anchor, CCTV and
   reachability constraints (CP-SAT model).
5. **Solve** twice — scenario (a) the contradictory CCTV time, scenario (b) a
   reachable CCTV time. Capture status and, on UNSAT, the minimal conflict.
6. **Interpret**: UNSAT = evidence mutually contradictory (report the conflict);
   SAT = a consistent timeline exists (report it).

---

## Encoding

**Variables.** One integer variable per time slot, value = region index:

```
loc[0..6]  ∈ {0:HOME_NORTH, 1:MIDTOWN, 2:CRIME_SCENE_SOUTH, 3:ELSEWHERE}
slots:      14:00 14:10 14:20 14:30 14:40 14:50 15:00   (10-min steps)
```

**Domains.** Each `loc[t]` ranges over the 4 region indices.

**Region grid** (centroids; offsets chosen so the speed limit actually bites):

| Region | Offset from anchor | Role |
|---|---|---|
| HOME_NORTH | +0.30° lat | suspect's phone-anchored home |
| MIDTOWN | +0.15° lat | the one region reachable from HOME in a single slot |
| CRIME_SCENE_SOUTH | −0.30° lat | crime scene, ~67 km from HOME (unreachable in one slot) |
| ELSEWHERE | +0.60° lon | distractor region, ~61 km east |

**Constraints.**

- **Anchor (hard):** `loc[0] == HOME_NORTH` and `loc[6] == HOME_NORTH`
  (phone-provider records).
- **CCTV (assumption literal):** `loc[k] == <region>` at slot `k`.
  Scenario (a): `loc[3] == CRIME_SCENE_SOUTH`. Scenario (b): `loc[3] == MIDTOWN`.
- **Reachability (assumption literal per consecutive pair):** for every slot
  transition `t → t+1`, the pair `(loc[t]=a, loc[t+1]=b)` is forbidden whenever
  `dist[a][b] > MAX_REACH_KM`, where `MAX_REACH_KM = 120 km/h × 10 min = 20 km`.

The CCTV and reachability constraints are registered as **assumption literals**
via `model.AddAssumptions(...)`, so that when the model is UNSAT, CP-SAT can
return the *minimal* contradicting subset.

---

## Algorithm & data structures

- **Solver: OR-Tools CP-SAT** (`ortools.sat.python.cp_model`), a lazy-clause-
  generation CP/SAT hybrid. We bound it with a 10 s time limit (the model is
  tiny and solves instantly).
- **Distance matrix:** 4×4 `dist[i][j]`, great-circle **haversine** distance in
  km between region centroids (Earth radius 6371.0088 km). This is the data
  structure the reachability constraints read.
- **Constraint graph:** time slots form a path `s0–s1–…–s6`; reachability
  constraints are the *edges* of this path, the anchor/CCTV constraints are
  *unary* pins on individual nodes. A location channelling pattern
  (`loc[t]==a  ⇔  bool ta`) turns each forbidden transition into a CNF clause
  `(¬ta ∨ ¬tb)` enforced under the slot's reachability literal.
- **UNSAT-core extraction:** `solver.SufficientAssumptionsForInfeasibility()`
  returns the minimal set of assumption literals (CCTV + the specific
  reachability hops) that together make the model infeasible. We map literal
  indices back to human-readable descriptions for the report.

---

## PLAN-PHASE PROMPT

> *(What an instructor/analyst types to an AI agent to PLAN the analysis.)*

```
You are a digital-forensics analyst's planning assistant. Plan — do not yet
execute — a constraint-satisfaction analysis that tests whether a suspect's
alibi is physically consistent with the evidence.

Context:
  - Phone-provider records place the suspect at HOME (north Beijing) at 14:00
    and at 15:00.
  - A CCTV hit reportedly places them at the CRIME SCENE (south Beijing, ~67 km
    from home) at 14:30.
  - Assume a maximum travel speed of 120 km/h.

Produce a plan covering:
  1. Data: which open dataset to use to ground real coordinates (GeoLife GPS
     Trajectories v1.3), how to download it, and the .plt format.
  2. Encoding: how to turn the one-hour window into discrete time-slot
     variables, what the region domains are, and which evidence becomes which
     constraint (anchor / CCTV / reachability via a haversine distance matrix).
  3. Tooling: use Python + OR-Tools CP-SAT; register CCTV and reachability as
     assumption literals so an UNSAT core can be extracted.
  4. Outputs: solver status for two scenarios (contradictory vs reachable CCTV
     time), the minimal conflicting-constraint set on UNSAT, and a satisfying
     region-per-slot timeline on SAT.
  5. Reporting rule: the deliverable is "consistent" or "contradictory (with the
     conflicting evidence named)" — NEVER a guilt determination.

Return the plan as numbered steps with the exact tools/commands you will use.
```

## EXECUTE-PHASE PROMPT

> *(What the analyst types to actually carry out the plan / run the tools.)*

```
Execute the plan now. Concretely:

  1. Create a Python venv with --system-site-packages and `pip install ortools`.
  2. Download GeoLife Trajectories 1.3 into data/ and unzip it. If the download
     fails, say so and fall back to a format-accurate synthetic .plt, clearly
     labelled.
  3. Write and run run.py so that it:
       a. parses data/.../010/Trajectory/*.plt (skip 6 header lines); print the
          point count and two sample rows;
       b. builds the 4-region grid anchored on the first real GPS point and
          prints the haversine distance matrix;
       c. builds the CP-SAT model (7 slot vars, anchor + CCTV + reachability
          constraints with assumption literals);
       d. solves scenario (a) CCTV @ CRIME_SCENE_SOUTH 14:30 → report status;
          on UNSAT print the minimal conflicting constraints;
       e. solves scenario (b) CCTV retimed to a reachable region → report status
          and the satisfying timeline.
  4. Capture the real output with `python3 run.py | tee output.txt`.
  5. Summarise: scenario (a) status + the named conflict; scenario (b) status +
     the timeline. Do not state guilt — only consistency / contradiction.
```

---

## Part 5 — Agent handling (ReAct)

**Analyst natural-language prompt to the agent:**

```
Check whether the suspect's alibi holds. Their phone shows them at home at 14:00
and 15:00, but a CCTV hit puts them at the crime scene (~67 km south) at 14:30,
assuming at most 120 km/h. Is that physically possible? If not, tell me exactly
which pieces of evidence conflict. Do not tell me whether they are guilty.
```

**Thought → Action → Observation trace** (matches what `run.py` actually does):

```
Thought:  I need real Beijing coordinates to make the geography credible.
          I'll use a GeoLife trajectory and parse it.
Action:   parse_plt("data/.../010/Trajectory/20070804033032.plt")
Observation: 1116 GPS points parsed; first point lat=39.921712, lon=116.472343.

Thought:  Build a region grid around that anchor and compute how far apart the
          regions are, so I know what is reachable in one 10-minute slot.
Action:   build_regions(anchor); haversine distance matrix
Observation: HOME↔CRIME_SCENE_SOUTH = 66.7 km. Max reach per slot at 120 km/h
             = 20 km. So the crime scene is NOT reachable within one slot.

Thought:  Encode evidence as a CSP. Anchor HOME at 14:00 and 15:00 (hard);
          CCTV at CRIME_SCENE_SOUTH @ 14:30 and each reachability hop as
          assumption literals; then solve.
Action:   solve_alibi(cctv=CRIME_SCENE_SOUTH @ 14:30)   [CP-SAT]
Observation: status = INFEASIBLE.

Thought:  Infeasible means the evidence contradicts itself. Extract the minimal
          conflicting set so I can report exactly which evidence clashes.
Action:   solver.SufficientAssumptionsForInfeasibility()
Observation: core = { CCTV @ CRIME_SCENE_SOUTH 14:30,
                      reachability 14:00→14:10, 14:10→14:20, 14:20→14:30 }.

  >>> HUMAN-IN-THE-LOOP GATE <<<
  The agent STOPS and reports a CONTRADICTION to the analyst. It does not, and
  must not, output a guilt verdict. The analyst decides next steps (e.g. is the
  CCTV timestamp reliable? re-examine the phone record?).

Thought:  As a sensitivity check, what if the CCTV timestamp/place is revised to
          a reachable region (MIDTOWN, 16.7 km from home)?
Action:   solve_alibi(cctv=MIDTOWN @ 14:30)   [CP-SAT]
Observation: status = FEASIBLE; timeline HOME→MIDTOWN→HOME→MIDTOWN→HOME→HOME→HOME.

Thought:  Now the evidence is mutually consistent. Report both results plus the
          named conflict from the original scenario.
```

**Tools the agent calls:** `parse_plt` (file I/O), `build_regions` + `haversine`
(geometry), `cp_model` build/solve (CP-SAT), and
`SufficientAssumptionsForInfeasibility` (conflict extraction).

**Human-in-the-loop gate & failure mode.** The gate fires the moment the solver
returns **INFEASIBLE**: the agent surfaces the *minimal conflicting evidence set*
and hands control to the analyst rather than escalating to a conclusion. The two
terminal modes are:

- **UNSAT (failure of the alibi):** evidence is contradictory → report *which*
  constraints clash. Never "guilty".
- **SAT (alibi holds):** at least one consistent timeline exists → report it.

---

## Verified output

The following is the **real** captured run (`output.txt`), verbatim:

```text
======================================================================
CSP FORENSIC ALIBI-CONSISTENCY PIPELINE  (GeoLife GPS dataset)
======================================================================

[1] Parsing real GeoLife trajectory:
    /mnt/d/courses/DF-AI/examples/01-csp-geolife/data/Geolife Trajectories 1.3/Data/010/Trajectory/20070804033032.plt
    Parsed 1116 GPS points (6 header lines skipped).
    Sample row 1: lat=39.921712, lon=116.472343, alt=13.0, date=2007-08-04, time=03:30:32
    Sample row 558: lat=39.907288, lon=116.438098, alt=98.0, date=2007-08-04, time=03:49:05

[2] Building region grid anchored on real GPS point lat=39.92171, lon=116.47234
    HOME_NORTH         centroid=(40.22171, 116.47234)
    MIDTOWN            centroid=(40.07171, 116.47234)
    CRIME_SCENE_SOUTH  centroid=(39.62171, 116.47234)
    ELSEWHERE          centroid=(39.92171, 117.07234)

    Haversine distance matrix (km), max reach per 10 min = 20 km:
                        HOME_NOR   MIDTOWN  CRIME_SC  ELSEWHER
    HOME_NORTH               0.0      16.7      66.7      61.0
    MIDTOWN                 16.7       0.0      50.0      53.8
    CRIME_SCENE_SOUTH       66.7      50.0       0.0      61.2
    ELSEWHERE               61.0      53.8      61.2       0.0

[3/4] Building & solving the CSP with OR-Tools CP-SAT ...

=== Scenario: (a) CCTV at 14:30  [expect INFEASIBLE] ===
CCTV evidence : CRIME_SCENE_SOUTH @ 14:30
Phone anchor  : HOME_NORTH @ 14:00 and @ 15:00
Solver status : INFEASIBLE
RESULT: INFEASIBLE -- the evidence is mutually contradictory.
Minimal conflicting constraint set (UNSAT core):
   - CCTV: suspect at CRIME_SCENE_SOUTH at 14:30
   - Reachability 14:00->14:10 (<= 20 km in 10 min)
   - Reachability 14:10->14:20 (<= 20 km in 10 min)
   - Reachability 14:20->14:30 (<= 20 km in 10 min)
Forensic reading: the alibi and the CCTV hit cannot both be true.
The agent reports a CONTRADICTION -- it does NOT conclude 'guilty'.

=== Scenario: (b) CCTV retimed to MIDTOWN @ 14:30  [expect FEASIBLE] ===
CCTV evidence : MIDTOWN @ 14:30
Phone anchor  : HOME_NORTH @ 14:00 and @ 15:00
Solver status : OPTIMAL
RESULT: FEASIBLE -- a consistent timeline exists:
   14:00  ->  HOME_NORTH
   14:10  ->  MIDTOWN
   14:20  ->  HOME_NORTH
   14:30  ->  MIDTOWN
   14:40  ->  HOME_NORTH
   14:50  ->  HOME_NORTH
   15:00  ->  HOME_NORTH

======================================================================
DONE. Interpretation:
  Scenario (a) is UNSAT: the phone-at-HOME alibi and the CCTV hit at
  CRIME_SCENE_SOUTH are physically irreconcilable given the speed
  limit -> the solver returns the minimal conflicting evidence set.
  Scenario (b) is SAT: re-timing the CCTV hit to the reachable
  MIDTOWN district yields a fully consistent HOME<->MIDTOWN timeline.
======================================================================
```

**Interpretation.** In scenario (a) the solver proves the suspect *cannot* have
been at home at 14:00, at the crime scene 67 km away at 14:30, and home again at
15:00 — 120 km/h covers only 20 km per slot, so the CCTV hit and the phone
anchor are mutually contradictory; CP-SAT names the exact conflicting evidence
(the CCTV claim plus the three impossible reachability hops). In scenario (b),
re-timing the CCTV hit to the nearby, reachable MIDTOWN district makes the
evidence consistent and the solver returns a concrete HOME↔MIDTOWN timeline. The
agent's output is always *consistent* vs *contradictory (with the conflict
named)* — never a guilt determination.

---

## Notes / deviations

- **Download succeeded.** The official Microsoft URL worked (HTTP 200, ~298 MB).
  No fallback / synthetic `.plt` was needed — the parsed trajectory is the real
  GeoLife user `010` file `20070804033032.plt` (1,116 GPS points).
- **`data/geolife.zip` was deleted after extraction** to save ~298 MB. The
  extracted `data/Geolife Trajectories 1.3/` (~1.6 GB) remains and is gitignored
  by the parent repo. Re-download with the command above if needed.
- **Conflict extraction** uses `solver.SufficientAssumptionsForInfeasibility()`
  with CCTV and per-hop reachability registered as assumption literals — this is
  the intended, exact method (not a manual fallback).
- **Scenario (b) design choice.** The brief suggested moving the CCTV to 15:30 to
  get a feasible case. Slots only run 14:00–15:00, so a 15:30 hit would simply
  fall outside the modelled window. To produce a *richer* SAT witness (real
  movement rather than a trivial stay-at-home), (b) instead keeps the hit inside
  the window but at the reachable MIDTOWN district — yielding the
  HOME↔MIDTOWN timeline shown above.
- **Pip warning (cosmetic).** Installing OR-Tools prints a dependency-resolver
  warning about a pre-existing system `mediapipe`/`protobuf` version mismatch.
  It is unrelated to this example; OR-Tools imports and runs correctly.
- **Geometry precision.** Region offsets are chosen so haversine distances clear
  the 20 km reach budget unambiguously (HOME↔MIDTOWN = 16.7 km; everything else
  ≥ 50 km), avoiding any borderline floating-point edge at exactly 20.0 km.
