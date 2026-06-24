# Example 02 — Optimization: Triage Prioritisation on GovDocs1

## Overview

A forensic examiner is handed a seized drive with **hundreds of files** and a
**fixed time budget**. Reviewing everything is impossible (this corpus alone
would take ~136 hours), so the examiner must choose *which files to review
first* to maximise investigative value within the budget. That is exactly a
**resource-allocation / knapsack** problem, and it is the canonical place where
**optimization** beats ad-hoc gut feeling.

This example runs a **real, end-to-end triage-prioritisation pipeline** over a
real open-access corpus:

1. **Featurize** every file → a cost (examiner minutes) and a *disclosed*
   value score (type prior + PII/regex hits + entropy).
2. **Baselines** for a 16 h budget: greedy, random, brute-force.
3. **0/1 knapsack** (Google OR-Tools) — the provably optimal single-examiner plan.
4. **Two-examiner split** (OR-Tools CP-SAT multiple-knapsack).
5. **Multi-objective NSGA-II** (DEAP) — a Pareto front trading off
   *value vs. type-coverage vs. time* so a human can pick the trade-off.

Everything in `run.py` actually executes; the numbers in this README are the
genuine `output.txt` produced on this machine.

---

## Dataset & download

| | |
|---|---|
| **Corpus** | GovDocs1 — `zipfiles/000.zip` (1 of 1000 zips, ~1000 files each) |
| **Provider** | [Digital Corpora](https://digitalcorpora.org/corpora/file-corpora/files/) |
| **License** | Public / open access. GovDocs1 files were harvested from US government web servers (public-domain government documents); freely usable for research and teaching. |
| **Download size** | ~486 MB (zip), expands to ~726 MB / **981 files** |
| **Format** | Heterogeneous real-world files: `pdf, html, txt, doc, jpg, ppt, xls, gif, ps, xml, csv, swf, rtf, …` (22 distinct extensions) |

Download + unzip command (the subset-zip path 404s; the `zipfiles/NNN.zip`
path is the reliable one):

```bash
mkdir -p data
curl -s -L https://downloads.digitalcorpora.org/corpora/files/govdocs1/zipfiles/000.zip -o data/000.zip
unzip -q -o data/000.zip -d data/corpus
rm data/000.zip          # keep the repo lean; corpus stays under data/corpus/
```

> If the host is unreachable, an anonymous S3 listing can discover a live path:
> `aws s3 ls s3://digitalcorpora/corpora/files/govdocs1/zipfiles/ --no-sign-request`

---

## How to run (copy-paste)

```bash
cd examples/02-optimization-govdocs1

# 1. environment (system site-packages so numpy/pandas are inherited)
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --quiet ortools deap

# 2. data (see "Dataset & download" above)
mkdir -p data
curl -s -L https://downloads.digitalcorpora.org/corpora/files/govdocs1/zipfiles/000.zip -o data/000.zip
unzip -q -o data/000.zip -d data/corpus && rm data/000.zip

# 3. run the whole pipeline
python3 run.py | tee output.txt
```

Outputs: `items.csv` (per-file features) and `output.txt` (the run log).

---

## Workflow

```
download → featurize → baselines → knapsack → 2-examiner → NSGA-II Pareto
```

1. **download** — fetch & unzip `zipfiles/000.zip` into `data/corpus/`.
2. **featurize** — walk the corpus; per file compute `ext`, `size`,
   `cost_minutes`, `value_score`; write `items.csv`.
3. **baselines** — greedy (value/cost density), random (seed 42), and exact
   brute-force on a 15-item slice, all under a 960-min budget.
4. **knapsack** — OR-Tools `KnapsackSolver` finds the optimal single-examiner
   selection for 960 min; we assert it is ≥ greedy and sweep budgets to show
   where it strictly wins.
5. **2-examiner** — OR-Tools CP-SAT assigns files to two examiners (2 × 480 min)
   with each file going to at most one examiner.
6. **NSGA-II Pareto** — DEAP evolves a population of subsets to surface the
   value / type-coverage / time trade-off curve.

---

## Encoding

Each file becomes an **item**:

```
item = (id, ext, size_bytes, cost_minutes, value_score)
```

**Cost (examiner minutes)** — a fixed per-type setup plus a size-proportional term:

```
cost_minutes = base[ext] + 2 * size_MB
```

`base[ext]` is the `BASE_MINUTES` dict in `run.py` (e.g. `pdf=10, txt=4, gz=12`,
default 7). The `2 * size_MB` term models the linear effort of paging through
larger files.

**Value score** — a *transparent, additive* model (no hidden weights):

```
value_score = type_prior[ext]                 # a-priori interest of the type
            + 3*min(#emails,10) + 8*#IBAN + 12*#cards   # regex/keyword bonus
            + entropy_bonus                   # 0..2, peaks at ~5 bits/byte
```

* The **regex/keyword bonus** is computed by **actually reading the first 64 KiB**
  of each file and matching email / IBAN / credit-card regexes. Card matches are
  **Luhn-validated** so random digit runs don't inflate the score.
* The **entropy bonus** is byte-level Shannon entropy mapped to `0..2`, peaking
  near 5 bits/byte (text-ish, human-reviewable) and falling off for both
  near-zero-entropy padding and near-8 (already-compressed/encrypted) blobs.

### Honesty / leakage warning

The value model is a **disclosed heuristic prior**, *not* ground truth. Every
weight lives in plain sight in `run.py` and in this README. Two consequences to
teach:

* **No label leakage:** we never peek at a "is this evidence" label — there
  isn't one. The optimiser maximises a *stated proxy*; if the proxy is wrong,
  the plan is confidently wrong.
* **Keep weights disclosable:** in a real case the value function must be
  defensible in court. Hidden or tuned-to-the-answer weights would be
  challengeable. That's why nothing here is opaque.

---

## Algorithm & data structures

| Stage | Algorithm | Key data structures |
|---|---|---|
| Featurize | linear scan, regex, Luhn, Shannon entropy | `csv.DictWriter`, `collections.Counter` |
| Greedy | sort by value/cost **density** (fractional-knapsack heuristic) | Python list sort |
| Brute-force | exhaustive `2^15` subset enumeration → exact optimum | bitmask integer |
| **Knapsack** | OR-Tools `KnapsackSolver` (branch-and-bound, multidimensional) | integerised **NumPy-style value/weight vectors** |
| **2-examiner** | OR-Tools **CP-SAT** multiple-knapsack / assignment (`x[i,e]` booleans) | CP-SAT BoolVar matrix |
| **NSGA-II** | DEAP multi-objective GA (`selNSGA2`, uniform crossover, bit-flip mutation) | `creator.Individual` (bit list), `tools.ParetoFront`, NumPy masks |

* Values/weights are scaled by 1000 and rounded to integers for the
  integer-programming solvers.
* NSGA-II objectives use weights `(+1, +1, -1)` = (maximise value, maximise
  type-coverage, minimise minutes); over-budget individuals are penalised back
  into the feasible region.
* `heapq` is the natural priority-queue for streaming-greedy variants; here the
  greedy uses a one-shot sort, but a priority queue is the production pattern
  when items arrive online during acquisition.

---

## PLAN-PHASE PROMPT

> You are a digital-forensics triage planner. We have seized a drive whose files
> have been extracted to `data/corpus/`. An examiner has a **16-hour** review
> budget (960 minutes). Produce a **plan** (do not execute yet) to decide which
> files to review first so we maximise investigative value while respecting the
> budget.
>
> In your plan:
> 1. Define how you will estimate a **review cost in minutes** for each file
>    from its type and size, and state the per-type base costs you'll use.
> 2. Define a **transparent value score** combining a type prior, a
>    PII/keyword bonus (emails, IBANs, Luhn-valid card numbers found by sampling
>    bytes), and an entropy term. List every weight explicitly — it must be
>    court-defensible, so no hidden tuning.
> 3. Specify the **optimisation models**: a 0/1 knapsack for the single-examiner
>    budget, a multiple-knapsack/CP-SAT split for two examiners (2 × 480 min),
>    and a multi-objective NSGA-II for the value / type-coverage / time
>    trade-off.
> 4. Name **baselines** you will compare against (greedy density, random,
>    brute-force on a small slice) and the **acceptance check**
>    (optimiser ≥ greedy).
> 5. Flag the **risks**: the value model is a proxy, not ground truth; call out
>    where it could mis-prioritise.
>
> Output the plan as numbered steps with the data structures and libraries
> (OR-Tools, DEAP, NumPy) you intend to use.

## EXECUTE-PHASE PROMPT

> Execute the triage plan now. Walk `data/corpus/`, featurize every file into
> `items.csv` with columns `id, path, ext, size_bytes, cost_minutes, n_emails,
> n_iban, n_cards, entropy, value_score` using the disclosed cost and value
> formulas. Then, for a 960-minute budget: run greedy, random (seed 42), and a
> 15-item brute-force; run the OR-Tools 0/1 knapsack and assert its value ≥
> greedy, sweeping budgets {120,240,480,720,960} to show where it strictly wins;
> run the CP-SAT two-examiner split (2 × 480 min) and print per-examiner load and
> value; run DEAP NSGA-II and print a 5-point Pareto front of (value, types,
> minutes). Print counts and totals at each stage. Save the run to `output.txt`.
> Do not fabricate any numbers — report exactly what the code produces.

---

## Part 5 — Agent handling (ReAct)

**Analyst prompt to the agent:**

> Act as the triage analyst for this seizure. Prioritise the corpus under a
> 16-hour budget, then present a small set of trade-off options and **wait for a
> human examiner to choose** before committing to a review plan. Reason step by
> step, calling the available tools, and show your Thought / Action / Observation
> trace.
>
> Tools: `featurize(corpus_dir)`, `greedy(items,budget)`,
> `ortools_knapsack(items,budget)`, `cpsat_two_examiners(items,cap)`,
> `nsga2_pareto(items,budget)`.

**ReAct trace** (matches what `run.py` actually does):

```
Thought: I can't review 981 files in 16h. First quantify cost & value per file.
Action: featurize("data/corpus")
Observation: 981 files, 22 types, mean cost 8.35 min, total 8188 min (136.5 h);
             349 files have a PII hit. items.csv written.

Thought: Establish a cheap baseline before optimising.
Action: greedy(items, 960)
Observation: 90 files, 959.8 min, value 26954.5.

Thought: Greedy is only a heuristic — get the provable optimum and check it never loses.
Action: ortools_knapsack(items, 960)
Observation: 90 files, 959.8 min, value 26954.5 (>= greedy: PASS).
             Budget sweep: at 240 min knapsack 13788.8 > greedy 13758.5 (+30.2);
             at 480 min 18844.4 > 18804.4 (+40.0). The optimiser strictly wins
             at tighter budgets where greedy's density ordering is suboptimal.

Thought: We have two examiners; split the work fairly and optimally.
Action: cpsat_two_examiners(items, 480)
Observation: status OPTIMAL; examiner1 42 files/479.9 min/16134.0,
             examiner2 48 files/479.9 min/10820.6; total 26954.5.

Thought: Value isn't the only goal — coverage and time matter too. Surface trade-offs.
Action: nsga2_pareto(items, 960)
Observation: Pareto front of 121 points, e.g.
             (value 14963, types 18, 664 min), (12292, 21, 585 min),
             (6417, 15, 257 min).

Thought: These are genuine trade-offs (more coverage costs value/time). A human
         must decide. >>> HUMAN-IN-THE-LOOP GATE <<<
Action: present_pareto_options_and_halt()
Observation: [WAITING] Examiner selects, e.g. the (12292, 21 types, 585 min)
             point — broad coverage, leaving 6 h slack for deep dives.
```

**Human-in-the-loop gate:** the agent **does not auto-commit** to a plan. After
NSGA-II it presents the Pareto options and **halts**; a qualified examiner picks
the trade-off (max value? max type-coverage? leave slack?). The optimiser frames
the choice; the human owns the legal/operational decision.

**Failure mode:** the value model is a **proxy**. If a key piece of evidence is a
tiny image with no email/IBAN/card text (e.g. a scanned cheque, or a `.gz`
that's actually an encrypted archive scoring only on entropy), it gets a low
`value_score` and is deprioritised — the optimiser will *confidently* skip it.
Mitigation taught here: keep weights disclosed and auditable, always pair the
plan with random/spot-check sampling, and never treat "not selected" as "not
evidence".

---

## Verified output

Real `output.txt` from this machine (`python3 run.py`):

```
======================================================================
DF-AI 02 -- Triage Prioritisation Optimization (GovDocs1 / 000.zip)
======================================================================

[1] FEATURIZE
    files            : 981
    distinct types   : 22  -> {'pdf': 200, 'html': 181, 'txt': 154, 'doc': 111, 'jpg': 89, 'ppt': 88, 'xls': 62, 'gif': 23} ...
    mean cost (min)  : 8.35
    total cost (min) : 8188.3  (136.5 h to review ALL)
    files w/ PII hit : 349
    wrote items.csv  : .../items.csv

[2] BASELINES  (budget = 960 min = 16 h)
    greedy (value/cost):   90 files,   959.8 min, value = 26954.5
    random (seed=42)   :  112 files,   958.4 min, value = 4800.6
    brute-force slice  : 15 items, budget=106.4 min -> optimum value = 9938.7 (11 files); greedy-on-slice = 9896.5

[3] OR-TOOLS 0/1 KNAPSACK  (budget = 960 min)
    knapsack optimum   :   90 files,   959.8 min, value = 26954.5
    vs greedy value    : 26954.5  -> knapsack gains +0.0 (+0.00%)
    CHECK knapsack >= greedy : PASS
    budget sweep  greedy   knapsack    gain
       120 min    10549.1    10549.1     +0.0
       240 min    13758.5    13788.8    +30.2  <- knapsack WINS
       480 min    18804.4    18844.4    +40.0  <- knapsack WINS
       720 min    23278.9    23278.9     -0.0
       960 min    26954.5    26954.5     +0.0

[4] TWO-EXAMINER SPLIT  (2 x 480 min via CP-SAT)
    examiner 1:   42 files, load  479.9/480 min, value = 16134.0
    examiner 2:   48 files, load  479.9/480 min, value = 10820.6
    CP-SAT status=OPTIMAL, total value = 26954.5 (single-knapsack@960 was 26954.5)

[5] DEAP NSGA-II MULTI-OBJECTIVE  (max value, max types, min minutes)
    corpus has 22 distinct types; budget = 960 min
    Pareto front size = 121; sample (value, types, minutes):
        value=14963.4   types=18   minutes=  663.8
        value=13644.6   types=19   minutes=  545.4
        value=12291.7   types=21   minutes=  584.6
        value=10681.0   types=18   minutes=  379.2
        value= 6417.3   types=15   minutes=  257.1

======================================================================
DONE -- all stages executed on real GovDocs1 files.
======================================================================
```

**Interpretation.** Reviewing all 981 files would take ~136 hours; in a 16-hour
budget the optimiser picks ~90 files. Against the random baseline the gain is
enormous — value **26954.5 vs 4800.6** (~5.6×), the headline argument for
optimised triage. Greedy is a strong heuristic and even ties the knapsack at the
960-min budget, **but the brute-force slice (optimum 9938.7 vs greedy 9896.5) and
the budget sweep (knapsack +30.2 at 240 min and +40.0 at 480 min) prove the
provably-optimal knapsack strictly beats greedy when the budget is tight** — the
exact regime where prioritisation matters most. NSGA-II then shows there is no
single "best" plan: you can trade ~2700 value points to lift type-coverage from
18 to 21 types, a decision left to the human examiner.

---

## Notes / deviations

* **Dataset path:** the documented `subsets/subset0.zip` URL returns HTTP 404
  (`NoSuchKey`). The working path is
  `…/govdocs1/zipfiles/000.zip` (one of the 1000 per-1000-file zips), which is
  what this example uses. No fallback corpus was needed — the real GovDocs1
  download succeeded.
* **`python-magic`:** `import magic` fails on this machine (no libmagic binding),
  so file type is taken from the **extension** and size, exactly as the task
  allows. The byte-sampling step still reads real file content for the
  PII/entropy signals.
* **Knapsack vs greedy at 960 min:** because a handful of high-PII files
  dominate the value distribution, greedy's density ordering happens to reach the
  optimum at the full budget (gain +0.0). This is a genuine, instructive result;
  the budget sweep is included precisely so the strict optimiser win is visible
  and honest rather than hidden.
* **Corpus size:** `data/corpus/` is ~726 MB and is intended to be
  re-downloaded, not committed. The `.zip` is deleted after extraction.
