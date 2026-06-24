#!/usr/bin/env python3
"""
Feature Engineering — Static Malware / File Triage (EMBER-style)
================================================================
A RUNNABLE, classroom worked example for the DF-AI course.

Goal
----
Turn raw PE-file *bytes* into an EMBER-style numeric feature vector, train a
real classifier, and triage an unknown file WITHOUT running it. We also
demonstrate the *leakage trap* that the course warns about.

SAFETY
------
We do NOT use live malware. The two classes are:
  * benign   : REAL, signed Windows PE files copied from C:\\Windows\\System32
  * packed   : SYNTHETIC samples built from those same benign files by appending
               a high-entropy (encrypted-looking) blob and rewriting a section's
               raw bytes with random data. This mimics the #1 static signal of
               packed/encrypted malware: high entropy. No malicious behaviour is
               present — these files are never executed, only featurized.

This mirrors EMBER's pipeline (byte histogram, byte-entropy, header fields,
section entropy, import counts) on a small, fully reproducible corpus.

Run:  python3 run.py | tee output.txt
"""

import os
import glob
import math
import shutil
import random
import warnings
import numpy as np

warnings.filterwarnings("ignore")   # quiet sklearn/lightgbm cosmetic warnings

random.seed(1337)
np.random.seed(1337)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BENIGN_DIR = os.path.join(DATA, "benign")
PACKED_DIR = os.path.join(DATA, "packed")
SRC_DIRS = ["/mnt/c/Windows/System32"]

N_PER_CLASS = 60          # 60 benign + 60 synthetic-packed = 120 samples
MIN_SIZE, MAX_SIZE = 8000, 250000

# Optional PE parser (EMBER uses lief). Degrade gracefully.
try:
    import lief
    lief.logging.disable()
    HAVE_LIEF = True
except Exception:
    HAVE_LIEF = False

try:
    from lightgbm import LGBMClassifier
    HAVE_LGBM = True
except Exception:
    HAVE_LGBM = False
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report


def rule(title=""):
    line = "=" * 72
    if title:
        print("\n" + line + "\n" + title + "\n" + line)
    else:
        print(line)


# ---------------------------------------------------------------------------
# 1. Gather a SAFE labeled corpus
# ---------------------------------------------------------------------------
def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts[counts > 0] / len(data)
    return float(-(probs * np.log2(probs)).sum())


def make_packed(src_path: str, dst_path: str, strength: float = 1.0):
    """Create a SYNTHETIC packed/encrypted-looking variant of a benign file.

    Mimics real packers (UPX, ASPack, custom crypters) by encrypting only a
    FRACTION of the body, governed by `strength` in [0,1]:
      * strength=1.0 -> heavily packed: whole body encrypted, big appended blob
      * strength~0.3 -> lightly packed: only part of the body encrypted, smaller
                        blob -> entropy is elevated but NOT a dead giveaway, so
                        the honest task is realistically hard (not 100%).
    The DOS+PE header region is kept intact so the file still parses; this is
    how real crypters preserve a runnable stub. No malicious behaviour exists.
    """
    with open(src_path, "rb") as f:
        raw = bytearray(f.read())
    head_keep = min(1024, len(raw))           # keep DOS+PE header region intact
    body = bytearray(raw[head_keep:])
    # encrypt a leading `strength` fraction of the body with a rolling keystream
    key = bytes(random.getrandbits(8) for _ in range(257))
    enc_len = int(len(body) * max(0.05, min(1.0, strength)))
    for i in range(enc_len):
        body[i] ^= key[i % len(key)]
    blob = os.urandom(int(random.randint(2000, 8000) * strength))  # appended payload
    out = bytes(raw[:head_keep]) + bytes(body) + blob
    with open(dst_path, "wb") as f:
        f.write(out)


