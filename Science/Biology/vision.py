# Science/Biology/vision.py
#
# VisionService — Qwen3-VL-8B visual understanding layer for Exora AI.
#
# Responsibilities:
#   1. Deterministic detection of when vision is needed
#   2. Render textbook pages to images (pymupdf, cached on disk)
#   3. Biology-specific structured extraction via Qwen3-VL-8B (LM Studio)
#   4. Disk cache keyed by book + page + image hash
#   5. Visual chunks (diagram/table/chart/figure) with their own
#      TF-IDF + semantic index so retrieval can find visuals by question
#   6. Student image analysis -> concept extraction -> textbook retrieval
#
# Qwen3-VL-8B is NOT the final teacher. It is the visual/document
# understanding specialist. GPT-OSS-20B remains the final reasoning
# and teaching model.

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from config import (
    PDF_FILE,
    VISION_ENABLED,
    VISION_MODEL,
    VISION_BASE_URL,
    VISION_TEMPERATURE,
    VISION_MAX_TOKENS,
    VISION_TIMEOUT,
    VISION_PAGE_IMAGE_DPI,
    VISION_PAGE_IMAGE_FORMAT,
    VISION_CACHE_EXTRACTS,
    VISION_CACHE_FILE,
    VISUAL_CHUNKS_FILE,
    PAGE_IMAGES_DIR,
)

BOOK_ID = "bio12"  # A/L Biology Resource Book (Grades 12-13 combined volume)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class VisionDecision:
    """Result of deterministic visual-requirement detection."""
    required: bool
    reason: str
    signals: list[str] = field(default_factory=list)
    page_hint: Optional[int] = None


@dataclass
class VisualAnalysis:
    """Full record of one Qwen3-VL visual analysis."""
    page: Optional[int]
    image_path: str
    image_hash: str
    cache_key: str
    visual_type: str
    structured: dict[str, Any]
    raw_output: str
    processing_time: float
    from_cache: bool = False
    error: Optional[str] = None


# ============================================================
# VISUAL QUESTION DETECTION (deterministic signals)
# ============================================================

VISUAL_QUESTION_PATTERNS = [
    r"\bdiagram\b",
    r"\bfigure\b",
    r"\bfig\.?\s*\d*\b",
    r"\bimage\b",
    r"\bpicture\b",
    r"\bchart\b",
    r"\bgraph\b",
    r"\btable\b",
    r"\blabelled?\b",
    r"\blabeled?\b",
    r"\billustration\b",
    r"\bshown in\b",
    r"\bshown above\b",
    r"\bprocess shown\b",
    r"\bflow chart\b",
    r"\bflowchart\b",
    r"\bcycle\b.*\bdiagram\b",
    r"\bdraw\b",
    r"\bsketch\b",
]

PAGE_REFERENCE_PATTERN = r"\bpage\s+(\d{1,3})\b"

# Text in extracted PDF pages that suggests visual content on that page.
PAGE_VISUAL_TEXT_HINTS = [
    "fig.",
    "figure",
    "diagram",
    "table",
    "graph",
    "chart",
    "labelled",
    "labeled",
    "illustration",
]

# Ratio thresholds for "image-heavy" pages.
IMAGE_AREA_HEAVY_RATIO = 0.25
IMAGE_COUNT_HEAVY = 3


