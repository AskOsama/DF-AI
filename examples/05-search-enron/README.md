# 05 — Search Engines: Inverted Index + BM25 over the Enron Corpus (E-Discovery)

A **runnable** worked example for the DF-AI course. It builds a real inverted
index with BM25 ranking over the genuine Enron email corpus and runs ranked
e-discovery queries, surfacing the most probative messages first instead of
linearly scanning ~500,000 files.

---

## Overview

Underneath much of digital forensics is plain **search**: build an index once,
then retrieve fast and *ranked*. This example takes the canonical e-discovery
dataset — the Enron emails released by FERC during the 2001–2004 investigation —
and builds the same kind of pipeline a litigation-support analyst uses:

```
ingest/parse  ->  preprocess  ->  build inverted index (BM25)  ->  ranked query
              ->  KWIC snippet  ->  refine (tighter terms / sender filter)
```

The forensic scenario: an analyst under a **litigation hold** must surface every
internal email discussing the off-balance-sheet **special-purpose entities** and
the **Raptor / LJM** hedging vehicles, *ranked by relevance*, so counsel reviews
the most probative documents first.

Everything here actually ran. The ranked tables in `output.txt` are real BM25
scores over real messages from real senders.

---

## Dataset & download

| Property | Value |
|---|---|
| **Name** | Enron Email Dataset (CMU distribution, May 2015 version) |
| **Home** | <https://www.cs.cmu.edu/~enron/> |
| **URL** | <https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz> |
| **License** | Public, freely downloadable for research. CMU asks only that users respect the privacy of those involved. No formal SPDX licence — treat as research-public. |
| **Size** | ~443 MB gzipped; ~2.6 GB uncompressed; **520,901** archive entries (~500k messages + folders) across **150 custodians**. |
| **Format** | Maildir tree — one RFC-822 text file per message at `maildir/<custodian>/<folder>/<n>` with standard headers + body. |

```bash
mkdir -p data
wget -q -O data/enron.tar.gz https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz
tar -xzf data/enron.tar.gz -C data          # creates data/maildir/
```

> **Note on observed size.** The course brief lists "~1.7 GB gzipped"; the actual
> CMU archive is **~443 MB gzipped / ~2.6 GB unpacked**. `gzip -t` confirmed the
> download was intact (520,901 entries).

> **Slow-filesystem deviation (important).** On a Windows-mounted volume
> (`/mnt/d` under WSL2), extracting ~500k tiny files is extremely slow — `tar`
> blocks on disk I/O for hours. As the brief permits, we extracted a **subset of
> custodians** that still covers the scenario, rather than the full tree. See
> **Notes / deviations** for the exact custodian list and message counts.

### A real fact about this corpus

The FERC/CMU release **does not contain Andrew Fastow's (`fastow-a`) or Richard
Causey's (`causey-r`) mailboxes** — those custodians were never part of the
public dataset. We therefore prioritise the Raptor/LJM-relevant custodians that
*are* present, most importantly **Vince Kaminski** (head of research, who flagged
the LJM/Raptor risk) and **Rick Buy** (Chief Risk Officer). Fastow still appears
in the results — as the *sender* of messages sitting in other people's
mailboxes (see Query 4b).

---

## How to run (copy-paste)

```bash
cd examples/05-search-enron

# environment (venv with system site-packages)
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --quiet rank-bm25 nltk
python -m nltk.downloader -q stopwords punkt punkt_tab

# data (see "Dataset & download" above)
mkdir -p data
wget -q -O data/enron.tar.gz https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz
tar -xzf data/enron.tar.gz -C data
#   on a slow filesystem, extract only the scenario custodians instead:
#   tar -xzf data/enron.tar.gz -C data \
#     maildir/skilling-j maildir/lay-k maildir/kaminski-v maildir/buy-r \
#     maildir/haedicke-m maildir/derrick-j maildir/sanders-r \
#     maildir/delainey-d maildir/whalley-g maildir/kean-s

# run
python3 run.py | tee output.txt
```

---

## Workflow

