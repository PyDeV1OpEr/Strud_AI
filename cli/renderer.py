# cli/renderer.py

"""
Strud AI Terminal Renderer
Responsible for all visual rendering, panels, tables, Markdown formatting,
source cards, status indicators, error messages, and startup visuals.
"""

from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text
from rich.status import Status
from rich.box import ROUNDED, HEAVY_HEAD, MINIMAL

from config import ASSISTANT_NAME

import pyfiglet


# ============================================================
# DESIGN SYSTEM & THEME
# ============================================================

STRUD_THEME = Theme({
    "primary": "cyan bold",
    "primary.dim": "dim cyan",
    "secondary": "bright_blue",
    "accent": "spring_green1",
    "muted": "bright_black",
    "success": "green bold",
    "warning": "gold1 bold",
    "error": "red bold",
    "info": "blue bold",
    "badge.biology": "cyan bold",
    "badge.grounded": "spring_green1 bold",
    "badge.general": "bright_blue",
    "user.prompt": "cyan bold",
    "assistant.name": "bright_cyan bold",
    "source.title": "gold1 bold",
    "source.body": "bright_white",
})

# Terminal-compatible icons & symbols
ICONS = {
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "●",
    "thinking": "⠋",
    "user": "›",
    "assistant": "◆",
    "book": "📖",
    "search": "⌕",
    "command": "⌘",
    "arrow": "→",
    "bullet": "•",
}


# ============================================================
# RENDERER CLASS
# ============================================================

