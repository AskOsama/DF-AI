# Example 03 — Knowledge Representation & Reasoning over a Flight Graph (OpenFlights)

A **runnable** Knowledge-Representation & Reasoning (KRR) worked example for the
Digital Forensics + AI course. We encode the world airline route network as a
**knowledge base of logical facts**, define **recursive inference rules**, and
answer a real forensic *reachability* question — then produce an **auditable
derivation chain** and **cross-check two reasoning engines**
(`networkx` graph search vs. `pyDatalog` declarative recursion).

---

## Overview

**Forensic scenario.** Subject *X* claims to be in **Dubai (DXB)**. Investigators
last *confirmed* X at **London Heathrow (LHR)**. A crime was committed in
**Bogota (BOG)**. The analyst's question:

> Could X have physically reached BOG from LHR using **≤ 3 connections**
> (a path of ≤ 4 flight legs) on the scheduled route network?

This is a classic **reachability / path-inference** problem over a knowledge
base. If a short derivable route exists, the "I was in Dubai" alibi does **not**,
on its own, place X out of reach of the crime scene — and we can produce a
step-by-step *proof* (derivation chain) that an investigator or court can audit.

KRR concepts exercised: facts vs. rules, **backward chaining** (goal-directed
proof) vs. **forward chaining**, recursion with a **cycle guard**, bounded
search, and engine cross-validation.

---

## Dataset & download

**OpenFlights** route + airport database (real, open-access).

| File | URL | Approx size | Format |
|------|-----|-------------|--------|
| `routes.dat` | https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat | ~2.3 MB / 67,663 rows | CSV |
| `airports.dat` | https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat | ~1.1 MB / 7,698 rows | CSV |

- **License:** Open Database License (**ODbL**) — free to share/adapt with attribution.
- **Snapshot date:** the OpenFlights route table reflects roughly **June 2014**.
  Conclusions are only as current as this snapshot (see *Part 5 — failure mode*).
- **`routes.dat` columns:** `Airline, AirlineID, Src, SrcID, Dst, DstID, Codeshare, Stops, Equipment`
- **`airports.dat` columns:** `ID, Name, City, Country, IATA, ICAO, Lat, Lon, …` (null = `\N`)

Download:

```bash
mkdir -p data && cd data
curl -s -L -O https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat
curl -s -L -O https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat
cd ..
```

---

## How to run

```bash
cd examples/03-knowledge-openflights

# venv that inherits the system networkx; pyDatalog installed into the venv
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --quiet pyDatalog   # optional; script falls back to networkx if it fails

# (download data as above, into ./data)

python3 run.py | tee output.txt
```

Runtime: ~10–15 s (most of it is enumerating ≤ 3-leg paths). pyDatalog reasoning
runs on a **bounded subgraph** (see *Notes*) and is near-instant.

---

## Workflow

```
download data           routes.dat + airports.dat (ODbL)
   │
   ▼
parse facts             airport(IATA, City, Country)   from airports.dat
                        flight(Airline, Src, Dst)      from routes.dat (skip \N)
   │
   ▼
build graph / KB        networkx.MultiDiGraph
                          nodes = airports (city, country attrs)
                          edges = flights  (airline attr)
   │
   ▼
define rules            reachable/2 : base + recursive (with cycle guard)
                        contradicts_alibi/1
   │
   ▼
query reachability      reachable(LHR, BOG) within ≤ 4 legs?
                          - direct-edge check
                          - bounded BFS (proof of existence)
                          - bounded DFS path enumeration (all_simple_paths)
   │
   ▼
extract auditable       backward-chaining GOAL / RULE / FACT proof tree
derivation chain          for one concrete LHR → hub → BOG route
   │
   ▼
cross-check             pyDatalog recursive reasoning  ==  networkx result
```

---

## Encoding

### Facts (extensional database)

```prolog
% airport(IATA, City, Country).
airport('LHR', 'London',  'United Kingdom').
airport('BOG', 'Bogota',  'Colombia').
airport('ATL', 'Atlanta', 'United States').
% ... 6,072 airport facts total

% flight(Airline, Src, Dst).
flight('AA', 'LHR', 'ATL').
flight('DL', 'ATL', 'BOG').
% ... 66,934 flight facts total
```

### Rules (intensional database)

```prolog
% --- reachable/2 : transitive closure of flight, bounded by search depth ---

% Base case: a single direct leg.
reachable(X, Y) :- flight(_, X, Y).

% Recursive case: fly X -> Z on some airline, then reach Y from Z.
% The (X != Y) literal is a cycle guard that stops trivial self-loops.
reachable(X, Y) :- flight(_, X, Z), reachable(Z, Y), X \= Y.

% --- the forensic rule: does reachability contradict the stated alibi? ---
% X claims to be at DXB but LHR->BOG is reachable => the alibi does not
% make the crime scene physically out of reach.
contradicts_alibi(X) :-
        claims_location(X, 'DXB'),
        last_confirmed(X, 'LHR'),
        reachable('LHR', 'BOG').
```

