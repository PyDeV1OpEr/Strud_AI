# question_router.py

from enum import Enum
from dataclasses import dataclass
import re


# ============================================================
# QUESTION ROUTES
# ============================================================

class QuestionRoute(Enum):
    BIOLOGY = "biology"
    GENERAL = "general"
    META = "meta"
    CONVERSATIONAL = "conversational"
    UNKNOWN = "unknown"


@dataclass
class RouteResult:
    route: QuestionRoute
    confidence: float
    reason: str


# ============================================================
# META / STRUD QUESTIONS
# ============================================================

META_PATTERNS = [
    r"\bwho built you\b",
    r"\bwho made you\b",
    r"\bwho created you\b",
    r"\bwho developed you\b",
    r"\bwhat are you\b",
    r"\bwhat model are you\b",
    r"\bwhat model were you\b",
    r"\bwhat model do you use\b",
    r"\bwhat ai are you\b",
    r"\bwhat llm are you\b",
    r"\bwhat is your model\b",
    r"\bwho trained you\b",
    r"\bwhat powers you\b",
    r"\bhow were you built\b",
    r"\bhow were you created\b",
    r"\btell me about yourself\b",
    r"\bare you an ai\b",
    r"\bare you artificial intelligence\b",
]


# ============================================================
# CONVERSATIONAL QUESTIONS
# ============================================================

CONVERSATIONAL_PATTERNS = [
    r"^hi$",
    r"^hello$",
    r"^hey$",
    r"^hey strud$",
    r"^hi strud$",
    r"^hello strud$",
    r"^good morning$",
    r"^good afternoon$",
    r"^good evening$",
    r"^thanks$",
    r"^thank you$",
    r"^thank you strud$",
    r"^thanks strud$",
    r"^bye$",
    r"^goodbye$",
]


# ============================================================
# GENERAL KNOWLEDGE PATTERNS
# ============================================================

GENERAL_PATTERNS = [
    r"\bwhat is a quadratic equation\b",
    r"\bsolve\b",
    r"\bcalculate\b",
    r"\bcalculate the\b",
    r"\bhow much is\b",
    r"\bwhat is the capital\b",
    r"\bwho is\b",
    r"\bwhen was\b",
    r"\bwhere is\b",
    r"\bhow old is\b",
    r"\bdefine\b",
]


# ============================================================
# BIOLOGY KEYWORDS
# ============================================================

BIOLOGY_KEYWORDS = {
    # Cell biology
    "cell",
    "cells",
    "cell membrane",
    "cell wall",
    "cytoplasm",
    "nucleus",
    "nucleolus",
    "ribosome",
    "ribosomes",
    "mitochondria",
    "mitochondrion",
    "chloroplast",
    "chloroplasts",
    "vacuole",
    "lysosome",
    "golgi",
    "endoplasmic reticulum",

    # Molecular biology
    "dna",
    "rna",
    "gene",
    "genes",
    "genetic",
    "genetics",
    "chromosome",
    "chromosomes",
    "protein",
    "proteins",
    "amino acid",
    "amino acids",
    "mutation",
    "mutations",
    "replication",
    "transcription",
    "translation",

    # Cell division
    "mitosis",
    "meiosis",
    "cell division",
    "cytokinesis",

    # Enzymes / metabolism
    "enzyme",
    "enzymes",
    "substrate",
    "metabolism",
    "metabolic",
    "respiration",
    "aerobic respiration",
    "anaerobic respiration",
    "atp",
    "glycolysis",
    "fermentation",

    # Photosynthesis
    "photosynthesis",
    "chlorophyll",
    "light reaction",
    "light reactions",
    "calvin cycle",
    "carbon fixation",
    "stomata",
    "stoma",

    # Human biology
    "blood",
    "heart",
    "artery",
    "arteries",
    "vein",
    "veins",
    "capillary",
    "capillaries",
    "circulatory system",
    "digestive system",
    "digestion",
    "digestive",
    "stomach",
    "small intestine",
    "large intestine",
    "liver",
    "pancreas",
    "kidney",
    "kidneys",
    "nephron",
    "nephrons",
    "urine",
    "excretion",
    "ultrafiltration",
    "ultra filtration",
    "glomerulus",
    "glomerular",
    "bowman",
    "bowman's capsule",
    "reabsorption",
    "selective reabsorption",

    # Nervous / endocrine
    "nervous system",
    "neuron",
    "neurone",
    "neurons",
    "nerve",
    "synapse",
    "synaptic",
    "reflex",
    "reflex arc",
    "hormone",
    "hormones",
    "endocrine",
    "insulin",
    "adrenaline",

    # Reproduction
    "reproduction",
    "reproductive system",
    "gamete",
    "gametes",
    "sperm",
    "ovum",
    "ova",
    "fertilization",
    "fertilisation",
    "zygote",
    "embryo",
    "menstrual",
    "menstrual cycle",

    # Plants
    "plant",
    "plants",
    "xylem",
    "phloem",
    "transpiration",
    "translocation",
    "root",
    "roots",
    "stem",
    "leaf",
    "leaves",
    "flower",
    "flowers",
    "pollination",
    "germination",

    # Ecology
    "ecology",
    "ecosystem",
    "ecosystems",
    "population",
    "community",
    "habitat",
    "food chain",
    "food web",
    "biodiversity",
    "energy flow",
    "nutrient cycle",

    # Evolution
    "evolution",
    "natural selection",
    "adaptation",
    "speciation",

    # Microbiology
    "bacteria",
    "bacterium",
    "virus",
    "viruses",
    "fungus",
    "fungi",
    "microorganism",
    "microorganisms",
}


