# tests/benchmark_grounding.py
#
# Phase 3 grounding benchmark: does the evidence-sufficiency layer
# distinguish "relevant text" from "sufficient evidence"?
#
# Categories (#31 / #32):
#   supported            - the book really answers these
#   unsupported_probe    - lexical false positives (the two known cases)
#   off_topic            - non-biology questions
#   multi_page           - questions the book answers across pages
#   conceptual           - biology questions needing synthesis
#
# Reported for each question:
#   score gate   - old behaviour (retrieval confidence >= 0.55)
#   sufficiency  - new behaviour (evidence_sufficiency verdict)
#
# An accurate sufficiency layer may safely GROUND fewer questions than
# the score gate, because "not grounded" no longer means "no answer" -
# it means "answer honestly from general knowledge".
#
# Run: .venv/bin/python tests/benchmark_grounding.py

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import Science.Biology.biology_retriever as br
from config import GROUNDING_THRESHOLD
from evidence_sufficiency import assess_evidence


# (category, question, book_should_answer: bool)
CASES = [
    # --- supported -------------------------------------------------
    ("supported", "What is photosynthesis?", True),
    ("supported", "Explain mitosis.", True),
    ("supported", "What is the function of mitochondria?", True),
    ("supported", "Explain the stages of meiosis.", True),
    ("supported", "How does ultrafiltration work in the nephron?", True),
    ("supported", "What are enzymes and how do they work?", True),
    ("supported", "Explain the light reaction of photosynthesis.", True),
    ("supported", "What is DNA replication?", True),
    ("supported", "Describe the structure of the cell membrane.", True),
    ("supported", "How is glucose broken down in glycolysis?", True),

    # --- multi_page ------------------------------------------------
    ("multi_page", "Explain respiration from glycolysis to the electron "
                   "transport chain.", True),
    ("multi_page", "Compare mitosis and meiosis.", True),
    ("multi_page", "How does the nervous system transmit signals?", True),
    ("multi_page", "Describe the human digestive system and absorption "
                   "of food.", True),

    # --- conceptual (needs synthesis, book supports it) ------------
    ("conceptual", "Why is chlorophyll important for plants?", True),
    ("conceptual", "Why does crossing over increase genetic variation?", True),
    ("conceptual", "Why is meiosis important?", True),
    ("conceptual", "How does the kidney maintain water balance?", True),

    # --- unsupported probes (lexical false positives, #32) ---------
    ("unsupported_probe",
     "Describe the role of the enzyme phosphofructokinase-1 in glycolysis.",
     False),
    ("unsupported_probe",
     "How does mRNA vaccine technology deliver antigens to cells?",
     False),
    ("unsupported_probe",
     "How many ATP molecules does hexokinase consume in the "
     "mitochondrial matrix?",
     False),
    ("unsupported_probe",
     "Explain the CRISPR-Cas9 gene editing mechanism in detail.",
     False),

    # --- off_topic -------------------------------------------------
    ("off_topic", "Who won the 2022 FIFA World Cup, and why?", False),
    ("off_topic", "Solve this quadratic equation for x: x^2 - 5x + 6 = 0",
     False),
    ("off_topic", "Write a Python function that reverses a string.", False),
    ("off_topic", "What is the stock price of Apple?", False),
]

CATEGORIES = [
    "supported", "multi_page", "conceptual",
    "unsupported_probe", "off_topic",
]


def main() -> None:
    print("=" * 78)
    print("Grounding benchmark: score gate vs evidence sufficiency")
    print("=" * 78)

    assert br.initialize_retriever(), "retriever failed to initialise"

    rows = []
    timings = {"retrieval_ms": 0.0, "sufficiency_ms": 0.0}

    for category, question, should_answer in CASES:
        t0 = time.perf_counter()
        retrieval = br.retrieve_biology(question)
        t1 = time.perf_counter()
        assessment = assess_evidence(question, retrieval)
        t2 = time.perf_counter()

        timings["retrieval_ms"] += (t1 - t0) * 1000
        timings["sufficiency_ms"] += (t2 - t1) * 1000

        score_gate = retrieval.grounded and (
            retrieval.confidence >= GROUNDING_THRESHOLD
        )
        sufficiency = (
            assessment.sufficient
            if retrieval.grounded
            else False
        )

        rows.append({
            "category": category,
            "question": question,
            "should": should_answer,
            "confidence": retrieval.confidence,
            "score_gate": score_gate,
            "verdict": assessment.verdict,
            "sufficiency": sufficiency,
            "suff_score": assessment.score,
            "coverage": assessment.signals.get("term_coverage", 0.0),
            "critical_gap": assessment.critical_gap,
        })

    # --------------------------------------------------------------
    # Per-category results
    # --------------------------------------------------------------
    print()
    print(f"{'category':<18} {'n':>3} "
          f"{'gate ok':>8} {'suff ok':>8} "
          f"{'gate acc':>9} {'suff acc':>9}")
    print("-" * 78)

    totals = {"n": 0, "gate_ok": 0, "suff_ok": 0}

    for category in CATEGORIES:
        subset = [r for r in rows if r["category"] == category]
        if not subset:
            continue

        gate_ok = sum(
            1 for r in subset
            if r["score_gate"] == r["should"]
        )
        suff_ok = sum(
            1 for r in subset
            if r["sufficiency"] == r["should"]
        )
        n = len(subset)

        print(f"{category:<18} {n:>3} {gate_ok:>8} {suff_ok:>8} "
              f"{gate_ok / n:>8.0%} {suff_ok / n:>9.0%}")

        totals["n"] += n
        totals["gate_ok"] += gate_ok
        totals["suff_ok"] += suff_ok

    print("-" * 78)
    n = totals["n"]
    print(f"{'OVERALL':<18} {n:>3} "
          f"{totals['gate_ok']:>8} {totals['suff_ok']:>8} "
          f"{totals['gate_ok'] / n:>8.0%} {totals['suff_ok'] / n:>9.0%}")

    # --------------------------------------------------------------
    # Detail table
    # --------------------------------------------------------------
    print()
    print(f"{'verdict':<13} {'conf':>5} {'suff':>5} {'cov':>5}  "
          f"question")
    print("-" * 78)
    for r in rows:
        verdict_tag = {"sufficient": "SUFF", "partial": "PART",
                       "insufficient": "INSU"}[r["verdict"]]
        marker = "ok " if r["sufficiency"] == r["should"] else "!! "
        print(f"{marker}{verdict_tag:<9} {r['confidence']:>5.2f} "
              f"{r['suff_score']:>5.2f} {r['coverage']:>5.2f}  "
              f"{r['question'][:58]}")

    # --------------------------------------------------------------
    # Latency
    # --------------------------------------------------------------
    n_cases = len(CASES)
    print()
    print(f"retrieval:   {timings['retrieval_ms'] / n_cases:.1f} ms/query "
          f"(includes index init on first call)")
    print(f"sufficiency: {timings['sufficiency_ms'] / n_cases:.1f} ms/query")

    failed = [r for r in rows if r["sufficiency"] != r["should"]]
    if failed:
        print(f"\nmisjudged by sufficiency ({len(failed)}):")
        for r in failed:
            print(f"  {r['category']:<18} {r['question'][:60]} "
                  f"-> {r['verdict']}")
    else:
        print("\nall categories judged correctly")


if __name__ == "__main__":
    main()
