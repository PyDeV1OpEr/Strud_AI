# evidence_sufficiency.py
#
# Evidence-sufficiency stage for Strud AI (Phase 3).
#
# WHY THIS EXISTS
# ---------------
# Retrieval gives us passages that are *relevant*. Relevance is not
# evidence. A high retrieval score (or, later, a high cross-encoder
# score) only means "these words look like the question". It does NOT
# mean the passages can actually answer the question.
#
# The two known Strud false positives make this concrete:
#
#   "Describe the role of the enzyme phosphofructokinase-1 in ..."
#   "How does mRNA vaccine technology deliver antigens to cells?"
#
# Both grounded (0.697 / 0.624) because ordinary glycolysis / mRNA
# pages matched. But the resource book never mentions the distinctive
# concept the student actually asked about, so there was nothing to
# ground an answer on.
#
# WHAT IT DOES
# ------------
# After retrieval (and after any future reranking), this module
# combines several *independent* signals:
#
#   1. term coverage   - IDF-weighted share of the question's
#                        distinctive terms that actually occur in the
#                        retrieved evidence (measured against what the
#                        model will really see, not the raw index)
#   2. critical gap    - the strongest concept in the question does not
#                        exist anywhere in the indexed textbook at all
#   3. multi-leg agreement - do lexical and dense retrieval agree on
#                        the same page? (guards the BM25 false lift)
#   4. support breadth - how many distinct pages independently carry
#                        relevant material
#   5. chunk relevance - how strong the best chunks actually are
#
# No single score decides grounding, and no arbitrary threshold was
# invented blindly: the constants below are validated by
# tests/benchmark_grounding.py (supported / unsupported / lexical
# false-positive / off-topic categories).
#
# The verdict is deliberately conservative. "partial" means: we have
# related textbook material but not enough to answer as asked, so the
# answer must be honest about that instead of claiming textbook
# support.

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from config import (
    EVIDENCE_SUFFICIENCY_THRESHOLD,
    EVIDENCE_PARTIAL_THRESHOLD,
    EVIDENCE_MIN_TERM_COVERAGE,
    EVIDENCE_MIN_SUPPORTING_PAGES,
    EVIDENCE_CRITICAL_TERM_RATIO,
    EVIDENCE_CHUNK_RELEVANCE_FLOOR,
    TFIDF_MIN_QUALITY,
    TFIDF_MAX_QUALITY,
    SEMANTIC_MIN_QUALITY,
    SEMANTIC_MAX_QUALITY,
)


# ============================================================
# VERDICTS
# ============================================================

SUFFICIENT = "sufficient"
PARTIAL = "partial"
INSUFFICIENT = "insufficient"


@dataclass
class EvidenceAssessment:
    """
    The answer to: "is there enough evidence to answer this?"

    verdict         - sufficient | partial | insufficient
    sufficient      - shortcut for verdict == "sufficient"
    score           - 0..1 combined sufficiency score
    signals         - every individual signal, for /debug output
    reason          - one short human sentence (debug only)
    supporting_pages - pages with at least one relevant chunk
    missing_terms   - distinctive question terms absent from the evidence
    critical_gap    - True when the textbook cannot answer as asked
    """

    verdict: str = INSUFFICIENT
    sufficient: bool = False
    score: float = 0.0
    signals: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    supporting_pages: list[int] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    critical_gap: bool = False

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "sufficient": self.sufficient,
            "score": round(self.score, 3),
            "critical_gap": self.critical_gap,
            "supporting_pages": list(self.supporting_pages),
            "missing_terms": list(self.missing_terms),
            "reason": self.reason,
            "signals": {
                key: (round(value, 3) if isinstance(value, float) else value)
                for key, value in self.signals.items()
            },
        }


# ============================================================
# TOKENISATION / NORMALISATION
# ============================================================

_TOKEN_PATTERN = re.compile(r"[a-z][a-z\-]{2,}")

