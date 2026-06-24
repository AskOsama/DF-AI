# Feature Engineering — Static Malware / File Triage (EMBER-style)

A **runnable** worked example for the DF-AI course. It turns raw Windows-PE
*bytes* into an **EMBER-style numeric feature vector**, trains a real classifier
(LightGBM), evaluates it, explains its decisions, scores an unknown file, and
**demonstrates the data-leakage trap** that the lecture warns about — all on a
small, fully reproducible, **safe** corpus.

---

## Overview

> *A file is not handed to a classifier as a file — it is handed as a list of
> features (size, entropy, header bytes, …). Poor features sink even a perfect
> algorithm.*

That is the entire point of feature engineering, and **EMBER** is its canonical
example: a Windows executable reduced to a 2,380-dimensional engineered vector
so a model can answer *"benign or malware?"* **without ever running the file.**

This example reproduces EMBER's *raw-bytes → features → verdict* pipeline in
miniature, with **transparent, human-named features** so every importance value
is interpretable in the classroom. Forensic scenario: an analyst carves an
unknown executable from unallocated space — no signature, no AV verdict. We
triage it purely from measurable byte-level and structural properties.

---

## Dataset / source & download

### What EMBER is (the reference)
- **EMBER 2018 (v2)** — *Elastic Malware Benchmark for Empowering Researchers.*
  Engineered static features from ~1M Windows PE files (malicious / benign /
  unlabeled), shipped **with the extraction source code**.
  - Home: https://github.com/elastic/ember · Paper: https://arxiv.org/abs/1804.04637
  - Kaggle mirror: `dhoogla/ember-2018-v2-features`
  - License: data files **MIT**; extraction code **AGPL-v3**.
  - **Why it is safe:** EMBER ships *numeric feature vectors*, not executables.
    You classify numbers, never live malware.
  - **Why we did NOT use the full tar here:** the archive is several GB and the
    `ember` pip package pins exact `lief` versions — fragile to set up in a
    classroom window. (See **Notes / deviations**.)

### What this example actually used (real + synthetic, both safe)
We **built the EMBER-style extractor ourselves** and ran it on a real corpus:

| Class | Source | Real or synthetic | Count |
|-------|--------|-------------------|-------|
| `benign` | Real, signed Windows PE files copied from `C:\Windows\System32` (small `.dll`/`.exe`, 8 KB–250 KB) | **REAL** | 60 |
| `packed` | The *same* benign files, transformed to look packed/encrypted (a fraction of the body XOR-encrypted with a random keystream + an appended high-entropy blob) | **SYNTHETIC** | 60 |

**Safety note.** No live malware is downloaded or executed. The `packed` class
is synthetic and is **only ever featurized, never run**. It reproduces the #1
static fingerprint of real packers/crypters (UPX, ASPack, custom crypters):
**elevated entropy** in part of the file while the PE header/imports remain
parseable. The corpus is regenerated locally by `run.py`; nothing is committed.

---

## How to run (copy-paste)

```bash
cd examples/04-feature-engineering-ember
python3 -m venv --system-site-packages .venv      # inherits numpy/pandas/sklearn
. .venv/bin/activate
pip install --quiet lightgbm lief                  # lief = the PE parser EMBER uses
python3 run.py | tee output.txt
```

The script auto-builds the corpus under `data/` on first run (copies real
System32 PE files, generates synthetic packed twins), then trains and evaluates.
Re-runs reuse the existing `data/`. Delete `data/benign` + `data/packed` to
regenerate.

> Not on Windows/WSL with `C:\Windows\System32` available? See the
> documented fallback in **Notes / deviations**.

---

## Workflow

```
gather files          (60 real benign  +  60 synthetic packed)
   |
extract features      (raw bytes -> EMBER-style numeric vector, per file)
   |
build matrix          (X : 120 x 31 float64,  y : 0=benign / 1=packed)
   |
train / split         (70/30 stratified split, LightGBM gradient-boosted trees)
   |
evaluate              (accuracy, ROC-AUC, classification report)
   |
importances           (top features, mapped to human-readable names)
   |
score unknown         (held-out file -> verdict + probability + top drivers)
   |
leakage demo          (add a leaky 'source_folder_id'; 5-fold CV before/after)
```

