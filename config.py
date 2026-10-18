# PEP 563 style annotation storage: config.py quotes Optional-type function
# annotations without importing the typing name; under Python 3.14
# annotations are lazily evaluated (PEP 649), but hosted runtimes on
# Python 3.12 evaluate them eagerly at definition time. Declaring the
# future import makes both behaviors identical.
from __future__ import annotations

import json
import os
from pathlib import Path



# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

_LOCAL_PDF_FILE = BASE_DIR / "Science" / "Biology" / "books" / "Biology_ResourceBook.pdf"

# Runtime data directory. Local development keeps everything in
# strud_cache/ next to the source. Hosted deployments (Render / container
# image with a mounted volume) point STRUD_DATA_DIR at the mounted disk —
# the SQLite databases, uploads and retrieval indexes are all created
# under whatever directory this resolves to.
_DATA_DIR_ENV = os.environ.get("STRUD_DATA_DIR", "").strip()

CACHE_DIR = Path(_DATA_DIR_ENV) if _DATA_DIR_ENV else BASE_DIR / "strud_cache"

# A deployed backend with these two secrets uses the private Supabase object
# as the authoritative textbook.  Local development remains completely
# offline and keeps using the existing source file.
CLOUD_KB_ENABLED = bool(
    os.environ.get("SUPABASE_URL", "").strip()
    and os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
PDF_FILE = (
    CACHE_DIR / "knowledge_base" / "Biology_ResourceBook.pdf"
    if CLOUD_KB_ENABLED
    else _LOCAL_PDF_FILE
)

CHUNKS_FILE = CACHE_DIR / "chunks.pkl"
TFIDF_FILE = CACHE_DIR / "tfidf.pkl"
META_FILE = CACHE_DIR / "metadata.json"

SEMANTIC_FILE = CACHE_DIR / "semantic_embeddings.npy"
SEMANTIC_META_FILE = CACHE_DIR / "semantic_metadata.json"

# BM25 sparse lexical index (Phase 1 hybrid retrieval)
BM25_FILE = CACHE_DIR / "bm25.pkl"

# Vision / Qwen3-VL
VISION_CONFIG_FILE = BASE_DIR / "vision_config.json"
VISION_CACHE_FILE = CACHE_DIR / "vision_cache.json"
VISUAL_CHUNKS_FILE = CACHE_DIR / "visual_chunks.pkl"
PAGE_IMAGES_DIR = CACHE_DIR / "page_images"

# Assistant (identity / verification / central flags)
ASSISTANT_CONFIG_FILE = BASE_DIR / "assistant_config.json"


def _load_assistant_config() -> dict:
    """
    Loads the central assistant configuration.

    Expected shape:

        {
          "assistant": {"name": ..., "creator": ..., "domain": ...},
          "vision": {...},
          "retrieval": {...},
          "verification": {...},
          "identity": {...}
        }
    """
    defaults = {
        "assistant": {
            "name": "Strud AI",
            "creator": "Mohammed",
            "domain": "G.C.E. Advanced Level Biology",
        },
        "vision": {"enabled": False},
        "retrieval": {
            "tfidf": True, "semantic": True,
            "reranking": True, "grounding": True,
        },
        "verification": {"enabled": True, "max_revision_attempts": 1},
        "identity": {},
    }

    try:
        with open(ASSISTANT_CONFIG_FILE, "r", encoding="utf-8") as file:
            raw = json.load(file)

        merged = dict(defaults)
        for key in ("assistant", "retrieval", "verification", "identity"):
            if isinstance(raw.get(key), dict):
                merged[key] = {**defaults[key], **raw[key]}

        if isinstance(raw.get("vision"), dict):
            merged["vision"].update(raw["vision"])

        # The externally-managed "model" block MUST be merged too. Without
        # this, changes saved from the API/Settings (model id, base URL,
        # temperature, max_tokens) were written to disk but silently
        # ignored by every runtime read of the config.
        if isinstance(raw.get("model"), dict):
            merged["model"] = {**merged.get("model", {}), **raw["model"]}

        return merged
    except Exception:
        return defaults


ASSISTANT_CONFIG = _load_assistant_config()

ASSISTANT_NAME = str(ASSISTANT_CONFIG["assistant"].get("name", "Strud AI"))
ASSISTANT_CREATOR = str(ASSISTANT_CONFIG["assistant"].get("creator", "Mohammed"))
ASSISTANT_DOMAIN = str(
    ASSISTANT_CONFIG["assistant"].get("domain", "G.C.E. Advanced Level Biology")
)

IDENTITY_CONFIG = ASSISTANT_CONFIG.get("identity", {})

VERIFICATION_ENABLED = bool(
    ASSISTANT_CONFIG.get("verification", {}).get("enabled", True)
)
VERIFICATION_MAX_REVISIONS = int(
    ASSISTANT_CONFIG.get("verification", {}).get("max_revision_attempts", 1)
)


# ============================================================
# LLM / LM STUDIO (— read from assistant_config.json "model" block)
# ============================================================
#
# The model is EXTERNALIZED CONFIG, not a constant in code. Changing
# which model Strud uses (e.g. to a GLM build you load into LM Studio)
# means editing assistant_config.json -> "model"."id" and restarting
# the backend; no source edits. Values below are defaults/fallbacks so
# config.py still exports the same names the rest of the code (LLM
# client, CLI, tests, vision) already imports.

def _load_model_config() -> dict:
    """Loads the model block, falling back to the proven defaults."""
    defaults = {
        "provider": "lm_studio",
        "base_url": "http://localhost:1234/v1",
        "id": "openai/gpt-oss-20b",
        "temperature": 0.2,
        "conversational_temperature": 0.55,
        "max_tokens": 2000,
        "timeout": 180,
    }
    try:
        block = ASSISTANT_CONFIG.get("model")
        if isinstance(block, dict):
            merged = dict(defaults)
            merged.update(block)
            # Strip internal documentation keys.
            return {
                key: value for key, value in merged.items()
                if not key.startswith("_")
            }
    except Exception:
        pass
    return defaults


_MODEL_CONFIG = _load_model_config()

MODEL_PROVIDER = str(_MODEL_CONFIG.get("provider", "lm_studio"))

# Environment overrides (hosted deployments). LLM_* environment variables
# win over assistant_config.json values so a hosted backend (Render) is
# configured without editing the config file inside an image.
MODEL = os.environ.get("LLM_MODEL_ID", "").strip() or str(
    _MODEL_CONFIG.get("id", "openai/gpt-oss-20b")
)

LM_STUDIO_BASE_URL = os.environ.get("LLM_BASE_URL", "").strip() or str(
    _MODEL_CONFIG.get("base_url", "http://localhost:1234/v1")
)

# Bearer token sent to the OpenAI-compatible endpoint. Local LM Studio
# ignores Authorization entirely; hosted providers (e.g. Gemini's
# OpenAI-compatible endpoint) REQUIRE a real key here.
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()

CHAT_ENDPOINT = f"{LM_STUDIO_BASE_URL}/chat/completions"

LLM_TEMPERATURE = float(_MODEL_CONFIG.get("temperature", 0.2))

# Slightly livelier sampling for casual/social conversational turns
# (laughter, small talk, reactions). Grounded teaching answers keep
# LLM_TEMPERATURE for factual stability.
LLM_CONVERSATIONAL_TEMPERATURE = float(
    _MODEL_CONFIG.get("conversational_temperature", 0.55)
)

LLM_MAX_TOKENS = int(_MODEL_CONFIG.get("max_tokens", 2000))

LLM_TIMEOUT = int(_MODEL_CONFIG.get("timeout", 180))

# Upper bound a user may configure for per-message output budgets.
# This is a safety ceiling, NOT what most requests use (LLM_MAX_TOKENS is
# the default budget). Raise/lower it in assistant_config.json ->
# model.max_output_tokens_limit to match what the served model accepts.
LLM_MAX_OUTPUT_LIMIT = max(
    LLM_MAX_TOKENS,
    int(_MODEL_CONFIG.get("max_output_tokens_limit", 32768)),
)

# Prompt-level reasoning-effort control for gpt-oss models.
# Accepted values mirror the OpenAI gpt-oss model card ("Reasoning: low|medium|high").
VALID_THINKING_LEVELS = ("low", "medium", "high")


def update_model_config(
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Safely updates assistant_config.json model block and refreshes runtime globals."""
    global ASSISTANT_CONFIG, _MODEL_CONFIG, MODEL, LM_STUDIO_BASE_URL, CHAT_ENDPOINT, LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_MAX_OUTPUT_LIMIT, LLM_API_KEY
    try:
        with open(ASSISTANT_CONFIG_FILE, "r", encoding="utf-8") as f:
            full_cfg = json.load(f)
    except Exception:
        full_cfg = dict(ASSISTANT_CONFIG)

    model_block = full_cfg.get("model", {})
    if model_id is not None and model_id.strip():
        model_block["id"] = model_id.strip()
    if temperature is not None:
        model_block["temperature"] = max(0.0, min(2.0, float(temperature)))
    if max_tokens is not None:
        model_block["max_tokens"] = max(1, min(32768, int(max_tokens)))
    if base_url is not None and base_url.strip():
        model_block["base_url"] = base_url.strip()

    full_cfg["model"] = model_block
    with open(ASSISTANT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(full_cfg, f, indent=2)

    ASSISTANT_CONFIG = _load_assistant_config()
    _MODEL_CONFIG = _load_model_config()
    # env > file (same precedence as module load, above).
    MODEL = os.environ.get("LLM_MODEL_ID", "").strip() or str(
        _MODEL_CONFIG.get("id", "openai/gpt-oss-20b")
    )
    LM_STUDIO_BASE_URL = os.environ.get("LLM_BASE_URL", "").strip() or str(
        _MODEL_CONFIG.get("base_url", "http://localhost:1234/v1")
    )
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
    CHAT_ENDPOINT = f"{LM_STUDIO_BASE_URL}/chat/completions"
    LLM_TEMPERATURE = float(_MODEL_CONFIG.get("temperature", 0.2))
    LLM_MAX_TOKENS = int(_MODEL_CONFIG.get("max_tokens", 2000))
    LLM_MAX_OUTPUT_LIMIT = max(
        LLM_MAX_TOKENS,
        int(_MODEL_CONFIG.get("max_output_tokens_limit", 32768)),
    )
    return dict(_MODEL_CONFIG)


# ============================================================
# VISION (QWEN3-VL) — externalized config
# ============================================================

def _load_vision_config() -> dict:
    """
    Loads externalized vision configuration.

    Expected shape:

        {
          "vision": {
            "enabled": true,
            "model": "qwen/qwen3-vl-8b",
            "base_url": "http://localhost:1234/v1",
            ...
          }
        }
    """

    defaults = {
        "enabled": False,
        "model": "qwen/qwen3-vl-8b",
        "base_url": LM_STUDIO_BASE_URL,
        "temperature": 0.1,
        "max_tokens": 2500,
        "timeout": 300,
        "page_image_dpi": 150,
        "page_image_format": "png",
        "cache_extracts": True,
    }

    try:

        with open(VISION_CONFIG_FILE, "r", encoding="utf-8") as file:
            raw = json.load(file)

        section = raw.get("vision", {})

        if not isinstance(section, dict):
            return defaults

        merged = dict(defaults)
        merged.update(section)
        return merged

    except Exception:
        return defaults


VISION_CONFIG = _load_vision_config()

VISION_ENABLED = bool(VISION_CONFIG.get("enabled", False))
VISION_MODEL = str(VISION_CONFIG.get("model", "qwen/qwen3-vl-8b"))
VISION_BASE_URL = str(VISION_CONFIG.get("base_url", LM_STUDIO_BASE_URL))
VISION_TEMPERATURE = float(VISION_CONFIG.get("temperature", 0.1))
VISION_MAX_TOKENS = int(VISION_CONFIG.get("max_tokens", 2500))
VISION_TIMEOUT = int(VISION_CONFIG.get("timeout", 300))
VISION_PAGE_IMAGE_DPI = int(VISION_CONFIG.get("page_image_dpi", 150))
VISION_PAGE_IMAGE_FORMAT = str(VISION_CONFIG.get("page_image_format", "png"))
VISION_CACHE_EXTRACTS = bool(VISION_CONFIG.get("cache_extracts", True))


# ============================================================
# SEMANTIC EMBEDDINGS
# ============================================================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

EMBEDDING_DEVICE = "cpu"

EMBEDDING_BATCH_SIZE = 32

# Build and cache semantic index during initialization
AUTO_BUILD_SEMANTIC = True


# ============================================================
# TEXT CHUNKING
# ============================================================

CHUNK_SIZE = 1400

CHUNK_OVERLAP = 250


# ============================================================
# RETRIEVAL
# ============================================================

TFIDF_TOP_K = 20

SEMANTIC_TOP_K = 20

# Maximum number of textbook pages sent to the LLM.
MAX_CONTEXT_PAGES = 5

# Maximum chunks taken from each selected page.
MAX_CHUNKS_PER_PAGE = 2


# ============================================================
# GROUNDING
# ============================================================

# Minimum confidence required before Strud claims that
# the answer is grounded in the Biology Resource Book.
#
# 0.55 -> 0.36 (Phase 3, measured):
#   The grounding gate is now the FIRST filter, not the last. It used
#   to carry the whole burden of rejecting off-topic questions, which
#   forced it high (0.55) and made it reject real textbook questions
#   whose lexical/dense legs disagree (mitochondria, chlorophyll).
#   With the evidence-sufficiency layer behind it, the gate can be
#   lenient again: it only decides "is there material worth judging",
#   and sufficiency decides "can we actually ground an answer on it".
#   Measured on tests/benchmark_grounding.py: supported-question
#   accuracy 73% -> 96%, while unsupported-probe rejection improved
#   to 100% (was 25%).
GROUNDING_THRESHOLD = 0.36


# ============================================================
# RECIPROCAL RANK FUSION
# ============================================================

RRF_K = 60


# ============================================================
# BM25 (SPARSE LEXICAL RETRIEVAL)
# ============================================================
#
# BM25 runs ALONGSIDE the existing TF-IDF leg. It is never used
# to replace the current path unless the retrieval mode below
# selects the hybrid pipeline.

BM25_TOP_K = 20

# Standard BM25 saturation / length-normalisation parameters.
BM25_K1 = 1.5

BM25_B = 0.75

# Raw BM25 scores are unbounded. These two bounds convert a raw
# BM25 score into a 0..1 "lexical quality" estimate, exactly like
# TFIDF_MIN_QUALITY / TFIDF_MAX_QUALITY do for TF-IDF.
#
# Calibrated empirically on the Biology Resource Book
# (see tests/benchmark_retrieval.py).

BM25_MIN_QUALITY = 4.0

BM25_MAX_QUALITY = 22.0


# ============================================================
# RETRIEVAL MODE (Phase 1)
# ============================================================
#
#   "tfidf_dense" -> existing pipeline: TF-IDF + MiniLM (RRF)
#   "hybrid"      -> add BM25 as an additional ranked list (RRF)
#
# Configured from assistant_config.json -> retrieval.mode

_RETRIEVAL_CONFIG = ASSISTANT_CONFIG.get("retrieval", {})
if not isinstance(_RETRIEVAL_CONFIG, dict):
    _RETRIEVAL_CONFIG = {}

RETRIEVAL_MODE = str(
    _RETRIEVAL_CONFIG.get("mode", "tfidf_dense")
).strip().lower()

if RETRIEVAL_MODE not in ("tfidf_dense", "hybrid"):
    RETRIEVAL_MODE = "tfidf_dense"

# BM25 leg active?
BM25_ENABLED = RETRIEVAL_MODE == "hybrid"

# Default per-list weights inside Reciprocal Rank Fusion.
# 1.0 keeps every leg equal to how it behaved before BM25 existed.
RRF_WEIGHTS = {
    "tfidf": 1.0,
    "bm25": 1.0,
    "semantic": 1.0,
}

_config_weights = _RETRIEVAL_CONFIG.get("rrf_weights")
if isinstance(_config_weights, dict):
    for _key in ("tfidf", "bm25", "semantic"):
        try:
            RRF_WEIGHTS[_key] = float(
                _config_weights.get(_key, RRF_WEIGHTS[_key])
            )
        except (TypeError, ValueError):
            pass


# ============================================================
# PAGE EXPANSION
# ============================================================

# Include nearby pages when they are useful for understanding
# a concept that continues across page boundaries.
ENABLE_NEIGHBOR_PAGES = True

NEIGHBOR_PAGE_PENALTY = 0.82


# ============================================================
# RETRIEVAL QUALITY CALIBRATION
# ============================================================

# Rough score ranges used to convert raw retrieval scores
# into quality estimates.
#
# These are NOT the grounding threshold.
# The final grounding confidence is calculated separately.

# Phase 3 recalibration (measured on the live index):
# the strongest raw TF-IDF match in this corpus is ~0.30, but well-
# grounded single-concept questions typically peak at 0.16-0.25. The
# old 0.30 cap made a 0.16 match look like 49% quality, starving the
# lexical term of the confidence formula. Similarly, dense cosine
# tops out around 0.60-0.68 for a direct topic hit (MiniLM), so the
# 0.70 cap systematically under-credited strong dense matches.
TFIDF_MIN_QUALITY = 0.02

TFIDF_MAX_QUALITY = 0.22

SEMANTIC_MIN_QUALITY = 0.25

SEMANTIC_MAX_QUALITY = 0.62


# ============================================================
# EVIDENCE SUFFICIENCY (post-retrieval stage)
# ============================================================
#
# A retrieval/reranking SCORE is not proof of usable evidence.
# After retrieval (and any future reranking) the sufficiency stage
# asks: "does this material actually answer the question?"
#
# It combines several independent signals (query-term coverage,
# multi-leg agreement, breadth of supporting chunks, chunk-level
# relevance) instead of trusting one score.

# Minimum sufficiency score before Strud claims textbook grounding.
EVIDENCE_SUFFICIENCY_THRESHOLD = 0.60

# Below this score the evidence is treated as unsupported.
EVIDENCE_PARTIAL_THRESHOLD = 0.40

# IDF-weighted share of the question's distinctive terms that must
# actually appear in the retrieved evidence.
EVIDENCE_MIN_TERM_COVERAGE = 0.62

# Number of distinct pages that must independently support the topic.
EVIDENCE_MIN_SUPPORTING_PAGES = 2

# A missing term whose IDF is at least this fraction of the query's
# strongest term is treated as a critical gap (the textbook cannot
# answer the question as asked).
EVIDENCE_CRITICAL_TERM_RATIO = 0.55

# Lower bound of "this chunk is about the question at all" used when
# counting independently relevant chunks.
EVIDENCE_CHUNK_RELEVANCE_FLOOR = 0.45


# ============================================================
# CONVERSATION
# ============================================================

# Number of previous messages included when building prompts.
MAX_HISTORY_MESSAGES = 6

# Bounded short-term conversational memory (turns kept for
# follow-up resolution such as "explain that again" / "why?").
MAX_MEMORY_TURNS = 8

# A follow-up this short (in words) is treated as context-dependent
# when it also looks like a follow-up or lacks its own subject.
FOLLOWUP_MAX_WORDS = 6

# Stop repeating the same closing/opening filler across turns.
REPETITION_LOOKBACK_TURNS = 6