def detect_visual_requirement(
    question: str,
    has_image: bool = False,
    retrieved_pages: Optional[list[int]] = None,
) -> VisionDecision:
    """
    Deterministic, lightweight decision on whether vision is needed.

    Signals (any one is enough):
        1. Student uploaded an image
        2. Question explicitly references a diagram/figure/table/etc.
        3. Question references a specific page -> that page may need vision
        4. Retrieved pages are image-heavy
    """
    signals: list[str] = []
    page_hint: Optional[int] = None

    if has_image:
        signals.append("student_uploaded_image")

    text = (question or "").lower()

    for pattern in VISUAL_QUESTION_PATTERNS:
        if re.search(pattern, text):
            signals.append(f"visual_term:{pattern}")
            break

    match = re.search(PAGE_REFERENCE_PATTERN, text)
    if match:
        page_hint = int(match.group(1))
        signals.append(f"page_reference:{page_hint}")

    # Image-heavy retrieved pages: recorded as information only.
    # They must NOT trigger Qwen on their own, otherwise every normal
    # text question about a visual topic (e.g. "What is ultrafiltration?")
    # would invoke the vision model.
    heavy_pages: list[int] = []
    if retrieved_pages and not has_image:
        for page in retrieved_pages[:5]:
            info = get_page_visual_info(page)
            if info and info.get("image_heavy"):
                heavy_pages.append(page)

    if heavy_pages:
        signals.append(f"retrieved_pages_image_heavy:{heavy_pages}")

    # Decide requirement: image, visual term, or page reference are
    # sufficient. Image-heavy retrieved pages alone are NOT.
    hard_signals = [
        s for s in signals
        if s == "student_uploaded_image"
        or s.startswith("visual_term:")
        or s.startswith("page_reference:")
    ]

    if not hard_signals:
        reason = "No visual signals in the question (retrieved pages may contain images, but vision is not required)."
        if heavy_pages:
            reason = (
                "No visual signals in the question; retrieved pages "
                f"{heavy_pages} contain images but the question is text-only."
            )
        return VisionDecision(
            required=False,
            reason=reason,
            signals=signals,
            page_hint=page_hint,
        )

    if has_image:
        reason = "Student uploaded an image for analysis."
    elif any(s.startswith("visual_term:") for s in signals):
        reason = "Question explicitly references visual content (diagram/figure/table/graph)."
    else:
        reason = "Question references a specific textbook page."

    return VisionDecision(
        required=True,
        reason=reason,
        signals=signals,
        page_hint=page_hint,
    )


def page_contains_visual_text(text: str) -> bool:
    """Checks whether extracted page text mentions figures/tables."""
    lowered = (text or "").lower()
    return any(hint in lowered for hint in PAGE_VISUAL_TEXT_HINTS)


# ============================================================
# PAGE IMAGE RENDERING (pymupdf, disk-cached)
# ============================================================

_page_visual_info_cache: dict[int, dict[str, Any]] = {}


def get_page_visual_info(page_number: int) -> Optional[dict[str, Any]]:
    """
    Lightweight metadata about a page's visual content:
    image count, image area ratio, image-heavy flag.

    Deterministic. Does NOT call Qwen.
    """
    if page_number in _page_visual_info_cache:
        return _page_visual_info_cache[page_number]

    try:
        import pymupdf
    except ImportError:
        return None

    if not PDF_FILE.exists():
        return None

    try:
        with pymupdf.open(PDF_FILE) as document:
            if page_number < 1 or page_number > len(document):
                return None

            page = document.load_page(page_number - 1)

            image_list = page.get_images(full=True)
            page_area = abs(page.rect)

            image_area = 0.0
            for image in image_list:
                try:
                    rects = page.get_image_rects(image[0])
                    for rect in rects:
                        image_area += abs(rect)
                except Exception:
                    continue

            area_ratio = image_area / page_area if page_area else 0.0

            text = page.get_text("text")
            has_visual_text = page_contains_visual_text(text)

            image_heavy = (
                area_ratio >= IMAGE_AREA_HEAVY_RATIO
                or len(image_list) >= IMAGE_COUNT_HEAVY
            )

            info = {
                "page": page_number,
                "image_count": len(image_list),
                "image_area_ratio": round(area_ratio, 3),
                "image_heavy": image_heavy,
                "visual_text_hints": has_visual_text,
                "likely_visual": image_heavy or has_visual_text,
            }

            _page_visual_info_cache[page_number] = info
            return info

    except Exception:
        return None


def render_page_image(page_number: int, force_refresh: bool = False) -> Optional[Path]:
    """
    Renders one textbook page to an image file (disk-cached).

    Returns the path to the PNG, or None on failure.
    """
    if not PDF_FILE.exists():
        return None

    PAGE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    image_path = PAGE_IMAGES_DIR / (
        f"{BOOK_ID}_page_{page_number:03d}.{VISION_PAGE_IMAGE_FORMAT}"
    )

    if image_path.exists() and not force_refresh:
        return image_path

    try:
        import pymupdf

        with pymupdf.open(PDF_FILE) as document:
            if page_number < 1 or page_number > len(document):
                return None

            page = document.load_page(page_number - 1)

            pix = page.get_pixmap(
                dpi=VISION_PAGE_IMAGE_DPI,
                alpha=False,
            )

            pix.save(str(image_path))
            return image_path

    except Exception:
        return None


