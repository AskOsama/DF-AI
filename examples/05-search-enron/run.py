#!/usr/bin/env python3
"""
05-search-enron — Inverted index + BM25 ranked search over the Enron email corpus.

A runnable e-discovery worked example for the DF-AI course.

Pipeline:  ingest/parse (email.parser)  ->  preprocess (tokenize/stopword/stem)
        -> build inverted index (BM25Okapi)  ->  ranked query  ->  KWIC snippet
        -> query refinement (tighter terms + sender filter).

Run:
    python3 run.py | tee output.txt
"""

import os
import re
import sys
import time
import email
from email import policy
from email.parser import BytesParser

from rank_bm25 import BM25Okapi
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MAILDIR = os.path.join(os.path.dirname(__file__), "data", "maildir")

# Cap total messages indexed so the example runs in a classroom timeframe.
# Key custodian folders are walked FIRST so they are always inside the cap.
MAX_MESSAGES = 80_000

# Custodians central to the Raptor / LJM / special-purpose-entity scenario.
#
# NOTE on the dataset: the FERC/CMU release does NOT contain Andrew Fastow's
# (fastow-a) or Richard Causey's (causey-r) mailboxes -- those custodians were
# never part of the public corpus. We therefore prioritise the Raptor/LJM-
# relevant custodians that ARE present:
#   skilling-j  CEO
#   lay-k       chairman
#   kaminski-v  head of research -- famously flagged the LJM/Raptor risk
#   buy-r       Chief Risk Officer -- approved the hedges
#   haedicke-m / derrick-j / sanders-r   in-house legal
#   delainey-d / whalley-g   senior management
#   kean-s      communications / chief of staff
# These are walked FIRST so they always survive the message cap.
PRIORITY_CUSTODIANS = [
    "skilling-j", "lay-k", "kaminski-v", "buy-r", "haedicke-m",
    "derrick-j", "sanders-r", "delainey-d", "whalley-g", "kean-s",
]

# The real e-discovery queries.
QUERY_1 = "raptor LJM special purpose entity mark to market"
QUERY_2 = "raptor LJM hedge off balance sheet special purpose entity accounting restatement"
SENDER_FILTER = "fastow"   # substring matched against the From: header

TOP_N = 10

# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #
STOP = set(stopwords.words("english"))
STEMMER = SnowballStemmer("english")
TOKEN_RE = re.compile(r"\w+")
# A small per-process stem cache: the corpus repeats tokens millions of times.
_stem_cache: dict[str, str] = {}


def _stem(tok: str) -> str:
    s = _stem_cache.get(tok)
    if s is None:
        s = STEMMER.stem(tok)
        _stem_cache[tok] = s
    return s


def preprocess(text: str) -> list[str]:
    """lowercase -> \\w+ tokenize -> drop stopwords/short tokens -> Snowball stem."""
    out = []
    for tok in TOKEN_RE.findall(text.lower()):
        if len(tok) < 2 or tok in STOP:
            continue
        out.append(_stem(tok))
    return out


# --------------------------------------------------------------------------- #
# Ingest / parse
# --------------------------------------------------------------------------- #
def get_body(msg) -> str:
    """Extract a plain-text body from a parsed email.message.Message."""
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("latin-1", errors="ignore"))
                except Exception:
                    continue
        return "\n".join(parts)
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode("latin-1", errors="ignore")
    return msg.get_payload() or ""


def ordered_message_paths(maildir: str):
    """Yield file paths, PRIORITY_CUSTODIANS first, so they survive the cap."""
    top = sorted(d for d in os.listdir(maildir)
                 if os.path.isdir(os.path.join(maildir, d)))
    priority = [d for d in PRIORITY_CUSTODIANS if d in top]
    rest = [d for d in top if d not in priority]

    for custodian in priority + rest:
        root = os.path.join(maildir, custodian)
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                yield custodian, os.path.join(dirpath, fn)