# Words that carry no topical meaning in a question. Deliberately
# small: anything larger starts deleting real biology vocabulary.
_QUESTION_NOISE = {
    "explain", "describe", "discuss", "define", "definition", "meaning",
    "tell", "about", "give", "show", "help", "please", "according",
    "textbook", "book", "resource", "page", "pages", "chapter",
    "what", "which", "when", "where", "why", "how", "does", "doing",
    "with", "from", "into", "that", "this", "these", "those", "there",
    "their", "them", "then", "than", "some", "your", "yours", "you",
    "and", "the", "for", "are", "was", "were", "will", "would", "can",
    "could", "should", "may", "might", "must", "not", "but", "its",
    "it", "is", "of", "in", "on", "to", "at", "as", "or", "if", "so",
    "also", "more", "most", "very", "really", "actually", "basic",
    "basics", "detail", "details", "detailedly", "fully", "again",
    "bro", "bruh", "dude", "ngl", "tbh", "lol", "lowkey", "highkey",
    "yo", "sup", "hey", "hi", "hello", "umm", "uhh", "okay", "ok",
    "yeah", "yep", "nah", "wait", "huh", "wow", "damn", "much",
    "want", "need", "know", "understand", "get", "got", "think",
    "like", "just", "now", "here", "thing", "things", "stuff",
    "question", "questions", "answer", "answers", "test", "quiz",
    "harder", "easier", "one", "two", "second", "first", "next",
    "same", "different", "difference", "between", "compare",
    "comparison", "summarise", "summarize", "summary", "revise",
    "revision", "exam", "paper", "marks", "level", "advanced",
    # Generic framing words: they shape the question but do not name
    # evidence the textbook must contain.
    "role", "roles", "function", "functions", "importance",
    "significance", "example", "examples", "process", "processes",
    "type", "types", "kind", "kinds", "called", "occurs", "occur",
    "involve", "involves", "involved", "include", "includes",
    "produce", "produces", "produced", "make", "makes", "made",
    "cause", "causes", "caused", "effect", "effects", "happen",
    "happens", "happened", "term", "terms", "word", "words",
    "biology", "biological", "topic", "topics", "concept",
    "concepts", "idea", "ideas",
}


def naive_singular(token: str) -> str:
    """
    Cheap plural folding WITHOUT mangling scientific words.

    Words ending in -is/-us/-ss are left alone: 'meiosis',
    'photosynthesis', 'phosphofructokinase-1' and 'nucleus' must not
    be truncated. Only true plurals fold ('enzymes' -> 'enzyme').
    """
    token = token.strip("-").lower()
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("es") and token[:-2].endswith(
        ("s", "x", "z", "ch", "sh")
    ):
        # Genuine -es plural: boxes, churches, kisses.
        return token[:-2]
    if (
        len(token) > 3
        and token.endswith("s")
        and not token.endswith(("ss", "is", "us"))
    ):
        # Regular plural: stages -> stage, divisions -> division.
        return token[:-1]
    return token


def normalise_term(token: str) -> str:
    """
    Canonical form used for query terms: the raw token, lowercased.
    Morphological folding happens at MATCHING time via
    naive_singular, never by mutating the term itself.
    """
    return token.strip("-").lower()


def query_terms(question: str) -> list[str]:
    """Distinctive (non-noise) terms the question is actually about."""
    terms: list[str] = []
    seen: set[str] = set()

    for raw in _TOKEN_PATTERN.findall((question or "").lower()):
        term = normalise_term(raw)
        if len(term) < 3:
            continue
        if term in _QUESTION_NOISE:
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)

    return terms


# ============================================================
# CORPUS LEXICON (document frequency / IDF)
# ============================================================