# ============================================================
# IMAGE LOADING / ENCODING
# ============================================================

def load_image_as_data_url(image_path: str | Path) -> Optional[str]:
    """
    Loads an image file and returns it as a base64 data URL
    for the OpenAI-compatible multimodal content format.
    """
    path = Path(image_path)

    if not path.exists():
        return None

    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
    }.get(suffix, "image/png")

    try:
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return None


def hash_image(image_path: str | Path) -> str:
    """Stable short hash of the image bytes (for cache keys)."""
    try:
        data = Path(image_path).read_bytes()
        return hashlib.sha256(data).hexdigest()[:12]
    except Exception:
        return "nohash"


# ============================================================
# QWEN3-VL EXTRACTION PROMPTS (Biology-specific)
# ============================================================

BASE_EXTRACTION_SYSTEM_PROMPT = """You are a visual document understanding \
specialist for Sri Lankan G.C.E. Advanced Level (A/L) Biology textbooks.

Your job is to extract what is VISIBLY present in a textbook page image \
as structured JSON. You are NOT answering the student. You are NOT teaching.

STRICT RULES:

1. Report ONLY what is clearly visible in the image.
2. Distinguish clearly between:
   - "visible": information you can literally read/see in the image
   - "inferred": biological knowledge you are adding from context
3. NEVER invent labels, structures, values or relationships.
4. If a label cannot be read clearly, write "unreadable label".
5. If something is unclear, write "unclear" rather than guessing.
6. Preserve EXACT textbook terminology. Do not simplify terms.
   Simplification is done later by a different model.
7. This is a Sri Lankan G.C.E. A/L Biology textbook (English medium).
   Prioritise: labelled biological structures, physiological processes, \
cellular/molecular structures, anatomical diagrams, ecological diagrams, \
experimental setups, graphs, tables, cycles, pathways, sequences, \
cause-and-effect arrows.
8. Output ONLY valid JSON. No markdown fences, no commentary.

Choose the schema matching the dominant visual:

DIAGRAM/labelled illustration:
{
  "page": <int page number if visible, else null>,
  "visual_type": "diagram",
  "topic": "<biological topic>",
  "title": "<figure title if present, else null>",
  "caption": "<caption text if present, else null>",
  "components": [{"name": "...", "label": "<exact label text>", "description": "..."}],
  "relationships": [{"from": "...", "to": "...", "relationship": "..."}],
  "process": null,
  "visible_text": ["<all readable embedded text>"],
  "table_data": null,
  "inferred_notes": ["<biological context you added, each clearly inferred>"],
  "confidence_notes": ["<anything uncertain>"]
}

PROCESS / cycle / pathway (ordered steps matter):
{
  ... same fields ...,
  "components": [...],
  "relationships": [...],
  "process": {
    "name": "...",
    "steps": [{"order": 1, "description": "...", "location": "..."}]
  }
}

TABLE:
{
  ... same fields ...,
  "visual_type": "table",
  "components": null,
  "relationships": null,
  "table_data": {
    "title": "...",
    "columns": ["..."],
    "rows": [["...", "..."]],
    "notes": ["..."]
  }
}

CHART / GRAPH:
{
  ... same fields ...,
  "visual_type": "chart",
  "components": null,
  "chart_data": {
    "chart_type": "line|bar|pie|scatter",
    "x_axis": {"label": "...", "units": "..."},
    "y_axis": {"label": "...", "units": "..."},
    "series": [{"name": "...", "points": "...", "trend": "..."}],
    "key_values": ["<important readable values>"],
    "trends": ["<described trends>"]
  },
  "table_data": null
}

If the page contains MULTIPLE visuals, output:
{"page": <int>, "visual_type": "multiple", "visuals": [<one object per visual using the schemas above>]}

If the page has NO meaningful visual content, output:
{"page": <int>, "visual_type": "none", "topic": null, "note": "No meaningful visual content on this page."}
"""

