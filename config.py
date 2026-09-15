import json
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PDF_FILE = BASE_DIR / "Science" / "Biology" / "books" / "Biology_ResourceBook.pdf"

CACHE_DIR = BASE_DIR / "strud_cache"

CHUNKS_FILE = CACHE_DIR / "chunks.pkl"
TFIDF_FILE = CACHE_DIR / "tfidf.pkl"
META_FILE = CACHE_DIR / "metadata.json"

SEMANTIC_FILE = CACHE_DIR / "semantic_embeddings.npy"
SEMANTIC_META_FILE = CACHE_DIR / "semantic_metadata.json"

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
# LLM / LM STUDIO
# ============================================================

MODEL = "openai/gpt-oss-20b"

LM_STUDIO_BASE_URL = "http://localhost:1234/v1"

CHAT_ENDPOINT = f"{LM_STUDIO_BASE_URL}/chat/completions"

LLM_TEMPERATURE = 0.2

LLM_MAX_TOKENS = 2000

LLM_TIMEOUT = 180


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
GROUNDING_THRESHOLD = 0.55


# ============================================================
# RECIPROCAL RANK FUSION
# ============================================================

RRF_K = 60


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

TFIDF_MIN_QUALITY = 0.03

TFIDF_MAX_QUALITY = 0.30

SEMANTIC_MIN_QUALITY = 0.25

SEMANTIC_MAX_QUALITY = 0.70


# ============================================================
# CONVERSATION
# ============================================================

# Number of previous messages included when building prompts.
MAX_HISTORY_MESSAGES = 6