def ingest(maildir: str, cap: int):
    """Parse messages into a doc_store. Returns (doc_store, custodian_counts)."""
    parser = BytesParser(policy=policy.compat32)
    doc_store = []          # list of dicts, index == doc_id
    custodian_counts: dict[str, int] = {}

    for custodian, path in ordered_message_paths(maildir):
        if len(doc_store) >= cap:
            break
        try:
            with open(path, "rb") as fh:
                msg = parser.parse(fh)
        except Exception:
            continue
        body = get_body(msg)
        doc_store.append({
            "doc_id": len(doc_store),
            "custodian": custodian,
            "message_id": (msg.get("Message-ID") or "").strip(),
            "from": (msg.get("From") or "").strip(),
            "date": (msg.get("Date") or "").strip(),
            "subject": (msg.get("Subject") or "").strip(),
            "body": body,
        })
        custodian_counts[custodian] = custodian_counts.get(custodian, 0) + 1

    return doc_store, custodian_counts


# --------------------------------------------------------------------------- #
# KWIC snippet (keyword-in-context)
# --------------------------------------------------------------------------- #
def kwic(body: str, query_terms_raw: list[str], width: int = 120) -> str:
    """Return a ~width-char window of body centred on the first matched term."""
    flat = re.sub(r"\s+", " ", body).strip()
    low = flat.lower()
    pos = -1
    for term in query_terms_raw:
        p = low.find(term.lower())
        if p != -1 and (pos == -1 or p < pos):
            pos = p
    if pos == -1:
        return flat[:width].strip()
    start = max(0, pos - width // 3)
    snippet = flat[start:start + width].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if start + width < len(flat) else ""
    return f"{prefix}{snippet}{suffix}"


# --------------------------------------------------------------------------- #
# Ranking / display
# --------------------------------------------------------------------------- #
def rank(bm25, tokenized_query, n):
    scores = bm25.get_scores(tokenized_query)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [(i, scores[i]) for i in order[:n]]


def short(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def print_table(title, hits, doc_store, raw_terms):
    print()
    print("=" * 110)
    print(title)
    print("=" * 110)
    hdr = f"{'#':>2}  {'score':>7}  {'date':<31}  {'from':<28}  subject"
    print(hdr)
    print("-" * 110)
    for rank_i, (doc_id, score) in enumerate(hits, 1):
        d = doc_store[doc_id]
        print(f"{rank_i:>2}  {score:>7.2f}  {short(d['date'], 31):<31}  "
              f"{short(d['from'], 28):<28}  {short(d['subject'], 60)}")
        print(f"      KWIC: {kwic(d['body'], raw_terms)}")
    print("-" * 110)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    print("#" * 110)
    print("# DF-AI 05 — Inverted Index + BM25 ranked search over the Enron corpus (e-discovery)")
    print("#" * 110)

    if not os.path.isdir(MAILDIR):
        sys.exit(f"ERROR: {MAILDIR} not found. Download + extract the corpus first (see README).")

    # ---- 1. Ingest -------------------------------------------------------- #
    print(f"\n[1/4] Ingesting from {MAILDIR} (cap = {MAX_MESSAGES:,} messages; "
          f"priority custodians walked first)...")
    t0 = time.time()
    doc_store, custodian_counts = ingest(MAILDIR, MAX_MESSAGES)
    print(f"      Parsed {len(doc_store):,} messages in {time.time() - t0:.1f}s.")
    print(f"      Key custodians present in index:")
    for c in PRIORITY_CUSTODIANS:
        cnt = custodian_counts.get(c, 0)
        flag = "OK " if cnt else "MISSING"
        print(f"         [{flag}] {c:<12} {cnt:>6} msgs")

    # ---- 2. Preprocess + build inverted index (BM25) ---------------------- #
    print(f"\n[2/4] Preprocessing (lowercase / \\w+ tokenize / drop stopwords / Snowball stem)"
          f" and building BM25Okapi inverted index...")
    t0 = time.time()
    tokenized_corpus = [preprocess(d["subject"] + " " + d["body"]) for d in doc_store]
    tok_time = time.time() - t0
    t0 = time.time()
    bm25 = BM25Okapi(tokenized_corpus, k1=1.5, b=0.75)
    build_time = time.time() - t0
    n_tokens = sum(len(t) for t in tokenized_corpus)
    print(f"      Tokenized corpus: {len(tokenized_corpus):,} docs, "
          f"{n_tokens:,} tokens, {len(bm25.idf):,} unique terms.")
    print(f"      Tokenize time: {tok_time:.1f}s   |   BM25 index build time: {build_time:.1f}s")
    print(f"      Avg doc length (tokens): {bm25.avgdl:.1f}   |   BM25 params k1=1.5, b=0.75")

    # ---- 3. Primary ranked query ----------------------------------------- #
    raw1 = QUERY_1.split()
    tok1 = preprocess(QUERY_1)
    print(f"\n[3/4] PRIMARY e-discovery query")
    print(f"      raw    : \"{QUERY_1}\"")
    print(f"      stemmed: {tok1}")
    t0 = time.time()
    hits1 = rank(bm25, tok1, TOP_N)
    print(f"      Ranked {len(doc_store):,} docs in {time.time() - t0:.3f}s "
          f"(sub-second retrieval).")
    print_table(f"TOP {TOP_N} — Query 1: {QUERY_1}", hits1, doc_store, raw1)

    # ---- 4. Query refinement --------------------------------------------- #
    print(f"\n[4/4] QUERY REFINEMENT")

    # 4a. Tighter accounting-heavy query.
    raw2 = QUERY_2.split()
    tok2 = preprocess(QUERY_2)
    print(f"\n   (4a) Tighter query (added: hedge / off balance sheet / restatement)")
    print(f"        raw    : \"{QUERY_2}\"")
    print(f"        stemmed: {tok2}")
    hits2 = rank(bm25, tok2, TOP_N)
    print_table(f"TOP {TOP_N} — Query 2 (refined accounting terms)", hits2, doc_store, raw2)

    # 4b. Sender-filtered query: rank with Query 1, then keep only From ~ fastow.
    print(f"\n   (4b) Sender-filtered: Query 1 ranking, restricted to From contains "
          f"'{SENDER_FILTER}'")
    all_ranked = rank(bm25, tok1, len(doc_store))   # full ranking
    filtered = [(i, s) for (i, s) in all_ranked
                if SENDER_FILTER in doc_store[i]["from"].lower()][:TOP_N]
    if filtered:
        print_table(
            f"TOP {len(filtered)} — Query 1 filtered to From~'{SENDER_FILTER}'",
            filtered, doc_store, raw1)
    else:
        print(f"        (no messages from '{SENDER_FILTER}' in the indexed subset)")

    # ---- Ranking-change commentary --------------------------------------- #
    set1 = [i for i, _ in hits1]
    set2 = [i for i, _ in hits2]
    moved_in = [i for i in set2 if i not in set1]
    print()
    print("=" * 110)
    print("RANKING-CHANGE NOTES")
    print("=" * 110)
    print(f" - Query 1 top score: {hits1[0][1]:.2f}   Query 2 top score: {hits2[0][1]:.2f}")
    print(f" - {len(set(set1) & set(set2))}/{TOP_N} documents stay in the top-{TOP_N} "
          f"across Q1 -> Q2; {len(moved_in)} new docs enter on the tighter terms.")
    print(f" - Sender filter (From~'{SENDER_FILTER}') returned {len(filtered)} hits, "
          f"pivoting from a topical view to a custodian-centric view.")
    print(f" - HUMAN-IN-THE-LOOP: BM25 ranking is a *starting point* for review order, "
          f"not a coverage guarantee.\n   The analyst, not the score, decides where the "
          f"responsive set ends.")
    print("\nDone.")


if __name__ == "__main__":
    main()
