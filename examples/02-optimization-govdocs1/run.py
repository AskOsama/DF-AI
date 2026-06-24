#!/usr/bin/env python3
"""
DF-AI worked example 02 -- Optimization / triage-prioritisation pipeline.

Runs a REAL triage-prioritisation pipeline over the GovDocs1 corpus
(zipfiles/000.zip from Digital Corpora). The forensic framing: an examiner
has a limited time budget and many seized files; which files should be
reviewed first to maximise investigative value?

Stages:
  1. Featurize the corpus -> items.csv
  2. Baselines for a single 960-min (16h) budget: greedy, random, brute-force
  3. OR-Tools 0/1 knapsack for the 960-min budget
  4. Two-examiner split (2 x 480-min bins) via CP-SAT
  5. DEAP NSGA-II multi-objective Pareto front (value, type-coverage, time)

Everything below actually executes; no value is faked.
"""

import os
import re
import csv
import math
import random
import collections

import numpy as np

CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "corpus")
ITEMS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.csv")

# ---------------------------------------------------------------------------
# Encoding constants -- DISCLOSED, no hidden weights (honesty requirement).
# ---------------------------------------------------------------------------

# base[ext] = fixed examiner minutes to open/triage a file of this type,
# independent of size (tooling spin-up, manual look, etc.).
BASE_MINUTES = {
    "doc": 8, "docx": 8, "pdf": 10, "ppt": 7, "pptx": 7,
    "xls": 9, "xlsx": 9, "csv": 6, "txt": 4, "html": 5, "xml": 5,
    "rtf": 6, "log": 4, "jpg": 6, "gif": 5, "png": 5, "swf": 6,
    "ps": 8, "gz": 12, "wp": 8, "f": 4, "unk": 10, "dbase3": 9,
}
DEFAULT_BASE = 7  # unknown extension

# Type prior: how investigatively interesting a file type is a priori.
# (Documents/spreadsheets tend to carry PII & business records; media less so.)
TYPE_PRIOR = {
    "doc": 6, "docx": 6, "pdf": 7, "ppt": 4, "pptx": 4,
    "xls": 7, "xlsx": 7, "csv": 6, "txt": 5, "html": 4, "xml": 4,
    "rtf": 5, "log": 5, "jpg": 2, "gif": 1, "png": 2, "swf": 1,
    "ps": 3, "gz": 3, "wp": 4, "f": 3, "unk": 3, "dbase3": 6,
}
DEFAULT_PRIOR = 3

# Keyword / regex bonuses found by actually reading a sample of bytes.
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# IBAN: 2 letters, 2 digits, then 11-30 alphanumerics.
IBAN_RE = re.compile(rb"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b")
# Candidate card numbers: 13-16 digits in groups; validated with Luhn below.
CARD_RE = re.compile(rb"\b(?:\d[ -]?){13,16}\b")

SAMPLE_BYTES = 65536  # read first 64 KiB of each file for pattern scan
BUDGET_TOTAL = 960    # single-examiner budget, minutes (16h)
BUDGET_EACH = 480     # per-examiner budget for the 2-examiner split


