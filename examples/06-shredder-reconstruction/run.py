#!/usr/bin/env python3
"""
Example 06 -- Shredded-document reconstruction as an OPTIMIZATION match.

A real document page is sliced into N vertical strips (strip-cut shredding) and
shuffled. We recover the original left-to-right order by MINIMISING total
adjacent-edge mismatch -- an OPEN Hamiltonian path over an asymmetric NxN
edge-compatibility cost matrix C (a TSP, solved with Google OR-Tools routing via
the dummy-node trick). A greedy nearest-neighbour reconstruction is run as a
baseline. We then score neighbour-adjacency accuracy against ground truth.

NO numbers are fabricated -- everything printed is computed at run time.
"""

import os
import sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
N_STRIPS = 32          # number of vertical strips (strip-cut shredding)
MIN_STRIP_PX = 6       # if a strip would be narrower than this, reduce N
SHUFFLE_SEED = 42      # fixed seed -> the "shredded pile" is reproducible
EDGE_COLS = 1          # compare the single innermost boundary column of each edge
GRAD_WEIGHT = 0.0      # optional weight on a horizontal-gradient term (0 = off)
RENDER_DPI = 150       # DPI used when rendering a PDF page

# Candidate REAL document on disk (govdocs1 corpus reused from example 02).
CORPUS = os.path.join(
    HERE, "..", "02-optimization-govdocs1", "data", "corpus", "000"
)
PREFERRED_PDF = "000013.pdf"   # a dense Federal Register page (real gov doc)

SEP = "=" * 70


def banner(title):
    print(SEP)
    print(title)
    print(SEP)


# ----------------------------------------------------------------------
# STEP 1 -- obtain the document image as a grayscale numpy array
# ----------------------------------------------------------------------
def load_document_image():
    """
    Return (gray_uint8_2d_array, source_description).

    Priority:
      1. Render page 1 of a real PDF from example 02's corpus via PyMuPDF.
      2. Load a real image file (jpg/gif/png) from the corpus.
      3. Render a real .txt excerpt from the corpus with Pillow + DejaVu font.
      4. Render an embedded public-domain excerpt with Pillow (last resort).
    """
    # --- (1) real PDF rendered with PyMuPDF (pdftoppm is not installed here) ---
    pdf_path = os.path.join(CORPUS, PREFERRED_PDF)
    if os.path.isfile(pdf_path):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            page = doc[0]
            m = fitz.Matrix(RENDER_DPI / 72.0, RENDER_DPI / 72.0)
            pix = page.get_pixmap(matrix=m, colorspace=fitz.csGRAY)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width
            ).copy()
            doc.close()
            desc = (
                f"REAL govdocs1 document {PREFERRED_PDF} (a U.S. Federal "
                f"Register page), page 1 rendered to grayscale at "
                f"{RENDER_DPI} dpi via PyMuPDF"
            )
            return arr, desc
        except Exception as e:  # pragma: no cover - fallback path
            print(f"[warn] PyMuPDF render of {PREFERRED_PDF} failed: {e}")

    # --- (2) real image file from the corpus ---
    try:
        import glob
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.gif"):
            hits = sorted(glob.glob(os.path.join(CORPUS, ext)))
            if hits:
                img = Image.open(hits[0]).convert("L")
                arr = np.asarray(img, dtype=np.uint8)
                return arr, f"REAL govdocs1 image {os.path.basename(hits[0])} (grayscale)"
    except Exception as e:  # pragma: no cover
        print(f"[warn] corpus image load failed: {e}")

    # --- (3) render a real .txt excerpt from the corpus ---
    try:
        import glob
        txts = sorted(glob.glob(os.path.join(CORPUS, "*.txt")))
        if txts:
            with open(txts[0], "r", errors="replace") as fh:
                text = fh.read()[:1800]
            arr = _render_text(text)
            return arr, (
                f"REAL govdocs1 text file {os.path.basename(txts[0])} "
                f"rendered to a page image with Pillow + DejaVuSansMono"
            )
    except Exception as e:  # pragma: no cover
        print(f"[warn] corpus text render failed: {e}")

    # --- (4) embedded public-domain excerpt (U.S. Constitution Preamble) ---
    text = (
        "We the People of the United States, in Order to form a more "
        "perfect Union, establish Justice, insure domestic Tranquility, "
        "provide for the common defence, promote the general Welfare, and "
        "secure the Blessings of Liberty to ourselves and our Posterity, "
        "do ordain and establish this Constitution for the United States "
        "of America."
    ) * 4
    arr = _render_text(text)
    return arr, "Public-domain excerpt (U.S. Constitution Preamble) rendered with Pillow"


