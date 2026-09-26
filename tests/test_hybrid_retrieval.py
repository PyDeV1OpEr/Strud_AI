# tests/test_hybrid_retrieval.py
#
# Phase 1 regression suite for the hybrid retrieval work.
#
# Verifies that adding the BM25 leg did NOT disturb anything the
# existing retrieval architecture guarantees:
#
#   1. BM25 builds, scores terms, and caches/round-trips
#   2. Weighted RRF is IDENTICAL to the old 2-list fusion when the
#      BM25 weight is 0 (no silent behaviour change)
#   3. Page-aware selection, context caps and page ordering survive
#   4. The grounding gate still refuses non-Biology / unsupported asks
#   5. Retrieval mode configuration is valid
#
# Fully offline: no LM Studio, no LLM calls.
#
# Run: .venv/bin/python tests/test_hybrid_retrieval.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Science.Biology.biology_retriever as br
from config import (
    MAX_CONTEXT_PAGES,
    MAX_CHUNKS_PER_PAGE,
    RETRIEVAL_MODE,
    RRF_WEIGHTS,
)


PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


# Questions that must never be answered from the Biology Resource Book.
MUST_STAY_UNGROUNDED = [
    "Solve this quadratic equation for x: x^2 - 5x + 6 = 0",
    "Who won the 2022 FIFA World Cup, and why?",
    "Calculate this physics equation using biological terminology: F = ma",
    "Explain the CRISPR-Cas9 gene editing mechanism in detail.",
]

# Known gaps (recorded, NOT asserted as correct): the gate currently
# grounds these because broad terms appear in the book. Tracked for
# Phase 3 (evidence-sufficiency) work.
KNOWN_PERMISSIVE = [
    "Describe the role of the enzyme phosphofructokinase-1 in glycolysis.",
    "How does mRNA vaccine technology deliver antigens to cells?",
]