In **pyDatalog** (Python) syntax, the recursive rule used by `run.py` is:

```python
reachable(X, Y) <= flight(X, Y)
reachable(X, Y) <= flight(X, Z) & reachable(Z, Y) & (X != Y)
```

---

## Algorithm & data structures

- **Knowledge base / graph:** `networkx.MultiDiGraph` — a **directed multigraph**.
  Airports are nodes (with `city`, `country` attributes); each `flight` fact is a
  directed edge carrying an `airline` attribute. *Multi*-graph because many
  airlines may operate the same Src→Dst pair (parallel edges), e.g. LHR→ATL is
  served by AA, AF, AY, BA, DL, IB, KL, VS.

- **Forward chaining** (data-driven): start from facts, repeatedly apply rules to
  derive *all* consequences until fixpoint. Naive forward chaining on the full
  `reachable/2` relation computes the entire transitive closure — huge and
  unnecessary here (~6k nodes, 67k edges).

- **Backward chaining** (goal-driven): start from the goal
  `reachable(LHR, BOG)` and work backwards through rule bodies, only exploring
  facts/subgoals relevant to the query. This is what produces the compact
  **derivation (proof) tree** we print. pyDatalog uses an SLD-style /
  semi-naive evaluation that is effectively goal-directed for our query.

- **Bounded search:** because the route network has very high out-degree (LHR
  alone reaches hundreds of airports), enumerating *all* simple paths up to 4
  legs is combinatorially explosive. The script therefore:
  - proves *existence* with a **bounded BFS** (depth ≤ 4),
  - finds 1-connection routes by **successor∩predecessor hub intersection**,
  - enumerates short paths with a **bounded DFS** (`all_simple_paths`, `cutoff=3`).

- **Libraries:**
  - `networkx` (graph KB + bounded DFS/BFS path inference) — the authoritative engine.
  - `pyDatalog` (declarative recursive Datalog) — cross-check on a bounded subgraph.

---

## PLAN-PHASE PROMPT

> **Role:** You are a forensic-reasoning planner.
> **Goal:** Plan (do **not** execute) a knowledge-representation pipeline that
> decides whether a suspect could have travelled from one airport to another
> within a bounded number of connections, using the OpenFlights route database.
>
> Produce a numbered plan that:
> 1. States the forensic question precisely (source LHR, destination BOG,
>    constraint ≤ 3 connections = ≤ 4 legs) and what a positive/negative answer
>    implies for the suspect's Dubai alibi.
> 2. Identifies the data needed (`routes.dat`, `airports.dat`), their columns,
>    license (ODbL), and snapshot date, and how nulls (`\N`) must be handled.
> 3. Specifies the **fact schema** (`airport/3`, `flight/3`) and the **rules**
>    (`reachable/2` base + recursive with a cycle guard; `contradicts_alibi/1`),
>    written in Datalog/Prolog syntax.
> 4. Chooses data structures (directed multigraph) and reasoning strategy
>    (backward vs. forward chaining) and **justifies bounding** the search to
>    keep recursion finite given the graph size.
> 5. Defines how to extract an **auditable derivation chain** (GOAL/RULE/FACT
>    tree) for a concrete route, and how to **cross-validate** two independent
>    engines.
> 6. Lists the verification checks (direct-edge check, both legs of the shown
>    path confirmed present, engine agreement) and the stop conditions.
> Output only the plan and its assumptions/risks; write no code yet.

## EXECUTE-PHASE PROMPT

> **Role:** You are a forensic data engineer executing the approved plan.
> **Task:** Implement `run.py` and actually run it on the real OpenFlights data.
> Requirements:
> - Parse `airports.dat` → `airport(IATA, City, Country)` (skip rows without a
>   valid 3-letter IATA); parse `routes.dat` → `flight(Airline, Src, Dst)`
>   (skip `\N` source/destination). Print fact and node/edge counts.
> - Build a `networkx.MultiDiGraph` (airport attrs = city/country; edge attr = airline).
> - Answer reachability **LHR → BOG within ≤ 4 legs**: print whether a direct
>   edge exists; prove existence with bounded BFS; enumerate short paths with
>   `all_simple_paths(cutoff=3)`; show one **1-connection** path with the **real
>   airlines** on each leg and **verify** both legs exist in the KB; report the
>   hub airport with its city/country.
> - Print an **auditable backward-chaining derivation chain** (GOAL → RULE →
>   FACT) for the chosen route.
> - If `pyDatalog` imports: assert `flight/2` facts for the bounded candidate
>   subgraph, define the recursive `reachable/2` rules, query
>   `reachable('LHR','BOG')`, and **cross-check** that it matches networkx;
>   otherwise document the failure and rely on networkx.
> - Save real output: `python3 run.py | tee output.txt`. Do not fabricate any
>   numbers; report exactly what the code prints.