def _render_text(text):
    """Render text to a grayscale page image (Pillow fallback renderers)."""
    from PIL import ImageDraw, ImageFont
    import textwrap

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    try:
        font = ImageFont.truetype(font_path, 18)
    except Exception:
        font = ImageFont.load_default()

    W, H = 1000, 1300
    img = Image.new("L", (W, H), color=255)
    draw = ImageDraw.Draw(img)
    y, lh = 30, 26
    for para in text.split("\n"):
        for line in textwrap.wrap(para, width=78) or [""]:
            draw.text((30, y), line, fill=0, font=font)
            y += lh
            if y > H - lh:
                break
        if y > H - lh:
            break
    return np.asarray(img, dtype=np.uint8)


# ----------------------------------------------------------------------
# STEP 2 -- SHRED: slice into N vertical strips, shuffle with a fixed seed
# ----------------------------------------------------------------------
def trim_blank_margins(gray, thresh=5):
    """
    Crop uniform (near-white) left/right border columns.

    Real pages have wide blank margins; a strip cut entirely inside a margin is
    uniformly white, so its left/right edges are indistinguishable -> the
    cost matrix has degenerate near-zero entries and the match is ambiguous.
    Trimming the margins is a standard preprocessing step and makes the strips
    information-bearing. (We keep this honest: it only removes content-free
    columns; see Notes in the README.)
    """
    colstd = gray.std(axis=0)
    ink = np.where(colstd > thresh)[0]
    if ink.size == 0:
        return gray
    lo, hi = int(ink.min()), int(ink.max()) + 1
    return gray[:, lo:hi]


def shred(gray, n_strips, seed):
    """
    Slice `gray` into n_strips equal-width vertical strips.

    Returns:
      strips        : list of 2D arrays in SHUFFLED ("shredded pile") order
      shuffled_order: the true original index of each pile strip
                      (strips[k] is original strip shuffled_order[k])
    """
    h, w = gray.shape
    strip_w = w // n_strips
    # Crop to an exact multiple of strip_w so every strip is identical width.
    usable = strip_w * n_strips
    g = gray[:, :usable]

    originals = [g[:, i * strip_w:(i + 1) * strip_w] for i in range(n_strips)]

    rng = np.random.default_rng(seed)
    shuffled_order = [int(x) for x in rng.permutation(n_strips)]
    strips = [originals[i] for i in shuffled_order]
    return strips, shuffled_order, strip_w


def save_strip_montage(strips, path, gap=2):
    """Save strips left-to-right (in their current list order) as one image."""
    h = strips[0].shape[0]
    w = sum(s.shape[1] for s in strips) + gap * (len(strips) - 1)
    canvas = np.full((h, w), 255, dtype=np.uint8)
    x = 0
    for i, s in enumerate(strips):
        canvas[:, x:x + s.shape[1]] = s
        x += s.shape[1] + gap
    Image.fromarray(canvas, mode="L").save(path)


