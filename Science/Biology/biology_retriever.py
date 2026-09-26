# biology_retriever.py
#
# Biology textbook retrieval engine for Strud AI.
#
# Responsibilities:
#   1. Load/build the Biology Resource Book index
#   2. TF-IDF retrieval
#   3. BM25 sparse lexical retrieval (hybrid mode only)
#   4. Optional semantic retrieval
#   5. Weighted Reciprocal Rank Fusion (N ranked lists)
#   6. Page-aware result aggregation
#   7. Grounding confidence calculation
#   8. 0.55 grounding gate
#   9. Build textbook context
#  10. Provide source pages
#
# main.py only needs:
#
#     retrieval = retrieve_biology(question)
#
# It does NOT need to know about vectorizers, matrices or chunks.


from __future__ import annotations

import gc
import hashlib
import json
import os
import pickle
import re
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pymupdf

from sklearn.feature_extraction.text import (
    CountVectorizer,
    TfidfVectorizer,
)
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# CONFIG
# ============================================================

from config import (
    PDF_FILE,
    CACHE_DIR,

    CHUNKS_FILE,
    TFIDF_FILE,
    META_FILE,

    SEMANTIC_FILE,
    SEMANTIC_META_FILE,

    BM25_FILE,

    EMBEDDING_MODEL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DEVICE,
    AUTO_BUILD_SEMANTIC,

    CHUNK_SIZE,
    CHUNK_OVERLAP,

    TFIDF_TOP_K,
    SEMANTIC_TOP_K,

    MAX_CONTEXT_PAGES,
    MAX_CHUNKS_PER_PAGE,

    GROUNDING_THRESHOLD,

    RRF_K,

    RRF_WEIGHTS,

    RETRIEVAL_MODE,
    BM25_ENABLED,
    BM25_TOP_K,
    BM25_K1,
    BM25_B,
    BM25_MIN_QUALITY,
    BM25_MAX_QUALITY,

    ENABLE_NEIGHBOR_PAGES,
    NEIGHBOR_PAGE_PENALTY,

    TFIDF_MIN_QUALITY,
    TFIDF_MAX_QUALITY,

    SEMANTIC_MIN_QUALITY,
    SEMANTIC_MAX_QUALITY,
)


# ============================================================
# ENVIRONMENT
# ============================================================

os.environ.setdefault(
    "TOKENIZERS_PARALLELISM",
    "false",
)

os.environ.setdefault(
    "OMP_NUM_THREADS",
    "2",
)

os.environ.setdefault(
    "MKL_NUM_THREADS",
    "2",
)


# ============================================================
# GLOBAL STATE
# ============================================================

chunks: list[dict[str, Any]] = []

tfidf_vectorizer: Optional[TfidfVectorizer] = None

tfidf_matrix: Any = None

semantic_embeddings: Any = None

semantic_model: Any = None

pdf_signature: Optional[dict[str, Any]] = None

semantic_available = False

_initialized = False

# --------------------------------------------------------
# BM25 index (Phase 1)
# --------------------------------------------------------

bm25_vectorizer: Any = None

# Sparse document-term count matrix (CSC, so per-term column
# lookups during scoring are cheap).
bm25_counts: Any = None

bm25_idf: Any = None

bm25_doc_len: Any = None

bm25_avgdl: float = 0.0

bm25_available = False

# --------------------------------------------------------
# Visual chunks (Qwen3-VL derived)
# --------------------------------------------------------

# Visual chunk records currently attached to the index.
visual_chunks: list[dict[str, Any]] = []

# Semantic embeddings for visual chunks only (parallel to visual_chunks).
visual_semantic_embeddings: Any = None

# Number of text chunks before visual chunks were appended.
# Visual chunk i lives at chunks[_base_chunk_count + i].
_base_chunk_count = 0

_visual_attached = False


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class RetrievalResult:
    index: int
    page: int
    text: str

    tfidf_score: float = 0.0
    semantic_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0

    page_score: float = 0.0
    confidence: float = 0.0


@dataclass
class RetrievalResponse:
    results: list[RetrievalResult]

    confidence: float

    grounded: bool

    best_page: Optional[int]

    reason: str


# ============================================================
# BASIC HELPERS
# ============================================================

def clamp01(value: float) -> float:
    return max(
        0.0,
        min(1.0, float(value)),
    )