def gather_corpus():
    if os.path.isdir(BENIGN_DIR) and len(os.listdir(BENIGN_DIR)) >= N_PER_CLASS:
        print("[gather] reusing existing data/ corpus")
        return
    os.makedirs(BENIGN_DIR, exist_ok=True)
    os.makedirs(PACKED_DIR, exist_ok=True)
    candidates = []
    for d in SRC_DIRS:
        for pat in ("*.dll", "*.exe"):
            candidates += glob.glob(os.path.join(d, pat))
    candidates = [c for c in candidates
                  if MIN_SIZE < os.path.getsize(c) < MAX_SIZE]
    candidates = sorted(set(candidates))
    random.shuffle(candidates)
    if len(candidates) < N_PER_CLASS:
        raise SystemExit("Not enough PE files found on disk; see README fallback.")
    chosen = candidates[:N_PER_CLASS]
    print(f"[gather] copying {len(chosen)} REAL benign PE files from {SRC_DIRS[0]}")
    for i, src in enumerate(chosen):
        b = os.path.join(BENIGN_DIR, f"benign_{i:03d}.bin")
        shutil.copyfile(src, b)
        p = os.path.join(PACKED_DIR, f"packed_{i:03d}.bin")
        # Mostly LIGHT packing so the honest task is realistically hard: light
        # packers leave most of the file untouched -> the classes overlap and
        # the honest model leaves headroom (this is what lets the leakage demo
        # show real accuracy inflation later).
        strength = random.choice([0.10, 0.12, 0.15, 0.18, 0.22, 0.30])
        make_packed(src, p, strength=strength)   # synthetic packed twin
    print(f"[gather] generated {len(chosen)} SYNTHETIC packed variants "
          f"(mixed light/heavy packing)")


# ---------------------------------------------------------------------------
# 2. EMBER-style feature extraction
# ---------------------------------------------------------------------------
# We build a compact, transparent feature vector with the SAME families EMBER
# uses, mapped to human-readable names so importances are interpretable.

def feature_names():
    names = []
    names += [f"byte_hist[{i}]" for i in range(16)]   # 16-bin byte histogram
    names += [
        "file_size",
        "byte_entropy_whole",
        "byte_entropy_win_mean",
        "byte_entropy_win_max",
        "byte_entropy_win_std",
        "frac_high_entropy_windows",   # share of 2KB windows with entropy>7.0
        "printable_string_count",
        "printable_string_mean_len",
        # --- PE header / structural (lief); zeros if parse fails ---
        "pe_num_sections",
        "pe_section_entropy_mean",
        "pe_section_entropy_max",
        "pe_import_count",
        "pe_dll_count",
        "pe_has_imports",
        "pe_timestamp",                # <-- LEAKY feature (see leakage demo)
    ]
    return names


N_HIST = 16


def extract_features(path: str):
    with open(path, "rb") as f:
        raw = f.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    feats = []

    # (a) Byte histogram, folded to 16 bins, normalized -> gross composition
    full = np.bincount(arr, minlength=256).astype(np.float64)
    hist16 = full.reshape(16, 16).sum(axis=1)
    hist16 = hist16 / max(hist16.sum(), 1)
    feats += hist16.tolist()

    # (b) Size + whole-file Shannon entropy
    feats.append(float(len(raw)))
    feats.append(shannon_entropy(raw))

    # (c) Windowed byte-entropy summary (sliding 2KB windows)
    win = 2048
    ents = []
    for s in range(0, max(len(raw) - win, 1), win):
        ents.append(shannon_entropy(raw[s:s + win]))
    ents = np.array(ents) if ents else np.array([0.0])
    feats += [float(ents.mean()), float(ents.max()), float(ents.std()),
              float((ents > 7.0).mean())]

    # (d) Printable-string stats (ASCII runs >= 5)
    runs, cur = [], 0
    for b in arr:
        if 32 <= b <= 126:
            cur += 1
        else:
            if cur >= 5:
                runs.append(cur)
            cur = 0
    if cur >= 5:
        runs.append(cur)
    feats.append(float(len(runs)))
    feats.append(float(np.mean(runs)) if runs else 0.0)

    # (e) PE header / structural features via lief
    num_sec = sec_ent_mean = sec_ent_max = imp_cnt = dll_cnt = has_imp = ts = 0.0
    if HAVE_LIEF:
        try:
            pe = lief.parse(path)
            if pe is not None:
                secs = list(pe.sections)
                num_sec = float(len(secs))
                sent = [shannon_entropy(bytes(s.content)) for s in secs
                        if len(s.content) > 0]
                if sent:
                    sec_ent_mean = float(np.mean(sent))
                    sec_ent_max = float(np.max(sent))
                libs = list(pe.imports)
                dll_cnt = float(len(libs))
                imp_cnt = float(sum(len(l.entries) for l in libs))
                has_imp = 1.0 if imp_cnt > 0 else 0.0
                try:
                    ts = float(pe.header.time_date_stamps)
                except Exception:
                    ts = 0.0
        except Exception:
            pass
    feats += [num_sec, sec_ent_mean, sec_ent_max, imp_cnt, dll_cnt, has_imp, ts]
    return np.array(feats, dtype=np.float64)