def luhn_ok(digits: str) -> bool:
    """Luhn checksum -- keeps card detection honest (avoids random-digit noise)."""
    if not (13 <= len(digits) <= 16):
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def shannon_entropy(buf: bytes) -> float:
    """Byte-level Shannon entropy in bits/byte (0..8). High = compressed/encrypted."""
    if not buf:
        return 0.0
    counts = collections.Counter(buf)
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def featurize():
    """Walk corpus, compute cost + transparent value_score, write items.csv."""
    items = []
    for root, _dirs, files in os.walk(CORPUS_DIR):
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else "noext"
            size_mb = size / (1024 * 1024)

            base = BASE_MINUTES.get(ext, DEFAULT_BASE)
            cost_minutes = round(base + 2 * size_mb, 3)

            # Read a sample of bytes for the regex/keyword + entropy signals.
            try:
                with open(path, "rb") as fh:
                    buf = fh.read(SAMPLE_BYTES)
            except OSError:
                buf = b""

            n_emails = len(set(EMAIL_RE.findall(buf)))
            n_iban = len(IBAN_RE.findall(buf))
            cards = [m.group(0) for m in CARD_RE.finditer(buf)]
            n_cards = sum(1 for c in cards if luhn_ok(re.sub(rb"[ -]", b"", c).decode("latin-1")))

            entropy = shannon_entropy(buf)

            # --- DISCLOSED value model (all weights visible above & here) ---
            prior = TYPE_PRIOR.get(ext, DEFAULT_PRIOR)
            keyword_bonus = 3 * min(n_emails, 10) + 8 * n_iban + 12 * n_cards
            # Mild entropy bonus: text-ish files (~4-6 bits) most reviewable;
            # cap so giant compressed blobs don't dominate.
            entropy_bonus = round(2 * max(0.0, 1 - abs(entropy - 5.0) / 5.0), 3)

            value_score = round(prior + keyword_bonus + entropy_bonus, 3)

            items.append({
                "id": len(items),
                "path": os.path.relpath(path, os.path.dirname(ITEMS_CSV)),
                "ext": ext,
                "size_bytes": size,
                "cost_minutes": cost_minutes,
                "n_emails": n_emails,
                "n_iban": n_iban,
                "n_cards": n_cards,
                "entropy": round(entropy, 3),
                "value_score": value_score,
            })

    with open(ITEMS_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(items[0].keys()))
        w.writeheader()
        w.writerows(items)

    return items


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def greedy(items, budget):
    """Greedy by value/cost density (classic fractional-knapsack heuristic)."""
    order = sorted(items, key=lambda it: it["value_score"] / max(it["cost_minutes"], 1e-9),
                   reverse=True)
    chosen, spent, value = [], 0.0, 0.0
    for it in order:
        if spent + it["cost_minutes"] <= budget:
            chosen.append(it)
            spent += it["cost_minutes"]
            value += it["value_score"]
    return chosen, spent, value


def random_baseline(items, budget, seed=42):
    rng = random.Random(seed)
    order = items[:]
    rng.shuffle(order)
    chosen, spent, value = [], 0.0, 0.0
    for it in order:
        if spent + it["cost_minutes"] <= budget:
            chosen.append(it)
            spent += it["cost_minutes"]
            value += it["value_score"]
    return chosen, spent, value


def brute_force(slice_items, budget):
    """Exact optimum over a small slice by enumerating all 2^n subsets."""
    n = len(slice_items)
    best_val, best_mask = 0.0, 0
    for mask in range(1 << n):
        spent = val = 0.0
        for i in range(n):
            if mask & (1 << i):
                spent += slice_items[i]["cost_minutes"]
                val += slice_items[i]["value_score"]
        if spent <= budget and val > best_val:
            best_val, best_mask = val, mask
    return best_val, best_mask


# ---------------------------------------------------------------------------
# OR-Tools 0/1 knapsack (integer values & weights)
# ---------------------------------------------------------------------------

def ortools_knapsack(items, budget):
    from ortools.algorithms.python import knapsack_solver

    SCALE = 1000  # integerise the (fractional) values and weights
    values = [int(round(it["value_score"] * SCALE)) for it in items]
    weights = [[int(round(it["cost_minutes"] * SCALE)) for it in items]]
    capacities = [int(round(budget * SCALE))]

    solver = knapsack_solver.KnapsackSolver(
        knapsack_solver.SolverType.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
        "TriageKnapsack",
    )
    solver.init(values, weights, capacities)
    solver.solve()

    chosen = [items[i] for i in range(len(items)) if solver.best_solution_contains(i)]
    spent = sum(it["cost_minutes"] for it in chosen)
    value = sum(it["value_score"] for it in chosen)
    return chosen, spent, value


# ---------------------------------------------------------------------------
# Two-examiner split via CP-SAT (a multiple-knapsack / assignment model)
# ---------------------------------------------------------------------------

