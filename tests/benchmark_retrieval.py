# tests/benchmark_retrieval.py
#
# Retrieval benchmark for Strud AI (Phase 1 of the upgrade plan).
#
# WHY THIS EXISTS
#   The upgrade brief forbids replacing TF-IDF (or claiming an
#   improvement) without measuring it first. This harness ranks the
#   same Biology questions with every retrieval leg and with every
#   hybrid fusion, on a gold-labelled page set, and prints honest
#   numbers. Nothing here changes runtime behaviour.
#
# WHAT IS MEASURED (page level, because pages are what Strud cites)
#   cover@20 : the gold page appears somewhere in the top-20 chunks
#   recall@5 : the gold page appears in the top-5 DISTINCT pages
#              (this mirrors MAX_CONTEXT_PAGES = 5)
#   MRR      : reciprocal rank of the first gold page
#   top-1    : the very first page of the ranking is a gold page
#   rank     : mean rank of the first gold page (lower is better)
#   ms/query : mean leg latency
#
# GOLD LABELS
#   Each case is (question, gold_pages, anchors). A case is only kept
#   if EVERY gold page really contains one of the anchors. Cases that
#   fail that check are reported and dropped, so a label mistake can
#   never silently inflate the scores.
#
# USE
#   .venv/bin/python tests/benchmark_retrieval.py
#
# There is no LM Studio requirement: retrieval is fully local.

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import Science.Biology.biology_retriever as br


# ============================================================
# EVALUATION SET
# ============================================================
#
# category "content"      : page located by reading the page itself
# category "terminology"  : exact-terminology question; gold pages are
#                           the pages where that term is discussed
# category "paraphrase"   : wording deliberately unlike the textbook

CASES = [
    # ---------------- content (single page) ----------------
    ("content", "Which elements make up about 96% of living matter?",
     [15], ["96%"]),
    ("content", "What is the function of messenger RNA?",
     [30], ["Messenger RNA"]),
    ("content", "Describe the 9+2 arrangement found in cilia and flagella",
     [45], ["9+2"]),
    ("content", "How do enzymes act as biological catalysts?",
     [60], ["biological catalyst"]),
    ("content", "What factors affect the rate of photosynthesis?",
     [75], ["Factors affecting photosynthesis"]),
    ("content", "How is the author's name shown when writing a scientific name?",
     [90], ["Linnaeus"]),
    ("content", "What are the characteristics of Phylum Basidiomycota?",
     [105], ["Basidiomycota"]),
    ("content", "Why did vascular tissues evolve in land plants?",
     [135], ["vascular tissues"]),
    ("content", "Explain alternation of generations in land plants",
     [150], ["alternation of generations"]),
    ("content", "What are the four major types of animal tissues?",
     [165], ["Epithelial tissue"]),
    ("content", "Where is most of the water reabsorbed in the alimentary canal?",
     [180], ["reabsorbed"]),
    ("content", "Trace the path of oxygenated blood from the lungs to the body",
     [195], ["pulmonary veins"]),
    ("content", "What are the major parts of the human respiratory system?",
     [210], ["nostrils"]),
    ("content", "Where do T lymphocytes mature in humans?",
     [225], ["thymus"]),
    ("content", "How does ADH increase water reabsorption in the distal convoluted tubule?",
     [240], ["ADH"]),
    ("content", "What kind of plastids store materials in plant cells?",
     [120], ["leucoplasts"]),

    # ---------------- exact terminology (multi page) ----------------
    ("terminology", "Explain the process of glycolysis",
     [76, 77, 78, 79], ["glycolysis"]),
    ("terminology", "What is the role of ribulose bisphosphate in carbon fixation?",
     [70], ["ribulose bisphosphate"]),
    ("terminology", "Which reactions make up the Calvin cycle?",
     [67, 70, 71], ["calvin cycle"]),
    ("terminology", "Describe the light reaction of photosynthesis",
     [67, 69, 70, 71], ["light reaction"]),
    ("terminology", "Explain meiosis and its role in gamete formation",
     [52, 53, 54, 55, 56], ["meiosis"]),
    ("terminology", "How does transpiration pull water up through the plant?",
     [140, 141, 143], ["transpiration"]),
    ("terminology", "What is osmosis?",
     [134, 135, 136, 137, 138, 139], ["osmosis"]),
    ("terminology", "Where does filtration of blood take place in the nephron?",
     [236, 237, 238, 239], ["glomerulus"]),

    # ---------------- paraphrased wording ----------------
    ("paraphrase", "How do plants turn sunlight into chemical energy stored in food?",
     [67, 70, 71, 75], ["photosynthesis"]),
    ("paraphrase", "How does the kidney remove waste from the blood?",
     [236, 237, 238, 239, 240],
     ["kidney", "urine", "nephron", "glomerulus", "ultrafiltration"]),
    ("paraphrase", "How does the body defend itself against pathogens that have infected it?",
     [225], ["lymphocytes"]),
    ("paraphrase", "Why do plants lose water vapour through their leaves?",
     [140, 141, 143], ["transpiration"]),
]


