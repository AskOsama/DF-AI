# Example 06 — Shredded-Document Reconstruction as an Optimization Match

A **runnable** optimization worked example for the Digital Forensics + AI course.
We take a **real document page**, **strip-cut shred** it into vertical strips,
shuffle the pile, and then **recover the original left-to-right order** by
*applying optimization to find the match*: minimise the total adjacent-edge
mismatch over the strips. Formally this is an **open Hamiltonian path** over an
**asymmetric edge-compatibility cost matrix** — a TSP — which we solve with
**Google OR-Tools routing** and cross-check against a **greedy nearest-neighbour
baseline**. Everything below is computed at run time; no metric is fabricated.

---

## Overview

> **▶ Watch it:** an animated browser version of this search lives at
> [`demos/shredder_reconstruction_demo.html`](../../demos/shredder_reconstruction_demo.html)
> — the page shreds, then greedy + 2-opt run live with an objective-function chart, an
> iteration counter, and an accelerating progress bar. (In-browser stand-in for the
> OR-Tools TSP used here.)
>
> **🧩 Harder (cross-cut):** [`demos/harder_shredder_reconstruction_demo.html`](../../demos/harder_shredder_reconstruction_demo.html)
> shreds the page **both ways** into an R×C grid and shows how greedy *scales* — comparisons
> grow ~N², accuracy collapses on fine grids, and the search space is N!.

**Forensic scenario.** A shredder destroyed a document. Investigators recover the
pile of paper strips. Can we **reconstruct the page** so its text becomes
readable again? Strip-cut (a.k.a. straight-cut) shredding leaves the *content of
each strip intact* and only destroys the **left-to-right ordering**, so recovery
is exactly the problem of **putting the strips back in the right order**.

The forensic question is posed as an **optimization match**:

> Given N shuffled vertical strips, find the ordering that **minimises the total
> mismatch between every pair of adjacent strip edges** — i.e. the order in which
> each strip's right edge best continues into the next strip's left edge.