# ============================================================
# VISION CAPABILITY QUESTIONS
# ============================================================

# Questions about Exora's own image abilities. These are answered
# directly by the CLI (Qwen3-VL-8B provides the vision, not GPT-OSS).

VISION_CAPABILITY_PATTERNS = [
    r"\bcan you (read|see|view|analyze|analyse|understand|process|load)\b.*\b(images?|pictures?|photos?|photographs?|diagrams?|figures?|graphs?|tables?)\b",
    r"\bdo you (support|accept|take|handle|understand)\b.*\b(images?|pictures?|photos?|diagrams?|figures?)\b",
    r"\bhow (do|can) i (upload|send|add|give)\b.*\b(image|picture|photo|diagram)",
    r"\bcan (strud|exora|you) read images?\b",
]


def is_vision_capability_question(question: str) -> bool:
    """
    Detects questions about Exora's own image/vision capabilities.
    """
    text = normalise_question(question)
    return matches_pattern(text, VISION_CAPABILITY_PATTERNS)


# ============================================================
# VISUAL REFERENCE PATTERNS (no image uploaded)
# ============================================================

# Questions that reference a textbook visual (diagram/figure/graph)
# must reach textbook retrieval + the vision pipeline, even when
# they contain no Biology keyword.

VISUAL_REFERENCE_PATTERNS = [
    r"\bdiagram\b",
    r"\bfigure\b",
    r"\bfig\.?\s*\d*\b",
    r"\bgraph\b",
    r"\bchart\b",
    r"\bflow ?chart\b",
    r"\blabelled diagram\b",
    r"\bshown in the\b",
    r"\bprocess shown\b",
    r"\bthis image\b",
    r"\bthe image\b",
    r"\bwhat does label\b",
    r"\blabel [a-z0-9]\b",
]


def references_visual(question: str) -> bool:
    """
    Detects whether the question references a visual element.
    """
    text = normalise_question(question)
    return matches_pattern(text, VISUAL_REFERENCE_PATTERNS)


# ============================================================
# TEXTBOOK INDICATORS
# ============================================================

TEXTBOOK_INDICATORS = [
    "according to the book",
    "according to the textbook",
    "according to the resource book",
    "in the book",
    "in the textbook",
    "in the resource book",
    "biology resource book",
    "resource book",
    "textbook",
    "which page",
    "what page",
    "page number",
    "on page",
]


# ============================================================
# TEXT NORMALISATION
# ============================================================

def normalise_question(question: str) -> str:
    """
    Cleans the question before classification.
    """

    question = question.lower().strip()

    question = re.sub(
        r"\s+",
        " ",
        question,
    )

    return question


# ============================================================
# PATTERN MATCHING
# ============================================================

def matches_pattern(
    text: str,
    patterns: list[str],
) -> bool:

    for pattern in patterns:

        if re.search(pattern, text):
            return True

    return False


# ============================================================
# BIOLOGY SCORE
# ============================================================

def calculate_biology_score(
    question: str,
) -> float:
    """
    Calculates how strongly the question appears to be
    Biology-related.

    This is intentionally simple and fast.
    """

    text = normalise_question(question)

    score = 0.0

    for keyword in BIOLOGY_KEYWORDS:

        if keyword in text:

            # Longer phrases are stronger signals.
            if len(keyword.split()) > 1:
                score += 0.20
            else:
                score += 0.10

    return min(score, 1.0)