def normalise_text(text: str) -> str:
    """
    Clean extracted textbook text while preserving
    useful scientific terminology.
    """
    if not text:
        return ""

    import unicodedata
    text = unicodedata.normalize("NFKC", text)

    text = text.replace("\x00", " ")
    text = text.replace("\u00ad", "")

    text = re.sub(r"\bfi\s+ltrate\b", "filtrate", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfi\s+ltration\b", "filtration", text, flags=re.IGNORECASE)
    text = re.sub(r"\bultra\s+fi\s+ltration\b", "ultrafiltration", text, flags=re.IGNORECASE)
    text = re.sub(r"\bultra\s+filtration\b", "ultrafiltration", text, flags=re.IGNORECASE)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# QUERY PREPROCESSING
# ============================================================

BIOLOGY_ALIASES = {
    "ultra filtration": "ultrafiltration",
    "ultra-filteration": "ultrafiltration",
    "ultra filteration": "ultrafiltration",
    "ultra-filtration": "ultrafiltration",
    "fi ltrate": "filtrate",
    "fi ltration": "filtration",
    "ultra fi ltration": "ultrafiltration",
    "ultra-fi ltration": "ultrafiltration",

    "bowman capsule": "bowmans capsule",
    "bowmans capsule": "bowman capsule",

    "glomerular filtration": "ultrafiltration",

    "selective re-absorption": "selective reabsorption",
    "selective re absorption": "selective reabsorption",
    "re-absorption": "reabsorption",
    "re absorption": "reabsorption",
}


CONCEPT_SYNONYMS = {
    "ultrafiltration": ["ultrafiltration", "glomerular filtration", "bowman", "glomerulus", "filtrate"],
    "nephron": ["nephron", "structure of nephron", "renal tubule", "bowman", "glomerulus", "collecting duct", "loop of henle"],
    "excretion": ["excretion", "osmoregulation", "nitrogenous waste", "kidney", "nephron"],
    "photosynthesis": ["photosynthesis", "chlorophyll", "light reaction", "calvin cycle", "chloroplast", "carbon fixation"],
    "respiration": ["respiration", "aerobic respiration", "anaerobic respiration", "glycolysis", "krebs cycle", "atp"],
    "mitosis": ["mitosis", "cell division", "chromosomes", "prophase", "metaphase", "anaphase", "telophase"],
    "meiosis": ["meiosis", "reduction division", "gametes", "crossing over", "homologous chromosomes"],
    "enzyme": ["enzyme", "substrate", "active site", "activation energy", "catalyst"],
    "dna": ["dna", "deoxyribonucleic acid", "double helix", "nucleotide", "replication"],
    "protein": ["protein", "amino acid", "polypeptide", "peptide bond", "primary structure"],
    "digestion": ["digestion", "digestive system", "enzyme", "stomach", "small intestine", "pancreas"],
    "circulation": ["circulation", "circulatory system", "blood", "heart", "artery", "vein", "capillary"],
}


def expand_query(query: str) -> str:
    """
    Apply conservative Biology terminology corrections and concept synonym expansion.
    """

    cleaned = normalise_text(query).lower()

    for old, new in BIOLOGY_ALIASES.items():
        cleaned = cleaned.replace(
            old,
            new,
        )

    synonyms = []
    for concept, syns in CONCEPT_SYNONYMS.items():
        if concept in cleaned:
            for s in syns:
                if s not in cleaned:
                    synonyms.append(s)

    if synonyms:
        cleaned = f"{cleaned} {' '.join(synonyms)}"

    return cleaned


# ============================================================
# PDF SIGNATURE
# ============================================================

def get_pdf_signature() -> Optional[dict[str, Any]]:
    """
    Create a reliable signature for the current PDF.

    If the PDF changes, the old cache becomes invalid.
    """

    if not PDF_FILE.exists():
        return None

    stat = PDF_FILE.stat()

    sha = hashlib.sha256()

    with open(
        PDF_FILE,
        "rb",
    ) as file:

        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha.update(block)

    return {
        "name": PDF_FILE.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha.hexdigest(),
    }


# ============================================================
# FILE HELPERS
# ============================================================

def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def safe_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_pages() -> list[dict[str, Any]]:
    """
    Extract text page-by-page from the Biology Resource Book.
    """

    if not PDF_FILE.exists():
        return []

    pages: list[dict[str, Any]] = []

    try:

        with pymupdf.open(PDF_FILE) as document:

            for page_index in range(
                len(document)
            ):

                page = document.load_page(
                    page_index
                )

                text = normalise_text(
                    page.get_text("text")
                )

                if not text:
                    continue

                pages.append(
                    {
                        "page": page_index + 1,
                        "text": text,
                    }
                )

    except Exception:
        return []

    return pages


# ============================================================
# CHUNKING
# ============================================================

def split_long_text(
    text: str,
) -> list[str]:
    """
    Split page text into manageable chunks.

    Paragraphs are preferred.
    Long paragraphs are split into sentences.
    """

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            text,
        )
        if paragraph.strip()
    ]

    pieces: list[str] = []

    for paragraph in paragraphs:

        if len(paragraph) <= CHUNK_SIZE:
            pieces.append(paragraph)
            continue

        sentences = re.split(
            r"(?<=[.!?])\s+",
            paragraph,
        )

        current = ""

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            if not current:

                current = sentence

            elif (
                len(current)
                + 1
                + len(sentence)
                <= CHUNK_SIZE
            ):

                current += " " + sentence

            else:

                pieces.append(current)

                current = sentence

        if current:
            pieces.append(current)

    return pieces


def add_overlap(
    texts: list[str],
) -> list[str]:
    """
    Add a small amount of overlap between chunks
    so concepts spanning boundaries aren't lost.
    """

    if not texts:
        return []

    final: list[str] = []

    for index, text in enumerate(texts):

        if index == 0:

            final.append(text)

            continue

        previous = texts[index - 1]

        if len(previous) <= CHUNK_OVERLAP:

            prefix = previous

        else:

            prefix = previous[
                -CHUNK_OVERLAP:
            ]

            first_space = prefix.find(" ")

            if 0 <= first_space < 80:

                prefix = prefix[
                    first_space + 1:
                ]

        combined = (
            f"{prefix} {text}"
        ).strip()

        final.append(
            combined[
                :CHUNK_SIZE + CHUNK_OVERLAP
            ]
        )

    return final


def build_chunks(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    output: list[dict[str, Any]] = []

    for page_data in pages:

        page_number = int(
            page_data["page"]
        )

        page_text = page_data["text"]

        page_pieces = split_long_text(
            page_text
        )

        page_pieces = add_overlap(
            page_pieces
        )

        for chunk_number, text in enumerate(
            page_pieces,
            start=1,
        ):

            clean = normalise_text(
                text
            )

            if len(clean) < 30:
                continue

            output.append(
                {
                    "page": page_number,
                    "chunk": chunk_number,
                    "text": clean,
                }
            )

    return output


# ============================================================
# TF-IDF
# ============================================================

def build_tfidf(
    textbook_chunks: list[dict[str, Any]],
):
    if not textbook_chunks:
        return None, None

    texts = [
        item["text"]
        for item in textbook_chunks
    ]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.98,
        sublinear_tf=True,
    )

    matrix = vectorizer.fit_transform(
        texts
    )

    return vectorizer, matrix


# ============================================================
# CACHE SAVE
# ============================================================