STUDENT_IMAGE_SYSTEM_PROMPT = """You are a visual analysis assistant for Sri \
Lankan G.C.E. Advanced Level (A/L) Biology.

A student has uploaded a Biology image (diagram, structure, graph, table, \
or photograph). Analyse what is VISIBLY present.

STRICT RULES:
1. Report only what is clearly visible; mark uncertain items "unclear".
2. Never invent labels. Use "unreadable label" where you cannot read.
3. Preserve exact biological terminology.
4. Output ONLY valid JSON, no markdown fences.

Output schema:
{
  "visual_type": "diagram|structure|table|chart|process|photograph|unknown",
  "topic": "<biological topic, or null if unsure>",
  "title": "<title if visible, else null>",
  "components": [{"name": "...", "label": "...", "description": "..."}],
  "relationships": [{"from": "...", "to": "...", "relationship": "..."}],
  "process": null or {"name": "...", "steps": [{"order": 1, "description": "..."}]},
  "table_data": null or {"columns": [...], "rows": [[...]]},
  "chart_data": null or {"chart_type": "...", "x_axis": {...}, "y_axis": {...}, "key_values": [...], "trends": [...]},
  "visible_text": ["..."],
  "inferred_notes": ["..."],
  "confidence_notes": ["..."],
  "possible_concepts": ["<3-8 A/L Biology concept keywords this image relates to>"]
}
"""

CONCEPT_EXTRACTION_PROMPT = """You are given a structured visual analysis of a \
Biology image a student uploaded.

Extract 3-8 concise A/L Biology retrieval keywords/concepts that would find \
the relevant textbook pages. Output ONLY a JSON array of strings, nothing else.

Visual analysis:
{analysis}

Student question (may be empty):
{question}
"""