# ----------------------------------------------------------------------
# STEP 3 -- ENCODE THE MATCH COST: asymmetric edge-compatibility matrix
# ----------------------------------------------------------------------
def build_cost_matrix(strips, edge_cols=EDGE_COLS, grad_weight=GRAD_WEIGHT):
    """
    C[i][j] = dissimilarity of strip i's RIGHT edge vs strip j's LEFT edge,
    measured row-by-row down the seam (one value per pixel row, then averaged).

    Term 1 (intensity): mean SQUARED difference between strip i's innermost
            right column and strip j's innermost left column, over all rows.
            Squared (not absolute) difference sharply rewards rows where ink
            continues across the seam and penalises ink-vs-white mismatches;
            this is what makes the true neighbour the clear minimum.
    Term 2 (gradient, optional, off by default): mean squared difference of the
            inward horizontal step across the seam -- compares (i's last col -
            i's 2nd-last) with (j's first col - j's 2nd) -- rewards continuous
            stroke slope. Enabled by grad_weight>0.

    Diagonal set to a large sentinel (a strip cannot follow itself).
    """
    n = len(strips)
    # innermost boundary columns (averaged if edge_cols>1)
    right = np.stack([s[:, -edge_cols:].astype(float).mean(axis=1) for s in strips])  # n x H
    left = np.stack([s[:, :edge_cols].astype(float).mean(axis=1) for s in strips])    # n x H
    # inward horizontal gradient at each edge
    right_grad = np.stack([(s[:, -1].astype(float) - s[:, -2].astype(float)) for s in strips])
    left_grad = np.stack([(s[:, 1].astype(float) - s[:, 0].astype(float)) for s in strips])

    C = np.zeros((n, n), dtype=float)
    for i in range(n):
        d_int = ((right[i][None, :] - left) ** 2).mean(axis=1)        # vs all j
        if grad_weight:
            d_grad = ((right_grad[i][None, :] - left_grad) ** 2).mean(axis=1)
            C[i] = d_int + grad_weight * d_grad
        else:
            C[i] = d_int
    big = C.max() * 10.0 + 1.0
    np.fill_diagonal(C, big)
    return C, big


# ----------------------------------------------------------------------
# STEP 4a -- greedy nearest-neighbour baseline
# ----------------------------------------------------------------------
def greedy_path(C):
    """Best open path found by trying every start node, greedily appending the
    lowest-cost unused successor. Returns (order, total_cost)."""
    n = C.shape[0]
    best_order, best_cost = None, float("inf")
    for start in range(n):
        used = [False] * n
        used[start] = True
        order = [start]
        cost = 0.0
        cur = start
        for _ in range(n - 1):
            nxt, ncost = -1, float("inf")
            for j in range(n):
                if not used[j] and C[cur][j] < ncost:
                    ncost, nxt = C[cur][j], j
            order.append(nxt)
            used[nxt] = True
            cost += ncost
            cur = nxt
        if cost < best_cost:
            best_cost, best_order = cost, order
    return best_order, best_cost