def save_tfidf_cache() -> bool:

    if (
        not chunks
        or tfidf_vectorizer is None
        or tfidf_matrix is None
        or pdf_signature is None
    ):
        return False

    ensure_cache_dir()

    temp_chunks = CHUNKS_FILE.with_suffix(
        ".tmp"
    )

    temp_tfidf = TFIDF_FILE.with_suffix(
        ".tmp"
    )

    temp_meta = META_FILE.with_suffix(
        ".tmp"
    )

    try:

        with open(
            temp_chunks,
            "wb",
        ) as file:

            pickle.dump(
                chunks,
                file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        with open(
            temp_tfidf,
            "wb",
        ) as file:

            pickle.dump(
                (
                    tfidf_vectorizer,
                    tfidf_matrix,
                ),
                file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        metadata = {
            "version": 3,
            "pdf_signature": pdf_signature,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "chunk_count": len(chunks),
        }

        with open(
            temp_meta,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                metadata,
                file,
                indent=2,
            )

        os.replace(
            temp_chunks,
            CHUNKS_FILE,
        )

        os.replace(
            temp_tfidf,
            TFIDF_FILE,
        )

        os.replace(
            temp_meta,
            META_FILE,
        )

        return True

    except Exception:

        safe_remove(temp_chunks)
        safe_remove(temp_tfidf)
        safe_remove(temp_meta)

        return False


# ============================================================
# CACHE LOAD
# ============================================================

def load_tfidf_cache() -> bool:

    global chunks
    global tfidf_vectorizer
    global tfidf_matrix
    global pdf_signature

    if not (
        CHUNKS_FILE.exists()
        and TFIDF_FILE.exists()
        and META_FILE.exists()
    ):
        return False

    try:

        with open(
            META_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            metadata = json.load(file)

        current_signature = (
            get_pdf_signature()
        )

        if current_signature is None:
            return False

        if (
            metadata.get(
                "pdf_signature"
            )
            != current_signature
        ):
            return False

        if (
            metadata.get("chunk_size")
            != CHUNK_SIZE
        ):
            return False

        if (
            metadata.get("chunk_overlap")
            != CHUNK_OVERLAP
        ):
            return False

        with open(
            CHUNKS_FILE,
            "rb",
        ) as file:

            loaded_chunks = pickle.load(
                file
            )

        with open(
            TFIDF_FILE,
            "rb",
        ) as file:

            loaded_vectorizer, loaded_matrix = (
                pickle.load(file)
            )

        if (
            not isinstance(
                loaded_chunks,
                list,
            )
            or not loaded_chunks
        ):
            return False

        if (
            loaded_vectorizer is None
            or loaded_matrix is None
        ):
            return False

        if (
            loaded_matrix.shape[0]
            != len(loaded_chunks)
        ):
            return False

        chunks = loaded_chunks

        tfidf_vectorizer = (
            loaded_vectorizer
        )

        tfidf_matrix = (
            loaded_matrix
        )

        pdf_signature = (
            current_signature
        )

        return True

    except Exception:

        return False


# ============================================================
# BUILD TF-IDF DATABASE
# ============================================================

def build_tfidf_database() -> bool:

    global chunks
    global tfidf_vectorizer
    global tfidf_matrix
    global pdf_signature

    pages = extract_pdf_pages()

    if not pages:
        return False

    new_chunks = build_chunks(
        pages
    )

    del pages

    gc.collect()

    if not new_chunks:
        return False

    new_vectorizer, new_matrix = (
        build_tfidf(new_chunks)
    )

    if (
        new_vectorizer is None
        or new_matrix is None
    ):
        return False

    chunks = new_chunks

    tfidf_vectorizer = (
        new_vectorizer
    )

    tfidf_matrix = new_matrix

    pdf_signature = (
        get_pdf_signature()
    )

    if pdf_signature is None:
        return False

    save_tfidf_cache()

    return True


# ============================================================
# INITIALIZATION
# ============================================================

def initialize_retriever() -> bool:
    """
    Load an existing valid TF-IDF cache.

    If no valid cache exists, build one from the PDF.

    This function is called automatically by retrieve_biology().
    """

    global _initialized

    if _initialized:
        return (
            tfidf_vectorizer is not None
            and tfidf_matrix is not None
            and bool(chunks)
        )

    _initialized = True

    if not PDF_FILE.exists():
        return False

    if load_tfidf_cache():

        # Also check for a previously completed
        # semantic cache.
        load_semantic_cache()

        if (
            AUTO_BUILD_SEMANTIC
            and not semantic_available
        ):
            build_semantic_index()

        # BM25 lexical leg (hybrid mode only; cached like the rest).
        ensure_bm25_index()

        # Attach persisted Qwen visual chunks to the index.
        # (This may rebuild the BM25 statistics if visual chunks
        #  were appended.)
        attach_visual_chunks()

        return True

    success = (
        build_tfidf_database()
    )

    if not success:
        return False

    load_semantic_cache()

    if (
        AUTO_BUILD_SEMANTIC
        and not semantic_available
    ):
        build_semantic_index()

    # BM25 lexical leg (hybrid mode only).
    ensure_bm25_index()

    # Attach persisted Qwen visual chunks to the index.
    attach_visual_chunks()

    return True


# ============================================================
# VISUAL CHUNK ATTACHMENT (Qwen3-VL)
# ============================================================

def attach_visual_chunks() -> int:
    """
    Appends persisted visual chunks (from Qwen3-VL page analysis)
    to the retrieval index.

    - TF-IDF is refit over text + visual chunks (cheap for ~1k docs).
    - Visual chunks get their own semantic embeddings so the existing
      text semantic index is never invalidated.

    Returns the number of visual chunks attached.
    """
    global chunks
    global tfidf_vectorizer
    global tfidf_matrix
    global visual_chunks
    global visual_semantic_embeddings
    global _base_chunk_count
    global _visual_attached

    if _visual_attached:
        return len(visual_chunks)

    try:
        from Science.Biology.vision import (
            load_visual_chunks,
            VISION_ENABLED,
        )
    except ImportError:
        return 0

    if not VISION_ENABLED:
        return 0

    persisted = load_visual_chunks()

    if not persisted or not chunks:
        return 0

    _base_chunk_count = len(chunks)

    wrapped: list[dict[str, Any]] = []

    for visual in persisted:

        page = visual.get("page")

        search_text = str(visual.get("text", "")).strip()

        if not search_text:
            continue

        content_type = str(
            visual.get("content_type", "visual")
        )

        labelled_text = (
            f"[{content_type.upper()} - visual analysis, "
            f"textbook page {page}]\n{search_text}"
        )

        wrapped.append(
            {
                "page": int(page) if page is not None else 0,
                "chunk": 1,
                "text": labelled_text,
                "chunk_id": visual.get("chunk_id", ""),
                "content_type": content_type,
                "visual_description": visual.get("visual_description", ""),
                "source_image": visual.get("source_image", ""),
                "is_visual": True,
            }
        )

    if not wrapped:
        return 0

    # Refit TF-IDF over text + visual chunks.
    try:
        new_vectorizer, new_matrix = build_tfidf(
            chunks + wrapped
        )
    except Exception:
        return 0

    if new_vectorizer is None or new_matrix is None:
        return 0

    chunks = chunks + wrapped
    tfidf_vectorizer = new_vectorizer
    tfidf_matrix = new_matrix
    visual_chunks = wrapped
    _visual_attached = True

    # Visual chunks change the document set: keep BM25 in sync.
    refresh_bm25_index()

    # Semantic embeddings for visual chunks only.
    model = load_embedding_model()

    if model is not None:
        try:
            vectors = model.encode(
                [item["text"] for item in wrapped],
                batch_size=EMBEDDING_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            visual_semantic_embeddings = np.asarray(
                vectors,
                dtype=np.float32,
            )
        except Exception:
            visual_semantic_embeddings = None

    return len(wrapped)


def attach_new_visual_chunk(visual_record: dict[str, Any]) -> bool:
    """
    Attaches a single newly-created visual chunk at runtime
    (e.g. right after Qwen analyses a page during a question).

    Rebuilds the TF-IDF matrix and the visual semantic array.
    """
    global chunks
    global tfidf_vectorizer
    global tfidf_matrix
    global visual_chunks
    global visual_semantic_embeddings

    if not chunks:
        return False

    page = visual_record.get("page")
    search_text = str(visual_record.get("text", "")).strip()

    if not search_text:
        return False

    chunk_id = visual_record.get("chunk_id", "")

    # Skip if already attached.
    for existing in visual_chunks:
        if existing.get("chunk_id") == chunk_id:
            return True

    content_type = str(
        visual_record.get("content_type", "visual")
    )

    wrapped = {
        "page": int(page) if page is not None else 0,
        "chunk": 1,
        "text": (
            f"[{content_type.upper()} - visual analysis, "
            f"textbook page {page}]\n{search_text}"
        ),
        "chunk_id": chunk_id,
        "content_type": content_type,
        "visual_description": visual_record.get("visual_description", ""),
        "source_image": visual_record.get("source_image", ""),
        "is_visual": True,
    }

    try:
        new_vectorizer, new_matrix = build_tfidf(
            chunks + [wrapped]
        )
    except Exception:
        return False

    if new_vectorizer is None or new_matrix is None:
        return False

    chunks = chunks + [wrapped]
    tfidf_vectorizer = new_vectorizer
    tfidf_matrix = new_matrix
    visual_chunks = visual_chunks + [wrapped]

    # Keep the BM25 document set in sync with the TF-IDF one.
    refresh_bm25_index()

    model = load_embedding_model()

    if model is not None:
        try:
            vectors = model.encode(
                [item["text"] for item in visual_chunks],
                batch_size=EMBEDDING_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            visual_semantic_embeddings = np.asarray(
                vectors,
                dtype=np.float32,
            )
        except Exception:
            pass

    return True


# ============================================================
# TF-IDF SEARCH
# ============================================================

def keyword_search(
    query: str,
    top_k: int = TFIDF_TOP_K,
) -> list[RetrievalResult]:

    if (
        not query.strip()
        or not chunks
        or tfidf_vectorizer is None
        or tfidf_matrix is None
    ):
        return []

    query = expand_query(
        query
    )

    query_vector = (
        tfidf_vectorizer.transform(
            [query]
        )
    )

    if query_vector.nnz == 0:
        return []

    scores = cosine_similarity(
        query_vector,
        tfidf_matrix,
    ).ravel()

    candidate_indices = np.where(
        scores > 0
    )[0]

    if len(candidate_indices) == 0:
        return []

    candidate_indices = (
        candidate_indices[
            np.argsort(
                scores[
                    candidate_indices
                ]
            )[::-1]
        ]
    )

    candidate_indices = (
        candidate_indices[:top_k]
    )

    results: list[
        RetrievalResult
    ] = []

    for index in candidate_indices:

        chunk = chunks[
            int(index)
        ]

        results.append(
            RetrievalResult(
                index=int(index),
                page=int(chunk["page"]),
                text=chunk["text"],
                tfidf_score=float(
                    scores[index]
                ),
            )
        )

    return results


# ============================================================
# BM25 (SPARSE LEXICAL RETRIEVAL)
# ============================================================
#
# BM25 complements TF-IDF. TF-IDF cosine similarity flattens long
# chunks; BM25 saturates term frequency and normalises by document
# length, which is what matters for exact Biology terminology
# (e.g. "ribulose bisphosphate", "antidiuretic hormone").
#
# It is added as a THIRD ranked list inside the SAME page-aware
# pipeline. It never replaces TF-IDF, never bypasses page
# aggregation, and never bypasses the grounding gate.

# Token pattern keeps hyphenated / primed Biology terms intact,
# e.g. "acetyl-coa", "9+2" is split as expected by the book text.
BM25_TOKEN_PATTERN = r"[a-z0-9]+(?:[-'][a-z0-9]+)*"

# Bump when the tokenizer or scoring model changes so that stale
# cached indexes are rebuilt instead of silently reused.
BM25_INDEX_VERSION = 1


def build_bm25(texts: list[str]) -> bool:
    """
    Build BM25 statistics over the given chunk texts.

    Stores:
        - the fitted count vectorizer (vocabulary)
        - document-term counts (CSC)
        - per-term IDF
        - document lengths + average document length
    """

    global bm25_vectorizer
    global bm25_counts
    global bm25_idf
    global bm25_doc_len
    global bm25_avgdl
    global bm25_available

    if not texts:
        return False

    try:

        vectorizer = CountVectorizer(
            lowercase=True,
            strip_accents="unicode",
            token_pattern=BM25_TOKEN_PATTERN,
            ngram_range=(1, 1),
            dtype=np.float32,
        )

        counts = vectorizer.fit_transform(texts)

    except Exception:

        return False

    if counts.shape[0] != len(texts) or counts.shape[1] == 0:
        return False

    doc_len = np.asarray(
        counts.sum(axis=1),
    ).ravel().astype(np.float32)

    avgdl = float(doc_len.mean()) if doc_len.size else 0.0

    if avgdl <= 0:
        return False

    document_frequency = np.asarray(
        (counts > 0).sum(axis=0),
    ).ravel().astype(np.float32)

    n_docs = float(counts.shape[0])

    # Standard BM25 IDF (the +1 variant keeps IDF non-negative for
    # terms that appear in most documents).
    idf = np.log(
        (n_docs - document_frequency + 0.5)
        / (document_frequency + 0.5)
        + 1.0
    ).astype(np.float32)

    bm25_vectorizer = vectorizer
    bm25_counts = counts.tocsc()
    bm25_idf = idf
    bm25_doc_len = doc_len
    bm25_avgdl = avgdl
    bm25_available = True

    return True


def save_bm25_cache() -> bool:

    if (
        not bm25_available
        or bm25_vectorizer is None
        or pdf_signature is None
    ):
        return False

    ensure_cache_dir()

    temp = BM25_FILE.with_suffix(".tmp")

    payload = {
        "version": BM25_INDEX_VERSION,
        "pdf_signature": pdf_signature,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "chunk_count": len(chunks),
        "k1": BM25_K1,
        "b": BM25_B,
        "token_pattern": BM25_TOKEN_PATTERN,
        "vectorizer": bm25_vectorizer,
        "counts": bm25_counts,
        "idf": bm25_idf,
        "doc_len": bm25_doc_len,
        "avgdl": bm25_avgdl,
    }

    try:

        with open(temp, "wb") as file:

            pickle.dump(
                payload,
                file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        os.replace(temp, BM25_FILE)

        return True

    except Exception:

        safe_remove(temp)

        return False


def load_bm25_cache() -> bool:

    global bm25_vectorizer
    global bm25_counts
    global bm25_idf
    global bm25_doc_len
    global bm25_avgdl
    global bm25_available

    if (
        not BM25_FILE.exists()
        or not chunks
        or pdf_signature is None
    ):
        return False

    try:

        with open(BM25_FILE, "rb") as file:

            payload = pickle.load(file)

        if not isinstance(payload, dict):
            return False

        if payload.get("version") != BM25_INDEX_VERSION:
            return False

        if payload.get("pdf_signature") != pdf_signature:
            return False

        if payload.get("chunk_size") != CHUNK_SIZE:
            return False

        if payload.get("chunk_overlap") != CHUNK_OVERLAP:
            return False

        if payload.get("chunk_count") != len(chunks):
            return False

        if payload.get("k1") != BM25_K1 or payload.get("b") != BM25_B:
            return False

        if payload.get("token_pattern") != BM25_TOKEN_PATTERN:
            return False

        counts = payload.get("counts")
        vectorizer = payload.get("vectorizer")

        if counts is None or vectorizer is None:
            return False

        if counts.shape[0] != len(chunks):
            return False

        avgdl = float(payload.get("avgdl") or 0.0)

        if avgdl <= 0:
            return False

        bm25_vectorizer = vectorizer
        bm25_counts = counts
        bm25_idf = payload.get("idf")
        bm25_doc_len = payload.get("doc_len")
        bm25_avgdl = avgdl
        bm25_available = True

        return True

    except Exception:

        bm25_available = False

        return False


def refresh_bm25_index() -> bool:
    """Rebuild + persist BM25 from the CURRENT chunk list."""

    if not BM25_ENABLED or not chunks:
        return False

    if not build_bm25([item["text"] for item in chunks]):
        return False

    save_bm25_cache()

    return True


def ensure_bm25_index() -> bool:
    """Load a valid BM25 cache, otherwise build one."""

    if not BM25_ENABLED:
        return False

    if load_bm25_cache():
        return True

    return refresh_bm25_index()


def bm25_search(
    query: str,
    top_k: int = BM25_TOP_K,
) -> list[RetrievalResult]:
    """
    BM25 ranking over the same chunks used by TF-IDF/semantic search.
    """

    if (
        not query.strip()
        or not chunks
        or not bm25_available
        or bm25_vectorizer is None
        or bm25_counts is None
        or bm25_idf is None
        or bm25_doc_len is None
    ):
        return []

    try:

        query_vector = bm25_vectorizer.transform(
            [expand_query(query)]
        )

    except Exception:

        return []

    if query_vector.nnz == 0:
        return []

    k1 = float(BM25_K1)
    b = float(BM25_B)

    length_ratio = bm25_doc_len / bm25_avgdl

    denominator_base = k1 * (
        1.0 - b + b * length_ratio
    )

    scores = np.zeros(
        bm25_counts.shape[0],
        dtype=np.float32,
    )

    for term in {int(t) for t in query_vector.indices}:

        column = bm25_counts.getcol(term).tocoo()

        if column.nnz == 0:
            continue

        rows = column.row
        frequencies = column.data.astype(np.float32)

        numerators = frequencies * (k1 + 1.0)
        denominators = frequencies + denominator_base[rows]

        scores[rows] += (
            bm25_idf[term]
            * (numerators / denominators)
        )

    candidates = np.where(scores > 0)[0]

    if candidates.size == 0:
        return []

    candidates = candidates[
        np.argsort(scores[candidates])[::-1]
    ]

    candidates = candidates[:top_k]

    results: list[RetrievalResult] = []

    for index in candidates:

        chunk = chunks[int(index)]

        results.append(
            RetrievalResult(
                index=int(index),
                page=int(chunk["page"]),
                text=chunk["text"],
                bm25_score=float(scores[index]),
            )
        )

    return results


# ============================================================
# SEMANTIC MODEL
# ============================================================

def load_embedding_model():
    """
    Load the embedding model only when needed.

    Semantic search is optional.
    """

    global semantic_model

    if semantic_model is not None:
        return semantic_model

    try:

        from sentence_transformers import (
            SentenceTransformer,
        )

    except ImportError:

        return None

    try:

        semantic_model = (
            SentenceTransformer(
                EMBEDDING_MODEL,
                device=EMBEDDING_DEVICE,
            )
        )

        return semantic_model

    except Exception:

        semantic_model = None

        gc.collect()

        return None


# ============================================================
# SEMANTIC CACHE
# ============================================================

def clear_semantic_cache() -> None:

    global semantic_embeddings
    global semantic_available

    semantic_embeddings = None

    semantic_available = False

    safe_remove(
        SEMANTIC_FILE
    )

    safe_remove(
        SEMANTIC_META_FILE
    )

    gc.collect()


def save_semantic_metadata(
    dimension: int,
    completed_chunks: int,
) -> bool:

    ensure_cache_dir()

    metadata = {
        "version": 2,
        "pdf_signature": pdf_signature,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": dimension,
        "chunk_count": len(chunks),
        "completed_chunks": completed_chunks,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "normalized": True,
    }

    temp = (
        SEMANTIC_META_FILE.with_suffix(
            ".tmp"
        )
    )

    try:

        with open(
            temp,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                metadata,
                file,
                indent=2,
            )

        os.replace(
            temp,
            SEMANTIC_META_FILE,
        )

        return True

    except Exception:

        safe_remove(temp)

        return False


def load_semantic_cache() -> bool:

    global semantic_embeddings
    global semantic_available

    if not (
        SEMANTIC_FILE.exists()
        and SEMANTIC_META_FILE.exists()
        and chunks
    ):
        return False

    try:

        with open(
            SEMANTIC_META_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            metadata = json.load(
                file
            )

        if (
            metadata.get(
                "pdf_signature"
            )
            != pdf_signature
        ):
            return False

        if (
            metadata.get(
                "embedding_model"
            )
            != EMBEDDING_MODEL
        ):
            return False

        if (
            metadata.get(
                "chunk_count"
            )
            != len(chunks)
        ):
            return False

        if (
            metadata.get(
                "completed_chunks"
            )
            != len(chunks)
        ):
            return False

        loaded = np.load(
            SEMANTIC_FILE,
            mmap_mode="r",
        )

        if loaded.ndim != 2:
            return False

        if (
            loaded.shape[0]
            != len(chunks)
        ):
            return False

        semantic_embeddings = loaded

        semantic_available = True

        return True

    except Exception:

        semantic_embeddings = None

        semantic_available = False

        return False


# ============================================================
# BUILD SEMANTIC INDEX
# ============================================================

def build_semantic_index() -> bool:

    global semantic_embeddings
    global semantic_available

    if not chunks:
        return False

    model = load_embedding_model()

    if model is None:
        return False

    clear_semantic_cache()

    temp_semantic = (
        SEMANTIC_FILE.with_suffix(
            ".building.npy"
        )
    )

    try:

        texts = [
            item["text"]
            for item in chunks
        ]

        total = len(texts)

        if total == 0:
            return False

        first_end = min(
            EMBEDDING_BATCH_SIZE,
            total,
        )

        first_vectors = model.encode(
            texts[:first_end],
            batch_size=EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        first_vectors = np.asarray(
            first_vectors,
            dtype=np.float32,
        )

        if first_vectors.ndim != 2:
            raise RuntimeError(
                "Embedding model returned invalid shape."
            )

        dimension = (
            first_vectors.shape[1]
        )

        memmap = np.lib.format.open_memmap(
            temp_semantic,
            mode="w+",
            dtype=np.float32,
            shape=(
                total,
                dimension,
            ),
        )

        memmap[
            :first_end
        ] = first_vectors

        memmap.flush()

        del first_vectors

        gc.collect()

        completed = first_end

        while completed < total:

            end = min(
                completed
                + EMBEDDING_BATCH_SIZE,
                total,
            )

            batch_texts = texts[
                completed:end
            ]

            vectors = model.encode(
                batch_texts,
                batch_size=EMBEDDING_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            vectors = np.asarray(
                vectors,
                dtype=np.float32,
            )

            expected_shape = (
                end - completed,
                dimension,
            )

            if vectors.shape != expected_shape:

                raise RuntimeError(
                    "Embedding model returned inconsistent shape."
                )

            memmap[
                completed:end
            ] = vectors

            memmap.flush()

            completed = end

            del vectors

            gc.collect()

        del memmap

        gc.collect()

        os.replace(
            temp_semantic,
            SEMANTIC_FILE,
        )

        save_semantic_metadata(
            dimension,
            total,
        )

        semantic_embeddings = np.load(
            SEMANTIC_FILE,
            mmap_mode="r",
        )

        semantic_available = True

        del texts

        gc.collect()

        return True

    except KeyboardInterrupt:

        safe_remove(
            temp_semantic
        )

        clear_semantic_cache()

        return False

    except Exception:

        safe_remove(
            temp_semantic
        )

        clear_semantic_cache()

        return False


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_search(
    query: str,
    top_k: int = SEMANTIC_TOP_K,
) -> list[RetrievalResult]:

    if (
        semantic_embeddings is None
        or not chunks
    ):
        return []

    model = load_embedding_model()

    if model is None:
        return []

    try:

        query_embedding = model.encode(
            [
                expand_query(query)
            ],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]

        query_embedding = np.asarray(
            query_embedding,
            dtype=np.float32,
        )

        scores = np.dot(
            semantic_embeddings,
            query_embedding,
        )

        top_k = min(
            top_k,
            len(scores),
        )

        if top_k <= 0:
            return []

        top_indices = np.argsort(
            scores
        )[::-1][:top_k]

        results: list[
            RetrievalResult
        ] = []

        for index in top_indices:

            if scores[index] <= 0:
                continue

            chunk = chunks[
                int(index)
            ]

            results.append(
                RetrievalResult(
                    index=int(index),
                    page=int(chunk["page"]),
                    text=chunk["text"],
                    semantic_score=float(
                        scores[index]
                    ),
                )
            )

        # ------------------------------------------------
        # Visual chunk semantic search (separate array so
        # the existing text semantic index is untouched)
        # ------------------------------------------------

        if (
            visual_semantic_embeddings is not None
            and visual_chunks
        ):
            try:
                visual_scores = np.dot(
                    visual_semantic_embeddings,
                    query_embedding,
                )

                visual_top_k = min(
                    top_k,
                    len(visual_scores),
                )

                visual_indices = np.argsort(
                    visual_scores
                )[::-1][
                    :visual_top_k
                ]

                for offset, v_index in enumerate(
                    visual_indices
                ):
                    v_score = float(
                        visual_scores[v_index]
                    )

                    if v_score <= 0:
                        continue

                    v_chunk = visual_chunks[
                        int(v_index)
                    ]

                    results.append(
                        RetrievalResult(
                            index=_base_chunk_count + int(v_index),
                            page=int(v_chunk["page"]),
                            text=v_chunk["text"],
                            semantic_score=v_score,
                        )
                    )
            except Exception:
                pass

        return results

    except Exception:

        return []


# ============================================================
# RRF
# ============================================================

def reciprocal_rank_fusion(
    tfidf_results: list[RetrievalResult],
    semantic_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[int, float]:
    """
    Weighted Reciprocal Rank Fusion over N ranked lists.

    With weights left at 1.0 this is IDENTICAL to the original
    two-list fusion, so existing behaviour is preserved.
    """

    active_weights = weights or RRF_WEIGHTS

    scores: dict[int, float] = {}

    def add_ranking(
        results: list[RetrievalResult] | None,
        weight: float,
    ) -> None:

        if not results or weight <= 0:
            return

        for rank, result in enumerate(
            results,
            start=1,
        ):

            scores[result.index] = (
                scores.get(
                    result.index,
                    0.0,
                )
                + weight
                / (RRF_K + rank)
            )

    add_ranking(
        tfidf_results,
        float(active_weights.get("tfidf", 1.0)),
    )

    add_ranking(
        semantic_results,
        float(active_weights.get("semantic", 1.0)),
    )

    add_ranking(
        bm25_results,
        float(active_weights.get("bm25", 1.0)),
    )

    return scores


# ============================================================
# MERGE RESULTS
# ============================================================

def calculate_phrase_boost(
    query: str,
    chunk_text: str,
) -> float:
    """
    Calculates exact phrase match boost for query phrases against chunk text.
    """
    clean_query = normalise_text(query).lower()
    clean_text = normalise_text(chunk_text).lower()

    if not clean_query or not clean_text:
        return 0.0

    stop_words = {
        "what", "are", "the", "is", "of", "in", "a", "an", "and", "or",
        "for", "to", "how", "why", "which", "describe", "explain", "according"
    }

    words = [w for w in re.findall(r"\b[a-z]{3,}\b", clean_query) if w not in stop_words]

    boost = 0.0

    if len(words) >= 2:
        full_phrase = " ".join(words)
        if full_phrase in clean_text:
            boost += 0.025

        for n in (3, 2):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i+n])
                if gram in clean_text:
                    boost += 0.006 * n

    matched_words = sum(1 for w in words if w in clean_text)
    if words:
        coverage = matched_words / len(words)
        if coverage >= 0.75:
            boost += 0.01

    return min(boost, 0.05)


def merge_results(
    tfidf_results: list[RetrievalResult],
    semantic_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult] | None = None,
    query: str = "",
) -> list[RetrievalResult]:

    bm25_results = bm25_results or []

    merged: dict[
        int,
        RetrievalResult
    ] = {}

    for result in tfidf_results:
        merged[result.index] = result

    for result in semantic_results:
        if result.index not in merged:
            merged[result.index] = result
        else:
            merged[result.index].semantic_score = result.semantic_score

    for result in bm25_results:
        if result.index not in merged:
            merged[result.index] = result
        else:
            merged[result.index].bm25_score = result.bm25_score

    rrf_scores = reciprocal_rank_fusion(
        tfidf_results,
        semantic_results,
        bm25_results,
    )

    for index, score in rrf_scores.items():
        if index in merged:
            res = merged[index]
            phrase_boost = calculate_phrase_boost(query, res.text)
            res.rrf_score = score + phrase_boost

    results = list(merged.values())

    results.sort(
        key=lambda result: (
            result.rrf_score
        ),
        reverse=True,
    )

    return results


# ============================================================
# PAGE AGGREGATION
# ============================================================

def aggregate_pages(
    results: list[RetrievalResult],
) -> dict[
    int,
    list[RetrievalResult]
]:

    pages: dict[
        int,
        list[RetrievalResult]
    ] = {}

    for result in results:

        pages.setdefault(
            result.page,
            [],
        ).append(result)

    for page in pages:

        pages[page].sort(
            key=lambda result: (
                result.rrf_score
            ),
            reverse=True,
        )

    return pages


# ============================================================
# SCORE QUALITY
# ============================================================

def lexical_quality(
    score: float,
) -> float:

    low = TFIDF_MIN_QUALITY

    high = TFIDF_MAX_QUALITY

    if score <= low:
        return 0.0

    if score >= high:
        return 1.0

    return clamp01(
        (
            score - low
        )
        / (
            high - low
        )
    )


def semantic_quality(
    score: float,
) -> float:

    low = SEMANTIC_MIN_QUALITY

    high = SEMANTIC_MAX_QUALITY

    if score <= low:
        return 0.0

    if score >= high:
        return 1.0

    return clamp01(
        (
            score - low
        )
        / (
            high - low
        )
    )


def bm25_quality(
    score: float,
) -> float:

    low = BM25_MIN_QUALITY

    high = BM25_MAX_QUALITY

    if score <= low:
        return 0.0

    if score >= high:
        return 1.0

    return clamp01(
        (
            score - low
        )
        / (
            high - low
        )
    )


# ============================================================
# AGREEMENT
# ============================================================

def calculate_agreement(
    tfidf_results: list[RetrievalResult],
    semantic_results: list[RetrievalResult],
) -> float:
    """
    Do the lexical and dense legs agree on the same material?

    Phase 3 change: this was binary (any overlap in the top 5 -> 1.0).
    That over-credited single-chance collisions. It is now graduated:
    0.5 for one shared page, 1.0 for two or more. Single-chance
    collisions remain the weakest form of agreement, which is exactly
    the situation the evidence-sufficiency layer then has to judge.
    """

    if (
        not tfidf_results
        or not semantic_results
    ):
        return 0.0

    tfidf_pages = {
        result.page
        for result in tfidf_results[:5]
    }

    semantic_pages = {
        result.page
        for result in semantic_results[:5]
    }

    common_pages = (
        tfidf_pages
        & semantic_pages
    )

    if not common_pages:
        return 0.0

    return 1.0 if len(common_pages) >= 2 else 0.5


# ============================================================
# MARGIN
# ============================================================

def calculate_margin_quality(
    results: list[RetrievalResult],
) -> float:

    if not results:
        return 0.0

    if len(results) < 2:
        return 0.5

    first = results[0].rrf_score

    second = results[1].rrf_score

    margin = first - second

    return clamp01(
        margin / 0.005
    )


# ============================================================
# GROUNDING CONFIDENCE
# ============================================================

def calculate_grounding_confidence(
    results: list[RetrievalResult],
    tfidf_results: list[RetrievalResult],
    semantic_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult] | None = None,
) -> float:

    if not results:
        return 0.0

    best = results[0]

    lexical = lexical_quality(
        best.tfidf_score
    )

    # BM25 may only STRENGTHEN the lexical signal (max, never a
    # replacement), so enabling the BM25 leg cannot make the
    # grounding gate stricter for an existing question.
    #
    # MEASURED SIDE EFFECT (tests/benchmark_retrieval.py): on questions
    # the textbook does not really answer, BM25 words raised this
    # lexical term and pushed an off-target page further above the gate
    # (e.g. 0.697 -> 0.783 on an enzyme-name probe).
    #
    # FIX (Phase 3): BM25 may only lift the lexical signal when the
    # DENSE leg agrees that the same page is relevant. Lexical vocab
    # alone is not evidence.
    if bm25_results and semantic_results:

        dense_top_pages = {
            result.page
            for result in semantic_results[:5]
        }

        if best.page in dense_top_pages:

            lexical = max(
                lexical,
                bm25_quality(best.bm25_score),
            )

    semantic = semantic_quality(
        best.semantic_score
    )

    agreement = (
        calculate_agreement(
            tfidf_results,
            semantic_results,
        )
    )

    margin = (
        calculate_margin_quality(
            results
        )
    )

    pages = {
        result.page
        for result in results[:6]
    }

    support_quality = clamp01(
        len(pages) / 3.0
    )

    if semantic_results:

        confidence = (
            0.30 * lexical
            + 0.35 * semantic
            + 0.20 * agreement
            + 0.10 * margin
            + 0.05 * support_quality
        )

    else:

        confidence = (
            0.65 * lexical
            + 0.20 * margin
            + 0.15 * support_quality
        )

    return clamp01(
        confidence
    )


# ============================================================
# PAGE SELECTION
# ============================================================

def select_pages(
    results: list[RetrievalResult],
) -> list[RetrievalResult]:

    if not results:
        return []

    pages = aggregate_pages(
        results
    )

    page_scores: dict[
        int,
        float
    ] = {}

    for page, page_results in pages.items():

        best_rrf = max(
            result.rrf_score
            for result in page_results
        )

        support_bonus = min(
            len(page_results),
            2,
        ) * 0.0005

        page_scores[page] = (
            best_rrf
            + support_bonus
        )

    ranked_pages = sorted(
        page_scores,
        key=page_scores.get,
        reverse=True,
    )

    selected_pages = ranked_pages[
        :MAX_CONTEXT_PAGES
    ]

    selected: list[
        RetrievalResult
    ] = []

    for page in selected_pages:

        page_results = pages[
            page
        ][
            :MAX_CHUNKS_PER_PAGE
        ]

        for result in page_results:

            result.page_score = (
                page_scores[page]
            )

            selected.append(
                result
            )

    selected.sort(
        key=lambda result: (
            result.page,
            -result.rrf_score,
        )
    )

    return selected


# ============================================================
# NEIGHBOUR PAGES
# ============================================================

def add_neighbor_pages(
    selected: list[RetrievalResult],
) -> list[RetrievalResult]:

    if not ENABLE_NEIGHBOR_PAGES or not selected:
        return selected

    existing_pages = list(dict.fromkeys(r.page for r in selected))

    if len(existing_pages) >= MAX_CONTEXT_PAGES:
        return selected

    candidate_neighbors: list[RetrievalResult] = []

    top_page = max(
        existing_pages,
        key=lambda p: max(r.rrf_score for r in selected if r.page == p)
    )

    for neighbour in (top_page - 1, top_page + 1):
        if neighbour <= 0 or neighbour in existing_pages:
            continue

        for index, chunk in enumerate(chunks):
            if int(chunk["page"]) == neighbour:
                base_score = max(r.rrf_score for r in selected if r.page == top_page)
                candidate_neighbors.append(
                    RetrievalResult(
                        index=index,
                        page=neighbour,
                        text=chunk["text"],
                        rrf_score=base_score * NEIGHBOR_PAGE_PENALTY,
                        page_score=base_score * NEIGHBOR_PAGE_PENALTY,
                    )
                )
                break

    final_results = list(selected)
    added_pages = set()

    for cand in candidate_neighbors:
        if len(existing_pages) + len(added_pages) < MAX_CONTEXT_PAGES:
            if cand.page not in existing_pages and cand.page not in added_pages:
                added_pages.add(cand.page)
                final_results.append(cand)

    final_results.sort(
        key=lambda result: (
            result.page,
            -result.rrf_score,
        )
    )

    return final_results


# ============================================================
# MAIN RETRIEVAL API
# ============================================================

def retrieve_biology(
    query: str,
) -> RetrievalResponse:
    """
    Public Biology retrieval API.

    main.py only needs:

        retrieve_biology(question)

    The retriever handles the rest.
    """

    # --------------------------------------------------------
    # Empty query
    # --------------------------------------------------------

    if not query or not query.strip():

        return RetrievalResponse(
            results=[],
            confidence=0.0,
            grounded=False,
            best_page=None,
            reason="Empty question.",
        )

    # --------------------------------------------------------
    # Make sure the index exists
    # --------------------------------------------------------

    if not initialize_retriever():

        return RetrievalResponse(
            results=[],
            confidence=0.0,
            grounded=False,
            best_page=None,
            reason=(
                "Biology Resource Book could not "
                "be indexed."
            ),
        )

    # --------------------------------------------------------
    # TF-IDF
    # --------------------------------------------------------

    tfidf_results = keyword_search(
        query
    )

    # --------------------------------------------------------
    # Semantic
    # --------------------------------------------------------

    semantic_results: list[
        RetrievalResult
    ] = []

    if (
        semantic_available
        and semantic_embeddings is not None
    ):

        semantic_results = (
            semantic_search(
                query
            )
        )

    # --------------------------------------------------------
    # BM25 (hybrid mode only)
    # --------------------------------------------------------

    bm25_results: list[RetrievalResult] = []

    if BM25_ENABLED and bm25_available:

        bm25_results = bm25_search(
            query
        )

    # --------------------------------------------------------
    # Merge with exact phrase matching boost
    # --------------------------------------------------------

    merged = merge_results(
        tfidf_results,
        semantic_results,
        bm25_results,
        query=query,
    )

    if not merged:

        return RetrievalResponse(
            results=[],
            confidence=0.0,
            grounded=False,
            best_page=None,
            reason=(
                "No meaningful textbook "
                "match found."
            ),
        )

    # --------------------------------------------------------
    # Grounding confidence
    # --------------------------------------------------------

    confidence = (
        calculate_grounding_confidence(
            results=merged,
            tfidf_results=tfidf_results,
            semantic_results=semantic_results,
            bm25_results=bm25_results,
        )
    )

    # --------------------------------------------------------
    # 0.55 GROUNDING GATE
    # --------------------------------------------------------

    grounded = (
        confidence
        >= GROUNDING_THRESHOLD
    )

    if not grounded:

        return RetrievalResponse(
            results=[],
            confidence=confidence,
            grounded=False,
            best_page=None,
            reason=(
                "Textbook matches were too weak "
                "to safely claim textbook grounding."
            ),
        )

    # --------------------------------------------------------
    # Select pages
    # --------------------------------------------------------

    selected = select_pages(
        merged
    )

    # --------------------------------------------------------
    # Neighbour pages (strictly capped at MAX_CONTEXT_PAGES)
    # --------------------------------------------------------

    selected = add_neighbor_pages(
        selected
    )

    # --------------------------------------------------------
    # Apply confidence & Select true best_page by highest score
    # --------------------------------------------------------

    for result in selected:

        result.confidence = (
            confidence
        )

    best_result = (
        max(selected, key=lambda r: (r.rrf_score, r.page_score))
        if selected
        else None
    )

    best_page = (
        best_result.page
        if best_result
        else None
    )

    return RetrievalResponse(
        results=selected,
        confidence=confidence,
        grounded=True,
        best_page=best_page,
        reason=(
            "Strong textbook evidence found."
        ),
    )


# ============================================================
# CONTEXT BUILDER
# ============================================================

def create_textbook_context(
    response: RetrievalResponse,
) -> str:
    """
    Convert retrieved pages into context for the LLM.
    """

    if not response.grounded:
        return ""

    if not response.results:
        return ""

    context_parts: list[str] = []

    current_page = None

    for result in response.results:

        if result.page != current_page:

            current_page = result.page

            context_parts.append(
                (
                    f"--- Biology Resource Book "
                    f"| Page {result.page} ---"
                )
            )

        context_parts.append(
            result.text.strip()
        )

    return "\n\n".join(
        context_parts
    )


# ============================================================
# SOURCE PAGES
# ============================================================

def get_source_pages(
    response: RetrievalResponse,
) -> list[int]:

    if not response.grounded:
        return []

    pages = sorted(
        {
            result.page
            for result in response.results
        }
    )

    return pages


# ============================================================
# RETRIEVER STATUS
# ============================================================

def get_retriever_status() -> dict[str, Any]:
    """
    Returns actual runtime status of the Biology retriever.
    """

    unique_pages = len({c["page"] for c in chunks}) if chunks else 0

    return {
        "initialized": _initialized,
        "pdf_exists": PDF_FILE.exists(),
        "textbook_loaded": bool(chunks),
        "page_count": unique_pages,
        "chunk_count": len(chunks),
        "tfidf_available": (
            tfidf_vectorizer is not None
            and tfidf_matrix is not None
        ),
        "bm25_available": (
            bm25_available
        ),
        "retrieval_mode": (
            RETRIEVAL_MODE
        ),
        "rrf_weights": dict(RRF_WEIGHTS),
        "semantic_available": (
            semantic_available
        ),
        "embedding_model": (
            EMBEDDING_MODEL
        ),
        "grounding_threshold": (
            GROUNDING_THRESHOLD
        ),
        "visual_chunks": len(visual_chunks),
    }