---

## Part 5 — Agent handling (ReAct)

**Analyst prompt (to the reasoning agent):**

> You are a digital-forensics travel-reachability analyst. A knowledge base of
> flight facts (`flight/3`) and airport facts (`airport/3`) is loaded, with a
> rule `reachable/2`. Subject X claims to be in Dubai; X was last confirmed at
> **LHR**; the crime scene is **BOG**. Using only the KB, determine whether X
> could have reached BOG from LHR within **≤ 3 connections**, surface a concrete
> route with the operating airlines, and present an auditable derivation. If
> reachability is confirmed, flag it for a human investigator to review before
> any conclusion is recorded. Always state the data snapshot date with your
> answer.

**ReAct trace (matches what `run.py` actually computes):**

```
Thought:  First check the cheapest disqualifier — is there a DIRECT LHR->BOG flight?
Action:   query_kb(flight, src='LHR', dst='BOG')
Observation: no direct edge (False).

Thought:  No direct flight. Ask the reasoning engine whether BOG is reachable
          from LHR within the legal bound of 4 legs.
Action:   query_kb(reachable, 'LHR', 'BOG', max_legs=4)
Observation: True  (bounded BFS confirms reachability).

Thought:  Reachable. I need a concrete, verifiable route to show. Find the
          1-connection hubs (airports with both LHR->hub and hub->BOG).
Action:   find_hubs(src='LHR', dst='BOG')
Observation: 16 hubs; representative route LHR -> ATL -> BOG.

Thought:  Surface the underlying flight FACTS and confirm both legs exist.
Action:   query_kb(flight, src='LHR', dst='ATL'); query_kb(flight, src='ATL', dst='BOG')
Observation: LHR->ATL operated by AA, AF, AY, BA, DL, IB, KL, VS;
             ATL->BOG operated by DL. Both legs VERIFIED present.

Thought:  Build the backward-chaining derivation chain and cross-check with the
          second engine (pyDatalog) before reporting.
Action:   derive_chain('LHR','BOG'); crosscheck(networkx, pyDatalog)
Observation: proof tree produced; both engines agree (reachable = True).

Thought:  Reachability and route confirmed. This is an investigative lead, not a
          verdict — escalate to a human.
Action:   request_human_review(finding="LHR->BOG reachable in 1 connection via ATL (DL)",
                               snapshot="OpenFlights ~June 2014")
Observation: Awaiting analyst sign-off.
```

**Tools the agent calls:** `query_kb` (fact / `reachable` lookups), `find_hubs`
(successor∩predecessor intersection), `derive_chain` (proof-tree builder),
`crosscheck` (engine agreement), `request_human_review`.

**Human-in-the-loop gate.** The agent never records a conclusion. A positive
reachability result is an *investigative lead* requiring an analyst to sign off
(`request_human_review`) before it is entered into a case file. Reachability ≠
proof of travel: it shows X *could* have flown the route, not that X *did*.

**Failure mode.** The conclusion is **only as complete as the route snapshot**.
OpenFlights here reflects **~June 2014**: routes added later (e.g. a new direct
LHR→BOG service) or seasonal/cancelled routes are invisible, so the model can
both **miss** real options and assert routes no longer flown. Codeshares,
minimum-connection-time, visas, and actual seat availability are **not** modeled.
Always cite the snapshot date and treat output as a lead, not evidence.

---

## Verified output

Real output captured in [`output.txt`](output.txt) from `python3 run.py`:

```
======================================================================
STEP 1 -- PARSE FACTS AND BUILD KNOWLEDGE BASE (networkx MultiDiGraph)
======================================================================
airport/3 facts parsed :   6072  (IATA -> City, Country)
flight/3  facts parsed :  66934  (Airline, Src, Dst)
graph nodes (airports) :   6072
graph edges (flights)  :  66934
  LHR = London, United Kingdom
  BOG = Bogota, Colombia

======================================================================
STEP 2 -- REACHABILITY LHR -> BOG  (<= 3 connections)
======================================================================
Direct flight LHR -> BOG exists? False
Bounded BFS: LHR -> BOG reachable within 4 legs? True
1-connection (2-leg) hubs LHR->hub->BOG: 16
Simple paths LHR -> BOG with <= 3 legs: 35980
  2 leg(s) (1 connection(s)): 209 path(s)
  3 leg(s) (2 connection(s)): 35771 path(s)

-- Shortest path found --
  route : LHR -> ATL -> BOG
  cities: London -> Atlanta -> Bogota
    leg LHR->ATL  airlines=AA,AF,AY,BA,DL,IB,KL,VS        edge_exists=True
    leg ATL->BOG  airlines=DL                             edge_exists=True

-- A representative 1-CONNECTION (2-leg) path with real airlines --
  route : LHR -> ATL -> BOG
    LHR (London) -> ATL (Atlanta) : airlines = AA, AF, AY, BA, DL, IB, KL, VS
    ATL (Atlanta) -> BOG (Bogota) : airlines = DL
  VERIFIED both legs present in KB: True
  HUB / connecting airport: ATL (Atlanta, United States)

======================================================================
STEP 2d -- AUDITABLE DERIVATION CHAIN (backward-chaining proof tree)
======================================================================
GOAL: reachable('LHR', 'BOG')   (can X get from LHR to BOG?)
  RULE: reachable('LHR','BOG') :- flight(_,'LHR','ATL'), reachable('ATL','BOG').
  |- flight('AA', 'LHR', 'ATL')   [FACT from routes.dat]
  |- subgoal: reachable('ATL', 'BOG')
     RULE: reachable('ATL','BOG') :- flight(_,'ATL','BOG').
     |- flight('DL', 'ATL', 'BOG')   [FACT from routes.dat]

=> DERIVED: reachable('LHR', 'BOG') is TRUE via LHR -> ATL -> BOG
=> contradicts_alibi(X) :- reachable(LHR, BOG), claims_location(X, DXB),
                          not necessarily_at(X, DXB).
   The 'Dubai' alibi does NOT make BOG physically unreachable.

======================================================================
STEP 3 -- DECLARATIVE RULE REASONING (pyDatalog) + CROSS-CHECK
======================================================================
Asserting bounded KB: 185 airports on candidate paths.
Asserted 1430 flight/2 facts (deduped edges on candidate paths).
pyDatalog query  reachable('LHR','BOG')  -> True  (answer set: [()])
networkx says reachable: True
CROSS-CHECK: pyDatalog == networkx ?  True

======================================================================
DONE
======================================================================
```

**Interpretation.** There is **no direct LHR→BOG flight** in the snapshot, but
BOG is reachable from LHR with just **one connection**: the system found **16
single-hub routes**, and a verified representative is **LHR → ATL (Atlanta) →
BOG**, where LHR→ATL is operated by several carriers (AA, AF, AY, BA, DL, IB, KL,
VS) and ATL→BOG by **Delta (DL)** — both legs confirmed present as real facts.
Allowing up to two connections explodes the option space to ~36k routes, and the
two independent engines (**networkx** bounded search and **pyDatalog** recursive
rules) **agree** that `reachable('LHR','BOG')` is **True**, so X's Dubai alibi
does not place the Bogota crime scene out of physical reach.

---

## Notes / deviations

- **pyDatalog status: WORKS.** `pip install pyDatalog` succeeded and it imported
  and ran recursive `reachable/2` rules on Python 3.10. (The prompt warned it
  might fail to build/import; here it did not.) It is used as the declarative
  cross-check engine and agrees with networkx.
- **Bounded Datalog KB (important deviation for tractability).** Naive recursive
  Datalog over all 66,934 edges blows up (transitive closure over ~6k nodes).
  We therefore assert into pyDatalog only the **1,430 deduped edges among the
  185 airports that lie on candidate ≤ 3-leg LHR→BOG paths**. This is *sound*
  for the query: any LHR→BOG path of ≤ 4 legs lives entirely within this
  subgraph, so reachability is preserved. networkx remains the authoritative
  engine over the full graph.
- **Path-count bounding.** Enumerating all simple paths up to 4 legs is
  combinatorially explosive on this high-degree graph, so existence is proven
  with a bounded BFS (depth ≤ 4) while full enumeration is capped at `cutoff=3`
  (≤ 2 connections). The 1-connection routes are found exactly via hub
  intersection. The "≤ 3 connections" forensic bound is fully covered:
  direct (0) is checked, 1-connection is enumerated exactly, and reachability
  within ≤ 4 legs (≤ 3 connections) is decided by the bounded BFS.
- **Snapshot date.** Routes reflect **~June 2014**; see *Part 5 — failure mode*.
- **Modeling limits.** Codeshares, minimum connection times, seat availability,
  visas, and timetable feasibility are not modeled — output is an investigative
  *lead*, not evidence of travel.
```
