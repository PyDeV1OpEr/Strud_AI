# tests/test_vision_pipeline.py
#
# Live end-to-end tests for the Qwen3-VL-8B visual pipeline.
# Requires LM Studio running with openai/gpt-oss-20b and
# qwen/qwen3-vl-8b loaded on http://localhost:1234/v1.
#
# Run: .venv/bin/python tests/test_vision_pipeline.py

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

console = Console()

# ------------------------------------------------------------
# Instrument QwenVLClient.chat to prove (non-)invocation
# ------------------------------------------------------------

from Science.Biology import vision as vision_module

_orig_chat = vision_module.QwenVLClient.chat
qwen_calls = []

def _counting_chat(self, messages):
    qwen_calls.append(time.time())
    console.print(
        f"    [gold1]>>> Qwen3-VL INVOKED (call #{len(qwen_calls)})[/gold1]"
    )
    return _orig_chat(self, messages)

vision_module.QwenVLClient.chat = _counting_chat

# ------------------------------------------------------------
# Build a minimal headless "CLI" driving the real pipeline
# ------------------------------------------------------------

from llm_client import LLMClient
from config import MODEL
from Science.Biology.biology_engine import BiologyEngine
from cli.interface import StrudCLI


class HeadlessCLI(StrudCLI):
    """Uses the real pipeline but captures output instead of printing panels."""

    def __init__(self):
        client = LLMClient(model=MODEL)
        engine = BiologyEngine(llm_client=client, model=MODEL)
        super().__init__(llm_client=client, biology_engine=engine, model=MODEL)
        self.captured_answer = None

    def print_answer(self, answer, **kwargs):
        self.captured_answer = answer


def report(title, qwen_before, cli, answer, notes=""):
    qwen_invoked = len(qwen_calls) > qwen_before
    console.print()
    console.print(
        Panel(
            Text(
                f"{title}\n"
                f"Qwen invoked: {'YES' if qwen_invoked else 'NO'}\n"
                f"Route/notes: {notes}\n"
                + "-" * 60 + "\n"
                + (answer or "")[:1500],
                style="bright_white",
            ),
            title=title,
            title_align="left",
            box=ROUNDED,
            border_style="green" if answer else "red",
            padding=(0, 1),
        )
    )


def reset_cli():
    cli = HeadlessCLI()
    cli.engine.clear_history()
    return cli


# ============================================================
# Initialize the real retriever once
# ============================================================

from Science.Biology.biology_retriever import initialize_retriever

with console.status("Initializing retriever..."):
    ok = initialize_retriever()
console.print(f"Retriever initialized: {ok}")


# ============================================================
# TEST 1: Normal text question — Qwen must NOT be invoked
# ============================================================

console.rule("[cyan]TEST 1: Normal text question")
cli = reset_cli()
before = len(qwen_calls)
t0 = time.time()
cli.process_question("What is ultrafiltration?")
elapsed = time.time() - t0
report(
    f"TEST 1 — 'What is ultrafiltration?' ({elapsed:.1f}s)",
    before, cli, cli.captured_answer,
    notes="Expected: NO Qwen invocation, textbook-grounded answer",
)

# ============================================================
# TEST 7: Unrelated question — Qwen must NOT be invoked
# ============================================================

console.rule("[cyan]TEST 7: Unrelated question")
cli = reset_cli()
before = len(qwen_calls)
t0 = time.time()
cli.process_question("Who wrote Hamlet?")
elapsed = time.time() - t0
report(
    f"TEST 7 — 'Who wrote Hamlet?' ({elapsed:.1f}s)",
    before, cli, cli.captured_answer,
    notes="Expected: NO Qwen invocation, general knowledge answer",
)

# ============================================================
# TEST 2/3/5/6: Image upload + question via visual pipeline
# ============================================================