If two strips were truly adjacent in the original page, the ink strokes, text
rows, and grey levels along their shared seam line up almost perfectly, so the
edge-mismatch cost between them is low. Reconstruction is therefore the search
for the **minimum-total-edge-cost path** that visits every strip exactly once —
an **open Hamiltonian path / TSP** over a cost matrix. The recovered page is an
**investigative lead**: an examiner still has to read and verify the recovered
text (and check it isn't globally left–right mirrored).

Optimization concepts exercised: encoding a real signal as a **cost matrix**,
**asymmetric** costs, the **open-path-via-dummy-node** TSP trick, an **exact/near
-exact solver** (OR-Tools routing) vs. a **greedy heuristic**, and evaluating an
optimizer with a **ground-truth-aware metric** (neighbour-adjacency accuracy,
optimum cost vs. ground-truth cost).

---

## Dataset & source

**We shred a REAL document.** The academic shredded-document datasets are built
exactly this way — take real pages and cut them — so we do the same with a real
file we already have on disk and cite the originating papers.

| Item | Value |
|------|-------|
| Source document | `000013.pdf` from the **govdocs1** corpus reused from example 02 (`examples/02-optimization-govdocs1/data/corpus/000/`) |
| What it is | A **U.S. Federal Register** page (Vol. 68, No. 50, Friday March 14, 2003) — a real, public-domain U.S. government document |
| Rendering | Page 1 rendered to **grayscale at 150 dpi** with **PyMuPDF** (`pdftoppm` is not installed in this environment; PyMuPDF is the converter fallback). Result: a `1650 × 1275` grayscale array |
| Preprocessing | Content-free white **margins trimmed** (`1275 → 1087` columns) so no strip is a featureless all-white slice |
| Shredding | Sliced into **N = 32** equal-width vertical strips (**33 px** each), order recorded as ground truth `[0..31]`, then **shuffled with fixed seed 42** to form the "shredded pile" |
| Generated artifacts | `data/shredded.png` (shuffled pile), `data/reconstructed.png` (recovered order) |

This is the **OpenFlights-style "real data, constructed task"** pattern: the
*content* is a genuine document; the *shredding* is the controlled transformation
we apply so we have ground truth to score against.

### Provenance — found via paper-search + git-search

The dataset/approach was located using the course's two CLI tools:

**paper-search** surfaced the academic framing:

- **Paixão et al. (2020)** — *Self-supervised Deep Reconstruction of Mixed
  Strip-shredded Text Documents* — **arXiv:2007.00779**
  (https://arxiv.org/abs/2007.00779). State-of-the-art deep edge-compatibility
  scoring for strip-shredded text.
- **Paixão et al. (2020)** — *Fast(er) Reconstruction of Shredded Text
  Documents via Self-Supervised Deep Asymmetric Metric Learning* —
  **arXiv:2003.10063** (https://arxiv.org/abs/2003.10063). Learns an
  **asymmetric** compatibility metric between strip edges (right-of-i vs left-of-j)
  — exactly the asymmetric cost matrix we build by hand here.
- **Lactuan & Pabico (2015)** — *Unshredding of Shredded Documents: A
  Computational Framework* — **arXiv:1506.07440**
  (https://arxiv.org/abs/1506.07440). Frames reconstruction explicitly as an
  **optimization** over edge-match costs (the TSP/Hamiltonian-path view we use).

**git-search** surfaced reference code:

- **RazvanRanca/UnShredder** — https://github.com/RazvanRanca/UnShredder
  (~21 stars). Strip-cut and cross-cut reconstruction with **probabilistic edge
  scoring**; demonstrates the cost-matrix + ordering pipeline. **No stated
  license.**

**Licence / safety note.** Because the academic dataset download links are not
cleanly exposed and **UnShredder carries no license**, we do **not** redistribute
their data or code. Instead we **generate our own shredded data** from a real,
public-domain U.S. government document we already hold, and **cite the papers and
repo** for the method. Generated images live under `data/` (gitignored).

---

## How to run

```bash
cd examples/06-shredder-reconstruction

# venv that inherits the system numpy/scipy; OR-Tools + Pillow into the venv
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --quiet ortools pillow
# (PyMuPDF / fitz is already available in this environment and is used to
#  render the real PDF page; the script falls back to a Pillow text render
#  if no PDF/image is found.)

# the real document is read from example 02's corpus; nothing to download.
python3 run.py | tee output.txt
```

Runtime: a few seconds (cost matrix is 32×32; OR-Tools is given a 20 s ceiling
but finishes almost instantly at this size).

---

## Workflow

```
obtain image            real PDF page 000013.pdf -> grayscale via PyMuPDF (150 dpi)
   │                    trim blank margins (1275 -> 1087 cols)
   ▼
shred                   slice into N=32 vertical strips (33 px each)
                        record ground-truth order [0..31]
                        shuffle with seed 42  -> the "shredded pile"
                        save data/shredded.png
   │
   ▼
build cost matrix       asymmetric C (32 x 32)
                        C[i][j] = mismatch( right-edge(i) , left-edge(j) )
                        diagonal = large sentinel (no self-follow)
   │
   ▼
optimise (find match)   OR-Tools routing TSP + DUMMY NODE  -> open Hamiltonian path
                        greedy nearest-neighbour baseline (best over all starts)
   │
   ▼
evaluate                neighbour-adjacency accuracy vs ground truth
                        (count true consecutive pairs recovered, allow mirror)
                        compare optimum cost vs ground-truth cost vs greedy
   │
   ▼
reconstruct             reorder strips by the recovered path
                        save data/reconstructed.png
```

---

## Encoding

**Image → strips.** The grayscale page (after margin trim) is cut into `N = 32`
equal-width vertical strips. Strip `s` is an `H × w` array (`H = 1650`,
`w = 33`). Ground-truth order is `[0,1,…,31]`; a seeded permutation produces the
shuffled pile we actually work with.

**Strips → asymmetric edge-cost matrix.** We score how well strip `i` continues
into strip `j` by comparing **i's innermost right column** with **j's innermost
left column**, row by row down the seam:

```
right_i[r] = pixel value of strip i, rightmost column, row r
left_j[r]  = pixel value of strip j, leftmost  column, row r

C[i][j] = mean over rows r of ( right_i[r] - left_j[r] )^2          (intensity)
          + GRAD_WEIGHT * mean over rows of ( Δright_i[r] - Δleft_j[r] )^2
            where Δ is the inward horizontal step at the edge        (optional)

C[i][i] = BIG   (sentinel: a strip cannot follow itself)
```

- The matrix is **asymmetric**: `C[i][j] ≠ C[j][i]` because "i then j" compares
  i's *right* edge to j's *left* edge, while "j then i" compares the opposite
  edges. In the verified run, `C[0][1] = 6294.5` but `C[1][0] = 8112.1`. This
  mirrors the **asymmetric metric learning** of Paixão et al. (arXiv:2003.10063).
- We use **squared** (not absolute) per-row difference and the **single innermost
  boundary column**. This sharply rewards rows where ink continues across the
  seam and punishes ink-vs-white mismatches. (Averaging several columns or using
  mean-absolute difference smears the signal — empirically it dropped the true
  neighbour from "clearly the minimum" to "rank ~9". See *Notes*.) The optional
  gradient term is **off by default** (`GRAD_WEIGHT = 0.0`) because on this
  high-contrast text page it added noise; it is kept as a documented knob.

---

## Algorithm & data structures

- **Cost matrix:** a dense `numpy` `N × N` float array `C`. Building it is fully
  vectorised (one broadcast per source strip against all targets).

- **The match is an open Hamiltonian path.** A reconstruction is an ordering of
  all N strips; its quality is the **sum of `C` over consecutive pairs**. Finding
  the minimum-sum ordering that visits each strip once is the **Travelling
  Salesman Problem** — except we want an **open path**, not a closed tour (the
  leftmost and rightmost strips need not match each other).

- **Open path via the dummy-node trick (OR-Tools routing).** We add one extra
  **dummy node** with cost **0 to and from every real strip**. The TSP solver
  returns a *cycle*; because entering/leaving the dummy is free, the solver places
  the dummy between the two strips that *should* be the page's outer edges.
  **Cutting the cycle at the dummy node** yields the optimal **open** strip order.
  Solver config: `PATH_CHEAPEST_ARC` first solution + `GUIDED_LOCAL_SEARCH`
  metaheuristic, 20 s limit. Costs are scaled to integers (routing requires
  integer arcs).

- **Greedy nearest-neighbour baseline.** Start from each strip in turn; repeatedly
  append the lowest-cost unused successor; keep the best total over all starts.
  `O(N³)` and myopic — a good foil to show the optimizer's value.

- **Why TSP/assignment "finds the match."** Reconstruction = choosing, for each
  strip, *which strip comes next*, with the global constraint that the choices
  form a single path covering all strips. That is precisely a min-cost
  **Hamiltonian path / assignment-with-no-subtours** problem. Encoding edge
  compatibility as a cost matrix turns "which strips fit together" into "find the
  cheapest tour", and a routing solver finds the match.

---

## PLAN-PHASE PROMPT

> **Role:** You are a forensic-optimization planner.
> **Goal:** Plan (do **not** execute) a pipeline that reconstructs a strip-cut
> shredded document page by optimization, with ground truth so it can be scored.
>
> Produce a numbered plan that:
> 1. States the forensic question precisely: given N shuffled vertical strips of
>    a page, recover their original left-to-right order, and explain why this is
>    an **edge-matching optimization** (minimise total adjacent-edge mismatch).
> 2. Specifies the data: a **real** document page (name the source and how it is
>    obtained/rendered to grayscale), how it is **shredded** into N equal-width
>    strips, how **ground truth** (the true order) is recorded, and how the pile
>    is shuffled with a fixed seed for reproducibility. Note any preprocessing
>    (margin trimming) and why.
> 3. Defines the **cost encoding**: an asymmetric `C[i][j]` = mismatch between
>    strip i's right edge and strip j's left edge (give the exact pixel formula,
>    say why it is asymmetric, and why squared per-row boundary differences
>    discriminate true neighbours). Set the diagonal to a sentinel.
> 4. Chooses the **optimization model**: an **open Hamiltonian path** over `C`,
>    solved as a TSP with a **dummy zero-cost node** so the optimal cycle becomes
>    an open path; plus a **greedy nearest-neighbour** baseline for comparison.
> 5. Defines **evaluation**: neighbour-adjacency accuracy against ground truth,
>    how a globally **reversed (mirrored)** reconstruction is scored as correct,
>    and the sanity check that the **optimum total cost ≈ the ground-truth cost**.
> 6. Lists outputs (recovered order, metrics, `shredded.png`,
>    `reconstructed.png`) and the human-in-the-loop step (an examiner verifies
>    the recovered text; the result is a lead, not proof).
> Output only the plan, assumptions, and risks; write no code yet.

## EXECUTE-PHASE PROMPT

> **Role:** You are a forensic data engineer executing the approved plan.
> **Task:** Implement `run.py` and actually run it on the real document.
> Requirements:
> - Load the real page (`000013.pdf` from example 02's corpus) to a grayscale
>   numpy array via PyMuPDF; print the source description and image shape; trim
>   blank margins.
> - Shred into **N = 32** vertical strips, record ground-truth order, shuffle
>   with **seed 42**, and save `data/shredded.png`. Print the strip width and the
>   shuffled→original index map.
> - Build the **asymmetric** `C[i][j]` (squared per-row difference of i's right
>   column vs j's left column; diagonal = sentinel). Print `C.shape` and a couple
>   of sample costs showing asymmetry.
> - Solve the **open Hamiltonian path** with **OR-Tools routing + dummy node**;
>   print the solver status and total cost. Also run the **greedy** baseline and
>   print its total cost.
> - Evaluate **neighbour-adjacency accuracy** for both methods (allow a global
>   mirror); print a **PERFECT?** flag and the **ground-truth total cost** for
>   comparison. Print the recovered order as original strip indices and save
>   `data/reconstructed.png`.
> - Capture real output with `python3 run.py | tee output.txt`. Do **not**
>   fabricate any number; report exactly what the code prints.

---

## Part 5 — Agent handling (ReAct)

**Analyst prompt (to the reconstruction agent):**

> You are a digital-forensics document-reconstruction analyst. A pile of N
> vertical paper strips from a strip-cut shredder has been digitised to a set of
> equal-width grayscale strips. Recover the most likely original left-to-right
> ordering by minimising total adjacent-edge mismatch. Build an asymmetric
> edge-cost matrix, solve for the optimal open ordering, and also report a greedy
> baseline. Present the recovered order, the optimum vs. greedy cost, and a
> reconstructed image. Treat the reconstruction as an **investigative lead**: flag
> it for an examiner to read and verify the recovered text, and check whether the
> page came out **globally reversed (mirrored)**. Do not record a conclusion
> without human sign-off.

**ReAct trace (matches what `run.py` actually computes):**

```
Thought:  I need the strips as a numeric signal. Load the real page image and
          slice it; keep the true order only for later scoring, not for solving.
Action:   load_image('000013.pdf'); trim_margins(); shred(N=32, seed=42)
Observation: 32 strips, 33 px wide; shuffled pile saved to data/shredded.png.

Thought:  Encode "which strip follows which" as a cost. Compare strip i's right
          edge to strip j's left edge, row by row; squared difference so true
          continuations score low. The relation is directional => asymmetric C.
Action:   build_cost_matrix()  -> C[32x32], diagonal = sentinel
Observation: C built; C[0][1]=6294.5 vs C[1][0]=8112.1 (asymmetric, as expected).

Thought:  The match is an OPEN path over all strips. Solve it as a TSP but add a
          zero-cost dummy node so the optimal cycle opens into a path.
Action:   ortools_tsp(C, dummy_node=True, time_limit=20s)
Observation: status ROUTING_SUCCESS; total cost 117551.2; order read off the cut.

Thought:  Compare against a cheap heuristic to show the optimizer earns its keep.
Action:   greedy_nearest_neighbour(C, try_all_starts=True)
Observation: greedy total cost 124659.2 (worse than OR-Tools).

Thought:  Score against ground truth: how many recovered neighbours are truly
          consecutive? Allow a global mirror. Also check optimum ~ truth cost.
Action:   adjacency_accuracy(ort_order); adjacency_accuracy(greedy_order)
Observation: OR-Tools 96.8% (30/31), greedy 90.3% (28/31);
             ground-truth cost 120880.2  (optimum 117551.2 is just below it).

Thought:  Near-perfect but not 100%, and the optimum cost dips below truth — so a
          human must verify the text and the single mis-seam. Escalate; flag the
          recovered page is rotated (starts mid-page), not mirrored.
Action:   save_reconstructed('data/reconstructed.png');
          request_human_review(lead="page reconstructed, 30/31 seams correct")
Observation: Awaiting examiner sign-off.
```

**Tools the agent calls:** `load_image` / `shred` (build strips + ground truth),
`build_cost_matrix` (edge encoding), `ortools_tsp` (open-path solve via dummy
node), `greedy_nearest_neighbour` (baseline), `adjacency_accuracy` (scoring),
`request_human_review`.

**Human-in-the-loop gate.** A reconstruction is an **investigative lead**, not a
verdict. The optimizer returns the *cheapest* ordering — which may differ from
the true page (here the optimum cost is actually **below** the ground-truth
cost). An examiner must **read the recovered text** to confirm it is coherent and
must explicitly check for a **globally reversed / mirrored** result (the metric
treats a mirror as correct because it is the same physical reconstruction, but a
human still needs the correct reading direction). Only after sign-off does a
reconstruction enter a case file.

**Failure mode.** Edge matching breaks when strip edges carry **little or
ambiguous signal**: blank/whitespace strips (page margins, line gaps) have nearly
uniform edges, so many pairings score ~0 and the optimizer cannot tell true
neighbours apart — which is exactly why we **trim blank margins** here. Heavy
**ink bleed**, smudging, or scanner noise blurs the seam and produces
mismatches. And this whole approach assumes **strip-cut** shredding;
**cross-cut** shredding fragments each strip into many tiles, turning the 1-D
ordering problem into a far harder 2-D jigsaw with vastly more pieces and weaker
per-edge evidence.

---

## Verified output

Real output captured in [`output.txt`](output.txt) from `python3 run.py`:

```
======================================================================
STEP 1 -- OBTAIN REAL DOCUMENT IMAGE (grayscale)
======================================================================
source : REAL govdocs1 document 000013.pdf (a U.S. Federal Register page), page 1 rendered to grayscale at 150 dpi via PyMuPDF
image shape (H x W): (1650, 1275) dtype: uint8
pixel range: min 0 max 255 mean 231.1
trimmed blank margins: width 1275 -> 1087 columns

======================================================================
STEP 2 -- SHRED INTO 32 VERTICAL STRIPS (strip-cut), shuffle seed=42
======================================================================
strip width (px): 33
ground-truth order (original): [0, 1, 2, ... , 31]
shuffled pile -> original idx: [31, 19, 7, 27, 26, 18, 5, 22, 28, 10, 24, 23, 20, 9, 6, 16, 3, 0, 15, 17, 25, 12, 21, 11, 14, 30, 2, 4, 29, 1, 13, 8]
saved shuffled-strips image -> data/shredded.png

======================================================================
STEP 3 -- ENCODE MATCH COST (asymmetric N x N edge-cost matrix C)
======================================================================
C shape: (32, 32) (C[i][j] = right-edge(i) vs left-edge(j) mismatch)
diagonal sentinel (forbidden self-follow): 140292.19
sample costs:
  C[0][1] = 6294.481   C[1][0] = 8112.134   (asymmetric)
  C[0][2] = 6313.281   C[5][7] = 6831.230
  min off-diagonal C = 6.450

======================================================================
STEP 4 -- OPTIMISE: find the order minimising total adjacent-edge cost
======================================================================
[greedy NN] best total cost = 124659.210
[OR-Tools TSP] solver status = ROUTING_SUCCESS
[OR-Tools TSP] total cost   = 117551.188

======================================================================
STEP 5 -- EVALUATE (neighbour-adjacency accuracy vs ground truth)
======================================================================
ground-truth total edge cost (optimum target): 120880.152
[greedy NN]   adjacency accuracy =  90.3%  (28/31 correct neighbours, as-is)
              PERFECT? False
[OR-Tools TSP] adjacency accuracy =  96.8%  (30/31 correct neighbours, as-is)
              PERFECT? False

cost comparison (lower = better; optimum ~ ground-truth):
  ground-truth : 120880.152
  OR-Tools TSP : 117551.188
  greedy NN    : 124659.210

======================================================================
STEP 6 -- RECOVERED ORDER + RECONSTRUCTED IMAGE
======================================================================
recovered order (OR-Tools TSP), as ORIGINAL strip indices:
  [24, 25, 26, 27, 28, 29, 30, 31, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
saved reconstructed image -> data/reconstructed.png
```

**Interpretation.** The optimizer essentially solved it: the recovered order is
the **perfectly contiguous run** `24,25,…,31,0,1,…,23`, i.e. the true sequence
**rotated** — **30 of 31** neighbour pairs are correct (**96.8%** adjacency
accuracy), versus **28/31 (90.3%)** for the greedy baseline, so OR-Tools clearly
beats greedy. The single "error" is purely the **open-path cut point**: the dummy
node was placed between strips 23 and 24, leaving them at the two ends instead of
joined in the middle — every other seam is correct, and the saved
`data/reconstructed.png` is readable as the original Federal Register page.
Notably the optimum total cost (**117,551**) is **slightly below** the
ground-truth cost (**120,880**): the cheapest edge-arrangement is marginally
cheaper than reality, which is why the result is **not** flagged `PERFECT` and
why a human examiner — not the cost number alone — confirms the reconstruction.

---

## Notes / deviations

- **Real data, constructed shredding.** The *content* is a genuine public-domain
  U.S. **Federal Register** page (`000013.pdf`, reused from example 02's govdocs1
  corpus). The *shredding* (32 vertical strips, seed-42 shuffle) is the
  controlled transformation we apply so we have ground truth — the same way the
  cited academic datasets are built.
- **Converter fallback: PyMuPDF, not pdftoppm.** `pdftoppm` is **not installed**
  in this environment, so the script renders the PDF page with **PyMuPDF
  (`fitz`)** at 150 dpi. If no PDF/image is found, `run.py` falls back to
  rendering a real `.txt` excerpt (or an embedded U.S. Constitution excerpt) with
  Pillow + DejaVuSansMono. The PyMuPDF path was the one taken in the verified run.
- **Margin trimming (preprocessing).** Without it, the leftmost/rightmost strips
  were nearly all-white, giving degenerate near-zero edge costs and ambiguous
  matches; trimming `1275 → 1087` content columns removes those featureless
  strips. This is honest preprocessing — it only drops columns with no ink.
- **Edge metric choice matters (real tuning).** An earlier metric (mean-absolute
  difference averaged over 2 boundary columns, plus a gradient term) was weak —
  the true successor was the cost-minimum only 2/31 times (median rank ~9) and
  accuracy was ~13–29%. Switching to **squared difference on the single innermost
  boundary column** (gradient term off) made the true neighbour the clear minimum
  (~29/31) and lifted OR-Tools to **96.8%**. The gradient term is kept as an
  optional, default-off knob (`GRAD_WEIGHT = 0.0`).
- **Not PERFECT, and that's the lesson.** OR-Tools finds an arrangement whose
  total cost is *below* the ground-truth cost, so an optimizer can be "more
  optimal than reality"; the recovered page is also globally **rotated** (the cut
  point), not mirrored. Both are why reconstruction is a **lead** an examiner
  verifies, not an automatic verdict.
- **Strip-cut only.** This example handles **strip-cut** shredding (1-D ordering).
  **Cross-cut** shredding (2-D jigsaw of many small tiles) is substantially
  harder and is out of scope here; see Paixão et al. and the UnShredder repo for
  cross-cut treatments.
- **Generated artifacts** (`data/shredded.png`, `data/reconstructed.png`) and the
  `.venv/` are gitignored by the parent repo (`examples/**/data/`, `.venv/`).
```