# ============================================================
# GATE PROBES
# ============================================================
#
# Questions that must NOT be answered from the textbook. These check
# that the grounding gate still refuses weak/absent evidence after a
# retrieval leg is added.

GATE_PROBES = [
    ("non-biology", "Solve this quadratic equation for x: x^2 - 5x + 6 = 0"),
    ("non-biology", "Who won the 2022 FIFA World Cup, and why?"),
    ("non-biology", "Calculate this physics equation using biological terminology: F = ma"),
    ("unsupported", "Explain the CRISPR-Cas9 gene editing mechanism in detail."),
    ("unsupported", "Describe the role of the enzyme phosphofructokinase-1 in glycolysis."),
    ("unsupported", "How does mRNA vaccine technology deliver antigens to cells?"),
]


# ============================================================
# HELPERS
# ============================================================

def normalise(text: str) -> str:
    return " ".join((text or "").split()).lower()


def build_page_text_map():
    """page -> normalised text of every chunk on that page."""
    pages: dict[int, list[str]] = {}

    for chunk in br.chunks:
        pages.setdefault(int(chunk["page"]), []).append(
            normalise(chunk["text"])
        )

    return {page: " ".join(parts) for page, parts in pages.items()}


def validate_cases(page_texts: dict[int, str]):
    """Drop cases whose gold pages do not contain any anchor."""
    kept = []
    dropped = []

    for category, question, gold, anchors in CASES:
        missing = [
            page
            for page in gold
            if not any(anchor.lower() in page_texts.get(page, "") for anchor in anchors)
        ]

        if missing:
            dropped.append((question, missing))
            gold = [page for page in gold if page not in missing]

        if not gold:
            dropped.append((question, "ALL gold pages unverified"))
            continue

        kept.append((category, question, gold, anchors))

    return kept, dropped


def page_ranking(chunks_ranked) -> list[int]:
    """Distinct pages in the order they first appear in a chunk ranking."""
    pages: list[int] = []

    for result in chunks_ranked:
        if result.page not in pages:
            pages.append(result.page)

    return pages


def fused_ranking(tf, sem, bm, question, weights):
    """Mirror merge_results() but with explicit per-leg weights."""
    scores = br.reciprocal_rank_fusion(tf, sem, bm, weights=weights)

    items = {}

    for result in list(tf) + list(sem) + list(bm):
        items.setdefault(result.index, result)

    for index, score in scores.items():
        result = items[index]
        result.rrf_score = score + br.calculate_phrase_boost(question, result.text)

    return sorted(items.values(), key=lambda r: r.rrf_score, reverse=True)


# ============================================================
# LANES
# ============================================================

def evaluate(lanes, cases, page_texts):
    table = {}

    for name, runner in lanes.items():
        rows = []
        timings = []

        for category, question, gold, _anchors in cases:
            started = time.perf_counter()
            ranked, elapsed = runner(question)
            timings.append(elapsed if elapsed is not None else (time.perf_counter() - started))

            pages = page_ranking(ranked)

            gold_set = set(gold)
            chunk_pages = {result.page for result in ranked[:20]}

            cover = 1.0 if chunk_pages & gold_set else 0.0
            recall5 = 1.0 if set(pages[:5]) & gold_set else 0.0
            top1 = 1.0 if pages and pages[0] in gold_set else 0.0

            rank = 0
            for position, page in enumerate(pages, start=1):
                if page in gold_set:
                    rank = position
                    break

            rows.append({
                "category": category,
                "question": question,
                "gold": sorted(gold_set),
                "cover": cover,
                "recall5": recall5,
                "top1": top1,
                "mrr": (1.0 / rank) if rank else 0.0,
                "rank": rank or 0,
                "pages": pages[:5],
                "hits": rank > 0,
            })

        table[name] = {
            "rows": rows,
            "ms": 1000.0 * sum(timings) / max(len(timings), 1),
        }

    return table