def make_test_image(path: Path, kind: str) -> Path:
    """Generates a simple biology test image with PIL."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 650), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        font = ImageFont.load_default()
        small = font

    if kind == "nephron":
        draw.text((30, 20), "Structure of the Nephron", fill="black", font=font)
        draw.ellipse([120, 120, 260, 230], outline="black", width=3)
        draw.text((140, 160), "Glomerulus", fill="black", font=small)
        draw.ellipse([110, 110, 280, 250], outline="blue", width=2)
        draw.text((290, 110), "Bowman's capsule", fill="blue", font=small)
        draw.line([200, 250, 200, 420], fill="black", width=3)
        draw.text((215, 320), "Proximal", fill="black", font=small)
        draw.text((215, 350), "convoluted tubule", fill="black", font=small)
        draw.line([70, 150, 120, 165], fill="red", width=4)
        draw.text((10, 115), "Afferent arteriole", fill="red", font=small)
        draw.line([260, 210, 330, 240], fill="darkred", width=4)
        draw.text((290, 240), "Efferent arteriole", fill="darkred", font=small)
        draw.line([200, 420, 420, 500], fill="black", width=3)
        draw.text((360, 520), "Loop of Henle", fill="black", font=small)
        draw.polygon([(400, 490), (430, 490), (415, 460)], fill="black")
        draw.text((470, 430), "Collecting duct", fill="black", font=small)

    elif kind == "mitosis_table":
        draw.text((30, 20), "Stages of Mitosis — Comparison Table", fill="black", font=font)
        rows = [
            ["Stage", "Chromosomes", "Spindle fibers", "Key event"],
            ["Prophase", "Condensed, visible", "Forming", "Nuclear envelope breaks down"],
            ["Metaphase", "Aligned at equator", "Fully formed", "Chromosomes line up"],
            ["Anaphase", "Sister chromatids separate", "Shortening", "Chromatids move to poles"],
            ["Telophase", "Decondensing", "Disassembling", "Two nuclei reform"],
        ]
        y = 90
        for row in rows:
            x = 40
            for cell in row:
                draw.text((x, y), cell, fill="black", font=small)
                x += 210
            draw.line([40, y + 35, 860, y + 35], fill="gray", width=1)
            y += 55

    elif kind == "enzyme_graph":
        draw.text((30, 20), "Effect of Temperature on Enzyme Activity", fill="black", font=font)
        # Axes
        draw.line([120, 120, 120, 520], fill="black", width=3)
        draw.line([120, 520, 780, 520], fill="black", width=3)
        draw.text((40, 300), "Rate of reaction", fill="black", font=small)
        draw.text((400, 545), "Temperature (C)", fill="black", font=small)
        # Bell curve peaking ~40C
        points = []
        import math
        for deg in range(0, 70, 2):
            x = 120 + deg * 9
            y = 520 - int(340 * math.exp(-((deg - 38) ** 2) / 260))
            points.append((x, y))
        draw.line(points, fill="blue", width=4)
        draw.text((440, 120), "Optimum ~ 38-40 C", fill="blue", font=small)
        draw.line([462, 175, 462, 520], fill="gray", width=1)
        draw.text((445, 545), "40", fill="black", font=small)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def run_image_test(cli, title, question):
    before = len(qwen_calls)
    t0 = time.time()
    cli.process_question(question)
    elapsed = time.time() - t0
    report(
        f"{title} ({elapsed:.1f}s)",
        before, cli, cli.captured_answer,
        notes=f"Image context: {cli._current_image_path.name if cli._current_image_path else None}",
    )
    debug = cli._last_vision_debug or {}
    console.print(
        f"    [dim]debug: qwen_invoked={debug.get('qwen_invoked')} "
        f"time={debug.get('processing_time', 0):.2f}s "
        f"type={debug.get('visual_type')} topic={debug.get('topic')} "
        f"labels={debug.get('labels', [])[:6]} "
        f"passed_to_gpt_oss={debug.get('passed_to_gpt_oss')}[/dim]"
    )


if Path("tests/test_images").exists() or True:
    console.rule("[cyan]TEST 2: Nephron diagram upload + 'What is shown in this image?'")
    cli = reset_cli()
    img = make_test_image(Path("tests/test_images/nephron_diagram.png"), "nephron")
    cli.handle_image_command(str(img))
    run_image_test(cli, "TEST 2 — nephron image", "What is shown in this image?")

    console.rule("[cyan]TEST 3: Nephron diagram + 'What does label X represent?'")
    cli = reset_cli()
    cli.handle_image_command(str(img))
    run_image_test(cli, "TEST 3 — label question", "What does the label 'Afferent arteriole' represent?")

    console.rule("[cyan]TEST 5: Table image upload")
    cli = reset_cli()
    table_img = make_test_image(Path("tests/test_images/mitosis_table.png"), "mitosis_table")
    cli.handle_image_command(str(table_img))
    run_image_test(cli, "TEST 5 — table image", "Summarise the key events in each stage shown in this table.")

    console.rule("[cyan]TEST 6: Graph image upload")
    cli = reset_cli()
    graph_img = make_test_image(Path("tests/test_images/enzyme_graph.png"), "enzyme_graph")
    cli.handle_image_command(str(graph_img))
    run_image_test(cli, "TEST 6 — graph image", "What does this graph show about enzyme activity?")

# ============================================================
# TEST 4: Textbook question that depends on a figure
# ============================================================

console.rule("[cyan]TEST 4: Textbook figure question")
cli = reset_cli()
before = len(qwen_calls)
t0 = time.time()
cli.process_question("Explain the diagram of the nephron and how urine is formed.")
elapsed = time.time() - t0
report(
    f"TEST 4 — nephron figure question ({elapsed:.1f}s)",
    before, cli, cli.captured_answer,
    notes="Expected: text retrieval + visual page analysis via Qwen if visual page found",
)

console.rule("[green]ALL TESTS COMPLETE")
console.print(f"Total Qwen3-VL invocations: {len(qwen_calls)}")