def build_page_extraction_messages(
    image_data_url: str,
    page_number: int,
    question: str = "",
) -> list[dict]:
    """Multimodal chat messages for textbook page extraction."""
    instruction = (
        f"This is page {page_number} of a Sri Lankan G.C.E. A/L Biology "
        f"textbook. Extract all meaningful visual information as structured "
        f"JSON following the system rules."
    )
    if question:
        instruction += f"\n\nThe student asked: \"{question}\"\nExtract ALL visual information on the page (not only what the question asks)."

    return [
        {"role": "system", "content": BASE_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]


def build_student_image_messages(
    image_data_url: str,
    question: str = "",
) -> list[dict]:
    """Multimodal chat messages for student-uploaded image analysis."""
    instruction = "Analyse this student-uploaded Biology image. Output only the JSON schema."
    if question:
        instruction = (
            f"The student asked: \"{question}\"\n"
            "Analyse the image and output only the JSON schema. "
            "Cover everything visible, not only what the question asks."
        )

    return [
        {"role": "system", "content": STUDENT_IMAGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]


# ============================================================
# JSON PARSING / VALIDATION
# ============================================================

def parse_json_output(raw: str) -> Optional[dict[str, Any]]:
    """
    Parses Qwen's JSON output tolerantly.
    Handles markdown fences and leading/trailing prose.
    """
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown fences
    fence_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL,
    )
    if fence_match:
        text = fence_match.group(1).strip()

    # Direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Find outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

    return None


KNOWN_VISUAL_TYPES = {
    "diagram", "table", "chart", "figure", "process",
    "multiple", "none", "structure", "photograph", "unknown",
}


def normalise_visual_type(structured: dict[str, Any]) -> str:
    """Extracts and normalises the visual_type field."""
    visual_type = str(structured.get("visual_type", "visual")).lower().strip()
    if visual_type in KNOWN_VISUAL_TYPES:
        return visual_type
    return "visual"


def build_visual_search_text(structured: dict[str, Any]) -> str:
    """
    Builds a natural-language searchable representation of the
    structured visual data so TF-IDF and semantic search can find it.
    """
    parts: list[str] = []

    topic = structured.get("topic")
    if topic:
        parts.append(f"Topic: {topic}")

    title = structured.get("title")
    if title:
        parts.append(f"Title: {title}")

    caption = structured.get("caption")
    if caption:
        parts.append(f"Caption: {caption}")

    components = structured.get("components")
    if isinstance(components, list):
        for comp in components:
            if isinstance(comp, dict):
                label = comp.get("label") or comp.get("name") or ""
                desc = comp.get("description") or ""
                line = f"Component: {label}"
                if desc:
                    line += f" — {desc}"
                parts.append(line)

    relationships = structured.get("relationships")
    if isinstance(relationships, list):
        for rel in relationships:
            if isinstance(rel, dict):
                frm = rel.get("from", "")
                to = rel.get("to", "")
                relation = rel.get("relationship", "")
                parts.append(f"Relationship: {frm} -> {to} ({relation})")

    process = structured.get("process")
    if isinstance(process, dict):
        name = process.get("name", "")
        parts.append(f"Process: {name}")
        steps = process.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    order = step.get("order", "")
                    desc = step.get("description", "")
                    parts.append(f"Step {order}: {desc}")

    table_data = structured.get("table_data")
    if isinstance(table_data, dict):
        t_title = table_data.get("title")
        if t_title:
            parts.append(f"Table: {t_title}")
        columns = table_data.get("columns")
        if isinstance(columns, list):
            parts.append("Columns: " + ", ".join(str(c) for c in columns))
        rows = table_data.get("rows")
        if isinstance(rows, list):
            for row in rows[:30]:
                if isinstance(row, list):
                    parts.append(" | ".join(str(cell) for cell in row))

    chart_data = structured.get("chart_data")
    if isinstance(chart_data, dict):
        parts.append(
            f"Chart ({chart_data.get('chart_type', '')}): "
            f"x={chart_data.get('x_axis', {}).get('label', '') if isinstance(chart_data.get('x_axis'), dict) else ''}, "
            f"y={chart_data.get('y_axis', {}).get('label', '') if isinstance(chart_data.get('y_axis'), dict) else ''}"
        )
        trends = chart_data.get("trends")
        if isinstance(trends, list):
            parts.extend(str(t) for t in trends)
        key_values = chart_data.get("key_values")
        if isinstance(key_values, list):
            parts.extend(str(v) for v in key_values)

    visible_text = structured.get("visible_text")
    if isinstance(visible_text, list):
        parts.extend(str(t) for t in visible_text)

    return "\n".join(p for p in parts if p)


def build_visual_description(structured: dict[str, Any]) -> str:
    """One-paragraph human-readable summary of the visual."""
    pieces: list[str] = []

    vtype = structured.get("visual_type", "visual")
    topic = structured.get("topic") or ""
    title = structured.get("title") or ""

    header = f"{str(vtype).capitalize()}"
    if topic:
        header += f" — {topic}"
    if title and title != topic:
        header += f" ({title})"
    pieces.append(header)

    components = structured.get("components")
    if isinstance(components, list) and components:
        labels = [
            (c.get("label") or c.get("name") or "")
            for c in components
            if isinstance(c, dict)
        ]
        labels = [l for l in labels if l]
        if labels:
            pieces.append("Labels: " + ", ".join(labels))

    process = structured.get("process")
    if isinstance(process, dict) and process.get("name"):
        steps = process.get("steps") or []
        pieces.append(
            f"Process '{process['name']}' with {len(steps)} steps"
        )

    table_data = structured.get("table_data")
    if isinstance(table_data, dict):
        rows = table_data.get("rows") or []
        pieces.append(f"Table with {len(rows)} rows")

    if structured.get("visual_type") == "none":
        return "No meaningful visual content."

    return ". ".join(p for p in pieces if p)


# ============================================================
# CACHE
# ============================================================

_vision_cache: dict[str, Any] = {}
_cache_loaded = False


def _load_vision_cache() -> None:
    global _vision_cache, _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    try:
        if VISION_CACHE_FILE.exists():
            with open(VISION_CACHE_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                _vision_cache = data
    except Exception:
        _vision_cache = {}


def _save_vision_cache() -> None:
    try:
        VISION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = VISION_CACHE_FILE.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as file:
            json.dump(_vision_cache, file, indent=2)
        import os
        os.replace(temp, VISION_CACHE_FILE)
    except Exception:
        pass


def make_cache_key(page: Optional[int], image_hash: str) -> str:
    """book + page + image hash"""
    return f"{BOOK_ID}_page_{page if page is not None else 'img'}_{image_hash}"


def get_cached_result(cache_key: str) -> Optional[dict[str, Any]]:
    _load_vision_cache()
    return _vision_cache.get(cache_key)


def cache_result(cache_key: str, record: dict[str, Any]) -> None:
    if not VISION_CACHE_EXTRACTS:
        return
    _load_vision_cache()
    _vision_cache[cache_key] = record
    _save_vision_cache()


def clear_vision_cache() -> int:
    """Clears the vision analysis cache. Returns number of entries removed."""
    global _vision_cache
    _load_vision_cache()
    count = len(_vision_cache)
    _vision_cache = {}
    _save_vision_cache()
    return count


# ============================================================
# QWEN3-VL CLIENT
# ============================================================

class QwenVLClient:
    """
    Minimal client for Qwen3-VL-8B through LM Studio's
    OpenAI-compatible chat completions endpoint.

    Reuses one HTTP session; does not manage model loading.
    """

    def __init__(
        self,
        base_url: str = VISION_BASE_URL,
        model: str = VISION_MODEL,
        temperature: float = VISION_TEMPERATURE,
        max_tokens: int = VISION_MAX_TOKENS,
        timeout: int = VISION_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.session = requests.Session()

    def is_available(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/models", timeout=5)
            return response.ok
        except requests.RequestException:
            return False

    def model_loaded(self) -> bool:
        """Checks whether the configured vision model is available in LM Studio."""
        try:
            response = self.session.get(f"{self.base_url}/models", timeout=5)
            response.raise_for_status()
            ids = [
                m.get("id", "")
                for m in response.json().get("data", [])
                if m.get("id")
            ]
            return any(
                VISION_MODEL.lower() in str(mid).lower() or str(mid).lower() in VISION_MODEL.lower()
                for mid in ids
            ) or VISION_MODEL in ids
        except Exception:
            return False

    def chat(self, messages: list[dict]) -> str:
        """
        Sends multimodal chat messages to Qwen3-VL-8B.
        Returns the raw text response.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.ConnectionError:
            raise RuntimeError(
                "Could not connect to LM Studio for vision. "
                "Make sure LM Studio is running and the local server is started."
            )
        except requests.Timeout:
            raise RuntimeError(
                "Qwen3-VL took too long to respond. The model may still be loading."
            )
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else "unknown"
            detail = ""
            try:
                detail = error.response.json().get("error", {}).get("message", "")
            except Exception:
                detail = str(error)
            raise RuntimeError(
                f"Vision API error ({status}): {detail or 'model may not be loaded'}"
            )
        except requests.RequestException as error:
            raise RuntimeError(f"Vision request failed: {error}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError("Vision API returned an unexpected response format.")

        if not content:
            raise RuntimeError("Qwen3-VL returned an empty response.")

        return str(content).strip()


_vl_client: Optional[QwenVLClient] = None


def get_vl_client() -> QwenVLClient:
    """Shared Qwen3-VL client instance (reuses the HTTP session)."""
    global _vl_client
    if _vl_client is None:
        _vl_client = QwenVLClient()
    return _vl_client


# ============================================================
# VISION SERVICE
# ============================================================

class VisionService:
    """
    Exora's visual understanding layer.

    Public API:
        detect_visual_requirement(question, has_image, retrieved_pages)
        analyze_page(page_number, question) -> VisualAnalysis
        analyze_image(image_path, question) -> VisualAnalysis (student image)
        extract_concepts(analysis, question) -> list[str]
        get_visual_chunks_for_pages(pages) -> list[dict]
    """

    def __init__(self, client: Optional[QwenVLClient] = None):
        self.client = client or get_vl_client()

    # ----------------------------------------------------
    # PAGE ANALYSIS
    # ----------------------------------------------------

    def analyze_page(
        self,
        page_number: int,
        question: str = "",
        force_refresh: bool = False,
    ) -> VisualAnalysis:
        """
        Sends a textbook page image to Qwen3-VL-8B for structured
        visual extraction. Cached by book + page + image hash.
        """
        started = time.time()

        image_path = render_page_image(page_number)
        if image_path is None:
            return VisualAnalysis(
                page=page_number,
                image_path="",
                image_hash="nohash",
                cache_key=make_cache_key(page_number, "nohash"),
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=0.0,
                error=f"Could not render page {page_number} to an image.",
            )

        image_hash = hash_image(image_path)
        cache_key = make_cache_key(page_number, image_hash)

        if not force_refresh:
            cached = get_cached_result(cache_key)
            if cached:
                return VisualAnalysis(
                    page=page_number,
                    image_path=str(image_path),
                    image_hash=image_hash,
                    cache_key=cache_key,
                    visual_type=cached.get("visual_type", "visual"),
                    structured=cached.get("structured", {}),
                    raw_output=cached.get("raw_output", ""),
                    processing_time=time.time() - started,
                    from_cache=True,
                )

        image_data_url = load_image_as_data_url(image_path)
        if image_data_url is None:
            return VisualAnalysis(
                page=page_number,
                image_path=str(image_path),
                image_hash=image_hash,
                cache_key=cache_key,
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=time.time() - started,
                error="Could not load rendered page image.",
            )

        messages = build_page_extraction_messages(
            image_data_url=image_data_url,
            page_number=page_number,
            question=question,
        )

        try:
            raw_output = self.client.chat(messages)
        except RuntimeError as error:
            return VisualAnalysis(
                page=page_number,
                image_path=str(image_path),
                image_hash=image_hash,
                cache_key=cache_key,
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=time.time() - started,
                error=str(error),
            )

        structured = parse_json_output(raw_output) or {
            "page": page_number,
            "visual_type": "unknown",
            "note": "Could not parse Qwen output as JSON.",
        }

        visual_type = normalise_visual_type(structured)

        record = {
            "page": page_number,
            "visual_type": visual_type,
            "image_hash": image_hash,
            "structured": structured,
            "raw_output": raw_output,
        }
        cache_result(cache_key, record)

        return VisualAnalysis(
            page=page_number,
            image_path=str(image_path),
            image_hash=image_hash,
            cache_key=cache_key,
            visual_type=visual_type,
            structured=structured,
            raw_output=raw_output,
            processing_time=time.time() - started,
            from_cache=False,
        )

    # ----------------------------------------------------
    # STUDENT IMAGE ANALYSIS
    # ----------------------------------------------------

    def analyze_image(
        self,
        image_path: str | Path,
        question: str = "",
    ) -> VisualAnalysis:
        """
        Analyses a student-uploaded Biology image.
        Produces structured interpretation + retrieval concepts.
        """
        started = time.time()

        path = Path(image_path)
        if not path.exists():
            return VisualAnalysis(
                page=None,
                image_path=str(path),
                image_hash="nohash",
                cache_key=make_cache_key(None, "nohash"),
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=0.0,
                error=f"Image file not found: {path}",
            )

        image_data_url = load_image_as_data_url(path)
        if image_data_url is None:
            return VisualAnalysis(
                page=None,
                image_path=str(path),
                image_hash="nohash",
                cache_key=make_cache_key(None, "nohash"),
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=0.0,
                error="Unsupported or unreadable image file.",
            )

        messages = build_student_image_messages(
            image_data_url=image_data_url,
            question=question,
        )

        try:
            raw_output = self.client.chat(messages)
        except RuntimeError as error:
            return VisualAnalysis(
                page=None,
                image_path=str(path),
                image_hash="nohash",
                cache_key=make_cache_key(None, "nohash"),
                visual_type="error",
                structured={},
                raw_output="",
                processing_time=time.time() - started,
                error=str(error),
            )

        structured = parse_json_output(raw_output) or {
            "visual_type": "unknown",
            "note": "Could not parse Qwen output as JSON.",
        }

        return VisualAnalysis(
            page=None,
            image_path=str(path),
            image_hash=hash_image(path),
            cache_key=make_cache_key(None, hash_image(path)),
            visual_type=normalise_visual_type(structured),
            structured=structured,
            raw_output=raw_output,
            processing_time=time.time() - started,
        )

    # ----------------------------------------------------
    # CONCEPT EXTRACTION (student image -> retrieval query)
    # ----------------------------------------------------

    def extract_concepts(
        self,
        analysis: VisualAnalysis,
        question: str = "",
    ) -> list[str]:
        """
        Extracts retrieval keywords from a student image analysis.

        First tries the model-provided 'possible_concepts' field;
        falls back to a text-only LLM call.
        """
        concepts: list[str] = []

        possible = analysis.structured.get("possible_concepts")
        if isinstance(possible, list):
            concepts = [str(c).strip() for c in possible if str(c).strip()]

        if concepts:
            return concepts[:8]

        # Fallback: deterministic extraction from structured fields
        text = build_visual_search_text(analysis.structured)
        if text:
            words = re.findall(r"[A-Za-z][A-Za-z\-']{3,}", text)
            seen: list[str] = []
            for word in words:
                lowered = word.lower()
                if lowered not in seen and len(seen) < 8:
                    seen.append(lowered)
            return seen

        return []

    # ----------------------------------------------------
    # VISUAL CONTEXT FORMATTING (for GPT-OSS)
    # ----------------------------------------------------

    def format_visual_context(
        self,
        analyses: list[VisualAnalysis],
    ) -> str:
        """
        Formats visual analyses as a context block for GPT-OSS.
        """
        if not analyses:
            return ""

        blocks: list[str] = ["VISUAL CONTEXT FROM QWEN3-VL-8B:"]

        for analysis in analyses:
            if analysis.error:
                blocks.append(
                    f"[Page {analysis.page}: vision error — {analysis.error}]"
                )
                continue

            header = (
                f"--- Visual analysis | Page {analysis.page} "
                f"| type: {analysis.visual_type} "
                f"| cached: {'yes' if analysis.from_cache else 'no'} ---"
            )
            blocks.append(header)
            blocks.append(
                json.dumps(
                    analysis.structured,
                    indent=2,
                    ensure_ascii=False,
                )
            )

        return "\n\n".join(blocks)


# ============================================================
# VISUAL CHUNKS (retrieval integration)
# ============================================================

def build_visual_chunk(
    analysis: VisualAnalysis,
) -> Optional[dict[str, Any]]:
    """
    Converts a page visual analysis into a visual chunk record
    compatible with the retriever's chunk format.
    """
    if analysis.error or not analysis.structured:
        return None

    if analysis.structured.get("visual_type") == "none":
        return None

    search_text = build_visual_search_text(analysis.structured)
    if not search_text or len(search_text) < 20:
        return None

    chunk_id = (
        f"{BOOK_ID}_p{analysis.page:03d}_visual_01"
        if analysis.page is not None
        else f"{BOOK_ID}_student_{analysis.image_hash}"
    )

    return {
        "chunk_id": chunk_id,
        "content_type": analysis.visual_type,
        "page": analysis.page,
        "chapter": None,
        "section": None,
        "text": search_text,
        "visual_description": build_visual_description(analysis.structured),
        "source_image": analysis.image_path,
        "cache_key": analysis.cache_key,
        "image_hash": analysis.image_hash,
    }


def save_visual_chunks(chunks: list[dict[str, Any]]) -> bool:
    """Persists visual chunks to disk (merged by chunk_id)."""
    try:
        existing: dict[str, dict[str, Any]] = {}
        if VISUAL_CHUNKS_FILE.exists():
            import pickle
            with open(VISUAL_CHUNKS_FILE, "rb") as file:
                for chunk in pickle.load(file) or []:
                    existing[chunk.get("chunk_id", "")] = chunk

        for chunk in chunks:
            existing[chunk["chunk_id"]] = chunk

        import pickle
        with open(VISUAL_CHUNKS_FILE, "wb") as file:
            pickle.dump(list(existing.values()), file)
        return True
    except Exception:
        return False


def load_visual_chunks() -> list[dict[str, Any]]:
    """Loads persisted visual chunks."""
    try:
        if not VISUAL_CHUNKS_FILE.exists():
            return []
        import pickle
        with open(VISUAL_CHUNKS_FILE, "rb") as file:
            chunks = pickle.load(file)
        return chunks if isinstance(chunks, list) else []
    except Exception:
        return []


# ============================================================
# MODULE-LEVEL CONVENIENCE API
# ============================================================

_service: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    global _service
    if _service is None:
        _service = VisionService()
    return _service


def get_vision_status() -> dict[str, Any]:
    """Runtime status for /status and /vision debugging."""
    _load_vision_cache()
    service_available = False
    model_ok = False
    if VISION_ENABLED:
        try:
            client = get_vl_client()
            service_available = client.is_available()
            model_ok = client.model_loaded() if service_available else False
        except Exception:
            pass

    visual_chunks = load_visual_chunks()

    return {
        "vision_enabled": VISION_ENABLED,
        "vision_model": VISION_MODEL,
        "vision_base_url": VISION_BASE_URL,
        "lm_studio_reachable": service_available,
        "vision_model_loaded": model_ok,
        "cached_analyses": len(_vision_cache),
        "visual_chunk_count": len(visual_chunks),
        "visual_pages": sorted(
            {
                c["page"]
                for c in visual_chunks
                if c.get("page") is not None
            }
        ),
    }