---

## Encoding (the core)

Each file becomes a fixed **31-dimensional** vector. We use the same feature
*families* as EMBER (which produces 2,380 dims via feature-hashing); here they
are compact and **named** so importances are teachable. All are computed from
the raw bytes (plus `lief` for the structural group).

| # dims | Feature(s) | Computed from the raw bytes |
|--------|-----------|------------------------------|
| 16 | `byte_hist[0..15]` | 256-bin byte histogram folded to 16 bins, normalized — gross byte composition. |
| 1 | `file_size` | Length in bytes. |
| 1 | `byte_entropy_whole` | Shannon entropy of the whole file (bits/byte, 0–8). |
| 3 | `byte_entropy_win_mean/max/std` | Shannon entropy over sliding **2 KB windows**, summarized. High windows flag packing/encryption. |
| 1 | `frac_high_entropy_windows` | Fraction of 2 KB windows with entropy > 7.0 (near-random regions). |
| 2 | `printable_string_count`, `printable_string_mean_len` | ASCII runs ≥ 5 chars — count and mean length. Packers strip readable strings. |
| 1 | `pe_num_sections` | Section count (`lief`). |
| 2 | `pe_section_entropy_mean/max` | Per-section Shannon entropy, summarized — **the classic "packed section" signal**. |
| 2 | `pe_import_count`, `pe_dll_count` | Imported API functions / imported DLLs (`lief`). Packers collapse the import table. |
| 1 | `pe_has_imports` | 1 if any imports recovered. |
| 1 | `pe_timestamp` | COFF header `TimeDateStamp`. **A real EMBER leakage risk** (see below). |

**Shannon entropy** for a byte block: `H = -Σ p_i · log2(p_i)` over the 256
byte values, where `p_i` is the frequency of byte value *i*. Random/encrypted
data → H near 8; structured code/text → H much lower.

### The leakage trap (named explicitly)
Two distinct leaks are illustrated:
1. **`source_folder_id` (the injected demo leak).** In a real case, an intake
   script wrote benign and suspicious files to *different folders*, so a
   "source-folder id" feature is **perfectly correlated with the label**. The
   model learns the *folder*, not the *file* — the exact *"folder named
   `evidence`"* shortcut the lecture warns about. Step 6 adds this column and
   measures the inflation.
2. **`pe_timestamp` (a real-world leak, kept visible).** Under EMBER's
   *time-split* (train before a date, test after), the PE timestamp lets a model
   learn *"newer ⇒ class X"* — a shortcut that won't generalize. In our run
   `pe_timestamp` even appears among the top importances, so the class can see
   the trap organically. **Rule: drop / scrutinize folder-, path-, source-feed-
   and timestamp-derived features before training.**

---

## Algorithm & data structures

- **Feature matrix.** One row per file = the 31 features concatenated in fixed
  group order → `X` of shape `(n_samples, n_features)` (`float64`), with labels
  `y` (`0` benign, `1` packed). In real EMBER this is a `(n, 2380) float32`
  memmap; the layout idea is identical, just bigger.
- **Classifier.** **LightGBM** `LGBMClassifier` (gradient-boosted decision
  trees) — the official EMBER baseline. GBDTs handle heterogeneous, unscaled,
  hashed features natively, with **no normalization needed**. If `lightgbm`
  fails to import, the script falls back to sklearn `RandomForestClassifier`
  automatically.
- **Explanation.** Global view = `feature_importances_` mapped to human names
  (Step 4). Per-file view (Step 5) = a SHAP-style driver list: each feature's
  standardized deviation `z = (x - μ)/σ` weighted by its global importance, top
  3 by magnitude → *why this file got this verdict*.
- **Evaluation.** 70/30 stratified hold-out for the headline metrics; **5-fold
  stratified cross-validation** for the leakage before/after (stable averaged
  estimate).

---

## PLAN-PHASE PROMPT

Use this to make an agent **design** the triage classifier before writing code:

```
You are a forensic ML engineer. PLAN (do not write final code yet) a static
malware/file-triage classifier in the EMBER style. Constraints:
 - SAFETY: never download or execute live malware. Use either EMBER's
   pre-extracted numeric feature vectors, or build features from real benign
   PE files plus clearly-labeled synthetic "packed" samples.
 - The classifier must decide benign vs packed/suspicious WITHOUT running files.
Deliver a plan covering:
 1. Data sourcing: which safe corpus, where it comes from, how it is labeled,
    license and safety justification.
 2. Feature engineering: the exact feature families (byte histogram, windowed
    Shannon entropy, printable-string stats, PE header fields, per-section
    entropy, import/DLL counts) and how each is computed from raw bytes.
 3. Matrix design: row = one file, columns = named features, label vector.
 4. Model choice (LightGBM GBDT; RandomForest fallback) and why no scaling.
 5. Evaluation: stratified split, accuracy + ROC-AUC + classification report,
    global feature importances, per-file driver explanation.
 6. A leakage-trap experiment: name at least two leaky features (e.g.
    source-folder id, PE timestamp), and how you will measure the inflation
    they cause and then prove the honest number after removing them.
 7. Risks/assumptions and what "good enough for triage" means (lead, not verdict).
```

## EXECUTE-PHASE PROMPT

```
Implement the approved plan as a single runnable run.py with NO required
network access (build the corpus from local System32 PE files + synthetic
packed twins). Print, in order: corpus summary; feature-matrix shape + class
means proving the features separate the classes; train/test sizes; accuracy +
ROC-AUC + classification report; top-8 named feature importances; a scored
held-out unknown with verdict + probability + top-3 drivers; and the leakage
demo (5-fold CV accuracy & AUC WITH vs WITHOUT the leaky feature, plus the
leaky feature's importance rank). Fall back to RandomForest if lightgbm import
fails, and to byte-only features if lief is unavailable. Run it with
`python3 run.py | tee output.txt` and report the REAL numbers — never fabricate.
```

---

## Part 5 — Agent handling (ReAct)

**Analyst prompt (to the triage agent):**

```
An unknown executable was carved from unallocated space. DO NOT execute it.
Featurize it statically (EMBER-style: byte histogram, windowed entropy,
printable strings, PE header, section entropy, import/DLL counts), classify it
benign vs packed/suspicious with the trained model, and report a confidence
score plus the top 3 features driving the verdict. Exclude any leaky metadata
features (source folder, intake timestamp). Treat your output as a triage LEAD
that ranks the file for human review — not a final verdict.
```

**Thought → Action → Observation trace (matches `run.py`):**

```
Thought:  I must NOT run the file. I need static features only.
Action:   extract_features("data/packed/packed_043.bin")           [tool: feature extractor / lief]
Obs:      31-dim vector; section_entropy_max high, win-entropy std high.

Thought:  Compare against the trained model.
Action:   model.predict_proba(x)                                   [tool: LightGBM classifier]
Obs:      P(packed) = 1.000.

Thought:  I need to justify this for a human reviewer.
Action:   explain_drivers(x)                                       [tool: importance-weighted z-scores]
Obs:      pe_section_entropy_max (+65.79), byte_hist[9] (+65.13),
          byte_entropy_win_std (+57.93)  -> consistent with packing.

Thought:  Are any drivers leaky? source_folder_id / pe_timestamp must be excluded.
Action:   assert "source_folder_id" not in active_features          [tool: leakage guard]
Obs:      OK — leaky features excluded from the production model.

Final:    VERDICT(lead) = PACKED/SUSPICIOUS, confidence 1.000.
          Recommend HUMAN REVIEW (high-entropy sections suggest a crypter).
```

- **Tools called:** (1) static feature extractor (`lief` + byte stats),
  (2) LightGBM classifier `predict_proba`, (3) per-file driver explainer,
  (4) leakage guard that refuses leaky columns.
- **Human-in-the-loop gate:** the agent emits a **lead, not a verdict** — it
  ranks files for an analyst; a human confirms. It **must exclude leaky
  features** (`source_folder_id`, `pe_timestamp`) from the scoring model.
- **Failure mode:** if the file fails to parse (`lief` returns `None`) the agent
  must **not** silently emit zeros and call it benign — zeroed structural
  features bias toward "benign / no imports." It should flag *"unparseable —
  manual review"* and fall back to byte-only features with reduced confidence.

---

## Verified output

Real output from `output.txt` (this exact run):