# ----------------------------------------------------------------------
# STEP 4b -- OR-Tools routing (TSP) with a dummy node => OPEN Hamiltonian path
# ----------------------------------------------------------------------
def ortools_path(C, big):
    """
    Solve the OPEN min-cost Hamiltonian path with OR-Tools routing.

    Trick: add a dummy node `n` with cost 0 to/from every real node. The TSP
    then returns a CYCLE; cutting it at the dummy node yields the optimal open
    path over the real nodes. Returns (order, total_cost, status_name).
    """
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    n = C.shape[0]
    dummy = n
    size = n + 1
    SCALE = 10  # integer cost units (routing needs ints; costs are already large)

    # integer cost matrix with dummy row/col = 0
    M = np.zeros((size, size), dtype=np.int64)
    M[:n, :n] = np.rint(C * SCALE).astype(np.int64)
    for i in range(n):
        M[i, i] = int(round(big * SCALE))  # keep diagonal forbidden

    manager = pywrapcp.RoutingIndexManager(size, 1, dummy)
    routing = pywrapcp.RoutingModel(manager)

    def cost_cb(from_index, to_index):
        a = manager.IndexToNode(from_index)
        b = manager.IndexToNode(to_index)
        return int(M[a][b])

    transit = routing.RegisterTransitCallback(cost_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(20)

    solution = routing.SolveWithParameters(params)
    status_map = {
        0: "ROUTING_NOT_SOLVED",
        1: "ROUTING_SUCCESS",
        2: "ROUTING_FAIL",
        3: "ROUTING_FAIL_TIMEOUT",
        4: "ROUTING_INVALID",
    }
    status = status_map.get(routing.status(), f"STATUS_{routing.status()}")
    if solution is None:
        return None, None, status

    # walk the cycle starting at dummy; collect real nodes in order
    index = routing.Start(0)
    cycle = []
    while not routing.IsEnd(index):
        cycle.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    # cycle begins at dummy node -> the real-node order is the tail
    order = [nd for nd in cycle if nd != dummy]

    total = path_cost(C, order)
    return order, total, status


# ----------------------------------------------------------------------
# Evaluation helpers
# ----------------------------------------------------------------------
def path_cost(C, order):
    return float(sum(C[order[k]][order[k + 1]] for k in range(len(order) - 1)))


def adjacency_accuracy(order, shuffled_order):
    """
    Neighbour-adjacency accuracy = fraction of recovered adjacent pairs that are
    truly consecutive in the ORIGINAL document, in the correct direction.

    `order` indexes into the shuffled pile; map each back to its original index
    via shuffled_order, then count pairs (a, b) where b == a + 1.

    The reconstruction may come out globally REVERSED (right-to-left). We score
    the sequence and its reverse and report the better one (a mirror is the same
    physical reconstruction), noting which orientation was used.
    """
    orig_seq = [shuffled_order[k] for k in order]

    def fwd_hits(seq):
        return sum(1 for k in range(len(seq) - 1) if seq[k + 1] == seq[k] + 1)

    hits = fwd_hits(orig_seq)
    rev = list(reversed(orig_seq))
    hits_rev = fwd_hits(rev)

    if hits_rev > hits:
        return hits_rev / (len(orig_seq) - 1), orig_seq, "reversed (mirror)"
    return hits / (len(orig_seq) - 1), orig_seq, "as-is"


def reconstruct_image(strips, order, path, gap=0):
    ordered = [strips[k] for k in order]
    save_strip_montage(ordered, path, gap=gap)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    global N_STRIPS

    banner("STEP 1 -- OBTAIN REAL DOCUMENT IMAGE (grayscale)")
    gray, desc = load_document_image()
    print("source :", desc)
    print("image shape (H x W):", gray.shape, "dtype:", gray.dtype)
    print("pixel range: min", int(gray.min()), "max", int(gray.max()),
          "mean", round(float(gray.mean()), 1))

    # preprocessing: drop content-free white margins (else margin-only strips
    # have ambiguous, near-zero-cost edges -- a real failure mode we avoid here)
    w0 = gray.shape[1]
    gray = trim_blank_margins(gray)
    print(f"trimmed blank margins: width {w0} -> {gray.shape[1]} columns")

    # adjust N so each strip is wide enough
    h, w = gray.shape
    if w // N_STRIPS < MIN_STRIP_PX:
        N_STRIPS = max(2, w // MIN_STRIP_PX)
        print(f"[info] strip width too small; reduced N_STRIPS to {N_STRIPS}")

    print()
    banner(f"STEP 2 -- SHRED INTO {N_STRIPS} VERTICAL STRIPS (strip-cut), shuffle seed={SHUFFLE_SEED}")
    strips, shuffled_order, strip_w = shred(gray, N_STRIPS, SHUFFLE_SEED)
    print("strip width (px):", strip_w)
    print("ground-truth order (original):", list(range(N_STRIPS)))
    print("shuffled pile -> original idx:", shuffled_order)
    shredded_png = os.path.join(DATA, "shredded.png")
    save_strip_montage(strips, shredded_png, gap=2)
    print("saved shuffled-strips image ->", os.path.relpath(shredded_png, HERE))

    print()
    banner("STEP 3 -- ENCODE MATCH COST (asymmetric N x N edge-cost matrix C)")
    C, big = build_cost_matrix(strips)
    print("C shape:", C.shape, "(C[i][j] = right-edge(i) vs left-edge(j) mismatch)")
    print("diagonal sentinel (forbidden self-follow):", round(big, 2))
    print("sample costs:")
    print(f"  C[0][1] = {C[0][1]:.3f}   C[1][0] = {C[1][0]:.3f}   (asymmetric)")
    print(f"  C[0][2] = {C[0][2]:.3f}   C[5][7] = {C[5][7]:.3f}")
    print(f"  min off-diagonal C = {C[~np.eye(N_STRIPS, dtype=bool)].min():.3f}")

    print()
    banner("STEP 4 -- OPTIMISE: find the order minimising total adjacent-edge cost")

    greedy_order, greedy_cost = greedy_path(C)
    print(f"[greedy NN] best total cost = {greedy_cost:.3f}")

    ort_order, ort_cost, ort_status = ortools_path(C, big)
    print(f"[OR-Tools TSP] solver status = {ort_status}")
    if ort_order is not None:
        print(f"[OR-Tools TSP] total cost   = {ort_cost:.3f}")
    else:
        print("[OR-Tools TSP] no solution returned")

    print()
    banner("STEP 5 -- EVALUATE (neighbour-adjacency accuracy vs ground truth)")

    # ground-truth path cost (strips placed in true original order)
    inv = [0] * N_STRIPS
    for pile_idx, orig_idx in enumerate(shuffled_order):
        inv[orig_idx] = pile_idx           # pile index of each original strip
    gt_order = inv                          # pile indices in true left->right order
    gt_cost = path_cost(C, gt_order)
    print(f"ground-truth total edge cost (optimum target): {gt_cost:.3f}")

    g_acc, g_seq, g_orient = adjacency_accuracy(greedy_order, shuffled_order)
    print(f"[greedy NN]   adjacency accuracy = {g_acc*100:5.1f}%  "
          f"({orient_count(g_seq)}/{N_STRIPS-1} correct neighbours, {g_orient})")
    print(f"              PERFECT? {g_acc == 1.0}")

    if ort_order is not None:
        o_acc, o_seq, o_orient = adjacency_accuracy(ort_order, shuffled_order)
        print(f"[OR-Tools TSP] adjacency accuracy = {o_acc*100:5.1f}%  "
              f"({orient_count(o_seq)}/{N_STRIPS-1} correct neighbours, {o_orient})")
        print(f"              PERFECT? {o_acc == 1.0}")

    print()
    print("cost comparison (lower = better; optimum ~ ground-truth):")
    print(f"  ground-truth : {gt_cost:10.3f}")
    print(f"  OR-Tools TSP : {ort_cost:10.3f}" if ort_order is not None else "  OR-Tools TSP : n/a")
    print(f"  greedy NN    : {greedy_cost:10.3f}")

    print()
    banner("STEP 6 -- RECOVERED ORDER + RECONSTRUCTED IMAGE")
    chosen_order = ort_order if ort_order is not None else greedy_order
    chosen_name = "OR-Tools TSP" if ort_order is not None else "greedy NN"
    recovered_original = [int(shuffled_order[k]) for k in chosen_order]
    print(f"recovered order ({chosen_name}), as ORIGINAL strip indices:")
    print(" ", recovered_original)
    recon_png = os.path.join(DATA, "reconstructed.png")
    reconstruct_image(strips, chosen_order, recon_png, gap=0)
    print("saved reconstructed image ->", os.path.relpath(recon_png, HERE))

    print()
    banner("DONE")


def orient_count(seq):
    """count of correct consecutive neighbours in the better orientation."""
    def fwd(s):
        return sum(1 for k in range(len(s) - 1) if s[k + 1] == s[k] + 1)
    return max(fwd(seq), fwd(list(reversed(seq))))


if __name__ == "__main__":
    main()