# ============================================================
# ROUTER
# ============================================================

def route_question(
    question: str,
    has_image: bool = False,
) -> RouteResult:
    """
    Main question router.

    Priority:

        1. Meta
        2. Conversation
        3. Image loaded -> visual pipeline (Biology)
        4. Visual reference -> Biology retrieval
        5. Explicit Biology
        6. General
        7. Unknown

    has_image: an image is loaded in the chat context (via /image).
    Questions asked while an image is loaded go through the visual
    pipeline instead of being dropped into General Knowledge.
    """

    text = normalise_question(question)

    if not text:

        return RouteResult(
            route=QuestionRoute.UNKNOWN,
            confidence=0.0,
            reason="Empty question.",
        )

    # --------------------------------------------------------
    # 1. META
    # --------------------------------------------------------

    if matches_pattern(
        text,
        META_PATTERNS,
    ):

        return RouteResult(
            route=QuestionRoute.META,
            confidence=0.99,
            reason="Question is about Strud or its AI model.",
        )

    # --------------------------------------------------------
    # 2. CONVERSATION
    # --------------------------------------------------------

    if matches_pattern(
        text,
        CONVERSATIONAL_PATTERNS,
    ):

        return RouteResult(
            route=QuestionRoute.CONVERSATIONAL,
            confidence=0.99,
            reason="Conversational message.",
        )

    # --------------------------------------------------------
    # 2b. IMAGE CONTEXT ACTIVE -> visual pipeline
    # --------------------------------------------------------

    if has_image:

        return RouteResult(
            route=QuestionRoute.BIOLOGY,
            confidence=0.95,
            reason="Image is loaded in chat context; visual pipeline active.",
        )

    # --------------------------------------------------------
    # 2c. VISUAL REFERENCE -> Biology retrieval + vision
    # --------------------------------------------------------

    if matches_pattern(text, VISUAL_REFERENCE_PATTERNS):

        return RouteResult(
            route=QuestionRoute.BIOLOGY,
            confidence=0.80,
            reason="Question references a diagram/figure/graph; textbook visual pipeline.",
        )

    # --------------------------------------------------------
    # 3. EXPLICIT TEXTBOOK REQUEST
    # --------------------------------------------------------

    if matches_pattern(
        text,
        TEXTBOOK_INDICATORS,
    ):

        biology_score = calculate_biology_score(
            text
        )

        # A textbook request inside the Biology section
        # should go to Biology retrieval.
        return RouteResult(
            route=QuestionRoute.BIOLOGY,
            confidence=max(
                0.85,
                biology_score,
            ),
            reason="Explicit textbook request.",
        )

    # --------------------------------------------------------
    # 4. BIOLOGY
    # --------------------------------------------------------

    biology_score = calculate_biology_score(
        text
    )

    if biology_score >= 0.10:

        return RouteResult(
            route=QuestionRoute.BIOLOGY,
            confidence=biology_score,
            reason="Biology terminology detected.",
        )

    # --------------------------------------------------------
    # 5. GENERAL KNOWLEDGE
    # --------------------------------------------------------

    if matches_pattern(
        text,
        GENERAL_PATTERNS,
    ):

        return RouteResult(
            route=QuestionRoute.GENERAL,
            confidence=0.85,
            reason="General knowledge question.",
        )

    # --------------------------------------------------------
    # 6. UNKNOWN
    # --------------------------------------------------------

    return RouteResult(
        route=QuestionRoute.UNKNOWN,
        confidence=0.40,
        reason="Could not confidently classify question.",
    )


# ============================================================
# ROUTE HELPERS
# ============================================================

def should_retrieve_biology(
    result: RouteResult,
) -> bool:

    return (
        result.route == QuestionRoute.BIOLOGY
    )


def should_use_general_model(
    result: RouteResult,
) -> bool:

    return (
        result.route
        in {
            QuestionRoute.GENERAL,
            QuestionRoute.META,
            QuestionRoute.CONVERSATIONAL,
        }
    )


def should_show_textbook_sources(
    result: RouteResult,
    grounded: bool,
) -> bool:

    return (
        result.route == QuestionRoute.BIOLOGY
        and grounded
    )


# ============================================================
# DEBUG INFORMATION
# ============================================================

def explain_route(
    result: RouteResult,
) -> str:
    """
    Useful during development/debugging.
    """

    return (
        f"Route: {result.route.value}\n"
        f"Confidence: {result.confidence:.2f}\n"
        f"Reason: {result.reason}"
    )