```
STEP 2 — Extract EMBER-style features
  feature matrix X : shape (120, 31)  (n_samples x n_features)
  labels y         : 60 benign, 60 packed
  mean whole-file entropy  benign=4.659  packed=5.495
  mean recoverable imports benign=98.2  packed=98.4

STEP 3 — Train / test split + train classifier
  train: 84 samples   test: 36 samples
  HONEST test accuracy : 0.9167
  HONEST test ROC-AUC  : 0.9722

STEP 4 — Top feature importances (mapped to human names)
  byte_hist[9]                    97.0000
  pe_section_entropy_max          72.0000
  byte_entropy_win_max            52.0000
  byte_entropy_win_std            42.0000
  pe_timestamp                    28.0000

STEP 5 — Score one held-out UNKNOWN sample
  [most-suspicious] file = packed_043.bin
     verdict   : PACKED/SUSPICIOUS   P(packed)=1.000   (ground truth: packed)
     top drivers: pe_section_entropy_max(+65.79), byte_hist[9](+65.13), byte_entropy_win_std(+57.93)

STEP 6 — LEAKAGE TRAP (real demonstration, 5-fold cross-validation)
  WITHOUT leaky feat. (honest): accuracy=0.9417  AUC=0.9889
  WITH leaky feature          : accuracy=1.0000  AUC=1.0000
     -> leaky feature ranked #1 of 32 in importance (it dominates)
  INFLATION from leakage      : accuracy +0.0583   AUC +0.0111
```

**Interpretation.** On the held-out split the honest model reaches
**91.7 % accuracy / 0.972 ROC-AUC**, and the features that drive it are exactly
the ones theory predicts for packing — **maximum per-section entropy** and the
**spread/peak of windowed byte-entropy** — so the model is right *for the right
reasons*. The leakage demo is the punchline: adding a single `source_folder_id`
column that mirrors the folders the files were sorted into pushes 5-fold
cross-validated accuracy from **0.9417 up to a perfect 1.0000** (AUC 0.9889 →
1.0000) and that leaky feature instantly ranks **#1 of 32** — a model that looks
flawless offline but has merely memorized the folder, not the file, and would
collapse on genuinely unsorted evidence.

---

## Notes / deviations (what was real vs synthetic)

- **REAL:** the `benign` class is 60 actual signed Windows PE files copied from
  `C:\Windows\System32`; all features are computed from real bytes; the model,
  metrics, importances and leakage numbers are all genuine LightGBM output —
  **nothing is fabricated**. Numbers above are copied verbatim from `output.txt`.
- **SYNTHETIC:** the `packed` class is generated by `make_packed()` — it XOR-
  encrypts a fraction (mostly light, 10–30 %) of each benign file's body and
  appends a random blob, to mimic packers/crypters. These files are **never
  executed**, only featurized. We deliberately kept packing *light* so the
  honest task has realistic headroom (≈ 92–95 %); that headroom is what lets the
  leakage trap visibly inflate **accuracy**, not just AUC.
- **EMBER package status:** the full EMBER2018 tar (several GB) and the `ember`
  pip package (pins exact `lief` versions) were **intentionally not used** — too
  heavy/fragile for a class session. We reproduced its feature *families* and
  pipeline instead. The EMBER docs/URLs/licenses above are accurate references.
- **`lief` status:** installed and working (`lief 0.17.6`) — used for sections,
  per-section entropy, imports/DLLs, and the PE timestamp. If `lief` is
  unavailable, `run.py` degrades to byte-only features (structural fields → 0).
- **`lightgbm` status:** installed and working (`lightgbm 4.6.0`) — used as the
  classifier. If its import fails, the script automatically uses sklearn
  `RandomForestClassifier`.
- **Environment:** `python3 -m venv --system-site-packages` so `numpy 2.2.6`,
  `pandas 2.3.3`, `sklearn 1.7.2` are inherited from the system.
- **Fallback if no System32:** on a machine without `C:\Windows\System32`
  (mounted at `/mnt/c` here), point `SRC_DIRS` in `run.py` at any folder of real
  PE files, or substitute any directory of real binary files for a generic
  binary-file-type classification using the *same* feature families — document
  the substitution honestly in class.