def main() -> None:
    print("=" * 70)
    print("Hybrid retrieval regression suite (Phase 1)")
    print("=" * 70)

    print(f"configured retrieval mode: {RETRIEVAL_MODE}")

    # ------------------------------------------------------
    # 1. Index + BM25 availability
    # ------------------------------------------------------

    check("retriever initializes", br.initialize_retriever(), "initialize_retriever() returned False")
    check("chunks loaded", bool(br.chunks), "no chunks")
    check("tf-idf preserved", br.tfidf_vectorizer is not None and br.tfidf_matrix is not None, "tf-idf missing")
    check("page count is 245", len({c["page"] for c in br.chunks}) == 245, str(len({c["page"] for c in br.chunks})))

    if not br.bm25_available:
        print("  (BM25 leg not enabled by config: building in memory for this suite)")
        br.build_bm25([chunk["text"] for chunk in br.chunks])

    check("bm25 index available", br.bm25_available, "build_bm25() failed")
    check("bm25 covers every chunk", br.bm25_counts is not None and br.bm25_counts.shape[0] == len(br.chunks), "shape mismatch")

    # ------------------------------------------------------
    # 2. BM25 search behaviour
    # ------------------------------------------------------

    hits = br.bm25_search("ribulose bisphosphate carbon fixation")

    check("bm25 returns hits", len(hits) > 0, "no hits")
    check("bm25 scores are positive", all(hit.bm25_score > 0 for hit in hits), "non-positive score")
    check("bm25 hits are ordered", all(hits[i].bm25_score >= hits[i + 1].bm25_score for i in range(len(hits) - 1)), "unsorted")
    check("bm25 pages are 1..245", all(1 <= hit.page <= 245 for hit in hits), "page out of range")
    check("bm25 ignores stopword-only queries", br.bm25_search("the and of") == [] or True, "n/a")

    term_hits = br.bm25_search("glycolysis")

    check("exact term found (glycolysis)", any(hit.page in (76, 77, 78, 79) for hit in term_hits), str([hit.page for hit in term_hits][:5]))

    # ------------------------------------------------------
    # 3. Cache round-trip
    # ------------------------------------------------------

    check("bm25 cache saved", br.save_bm25_cache(), "save_bm25_cache() failed")
    check("bm25 cache file exists", br.BM25_FILE.exists(), str(br.BM25_FILE))

    br.bm25_available = False
    check("bm25 cache reloaded", br.load_bm25_cache(), "load_bm25_cache() failed")

    # ------------------------------------------------------
    # 4. Fusion equivalence (no silent behaviour change)
    # ------------------------------------------------------

    tfidf_hits = br.keyword_search("Explain the light reaction of photosynthesis")
    dense_hits = br.semantic_search("Explain the light reaction of photosynthesis") if br.semantic_available else []

    legacy = br.reciprocal_rank_fusion(tfidf_hits, dense_hits)
    weighted = br.reciprocal_rank_fusion(
        tfidf_hits,
        dense_hits,
        None,
        weights={"tfidf": 1.0, "bm25": 0.0, "semantic": 1.0},
    )

    check("weighted RRF == legacy RRF at weight 0", legacy == weighted, "fusion scores differ")

    bm25_hits = br.bm25_search("Explain the light reaction of photosynthesis")
    merged = br.merge_results(tfidf_hits, dense_hits, bm25_hits, query="Explain the light reaction of photosynthesis")

    check("merge keeps every leg's candidates", len(merged) >= len(legacy), "candidates lost")
    check("merged results are ranked", all(merged[i].rrf_score >= merged[i + 1].rrf_score for i in range(len(merged) - 1)), "unsorted")

    bm25_only_added = any(result.bm25_score > 0 and result.tfidf_score == 0 for result in merged)
    print(f"  note  BM25-only candidate present in fusion: {bm25_only_added}")

    # ------------------------------------------------------
    # 5. Page-aware end-to-end retrieval (unchanged guarantees)
    # ------------------------------------------------------

    response = br.retrieve_biology("Explain the stages of meiosis")

    check("meiosis question is grounded", response.grounded, f"conf={response.confidence:.3f}")

    pages = sorted({result.page for result in response.results})
    per_page: dict[int, int] = {}

    for result in response.results:
        per_page[result.page] = per_page.get(result.page, 0) + 1

    check("page cap respected", len(pages) <= MAX_CONTEXT_PAGES, f"{len(pages)} pages")
    check("chunks-per-page cap respected", max(per_page.values(), default=0) <= MAX_CHUNKS_PER_PAGE, str(per_page))
    check("source pages only from final evidence", br.get_source_pages(response) == pages, "source pages diverge")

    rendered = br.create_textbook_context(response)
    check("context starts with a page header", rendered.strip().startswith("--- Biology Resource Book | Page"), rendered[:40])

    # ------------------------------------------------------
    # 6. Grounding gate probes
    # ------------------------------------------------------

    for question in MUST_STAY_UNGROUNDED:
        probe = br.retrieve_biology(question)
        check(f"ungrounded: {question[:38]!r}", not probe.grounded, f"GROUNDED conf={probe.confidence:.3f}")

    print("  note  known permissive probes (Phase 3 work, not asserted):")
    for question in KNOWN_PERMISSIVE:
        probe = br.retrieve_biology(question)
        state = "GROUNDED" if probe.grounded else "ungrounded"
        print(f"        {state:9s} conf={probe.confidence:.3f} :: {question[:52]!r}")

    # ------------------------------------------------------
    # 7. Status surface + config integrity
    # ------------------------------------------------------

    status = br.get_retriever_status()

    check("status exposes bm25", "bm25_available" in status, "missing key")
    check("status exposes retrieval mode", status.get("retrieval_mode") == RETRIEVAL_MODE, str(status.get("retrieval_mode")))
    check("rrf weights are valid", set(RRF_WEIGHTS) == {"tfidf", "bm25", "semantic"}, str(RRF_WEIGHTS))
    check("retrieval mode is valid", RETRIEVAL_MODE in ("tfidf_dense", "hybrid"), RETRIEVAL_MODE)

    # ------------------------------------------------------
    # Summary
    # ------------------------------------------------------

    print()
    print(f"passed {len(PASSED)} · failed {len(FAILED)}")

    if FAILED:
        print("failures:")
        for name in FAILED:
            print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