class CorpusLexicon:
    """
    Document-frequency statistics over the indexed textbook.

    Built once per process from the retriever's chunks. Used to know
    which concepts the textbook can even talk about, and how
    distinctive each question term is.
    """

    def __init__(self) -> None:
        self.doc_freq: Counter[str] = Counter()
        self.n_docs: int = 0
        self.max_idf: float = 1.0
        self._built = False

    # ------------------------------------------------------

    def build_from_chunks(self, chunks: list[dict]) -> None:
        self.doc_freq = Counter()
        self.n_docs = 0

        for chunk in chunks or []:
            text = chunk.get("text") if isinstance(chunk, dict) else None
            if not text:
                continue
            self.n_docs += 1
            self.doc_freq.update(set(_corpus_tokens(text)))

        self.max_idf = math.log(self.n_docs + 1.0) + 1.0 if self.n_docs else 1.0
        self._built = True

    def build_from_retriever(self) -> None:
        """Lazy, failure-tolerant hook-up to the live index."""
        try:
            from Science.Biology import biology_retriever as retriever

            if retriever.chunks:
                self.build_from_chunks(retriever.chunks)
                return
        except Exception:
            pass

        # Retriever unavailable (offline unit tests): stay empty.
        self.max_idf = 1.0
        self._built = True

    def ensure_built(self) -> None:
        # Rebuild when never built OR when the last build saw an empty
        # index (retriever not initialised yet at first call).
        if not self._built or not self.n_docs:
            self.build_from_retriever()

    # ------------------------------------------------------

    def idf(self, term: str) -> float:
        """High IDF = distinctive. Unknown terms get the maximum."""
        self.ensure_built()

        if not self.n_docs:
            return 1.0

        df = self.doc_freq.get(term, 0) or self.doc_freq.get(
            naive_singular(term), 0
        )
        if df <= 0:
            return self.max_idf

        return math.log((self.n_docs + 1.0) / (df + 1.0)) + 1.0

    def in_corpus(self, term: str) -> bool:
        self.ensure_built()
        return (
            self.doc_freq.get(term, 0) > 0
            or self.doc_freq.get(naive_singular(term), 0) > 0
        )


def _corpus_tokens(text: str) -> list[str]:
    """
    Tokens indexed for a document: the raw token plus its folded
    singular, so 'enzymes' in the book also registers 'enzyme'.
    """
    tokens: list[str] = []
    for raw in _TOKEN_PATTERN.findall((text or "").lower()):
        raw = raw.strip("-").lower()
        if len(raw) >= 3:
            tokens.append(raw)
        folded = naive_singular(raw)
        if folded != raw and len(folded) >= 3:
            tokens.append(folded)
        # Hyphenated scientific terms are reachable per part so
        # 'oxidative-phosphorylation' matches 'phosphorylation'.
        if "-" in raw:
            for part in raw.split("-"):
                part = part.strip("-").lower()
                if len(part) >= 3:
                    tokens.append(part)
                    folded_part = naive_singular(part)
                    if folded_part != part and len(folded_part) >= 3:
                        tokens.append(folded_part)
    return tokens


_LEXICON = CorpusLexicon()


def get_corpus_lexicon() -> CorpusLexicon:
    return _LEXICON


def reset_corpus_lexicon() -> None:
    """Test hook — forces a rebuild against the current index."""
    global _LEXICON
    _LEXICON = CorpusLexicon()