| Step | What happens | Where in `run.py` |
|---|---|---|
| **Download** | `wget` the CMU archive; `tar -xzf` into `data/maildir/`. | (shell) |
| **Ingest / parse** | Walk the maildir tree (priority custodians **first**), parse each file with `email.parser.BytesParser` (`errors='ignore'` semantics via `latin-1` decode + try/except), keep `Message-ID / From / Date / Subject + body` in a `doc_store`. | `ingest`, `get_body`, `ordered_message_paths` |
| **Preprocess** | lowercase → regex tokenize `\w+` → drop English stopwords + <2-char tokens → Snowball (Porter2) stem (e.g. `hedging→hedg`). | `preprocess` |
| **Build index** | Feed the tokenized corpus to `BM25Okapi(...)` — the in-memory inverted index + document-length statistics. | `main` step 2 |
| **Query** | Tokenize the query the *same way*, score every doc with BM25, sort descending. | `rank` |
| **Rank + snippet** | Print the top-10 as a table with a ~120-char **KWIC** (keyword-in-context) snippet pulled from the raw body. | `print_table`, `kwic` |
| **Refine** | (4a) tighter accounting-heavy query; (4b) sender filter `From ~ "fastow"`. Report how the ranking changed. | `main` step 4 |

---

## Encoding / indexing

Raw RFC-822 messages become an inverted index in four passes:

1. **Parse** — `email.parser` reads each maildir file; `Message-ID` is kept as a
   stable doc identifier, `From / Date / Subject` are retained as display fields,
   and `Subject + body` is the searchable content.
2. **Tokenize** — split on non-word boundaries with `re.findall(r"\w+", text.lower())`.
3. **Normalize** — drop English stopwords and <2-char tokens, then **Snowball
   stem** so `valuations`, `valuation`, `valuing` collapse to one term.
4. **Postings** — conceptually, `term -> [(doc_id, term_freq, [positions])]`.
   Positions are what enable phrase / proximity queries. A parallel `doc_store`
   maps `doc_id -> {message_id, from, date, subject, body}` for display.

```
postings[ "raptor" ] = [ (1187, 3, [12, 40, 91]),
                         (1188, 1, [7]),
                         (5530, 5, [2, 9, 33, 88, 140]),
                         ... ]
```

`rank_bm25` stores this compactly as per-document term-frequency dicts plus a
document-length table and the corpus average length `avgdl` — everything BM25
needs. (We do not need explicit positions for this example, so we use the
length-aware bag-of-words form; the positional form above is what a phrase-query
engine such as Whoosh would persist on disk.)

### Ranking model: BM25 (Okapi) vs TF-IDF

**BM25** is the primary scorer (`k1 = 1.5`, `b = 0.75`):

```
score(D, Q) = Σ_t  IDF(t) ·  f(t,D)·(k1+1)
                            ─────────────────────────────────
                            f(t,D) + k1·(1 − b + b·|D|/avgdl)
```

* `f(t,D)` — term frequency of `t` in document `D`
* `|D|` — document length (tokens); `avgdl` — average over the corpus
* `IDF(t)` — inverse document frequency of `t`

**Why BM25 over plain TF-IDF:**

* **TF saturation** — the `k1` term means the 10th occurrence of `raptor` adds
  far less than the 2nd. Plain TF-IDF grows linearly, over-rewarding keyword
  stuffing and long forwarded threads.
* **Length normalization** — the `b·|D|/avgdl` term penalises long documents so a
  500-line forwarded chain doesn't automatically beat a tight 5-line memo. Email
  lengths in this corpus vary wildly (avg ≈ 218 tokens, but many are 10× that),
  so this matters a lot.

TF-IDF (e.g. scikit-learn `TfidfVectorizer` + cosine) is the simpler baseline and
is fine for a first cut, but it lacks both behaviours above.

---

## Algorithm & data structures

* **Inverted index** — `dict[str, list[Posting]]` (term → postings list) plus a
  document-length table and `avgdl`. `rank_bm25` builds and holds this in memory.