def summarise(rows):
    total = len(rows)

    return {
        "cover": sum(row["cover"] for row in rows) / total,
        "recall5": sum(row["recall5"] for row in rows) / total,
        "mrr": sum(row["mrr"] for row in rows) / total,
        "top1": sum(row["top1"] for row in rows) / total,
        "rank": sum(row["rank"] for row in rows if row["rank"]) / max(
            sum(1 for row in rows if row["rank"]), 1
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("=" * 78)
    print("STRUD retrieval benchmark — Phase 1 (BM25 + hybrid fusion)")
    print("=" * 78)

    started = time.perf_counter()
    ok = br.initialize_retriever()
    init_seconds = time.perf_counter() - started

    if not ok or not br.chunks:
        print("Retriever could not be initialized. Aborting.")
        return

    print(f"Index ready in {init_seconds:.2f}s")
    print(f"  pages           : {len({c['page'] for c in br.chunks})}")
    print(f"  chunks          : {len(br.chunks)}")
    print(f"  tf-idf          : {br.tfidf_vectorizer is not None}")
    print(f"  dense (MiniLM)  : {br.semantic_available}")
    print(f"  configured mode : {br.RETRIEVAL_MODE}")

    if not br.bm25_available:
        print("  bm25            : building in memory (config mode is not hybrid)")
        br.build_bm25([chunk["text"] for chunk in br.chunks])

    if not br.bm25_available:
        print("BM25 could not be built. Aborting.")
        return

    print(f"  bm25            : True (vocabulary {br.bm25_counts.shape[1]:,} terms)")
    print()

    page_texts = build_page_text_map()
    cases, dropped = validate_cases(page_texts)

    if dropped:
        print("Dropped cases (anchor not found on gold page):")
        for question, pages in dropped:
            print(f"  - {question!r}: {pages}")
        print()

    dense = bool(br.semantic_available and br.semantic_embeddings is not None)

    def leg_tfidf(question):
        started = time.perf_counter()
        results = br.keyword_search(question)
        return results, time.perf_counter() - started

    def leg_bm25(question):
        started = time.perf_counter()
        results = br.bm25_search(question)
        return results, time.perf_counter() - started

    def leg_dense(question):
        started = time.perf_counter()
        results = br.semantic_search(question)
        return results, time.perf_counter() - started

    def fused(weights):
        def runner(question):
            started = time.perf_counter()
            tfidf_hits = leg_tfidf(question)[0]
            bm25_hits = leg_bm25(question)[0]
            dense_hits = leg_dense(question)[0] if dense else []
            ranked = fused_ranking(
                tfidf_hits, dense_hits, bm25_hits, question, weights
            )
            return ranked, time.perf_counter() - started

        return runner

    weights_current = {"tfidf": 1.0, "bm25": 0.0, "semantic": 1.0}
    weights_hybrid = {"tfidf": 1.0, "bm25": 1.0, "semantic": 1.0}
    weights_hybrid_bm25_lead = {"tfidf": 0.5, "bm25": 1.0, "semantic": 1.0}
    weights_bm25_dense = {"tfidf": 0.0, "bm25": 1.0, "semantic": 1.0}
    weights_tfidf_bm25 = {"tfidf": 1.0, "bm25": 1.0, "semantic": 0.0}
    weights_bm25_half = {"tfidf": 1.0, "bm25": 0.5, "semantic": 1.0}
    weights_bm25_quarter = {"tfidf": 1.0, "bm25": 0.25, "semantic": 1.0}

    lanes = {
        "tfidf only": leg_tfidf,
        "bm25 only": leg_bm25,
    }

    if dense:
        lanes["dense only"] = leg_dense

    fusion_lanes = {
        "tfidf + dense (current)": weights_current,
        "bm25 + dense": weights_bm25_dense,
        "tfidf + bm25": weights_tfidf_bm25,
        "tfidf + bm25 + dense": weights_hybrid,
        "bm25 1.0 lead + tfidf + dense": weights_hybrid_bm25_lead,
        "bm25 0.5 + tfidf + dense": weights_bm25_half,
        "bm25 0.25 + tfidf + dense": weights_bm25_quarter,
    }

    if not dense:
        fusion_lanes = {
            "tfidf + bm25": weights_tfidf_bm25,
        }
        print("Dense leg unavailable: skipping dense lanes.\n")

    for name, weights in fusion_lanes.items():
        if not dense and weights.get("semantic", 0.0) > 0:
            continue
        lanes[name] = fused(weights)

    results = evaluate(lanes, cases, page_texts)

    header = f"{'lane':30s} {'cover@20':>9s} {'recall@5':>9s} {'MRR':>7s} {'top-1':>7s} {'mean rank':>10s} {'ms/query':>9s}"
    print(header)
    print("-" * len(header))

    for name in lanes:
        stats = summarise(results[name]["rows"])
        print(
            f"{name:30s} "
            f"{stats['cover']*100:8.1f}% "
            f"{stats['recall5']*100:8.1f}% "
            f"{stats['mrr']:7.3f} "
            f"{stats['top1']*100:6.1f}% "
            f"{stats['rank']:10.1f} "
            f"{results[name]['ms']:9.1f}"
        )

    # --------------------------------------------------------
    # Per-category breakdown for the two pipelines that matter
    # --------------------------------------------------------

    print()
    print("Per-category recall@5")
    print(f"{'lane':30s} {'content':>10s} {'terminology':>12s} {'paraphrase':>11s}")
    print("-" * 66)

    for name in lanes:
        rows = results[name]["rows"]
        line = f"{name:30s}"
        for category in ("content", "terminology", "paraphrase"):
            subset = [row for row in rows if row["category"] == category]
            value = (
                sum(row["recall5"] for row in subset) / len(subset) * 100
                if subset
                else 0.0
            )
            line += f" {value:9.1f}%"
        print(line)

    # --------------------------------------------------------
    # BM25 score distribution (used to calibrate the quality band)
    # --------------------------------------------------------

    print()
    print("BM25 raw score of the best hit per question (calibration)")

    best_scores = []

    for _category, question, _gold, _anchors in cases:
        hits = br.bm25_search(question)

        if hits:
            best_scores.append(hits[0].bm25_score)

    if best_scores:
        array = np.asarray(best_scores)
        print(
            f"  min {array.min():.2f} · p25 {np.percentile(array, 25):.2f} · "
            f"median {np.median(array):.2f} · p75 {np.percentile(array, 75):.2f} · "
            f"max {array.max():.2f}"
        )
        print(
            f"  current BM25_MIN_QUALITY = {br.BM25_MIN_QUALITY}, "
            f"BM25_MAX_QUALITY = {br.BM25_MAX_QUALITY}"
        )

    # --------------------------------------------------------
    # Misses for the proposed hybrid lane
    # --------------------------------------------------------

    for wanted in ("tfidf + bm25 + dense", "tfidf + dense (current)"):
        if wanted not in results:
            continue

        misses = [row for row in results[wanted]["rows"] if not row["recall5"]]

        print()
        print(f"recall@5 misses — {wanted}: {len(misses)}/{len(cases)}")

        for row in misses:
            print(
                f"  [{row['category']}] {row['question'][:58]!r}\n"
                f"      gold {row['gold']} · top-5 pages {row['pages']}"
            )

    # --------------------------------------------------------
    # Grounding gate probes (end-to-end retrieve_biology)
    # --------------------------------------------------------

    print()
    print("Grounding gate probes (must stay UNGROUNDED)")
    print(f"  configured mode: {br.RETRIEVAL_MODE}")

    for category, question in GATE_PROBES:
        response = br.retrieve_biology(question)
        pages = sorted({result.page for result in response.results})
        verdict = "GROUNDED" if response.grounded else "ungrounded"
        flag = "" if not response.grounded else "   <-- CHECK"
        print(
            f"  [{category:11s}] {verdict:9s} conf={response.confidence:.3f} "
            f"pages={pages[:6]} :: {question[:52]}{flag}"
        )

    print()
    print("Note: this benchmark measures RETRIEVAL only. Generation quality,")
    print("citation correctness and guardrail behaviour are separate suites.")


if __name__ == "__main__":
    main()
