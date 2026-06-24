# DF-AI — Runnable Worked Examples

Five end-to-end, **actually executed** pipelines — one per Part 4 technique — each over a
real, open-access digital-forensics dataset. Every folder contains:

- **`run.py`** — the script that was run (copy-paste reproducible).
- **`output.txt`** — the *real* captured output from running it (no fabricated numbers).
- **`README.md`** — full classroom documentation: Overview · Dataset & download · How to
  run · Workflow · Encoding · Algorithm & data structures · **Plan-phase prompt** ·
  **Execute-phase prompt** · **Part 5 — agent handling (ReAct)** · Verified output ·
  Notes/deviations.

Each example pairs with its Part 4 sub-page (`modules/part4-*.html`) and the Part 5
"Five prompts on real data" section (`modules/part5.html#worked-prompts`).

## The five examples

| # | Technique | Dataset (real, open-access) | What the verified run showed |
|---|-----------|------------------------------|------------------------------|
| [01](01-csp-geolife/) | Constraint satisfaction | **GeoLife GPS** (Microsoft) — real 1,116-point trajectory | Alibi **INFEASIBLE** + UNSAT core (CCTV vs phone log, 66.7 km in one 10-min slot); re-timed CCTV → **FEASIBLE** timeline. OR-Tools CP-SAT. |
| [02](02-optimization-govdocs1/) | Optimization | **GovDocs1** (Digital Corpora) — 981 real carved files | Optimised triage ≈ **5.6× random**; provably-optimal knapsack strictly beats greedy at tight budgets; **121-point NSGA-II Pareto** front. |
| [03](03-knowledge-openflights/) | Knowledge & reasoning | **OpenFlights** — 66,934 real routes | No direct LHR→BOG; reachable in **1 stop via Atlanta (Delta)**; auditable GOAL/RULE/FACT chain; pyDatalog ↔ networkx cross-check passed. |
| [04](04-feature-engineering-ember/) | Feature engineering | **EMBER-style** on 60 real Windows PEs + 60 synthetic packed | LightGBM **acc 0.92 / AUC 0.97**; top drivers = section/byte entropy; **leakage trap demo**: a leaky feature inflates accuracy +0.058 to a perfect 1.0. |
| [05](05-search-enron/) | Search engines | **Enron emails** (CMU) — 80,000 messages indexed | BM25 inverted index (145k terms) built in ~4 s; real ranked hits (Kaminski "LJM/Raptor valuations"); refinement + Fastow sender-filter. |

## Published on the course site

Each example is also published as a styled **Part 5 "verified run" results page**, framing the
outcome as the agent's loop (Approach → Action → Observation → Done) with the real output:

- 01 → [`modules/part5-csp-geolife.html`](../modules/part5-csp-geolife.html)
- 02 → [`modules/part5-optimization-govdocs1.html`](../modules/part5-optimization-govdocs1.html)
- 03 → [`modules/part5-knowledge-openflights.html`](../modules/part5-knowledge-openflights.html)
- 04 → [`modules/part5-feature-engineering-ember.html`](../modules/part5-feature-engineering-ember.html)
- 05 → [`modules/part5-search-enron.html`](../modules/part5-search-enron.html)

They are linked from the Part 5 "Five prompts on real data" section
(`modules/part5.html#worked-prompts`).

## Quick start (any example)

```bash
cd examples/01-csp-geolife          # or any 0N-… folder
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r <see that folder's README "How to run">
# download the dataset per the folder's "Dataset & download" section, then:
python3 run.py | tee output.txt
```

## Notes

- **Datasets and virtualenvs are not committed** (they are multi-GB) — they are excluded
  via the repo `.gitignore`. Each folder's README has the exact download command to
  recreate `data/`.
- A few examples document honest **deviations** (e.g. the GovDocs1 download path, the
  Fastow/Causey mailboxes being absent from the public Enron release, EMBER's full
  multi-GB benchmark being substituted by a safe local feature-engineering demo). These
  are written up in each folder's "Notes / deviations" — read them before teaching.
- Every metric in every `output.txt` is a genuine result of running `run.py`.