* **Scoring** — sum BM25 contributions across query terms; rank docs by
  descending score. Retrieval is **sub-second** (0.176 s over 80,000 docs here),
  versus a linear scan of half a million files.
* **doc_store** — `list[dict]` indexed by `doc_id` for O(1) display lookup.
* **KWIC snippet** — locate the first raw query term in the body and emit a
  ~120-char window around it.
* **Libraries**
  * `rank_bm25` (Apache-2.0) — transparent, from-scratch BM25 pipeline (used here).
  * `nltk` — English stopword list and the Snowball stemmer.
  * *Optional* `Whoosh` (BSD) — a pure-Python **on-disk** index with positional
    postings if you need persistence and phrase queries beyond an in-memory run.
  * *Optional* scikit-learn `TfidfVectorizer` — the TF-IDF baseline.

The Part-4 search strategies map onto retrieval: **brute force** = the linear
scan of all 500k files (the thing we avoid); **greedy** = expand the
top-scored postings first; **ε-greedy / random** = occasionally sample
lower-ranked hits for review diversity.

---

## PLAN-PHASE PROMPT

Use this to make an agent **plan** the e-discovery search before touching data:

```
You are an e-discovery analyst supporting a litigation hold on the Enron matter.
Goal: surface every internal email discussing the off-balance-sheet
special-purpose entities and the Raptor / LJM hedging vehicles, RANKED by
relevance so counsel reviews the most probative documents first.

Produce a PLAN only (no code execution yet). It must specify:
1. Dataset acquisition: the exact source, license constraints, size, and the
   maildir/RFC-822 format you will parse. Note which key custodians you expect
   (and verify whether Fastow/Causey mailboxes even exist in the public release).
2. Ingestion: how you parse each message, which fields you keep (Message-ID,
   From, Date, Subject, body), and how you bound memory/time (a message cap, and
   walking priority custodians first so they survive the cap).
3. Index design: tokenization (\w+), normalization (lowercase, stopwords,
   Snowball stem), the postings structure term -> [(doc_id, tf, positions)], and
   the ranking model. Justify BM25 (k1=1.5, b=0.75) over TF-IDF for email.
4. Query design: the initial broad query and at least two refinement moves
   (tighter accounting terms; a sender/custodian filter).
5. Output: a ranked top-N table with date/from/subject and a KWIC snippet.
6. The human-in-the-loop gate: state explicitly that the ranking is a starting
   point for REVIEW ORDER, not a coverage/responsiveness guarantee.

Return the plan as numbered steps with the data structures named.
```

## EXECUTE-PHASE PROMPT

Use this to make the agent **run** the plan:

```
Execute the e-discovery search plan now, end to end, and show real output.

1. Build the venv and install rank-bm25 + nltk; download the NLTK stopwords +
   punkt + punkt_tab.
2. Download and extract the Enron corpus to data/maildir/. If full extraction is
   too slow on this filesystem, extract the scenario custodians only and SAY SO.
3. Implement run.py exactly as planned: parse with email.parser, preprocess,
   build BM25Okapi(tokenized_corpus, k1=1.5, b=0.75), and confirm the key
   custodians are in the index (print counts).
4. Run the primary query "raptor LJM special purpose entity mark to market" and
   print the TOP 10 as rank/score/date/from/subject + a ~120-char KWIC snippet.
   Scores and senders MUST be the real values from the data.
5. Refine: (a) a tighter accounting query, (b) a sender filter From~"fastow".
   Print the new tops and describe how the ranking changed.
6. Run: python3 run.py | tee output.txt. Report indexed-message count, the real
   top hits, and any deviation. Do not fabricate any score or sender.
```

---

## Part 5 — Agent handling (ReAct)

**Analyst (system) prompt:**

```
You are a forensic e-discovery analyst. You have one tool: search(query,
sender_filter=None) -> ranked list of (score, date, from, subject, snippet) over
a BM25 index of the Enron corpus. Iterate: search, READ the top snippets, judge
whether they are responsive, and refine the query (tighten terms, add a phrase,
or filter by sender/custodian) until the top of the list is dense with probative
hits. The ranking is a starting point for review ORDER, not a coverage
guarantee — escalate the final responsiveness call to a human reviewer.
```