def build_matrix():
    rows, labels, paths = [], [], []
    for path in sorted(glob.glob(os.path.join(BENIGN_DIR, "*.bin"))):
        rows.append(extract_features(path)); labels.append(0); paths.append(path)
    for path in sorted(glob.glob(os.path.join(PACKED_DIR, "*.bin"))):
        rows.append(extract_features(path)); labels.append(1); paths.append(path)
    X = np.vstack(rows)
    y = np.array(labels)
    return X, y, paths


def new_model():
    if HAVE_LGBM:
        return LGBMClassifier(n_estimators=200, num_leaves=31,
                              learning_rate=0.05, random_state=0, verbose=-1)
    return RandomForestClassifier(n_estimators=300, random_state=0)


def importances(model, names):
    if hasattr(model, "feature_importances_"):
        imp = np.array(model.feature_importances_, dtype=float)
        return sorted(zip(names, imp), key=lambda t: -t[1])
    return []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    rule("STEP 1 — Gather a SAFE labeled corpus (real benign + synthetic packed)")
    gather_corpus()
    nb = len(glob.glob(os.path.join(BENIGN_DIR, "*.bin")))
    npk = len(glob.glob(os.path.join(PACKED_DIR, "*.bin")))
    print(f"  benign (REAL System32 PE) : {nb}")
    print(f"  packed (SYNTHETIC)        : {npk}")
    print(f"  PE parser (lief)          : {'available' if HAVE_LIEF else 'NOT available'}")
    print(f"  classifier                : {'LightGBM' if HAVE_LGBM else 'RandomForest (lgbm import failed)'}")

    rule("STEP 2 — Extract EMBER-style features  (raw bytes -> numeric vector)")
    names = feature_names()
    X, y, paths = build_matrix()
    print(f"  feature matrix X : shape {X.shape}  (n_samples x n_features)")
    print(f"  labels y         : {int((y==0).sum())} benign, {int((y==1).sum())} packed")
    print(f"  feature families : byte-histogram(16), entropy summary(5), "
          f"strings(2), PE header/sections/imports(7)")

    # Quick sanity: mean entropy per class proves features separate the classes
    e_idx = names.index("byte_entropy_whole")
    print(f"  mean whole-file entropy  benign={X[y==0, e_idx].mean():.3f}  "
          f"packed={X[y==1, e_idx].mean():.3f}")
    i_idx = names.index("pe_import_count")
    print(f"  mean recoverable imports benign={X[y==0, i_idx].mean():.1f}  "
          f"packed={X[y==1, i_idx].mean():.1f}")

    rule("STEP 3 — Train / test split + train classifier")
    Xtr, Xte, ytr, yte, ptr, pte = train_test_split(
        X, y, paths, test_size=0.30, random_state=42, stratify=y)
    print(f"  train: {Xtr.shape[0]} samples   test: {Xte.shape[0]} samples")
    model = new_model()
    model.fit(Xtr, ytr)
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    acc = accuracy_score(yte, pred)
    auc = roc_auc_score(yte, proba)
    print(f"  HONEST test accuracy : {acc:.4f}")
    print(f"  HONEST test ROC-AUC  : {auc:.4f}")
    print("  classification report:")
    print(classification_report(yte, pred, target_names=["benign", "packed"],
                                digits=3))

    rule("STEP 4 — Top feature importances (mapped to human names)")
    imp = importances(model, names)
    for name, val in imp[:8]:
        bar = "#" * int(40 * val / (imp[0][1] + 1e-9))
        print(f"  {name:28s} {val:10.4f} {bar}")

    rule("STEP 5 — Score one held-out UNKNOWN sample")
    # take the test sample the model is most confident is packed, and one benign
    order = np.argsort(-proba)
    for tag, idx in [("most-suspicious", order[0]), ("most-benign", order[-1])]:
        p = proba[idx]
        verdict = "PACKED/SUSPICIOUS" if p >= 0.5 else "BENIGN"
        truth = "packed" if yte[idx] == 1 else "benign"
        print(f"  [{tag}] file = {os.path.basename(pte[idx])}")
        print(f"     verdict   : {verdict}   P(packed)={p:.3f}   (ground truth: {truth})")
        # top drivers for THIS sample (importance-weighted standardized value)
        mu, sd = X.mean(0), X.std(0) + 1e-9
        z = (Xte[idx] - mu) / sd
        contrib = z * np.array([dict(imp).get(n, 0) for n in names])
        drivers = sorted(zip(names, contrib), key=lambda t: -abs(t[1]))[:3]
        print("     top drivers:", ", ".join(f"{n}({c:+.2f})" for n, c in drivers))

    rule("STEP 6 — LEAKAGE TRAP (real demonstration, 5-fold cross-validation)")
    print("  We add a LEAKY feature 'source_folder_id': every benign file gets")
    print("  id=0, every packed file gets id=1 -- exactly the 'folder named")
    print("  evidence' shortcut. In a real case the analyst's intake script wrote")
    print("  benign and suspicious files to different folders, so the folder id")
    print("  is PERFECTLY correlated with the label. The model can cheat.\n")
    print("  We compare HONEST vs LEAKY feature sets with 5-fold CV (stable est.)\n")

    # Build leaky matrix: append a column perfectly correlated with the label.
    leak_col = y.reshape(-1, 1).astype(float)         # == the label, by folder
    X_leak = np.hstack([X, leak_col])
    names_leak = names + ["source_folder_id (LEAKY)"]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)

    acc_honest_cv = cross_val_score(new_model(), X, y, cv=cv, scoring="accuracy")
    auc_honest_cv = cross_val_score(new_model(), X, y, cv=cv, scoring="roc_auc")
    acc_leak_cv = cross_val_score(new_model(), X_leak, y, cv=cv, scoring="accuracy")
    auc_leak_cv = cross_val_score(new_model(), X_leak, y, cv=cv, scoring="roc_auc")

    # importance rank of the leaky feature when present
    m_leak = new_model(); m_leak.fit(X_leak, y)
    imp_leak = importances(m_leak, names_leak)
    leak_rank = [n for n, _ in imp_leak].index("source_folder_id (LEAKY)") + 1

    print(f"  WITHOUT leaky feat. (honest): accuracy={acc_honest_cv.mean():.4f}"
          f"  AUC={auc_honest_cv.mean():.4f}")
    print(f"  WITH leaky feature          : accuracy={acc_leak_cv.mean():.4f}"
          f"  AUC={auc_leak_cv.mean():.4f}")
    print(f"     -> leaky feature ranked #{leak_rank} of {len(names_leak)} "
          f"in importance (it dominates)")
    print(f"  INFLATION from leakage      : accuracy {acc_leak_cv.mean()-acc_honest_cv.mean():+.4f}"
          f"   AUC {auc_leak_cv.mean()-auc_honest_cv.mean():+.4f}")
    print("\n  LESSON: the leaky model looks great offline but learned the FOLDER,")
    print("          not the FILE. On genuinely unknown evidence -- where every")
    print("          file is 'unsorted' -- the shortcut is gone and it collapses.")
    print("          -> drop folder/timestamp/source-feed metadata before training.")

    rule("DONE")


if __name__ == "__main__":
    main()