class StrudRenderer:
    """
    Handles all visual output using Rich.
    Maintains clean separation between UI representation and backend execution.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(theme=STRUD_THEME)

    # --------------------------------------------------------
    # STARTUP BANNER
    # --------------------------------------------------------

    def print_startup(
        self,
        textbook_status: bool,
        llm_status: bool,
        model_name: str,
        base_url: str = "http://localhost:1234/v1",
        page_count: int = 0,
        chunk_count: int = 0,
    ) -> None:
        """
        Renders a polished startup banner and system check.
        """
        self.console.clear()
        
        # Render ASCII header cleanly using pyfiglet
        try:
            fig = pyfiglet.Figlet(font="slant")
            ascii_title = fig.renderText("Strud  AI")
            title_text = Text(ascii_title.rstrip(), style="cyan bold")
        except Exception:
            title_text = Text("STRUD AI", style="cyan bold")

        header_content = Text()
        header_content.append("Personal AI Study Assistant for G.C.E. A/L Biology\n", style="italic bright_white")
        header_content.append("Biology-focused  •  Local / Offline", style="dim white")

        banner_panel = Panel(
            Text.assemble(title_text, "\n", header_content),
            box=ROUNDED,
            border_style="cyan",
            padding=(0, 2),
        )
        self.console.print(banner_panel)

        # Status Table
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()

        if llm_status:
            table.add_row(f"[{ICONS['success']}] Engine", "[green]Connected[/green]")
        else:
            table.add_row(f"[{ICONS['error']}] Engine", "[red]Not connected[/red] (Start the local engine on port 1234)")

        if textbook_status:
            table.add_row(
                f"[{ICONS['success']}] Textbook",
                f"[green]Biology Resource Book Loaded[/green] ({page_count} pages, {chunk_count} chunks)"
            )
        else:
            table.add_row(f"[{ICONS['warning']}] Textbook", "[gold1]Biology Resource Book missing[/gold1]")

        status_panel = Panel(
            table,
            title="System Status",
            title_align="left",
            box=ROUNDED,
            border_style="dim cyan",
            padding=(0, 1),
        )
        self.console.print(status_panel)

        ready_text = Text()
        ready_text.append(f" {ICONS['info']} ", style="cyan bold")
        ready_text.append("Strud AI is ready. Type ", style="bright_white")
        ready_text.append("/help", style="cyan bold")
        ready_text.append(" for commands or ask a question directly.", style="bright_white")
        
        self.console.print(ready_text)
        self.console.print()

    # --------------------------------------------------------
    # HELP & COMMANDS
    # --------------------------------------------------------

    def print_help(self) -> None:
        """
        Renders available slash commands in a structured table.
        """
        table = Table(box=MINIMAL, show_header=True, header_style="cyan bold")
        table.add_column("Command", style="cyan bold", width=16)
        table.add_column("Description", style="bright_white")

        table.add_row("/help", "Show this help menu")
        table.add_row("/clear", "Clear conversation history")
        table.add_row("/status", "Display engine connection & retriever status")
        table.add_row("/vision", "Vision status, or debug vision for a question")
        table.add_row("/image <path>", "Upload a Biology image for analysis")
        table.add_row("/quit", "Exit Strud AI")

        panel = Panel(
            table,
            title=f"{ICONS['command']} Commands",
            title_align="left",
            box=ROUNDED,
            border_style="cyan",
            padding=(0, 1),
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    # --------------------------------------------------------
    # STATUS VIEW
    # --------------------------------------------------------

    def print_status(
        self,
        llm_available: bool,
        model_name: str,
        base_url: str,
        retriever_status: Dict[str, Any],
    ) -> None:
        """
        Renders a detailed status view.
        """
        table = Table.grid(padding=(0, 3))
        table.add_column(style="bold cyan", width=18)
        table.add_column(style="bright_white")

        table.add_row("Assistant", ASSISTANT_NAME)
        table.add_row("Mode", "Local / Offline • No cloud")
        table.add_row("LLM Status", f"[green]✓ Connected[/green]" if llm_available else f"[red]✗ Disconnected[/red]")
        
        table.add_row("", "")
        textbook_loaded = retriever_status.get("textbook_loaded", False)
        page_count = retriever_status.get("page_count", 0)
        chunk_count = retriever_status.get("chunk_count", retriever_status.get("chunks", 0))
        tfidf_ok = retriever_status.get("tfidf_available", False)
        bm25_ok = retriever_status.get("bm25_available", False)
        retrieval_mode = retriever_status.get("retrieval_mode", "tfidf_dense")
        semantic_ok = retriever_status.get("semantic_available", False)
        gate = retriever_status.get("grounding_threshold", 0.55)

        table.add_row("Textbook Index", f"[green]✓ Loaded[/green]" if textbook_loaded else f"[red]✗ Not Loaded[/red]")
        table.add_row("Pages", str(page_count))
        table.add_row("Indexed Chunks", str(chunk_count))
        table.add_row("TF-IDF Search", f"[green]✓ Active[/green]" if tfidf_ok else f"[red]✗ Inactive[/red]")
        table.add_row("BM25 Search", f"[green]✓ Active[/green]" if bm25_ok else "[dim]○ Disabled / Off[/dim]")
        table.add_row("Policy", "BM25 + TF-IDF + Semantic" if bm25_ok else "TF-IDF + Semantic")
        table.add_row("Semantic Index", f"[green]✓ Active[/green]" if semantic_ok else f"[dim]○ Disabled / Off[/dim]")
        table.add_row("Grounding Gate", f"{gate:.2f} · {retrieval_mode}")

        # Vision (Qwen3-VL) status
        table.add_row("", "")
        try:
            from Science.Biology.vision import get_vision_status
            vision = get_vision_status()
        except Exception:
            vision = {}

        if vision.get("vision_enabled"):
            if vision.get("vision_model_loaded"):
                table.add_row("Vision", "[green]\u2713 Available[/green]")
            elif vision.get("lm_studio_reachable"):
                table.add_row("Vision", "[gold1]\u26a0 Visual engine not loaded[/gold1]")
            else:
                table.add_row("Vision", "[red]\u2717 Unreachable[/red]")
            table.add_row("Cached Analyses", str(vision.get("cached_analyses", 0)))
            table.add_row("Visual Chunks", str(vision.get("visual_chunk_count", 0)))
        else:
            table.add_row("Vision", "[dim]\u25cb Disabled (vision_config.json)[/dim]")

        panel = Panel(
            table,
            title=f"{ICONS['info']} System Status",
            title_align="left",
            box=ROUNDED,
            border_style="cyan",
            padding=(0, 1),
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    # --------------------------------------------------------
    # USER QUESTION DISPLAY
    # --------------------------------------------------------

    def print_user_question(self, question: str) -> None:
        """
        Renders user's input with clean visual separation.
        """
        self.console.print()
        user_text = Text()
        user_text.append(f"{ICONS['user']} ", style="cyan bold")
        user_text.append("You: ", style="cyan bold")
        user_text.append(question, style="bright_white")
        self.console.print(user_text)

    # --------------------------------------------------------
    # ANSWER DISPLAY
    # --------------------------------------------------------

    def print_answer(
        self,
        answer: str,
        route_label: str,
        grounded: bool = False,
        sources: Optional[List[int]] = None,
        note: Optional[str] = None,
    ) -> None:
        """
        Renders model answer formatted as Markdown with badge and optional source card.
        """
        self.console.print()

        # Build badge header
        badge = Text()
        badge.append(f"{ICONS['assistant']} ", style="cyan bold")

        if route_label == "Biology":
            if grounded:
                badge.append("Biology", style="cyan bold")
                badge.append(" • ", style="dim white")
                badge.append("Textbook Grounded", style="spring_green1 bold")
            else:
                badge.append("Biology", style="cyan bold")
                badge.append(" • ", style="dim white")
                badge.append("General Knowledge", style="bright_blue bold")
        elif route_label == "About Strud":
            badge.append("About Strud", style="cyan bold")
        elif route_label == "Conversation":
            badge.append("Conversation", style="bright_blue bold")
        else:
            badge.append("General Knowledge", style="bright_blue bold")

        self.console.print(badge)
        self.console.print()

        # Render Markdown content safely
        try:
            md = Markdown(answer.strip())
            self.console.print(md)
        except Exception:
            self.console.print(answer.strip())

        # Render textbook sources ONLY when grounded
        if grounded and sources:
            self.console.print()
            pages_str = ", ".join(str(p) for p in sources)
            
            source_content = Text()
            source_content.append("Biology Resource Book\n", style="gold1 bold")
            source_content.append(f"Pages: {pages_str}", style="bright_white")

            source_panel = Panel(
                source_content,
                title=f"{ICONS['book']} Sources",
                title_align="left",
                box=ROUNDED,
                border_style="gold1",
                padding=(0, 1),
            )
            self.console.print(source_panel)

        # Render note if weak grounding
        if note:
            self.console.print()
            note_text = Text()
            note_text.append(f"{ICONS['info']} ", style="dim yellow")
            note_text.append(note, style="dim yellow")
            self.console.print(note_text)

        self.console.print()

    # --------------------------------------------------------
    # ERROR & MESSAGES
    # --------------------------------------------------------

    def print_error(self, message: str, title: str = "Error") -> None:
        """
        Renders error messages in a structured warning panel.
        """
        self.console.print()
        error_panel = Panel(
            Text(message, style="bright_white"),
            title=f"{ICONS['warning']} {title}",
            title_align="left",
            box=ROUNDED,
            border_style="red",
            padding=(0, 1),
        )
        self.console.print(error_panel)
        self.console.print()

    # --------------------------------------------------------
    # VISION DEBUG VIEW (/vision)
    # --------------------------------------------------------

    def print_vision_debug(
        self,
        question: str,
        vision_required: bool,
        reason: str,
        source_page: Optional[int],
        qwen_model: str,
        processing_time: float,
        visual_type: str,
        qwen_output: str,
        passed_to_gpt_oss: bool,
        from_cache: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """
        Renders the /vision debug report.
        """
        self.console.print()

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", width=20)
        table.add_column(style="bright_white")

        table.add_row("Question", question[:80])
        table.add_row(
            "Vision required",
            "[green]YES[/green]" if vision_required else "[red]NO[/red]",
        )
        table.add_row("Reason", reason)
        table.add_row("Source page", str(source_page) if source_page else "\u2014")
        table.add_row("Qwen model", qwen_model)
        table.add_row("Processing time", f"{processing_time:.2f}s")
        if from_cache:
            table.add_row("Cache", "[green]\u2713 Served from cache[/green]")
        table.add_row("Visual type", visual_type)
        table.add_row(
            "Passed to GPT-OSS",
            "[green]YES[/green]" if passed_to_gpt_oss else "[red]NO[/red]",
        )
        if error:
            table.add_row("Error", f"[red]{error}[/red]")

        panel = Panel(
            table,
            title=f"{ICONS['search']} VISION ANALYSIS",
            title_align="left",
            box=ROUNDED,
            border_style="spring_green1" if vision_required else "dim cyan",
            padding=(0, 1),
        )
        self.console.print(panel)

        if qwen_output:
            output_panel = Panel(
                Text(qwen_output[:4000], style="bright_white"),
                title="Qwen3-VL output",
                title_align="left",
                box=ROUNDED,
                border_style="dim cyan",
                padding=(0, 1),
            )
            self.console.print(output_panel)

        self.console.print()

    def print_message(self, message: str, style: str = "green") -> None:
        """
        Renders simple feedback messages (e.g., cleared history).
        """
        self.console.print()
        text = Text()
        text.append(f"{ICONS['success']} ", style=f"{style} bold")
        text.append(message, style="bright_white")
        self.console.print(text)
        self.console.print()

    # --------------------------------------------------------
    # THINKING / SPINNER SPINNER
    # --------------------------------------------------------

    @contextmanager
    def thinking(self, status_text: str = "Thinking..."):
        """
        Displays a animated spinner during async operations.
        """
        with Status(
            Text(status_text, style="cyan italic"),
            console=self.console,
            spinner="dots",
        ):
            yield