**ReAct trace (matches what `run.py` actually does):**

```
Thought:  Start broad on the scenario terms to see what the corpus surfaces.
Action:   search("raptor LJM special purpose entity mark to market")
Observation: Top hits mix true gold (Kaminski "FW: LJM/Raptor valuations",
             score ~26) with NOISE: PR threads "FW: Erroneous press" rank #1–3
             (~29) because they repeat "LJM" many times. Top score 29.09.

Thought:  The PR/press chatter is crowding out the substantive valuation memos.
          Tighten with accounting/disclosure vocabulary that the probative docs
          share but the press chatter does not.
Action:   search("raptor LJM hedge off balance sheet special purpose entity
                  accounting restatement")
Observation: Ranking shifts hard. Ken Lay's "SEC Information/Earnings
             Restatement" (off-balance-sheet disclosure) now dominates at 42.97;
             only 3/10 docs carry over from the first query, 7 are new. The
             disclosure/restatement core is now at the top.

Thought:  Pivot from topic to custodian — I want anything authored by Fastow,
          even though his mailbox isn't in the corpus.
Action:   search("raptor LJM special purpose entity mark to market",
                 sender_filter="fastow")
Observation: 5 real messages From andrew.fastow@enron.com (sitting in OTHER
             custodians' boxes). Top: "FW: Monday Meeting" (score 16.65) — Fastow
             writing that "it looks like LJM is be[ing favoured]". Custodian
             pivot succeeds despite the missing mailbox.

Thought:  Top of the list is now dense with valuation memos, the disclosure
          thread, and a Fastow original. Hand off to a human for the
          responsiveness/coverage decision.
```

**Tools called:** `search(query)`, `search(query)` (refined), `search(query,
sender_filter)`.

**Human-in-the-loop gate:** BM25 gives **review order**, not a responsiveness
ruling. The analyst (a human) decides where the responsive set ends, whether to
broaden custodians, and whether near-duplicate forwarded copies count once or
many times. The score never closes the matter.