# ============================================================
# SIGNAL HELPERS
# ============================================================

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _quality(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return _clamp01((float(value) - low) / (high - low))


def _evidence_text(retrieval, visual_evidence: str = "") -> str:
    parts: list[str] = []

    for result in getattr(retrieval, "results", None) or []:
        text = getattr(result, "text", None)
        if text:
            parts.append(text)

    if visual_evidence:
        parts.append(visual_evidence)

    return "\n".join(parts)


def _evidence_terms(text: str) -> tuple[set[str], str]:
    """Token set + a hyphen-stripped blob for substring checks."""
    tokens = set(_corpus_tokens(text))
    blob = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    blob = re.sub(r"\s+", " ", blob)
    return tokens, blob


def _term_present(term: str, tokens: set[str], blob: str) -> bool:
    """
    Match the term, its folded singular, or a clear substring form.

    The substring path is what rescues morphology the cheap folder
    cannot handle: 'stages' <-> 'stage', 'divisions' <-> 'division',
    'chromosomes' <-> 'chromosome'. Restricted to a minimum stem
    length so short words never match spuriously.
    """
    candidates = {term, naive_singular(term)}
    if any(candidate in tokens for candidate in candidates):
        return True
    if term.replace("-", " ") in blob:
        return True
    if len(term) >= 8 and term.replace("-", "") in blob.replace(" ", ""):
        return True

    # Folded singular of the term against the token set, and vice
    # versa (evidence plural vs query singular, and the reverse).
    folded = naive_singular(term)
    if folded != term:
        if folded in tokens or term in tokens:
            return True
        if len(folded) >= 5:
            # 'stages' -> check 'stage' as prefix of indexed plurals
            for token in tokens:
                if len(token) >= len(folded) and (
                    token.startswith(folded) or folded.startswith(token)
                ):
                    # Guard against unrelated words sharing a prefix
                    if abs(len(token) - len(folded)) <= 3:
                        return True
    return False


def _chunk_relevance(result) -> float:
    """Per-chunk relevance from the legs that actually scored it."""
    lexical = _quality(
        getattr(result, "tfidf_score", 0.0) or 0.0,
        TFIDF_MIN_QUALITY,
        TFIDF_MAX_QUALITY,
    )
    semantic = _quality(
        getattr(result, "semantic_score", 0.0) or 0.0,
        SEMANTIC_MIN_QUALITY,
        SEMANTIC_MAX_QUALITY,
    )
    if semantic > 0 and lexical > 0:
        return _clamp01(0.5 * lexical + 0.5 * semantic)
    return max(lexical, semantic)


def _leg_agreement(retrieval) -> float:
    """
    Do independent retrieval legs agree?

    A page supported by both lexical and dense retrieval is much more
    trustworthy than a page lifted by one keyword. This is also the
    guard against the BM25 false lift: BM25 vocabulary alone no longer
    reads as evidence.
    """
    results = getattr(retrieval, "results", None) or []
    if not results:
        return 0.0

    best = max(results, key=lambda r: getattr(r, "rrf_score", 0.0) or 0.0)
    page = getattr(best, "page", None)

    same_page = [r for r in results if getattr(r, "page", None) == page]

    legs = 0
    if any((r.tfidf_score or 0.0) > 0 for r in same_page):
        legs += 1
    if any((getattr(r, "semantic_score", 0.0) or 0.0) > 0 for r in same_page):
        legs += 1
    if any((getattr(r, "bm25_score", 0.0) or 0.0) > 0 for r in same_page):
        legs += 1

    if legs >= 2:
        return 1.0
    if legs == 1:
        return 0.55
    return 0.0


# ============================================================
# MAIN ASSESSMENT
# ============================================================

def assess_evidence(
    question: str,
    retrieval,
    visual_evidence: str = "",
) -> EvidenceAssessment:
    """
    Decide whether the retrieved material actually supports an answer.

    This is intentionally NOT a reranker-score check. It looks at what
    concepts the question needs, whether those concepts exist in the
    evidence at all, and whether the textbook can speak about them.
    """
    results = getattr(retrieval, "results", None) or []
    grounded = bool(getattr(retrieval, "grounded", False))
    confidence = float(getattr(retrieval, "confidence", 0.0) or 0.0)

    terms = query_terms(question)

    assessment = EvidenceAssessment(
        signals={"retrieval_confidence": confidence, "grounded": grounded},
        reason="",
    )

    # --------------------------------------------------------
    # No retrieval support at all.
    # --------------------------------------------------------

    if not results or not grounded:
        assessment.verdict = INSUFFICIENT
        assessment.sufficient = False
        assessment.score = 0.0
        assessment.reason = (
            "No textbook material passed retrieval for this question."
        )
        assessment.signals.update(
            {
                "term_coverage": 0.0,
                "top_relevance": 0.0,
                "leg_agreement": 0.0,
                "support_pages": 0,
                "breadth": 0.0,
            }
        )
        return assessment

    # --------------------------------------------------------
    # 1. Term coverage (IDF-weighted, measured on real evidence)
    # --------------------------------------------------------

    lexicon = get_corpus_lexicon()
    lexicon.ensure_built()

    tokens, blob = _evidence_terms(_evidence_text(retrieval, visual_evidence))

    total_weight = 0.0
    covered_weight = 0.0
    missing: list[str] = []
    missing_weights: dict[str, float] = {}

    for term in terms:
        weight = lexicon.idf(term)
        total_weight += weight

        if _term_present(term, tokens, blob):
            covered_weight += weight
        else:
            missing.append(term)
            missing_weights[term] = weight

    term_coverage = (
        covered_weight / total_weight if total_weight > 0 else 0.0
    )

    # --------------------------------------------------------
    # 2. Critical gap: can the textbook even talk about this?
    # --------------------------------------------------------

    strongest_query_weight = max(
        (lexicon.idf(term) for term in terms), default=0.0
    )

    critical_gap = False
    critical_terms: list[str] = []

    for term in missing:
        weight = missing_weights[term]
        if strongest_query_weight <= 0:
            continue
        if weight < EVIDENCE_CRITICAL_TERM_RATIO * strongest_query_weight:
            continue
        # Only concepts the textbook has never seen count as a hard gap;
        # a term that appears elsewhere in the book but not on the
        # retrieved pages is a coverage problem, not an absence.
        if lexicon.in_corpus(term):
            continue
        if len(term) < 5:
            continue
        critical_terms.append(term)

    if critical_terms:
        critical_gap = True

    # --------------------------------------------------------
    # 3. Chunk relevance + breadth of independent support
    # --------------------------------------------------------

    relevances = [_chunk_relevance(r) for r in results]
    top_relevance = max(relevances) if relevances else 0.0

    strong_chunks = [
        r for r, rel in zip(results, relevances)
        if rel >= EVIDENCE_CHUNK_RELEVANCE_FLOOR
    ]

    supporting_pages = sorted({r.page for r in strong_chunks}) or sorted(
        {r.page for r in results}
    )

    distinct_support = len({r.page for r in strong_chunks})
    breadth = _clamp01(distinct_support / 2.0)

    leg_agreement = _leg_agreement(retrieval)

    # --------------------------------------------------------
    # 4. Combined sufficiency score (no single signal decides)
    # --------------------------------------------------------

    score = _clamp01(
        0.40 * term_coverage
        + 0.20 * top_relevance
        + 0.20 * breadth
        + 0.20 * leg_agreement
    )

    # A question whose central concept is absent from the entire
    # textbook cannot be answered from it, however good the score.
    if critical_gap:
        score = min(score, EVIDENCE_PARTIAL_THRESHOLD - 0.01)

    assessment.score = score
    assessment.missing_terms = missing
    assessment.critical_gap = critical_gap
    assessment.supporting_pages = supporting_pages
    assessment.signals.update(
        {
            "term_coverage": term_coverage,
            "top_relevance": top_relevance,
            "leg_agreement": leg_agreement,
            "support_pages": distinct_support,
            "breadth": breadth,
            "strong_chunks": len(strong_chunks),
            "question_terms": terms,
            "missing_term_weights": {
                term: round(weight, 2)
                for term, weight in missing_weights.items()
            },
            "critical_terms": critical_terms,
        }
    )

    # --------------------------------------------------------
    # 5. Verdict
    # --------------------------------------------------------

    broad_enough = (
        distinct_support >= EVIDENCE_MIN_SUPPORTING_PAGES
        or (
            distinct_support >= 1
            and term_coverage >= 0.85
            and top_relevance >= 0.70
        )
    )

    if (
        not critical_gap
        and score >= EVIDENCE_SUFFICIENCY_THRESHOLD
        and term_coverage >= EVIDENCE_MIN_TERM_COVERAGE
        and broad_enough
    ):
        assessment.verdict = SUFFICIENT
        assessment.sufficient = True
        assessment.reason = (
            "Retrieved material covers the question's key concepts."
        )
    elif not critical_gap and score >= EVIDENCE_PARTIAL_THRESHOLD:
        assessment.verdict = PARTIAL
        assessment.sufficient = False
        assessment.reason = (
            "Related textbook material exists, but it does not fully "
            "cover what the question asks."
        )
    else:
        assessment.verdict = INSUFFICIENT
        assessment.sufficient = False
        if critical_gap:
            assessment.reason = (
                "The question hinges on "
                f"{', '.join(critical_terms[:3])}, which the indexed "
                "textbook does not cover."
            )
        else:
            assessment.reason = (
                "Retrieved pages are only weakly related to the question."
            )

    return assessment


def describe(assessment: EvidenceAssessment) -> str:
    """One-line debug summary (used by /debug routing)."""
    if assessment is None:
        return "evidence: not assessed"
    return (
        f"evidence: {assessment.verdict} "
        f"(score {assessment.score:.2f}, "
        f"coverage {assessment.signals.get('term_coverage', 0):.2f}, "
        f"pages {assessment.signals.get('support_pages', 0)})"
    )