def cpsat_two_examiners(items, cap_each, time_limit_s=20.0):
    from ortools.sat.python import cp_model

    SCALE = 1000
    vals = [int(round(it["value_score"] * SCALE)) for it in items]
    costs = [int(round(it["cost_minutes"] * SCALE)) for it in items]
    cap = int(round(cap_each * SCALE))
    n, m = len(items), 2

    model = cp_model.CpModel()
    x = {(i, e): model.NewBoolVar(f"x_{i}_{e}") for i in range(n) for e in range(m)}
    for i in range(n):
        model.Add(sum(x[i, e] for e in range(m)) <= 1)  # each file to <=1 examiner
    for e in range(m):
        model.Add(sum(costs[i] * x[i, e] for i in range(n)) <= cap)  # per-examiner budget
    model.Maximize(sum(vals[i] * x[i, e] for i in range(n) for e in range(m)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    per = []
    for e in range(m):
        idx = [i for i in range(n) if solver.Value(x[i, e]) == 1]
        load = sum(items[i]["cost_minutes"] for i in idx)
        value = sum(items[i]["value_score"] for i in idx)
        per.append((len(idx), load, value))
    return per, solver.StatusName(status), solver.ObjectiveValue() / SCALE


# ---------------------------------------------------------------------------
# DEAP NSGA-II: maximise value, maximise type-coverage, minimise time
# ---------------------------------------------------------------------------

def nsga2_pareto(items, budget, n_gen=40, pop_size=120, seed=7):
    from deap import base, creator, tools, algorithms

    random.seed(seed)
    np.random.seed(seed)

    vals = np.array([it["value_score"] for it in items], dtype=float)
    costs = np.array([it["cost_minutes"] for it in items], dtype=float)
    exts = [it["ext"] for it in items]
    ext_index = {e: i for i, e in enumerate(sorted(set(exts)))}
    ext_id = np.array([ext_index[e] for e in exts])
    n_types = len(ext_index)
    n = len(items)

    # Objectives: (+value, +types_covered, -minutes)
    if hasattr(creator, "FitnessTriage"):
        del creator.FitnessTriage
    if hasattr(creator, "IndividualTriage"):
        del creator.IndividualTriage
    creator.create("FitnessTriage", base.Fitness, weights=(1.0, 1.0, -1.0))
    creator.create("IndividualTriage", list, fitness=creator.FitnessTriage)

    tb = base.Toolbox()
    # Sparse init: ~10% of files selected, keeps individuals inside budget-ish.
    tb.register("attr_bit", lambda: 1 if random.random() < 0.10 else 0)
    tb.register("individual", tools.initRepeat, creator.IndividualTriage, tb.attr_bit, n)
    tb.register("population", tools.initRepeat, list, tb.individual)

    def evaluate(ind):
        sel = np.fromiter(ind, dtype=bool, count=n)
        minutes = float(costs[sel].sum())
        if minutes > budget:  # penalise overspend (push to feasible region)
            return (0.0, 0.0, minutes + 1e6)
        value = float(vals[sel].sum())
        types = int(len(np.unique(ext_id[sel]))) if sel.any() else 0
        return (value, float(types), minutes)

    tb.register("evaluate", evaluate)
    tb.register("mate", tools.cxUniform, indpb=0.5)
    tb.register("mutate", tools.mutFlipBit, indpb=1.0 / n)
    tb.register("select", tools.selNSGA2)

    pop = tb.population(n=pop_size)
    hof = tools.ParetoFront()

    fits = map(tb.evaluate, pop)
    for ind, fit in zip(pop, fits):
        ind.fitness.values = fit
    pop = tb.select(pop, len(pop))

    for _ in range(n_gen):
        offspring = algorithms.varAnd(pop, tb, cxpb=0.7, mutpb=0.3)
        fits = map(tb.evaluate, offspring)
        for ind, fit in zip(offspring, fits):
            ind.fitness.values = fit
        pop = tb.select(pop + offspring, pop_size)
        hof.update(pop)

    # Feasible Pareto solutions only, sorted by value desc.
    front = [ind.fitness.values for ind in hof if ind.fitness.values[2] <= budget]
    front = sorted(set(front), key=lambda f: f[0], reverse=True)
    return front, n_types


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("DF-AI 02 -- Triage Prioritisation Optimization (GovDocs1 / 000.zip)")
    print("=" * 70)

    # --- Stage 1: featurize ---
    print("\n[1] FEATURIZE")
    items = featurize()
    n = len(items)
    exts = collections.Counter(it["ext"] for it in items)
    mean_cost = sum(it["cost_minutes"] for it in items) / n
    total_cost = sum(it["cost_minutes"] for it in items)
    pii_hits = sum(1 for it in items if it["n_emails"] or it["n_iban"] or it["n_cards"])
    print(f"    files            : {n}")
    print(f"    distinct types   : {len(exts)}  -> {dict(exts.most_common(8))} ...")
    print(f"    mean cost (min)  : {mean_cost:.2f}")
    print(f"    total cost (min) : {total_cost:.1f}  ({total_cost/60:.1f} h to review ALL)")
    print(f"    files w/ PII hit : {pii_hits}")
    print(f"    wrote items.csv  : {ITEMS_CSV}")

    # --- Stage 2: baselines (single 960-min budget) ---
    print(f"\n[2] BASELINES  (budget = {BUDGET_TOTAL} min = 16 h)")
    g_chosen, g_spent, g_val = greedy(items, BUDGET_TOTAL)
    r_chosen, r_spent, r_val = random_baseline(items, BUDGET_TOTAL)
    print(f"    greedy (value/cost): {len(g_chosen):4d} files, "
          f"{g_spent:7.1f} min, value = {g_val:.1f}")
    print(f"    random (seed=42)   : {len(r_chosen):4d} files, "
          f"{r_spent:7.1f} min, value = {r_val:.1f}")

    # brute force on a small 15-item slice (top-value 15) with a small budget
    slice_items = sorted(items, key=lambda it: it["value_score"], reverse=True)[:15]
    bf_budget = sum(it["cost_minutes"] for it in slice_items) / 2  # tight, forces choice
    bf_val, bf_mask = brute_force(slice_items, bf_budget)
    bf_count = bin(bf_mask).count("1")
    g_slice = greedy(slice_items, bf_budget)
    print(f"    brute-force slice  : 15 items, budget={bf_budget:.1f} min -> "
          f"optimum value = {bf_val:.1f} ({bf_count} files); "
          f"greedy-on-slice = {g_slice[2]:.1f}")

    # --- Stage 3: OR-Tools knapsack ---
    print(f"\n[3] OR-TOOLS 0/1 KNAPSACK  (budget = {BUDGET_TOTAL} min)")
    k_chosen, k_spent, k_val = ortools_knapsack(items, BUDGET_TOTAL)
    print(f"    knapsack optimum   : {len(k_chosen):4d} files, "
          f"{k_spent:7.1f} min, value = {k_val:.1f}")
    print(f"    vs greedy value    : {g_val:.1f}  -> "
          f"knapsack gains +{k_val - g_val:.1f} ({100*(k_val-g_val)/g_val:+.2f}%)")
    assert k_val >= g_val - 1e-6, "knapsack must be >= greedy"
    print("    CHECK knapsack >= greedy : PASS")
    # Sweep: where DOES the optimiser beat greedy? (greedy is only a heuristic)
    print("    budget sweep  greedy   knapsack    gain")
    for b in (120, 240, 480, 720, BUDGET_TOTAL):
        gv = greedy(items, b)[2]
        kv = ortools_knapsack(items, b)[2]
        flag = "  <- knapsack WINS" if kv > gv + 1e-6 else ""
        print(f"      {b:4d} min  {gv:9.1f}  {kv:9.1f}  {kv-gv:+7.1f}{flag}")

    # --- Stage 4: two-examiner split ---
    print(f"\n[4] TWO-EXAMINER SPLIT  (2 x {BUDGET_EACH} min via CP-SAT)")
    per, status, obj = cpsat_two_examiners(items, BUDGET_EACH)
    for e, (cnt, load, val) in enumerate(per):
        print(f"    examiner {e+1}: {cnt:4d} files, load {load:6.1f}/{BUDGET_EACH} min, "
              f"value = {val:.1f}")
    tot_val = sum(p[2] for p in per)
    print(f"    CP-SAT status={status}, total value = {tot_val:.1f} "
          f"(single-knapsack@960 was {k_val:.1f})")

    # --- Stage 5: NSGA-II Pareto front ---
    print(f"\n[5] DEAP NSGA-II MULTI-OBJECTIVE  (max value, max types, min minutes)")
    front, n_types = nsga2_pareto(items, BUDGET_TOTAL)
    print(f"    corpus has {n_types} distinct types; budget = {BUDGET_TOTAL} min")
    print(f"    Pareto front size = {len(front)}; sample (value, types, minutes):")
    # spread 5 points across the front
    if front:
        picks = [front[int(round(i * (len(front) - 1) / 4))] for i in range(5)]
        for v, t, m in dict.fromkeys(picks):
            print(f"        value={v:7.1f}   types={int(t):2d}   minutes={m:7.1f}")

    print("\n" + "=" * 70)
    print("DONE -- all stages executed on real GovDocs1 files.")
    print("=" * 70)


if __name__ == "__main__":
    main()