**Failure mode:** keyword/stem ranking has **no semantics**. A message that says
"the structured-finance vehicles we used to keep debt off the books" without ever
typing *raptor*, *LJM*, or *SPE* will rank low or miss entirely — and conversely,
high-frequency mentions in irrelevant **press/PR chatter** rank spuriously high
(exactly what we saw at #1–3 in Query 1). Mitigation: query expansion / synonyms,
phrase + proximity queries, and ultimately human review — not blind trust in the
top-N.

---

## Verified output

Real head of `output.txt` (full file in this folder). Indexed **80,000**
messages; BM25 built in **3.7 s**; primary query ranked in **0.176 s**.

```
[1/4] Parsed 80,000 messages ... key custodians OK:
      skilling-j 4139 | lay-k 5937 | kaminski-v 28465 | buy-r 2429 |
      haedicke-m 5246 | derrick-j 1766 | sanders-r 7329 | delainey-d 3566 |
      whalley-g 1878 | kean-s 19245
[2/4] 80,000 docs, 17,414,728 tokens, 145,360 unique terms. avgdl=217.7. k1=1.5 b=0.75

TOP 10 — Query 1: raptor LJM special purpose entity mark to market
 #    score  date                       from                     subject
 1    29.09  Fri, 26 Oct 2001 ...       pr <.palmer@enron.com>   FW: Erroneous press
 2    29.01  Thu, 25 Oct 2001 ...       mark.koenig@enron.com    FW: Erroneous press
 3    29.01  Thu, 25 Oct 2001 ...       mark.koenig@enron.com    FW: Erroneous press
 4    26.17  Tue, 6 Nov 2001 ...        j.kaminski@enron.com     FW: LJM/Raptor valuations
 5    25.60  Tue, 6 Nov 2001 ...        j.kaminski@enron.com     FW: LJM/Raptor valuations
 6    25.60  Tue, 6 Nov 2001 ...        j.kaminski@enron.com     FW: LJM/Raptor valuations
 7    24.77  Mon, 8 Oct 2001 ...        j.kaminski@enron.com     FW: LJM/Raptor valuations
 8    24.67  Thu, 1 Nov 2001 ...        rick.buy@enron.com       FW: LJM/Raptor valuations
 9    24.31  Fri, 28 Dec 2001 ...       j.kaminski@enron.com     FW: Raptors
10    23.48  Thu, 4 Oct 2001 ...        j.kaminski@enron.com     LJM/Raptor valuations

TOP (refined) — Query 2: + hedge / off balance sheet / restatement
 1    42.97  Thu, 8 Nov 2001 ...        chairman.ken@enron.com   SEC Information/Earnings Restatement
 ...
 9    26.85  Mon, 26 Nov 2001 ...       vkaminski@aol.com        Fwd: FYI

TOP — Query 1 filtered to From ~ 'fastow'
 1    16.65  Mon, 16 Apr 2001 ...       andrew.fastow@enron.com  FW: Monday Meeting
 2     2.01  Tue, 26 Jun 2001 ...       andrew.fastow@enron.com  FW: MD PRC Committee
```

**Interpretation.** The primary query already pulls the substantive evidence to
the top: **Vince Kaminski's** "FW: LJM/Raptor valuations" thread (with **Rick
Buy**, the Chief Risk Officer, cc'd) — internal head-of-research correspondence
questioning the Raptor valuations — dominates ranks 4–10, exactly the probative
material an analyst wants first. The #1–3 "FW: Erroneous press" / Sherron Watkins
thread is a realistic **noise** result: it repeats "LJM" enough to score 29 even
though it is press-handling chatter, which is precisely why refinement is needed.
Adding accounting/disclosure terms (Query 2) reshuffles the list so **Ken Lay's**
"SEC Information/Earnings Restatement" (the off-balance-sheet disclosure memo)
jumps to **42.97** and only 3/10 docs carry over — a textbook demonstration that
BM25 re-weights toward the tighter intent. Finally, the sender filter recovers
five genuine **Andrew Fastow** emails (top: a real note that "it looks like LJM
is be[ing favoured]") even though his mailbox is absent from the corpus, proving
the custodian-pivot move on real data.

---

## Notes / deviations

* **Messages indexed:** **80,000** (the `MAX_MESSAGES` cap in `run.py`). Priority
  custodians are walked first, so all of them fall inside the cap.
* **Custodians indexed (Raptor/LJM-relevant subset):** `skilling-j` (4,139),
  `lay-k` (5,937), `kaminski-v` (28,465), `buy-r` (2,429), `haedicke-m` (5,246),
  `derrick-j` (1,766), `sanders-r` (7,329), `delainey-d` (3,566), `whalley-g`
  (1,878), `kean-s` (19,245), plus messages from the alphabetically-early
  custodians that extracted before the subset switch — 80,000 total.
* **Why a subset, not the full 500k:** extracting ~500k tiny files onto a
  Windows-mounted volume (`/mnt/d` under WSL2) is I/O-bound and effectively
  stalls for hours (`tar` sits in uninterruptible-sleep). The brief explicitly
  permits indexing a subset that still includes the scenario custodians, so we
  extracted those custodian subtrees directly with `tar -xzf ... maildir/<name>`.
  The download itself was the full, integrity-checked archive (520,901 entries).
* **Fastow / Causey mailboxes are not in the corpus** — a real property of the
  FERC/CMU release. We substituted the present Raptor/LJM-relevant custodians
  (Kaminski, Buy, legal). Fastow still surfaces via the **sender filter** because
  his messages live in other custodians' boxes.
* **Near-duplicate hits** (e.g. the same "FW: LJM/Raptor valuations" appearing
  more than once) are genuine — the corpus keeps separate sent/inbox/forwarded
  copies. De-duplication by `Message-ID` would be the next refinement; we left
  them in so the duplication is visible to students.
* **Size correction:** the archive is ~443 MB gzipped (not the ~1.7 GB the brief
  estimated); ~2.6 GB unpacked.
