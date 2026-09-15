# cli/interface.py

"""
Strud AI Interface Coordinator
Manages CLI application lifecycle, startup sequence, interactive command loop,
thinking states, routing, and dispatching tasks to renderer/input handler.
"""

import sys
from typing import Any

from pathlib import Path

from config import PDF_FILE, LM_STUDIO_BASE_URL, MODEL
from question_router import route_question, QuestionRoute
from assistant_identity import classify_identity_intent
from answer_verification import get_verification_service
from Science.Biology.biology import BiologyMode
from Science.Biology.biology_retriever import (
    initialize_retriever,
    retrieve_biology,
    create_textbook_context,
    get_source_pages,
    get_retriever_status,
)
from config import VISION_ENABLED, VISION_MODEL
from Science.Biology.vision import (
    VisionService,
    detect_visual_requirement,
    build_visual_chunk,
    save_visual_chunks,
    get_vision_status,
    get_vl_client,
)
from Science.Biology.biology_retriever import attach_new_visual_chunk

from .renderer import StrudRenderer
from .input_handler import StrudInputHandler


class StrudCLI:
    """
    Main CLI controller. Orchestrates input, thinking status, answer generation,
    and rendering. Does NOT modify backend logic.
    """

    def __init__(self, llm_client: Any, biology_engine: Any, model: str = MODEL):
        self.client = llm_client
        self.engine = biology_engine
        self.model = model

        self.renderer = StrudRenderer()
        self.input_handler = StrudInputHandler()
        self.vision = VisionService() if VISION_ENABLED else None

        # ----------------------------------------------------
        # Chat image context (/image)
        # ----------------------------------------------------

        # Path of the currently loaded student image.
        self._current_image_path: Path | None = None

        # Cached VisualAnalysis of the loaded image.
        self._current_image_analysis = None

        # Concepts extracted from the loaded image.
        self._current_image_concepts: list[str] = []

        # Last full vision debug record (for /debug vision)
        self._last_vision_debug: dict | None = None

        # Last routing debug record (for /debug routing)
        self._last_route_debug: dict | None = None

        # Answer verification service (silent quality gate)
        self.verifier = get_verification_service(
            llm_client=llm_client, model=model
        )

    def get_route_label(self, route: QuestionRoute) -> str:
        """
        Maps QuestionRoute to user-facing category label.
        """
        labels = {
            QuestionRoute.BIOLOGY: "Biology",
            QuestionRoute.GENERAL: "General Knowledge",
            QuestionRoute.META: "About Strud",
            QuestionRoute.CONVERSATIONAL: "Conversation",
            QuestionRoute.UNKNOWN: "General Knowledge",
        }
        return labels.get(route, "General Knowledge")

    def handle_command(self, command: str) -> bool:
        """
        Processes slash commands.
        Returns True to continue loop, False to exit.
        """
        cmd = command.lower().strip()

        if cmd == "/quit":
            self.renderer.print_message("Goodbye! Happy studying 👋", style="cyan")
            return False

        if cmd == "/help":
            self.renderer.print_help()
            return True

        if cmd == "/clear":
            self.engine.clear_history()
            self._current_image_path = None
            self._current_image_analysis = None
            self._current_image_concepts = []
            self.renderer.print_message("Conversation history cleared.")
            return True

        if cmd in ("/debug vision", "/debug  vision"):
            self.handle_debug_vision()
            return True

        if cmd in ("/debug routing", "/debug  routing"):
            self.handle_debug_routing()
            return True

        if cmd == "/debug":
            self.renderer.print_error(
                "Usage: /debug vision | /debug routing",
                title="Debug",
            )
            return True

        if cmd == "/status":
            llm_ok = self.client.is_available()
            ret_status = get_retriever_status()
            self.renderer.print_status(
                llm_available=llm_ok,
                model_name=self.client.model,
                base_url=self.client.base_url,
                retriever_status=ret_status,
            )
            return True

        if cmd == "/vision":
            self.handle_vision_command("")
            return True

        if cmd.startswith("/vision "):
            self.handle_vision_command(command[len("/vision "):].strip())
            return True

        if cmd.startswith("/image "):
            self.handle_image_command(command[len("/image "):].strip())
            return True

        if cmd == "/image clear":
            self._current_image_path = None
            self._current_image_analysis = None
            self._current_image_concepts = []
            self.renderer.print_message("Image context cleared.")
            return True

        if cmd == "/image":
            self.renderer.print_error(
                "Usage: /image <path-to-image-file>",
                title="Image Upload",
            )
            return True

        self.renderer.print_error(f"Unknown command '{command}'. Type /help for available commands.", title="Unknown Command")
        return True

    def process_question(self, question: str) -> None:
        """
        Processes a user question through the full pipeline:

        identity/capability interception -> routing ->
        biology-first retrieval -> visual analysis (when needed)
        -> answer generation -> silent verification -> rendering.
        """
        # ------------------------------------------------------
        # 0. Identity & capability interception (before routing)
        # ------------------------------------------------------

        identity = classify_identity_intent(question)

        if identity is not None:
            self._last_route_debug = {
                "question": question,
                "route": "identity",
                "intent": identity.intent,
                "confidence": identity.confidence,
                "retrieval_attempted": False,
            }

            # Capability answers must reflect the REAL state.
            if identity.intent == "capability_vision" and not (
                VISION_ENABLED and self.vision is not None
            ):
                from Science.Biology.vision import get_vision_status
                status = get_vision_status()

                if not status.get("vision_enabled"):
                    self.renderer.print_message(
                        "Image analysis is currently unavailable in this "
                        "session.",
                        style="yellow",
                    )
                    return

                if not status.get("vision_model_loaded"):
                    self.renderer.print_message(
                        "Image analysis is currently unavailable because "
                        "the vision model is not loaded in LM Studio. "
                        "Please load it and try again.",
                        style="yellow",
                    )
                    return

            self.renderer.print_message(identity.response, style="cyan")
            return

        # ------------------------------------------------------
        # 1. Image context active -> visual pipeline
        # ------------------------------------------------------

        if self._current_image_path is not None and self._current_image_analysis is not None:
            self.process_image_question(question)
            return

        # 2. Route question
        route_result = route_question(question)
        route = route_result.route
        route_label = self.get_route_label(route)

        # ------------------------------------------------------
        # 3. Conversational messages (no retrieval needed)
        # ------------------------------------------------------

        if route == QuestionRoute.CONVERSATIONAL:
            self._last_route_debug = {
                "question": question,
                "route": route.value,
                "reason": route_result.reason,
                "retrieval_attempted": False,
            }

            with self.renderer.thinking("Thinking..."):
                answer = self.engine.answer(
                    question=question,
                    context="",
                    mode=BiologyMode.GENERAL,
                )

            self.renderer.print_answer(
                answer=answer,
                route_label=route_label,
                grounded=False,
            )
            return

        # ------------------------------------------------------
        # 4. BIOLOGY-FIRST ROUTING
        #
        # Every non-conversational question gets a retrieval
        # attempt BEFORE being treated as general knowledge or
        # out-of-domain. This prevents Biology questions phrased
        # in ordinary words ("Why does the heart beat faster
        # when running?") from being rejected.
        # ------------------------------------------------------

        with self.renderer.thinking("Searching Biology Resource Book..."):
            retrieval = retrieve_biology(question)

        self._last_route_debug = {
            "question": question,
            "route": route.value,
            "reason": route_result.reason,
            "retrieval_attempted": True,
            "grounded": retrieval.grounded,
            "confidence": retrieval.confidence,
            "best_page": retrieval.best_page,
            "pages": sorted({r.page for r in (retrieval.results or [])}),
        }

        # 4b. Textbook grounded -> answer from the book
        if retrieval.grounded:
            return self._answer_grounded(
                question=question,
                retrieval=retrieval,
                route_label=(
                    route_label
                    if route in (QuestionRoute.BIOLOGY,)
                    else "Biology"
                ),
            )

        # ------------------------------------------------------
        # 4c. Retrieval did not ground the question.
        #     Distinguish Biology (ungrounded) from clearly
        #     out-of-domain questions.
        # ------------------------------------------------------

        if route in (QuestionRoute.GENERAL, QuestionRoute.UNKNOWN):
            # Out-of-domain: professional redirect to Biology.
            from config import ASSISTANT_NAME, ASSISTANT_DOMAIN
            from config import IDENTITY_CONFIG

            message = IDENTITY_CONFIG.get(
                "out_of_domain_response",
                f"That topic is outside {ASSISTANT_NAME}'s primary focus. "
                f"I'm designed specifically as a {ASSISTANT_DOMAIN} study "
                "assistant. If you'd like, ask me a Biology question and "
                "I can help.",
            )
            self.renderer.print_message(message, style="cyan")
            return

        # Biology question but no reliable textbook evidence:
        # general Biology explanation with an honest note.
        with self.renderer.thinking("Preparing general Biology explanation..."):
            answer = self.engine.answer(
                question=question,
                context="",
                mode=BiologyMode.GENERAL,
            )

    def _answer_grounded(
        self,
        question: str,
        retrieval,
        route_label: str = "Biology",
        visual_context: str | None = None,
        visual_analyses: list | None = None,
    ) -> None:
        """
        Textbook-grounded answer path:

        visual analysis (when needed) -> answer generation ->
        silent verification -> rendering.
        """
        visual_analyses = visual_analyses or []

        # ------------------------------------------------------
        # Visual detection & analysis (text questions only;
        # student-image questions pass visual_context directly)
        # ------------------------------------------------------

        if self.vision is not None and VISION_ENABLED and visual_context is None:

            retrieved_pages = (
                [r.page for r in retrieval.results]
                if retrieval.results
                else None
            )

            decision = detect_visual_requirement(
                question=question,
                has_image=False,
                retrieved_pages=retrieved_pages,
            )

            if decision.required:

                target_pages: list[int] = []

                if decision.page_hint:
                    target_pages = [decision.page_hint]
                else:
                    from Science.Biology.vision import get_page_visual_info

                    for result in retrieval.results[:6]:
                        info = get_page_visual_info(result.page)
                        if info and info.get("likely_visual"):
                            target_pages.append(result.page)
                        if len(target_pages) >= 2:
                            break

                for page in target_pages:
                    with self.renderer.thinking(
                        f"Analyzing visuals on page {page} (vision component)..."
                    ):
                        analysis = self.vision.analyze_page(
                            page_number=page,
                            question=question,
                        )

                    if not analysis.error and analysis.structured.get(
                        "visual_type"
                    ) not in ("none",):
                        visual_analyses.append(analysis)

                        chunk = build_visual_chunk(analysis)
                        if chunk:
                            save_visual_chunks([chunk])
                            attach_new_visual_chunk(chunk)

                if visual_analyses:
                    visual_context = self.vision.format_visual_context(
                        visual_analyses
                    )

            self._last_vision_debug = {
                "source": "textbook_page",
                "image_path": (
                    visual_analyses[0].image_path if visual_analyses else None
                ),
                "qwen_invoked": bool(visual_analyses),
                "qwen_model": VISION_MODEL,
                "processing_time": (
                    sum(a.processing_time for a in visual_analyses)
                    if visual_analyses
                    else 0.0
                ),
                "visual_type": (
                    visual_analyses[0].visual_type if visual_analyses else None
                ),
                "topic": (
                    visual_analyses[0].structured.get("topic")
                    if visual_analyses else None
                ),
                "labels": (
                    self._extract_labels(visual_analyses[0].structured)
                    if visual_analyses else []
                ),
                "visual_evidence": (
                    visual_analyses[0].raw_output if visual_analyses else ""
                ),
                "retrieved_chunks": [
                    {"page": r.page, "text": r.text[:200]}
                    for r in (retrieval.results or [])
                ],
                "combined_context": (
                    visual_context[:1200] if visual_context else None
                ),
                "passed_to_gpt_oss": bool(visual_context),
                "from_cache": (
                    visual_analyses[0].from_cache if visual_analyses else False
                ),
                "error": (
                    visual_analyses[0].error if visual_analyses else None
                ),
            }

        # ------------------------------------------------------
        # Answer generation
        # ------------------------------------------------------

        with self.renderer.thinking("Reviewing relevant textbook material..."):
            context = create_textbook_context(retrieval)
            answer = self.engine.answer(
                question=question,
                context=context,
                mode=BiologyMode.TEXTBOOK,
                visual_context=visual_context,
            )

        # ------------------------------------------------------
        # Silent verification (never exposed to the student)
        # ------------------------------------------------------

        retrieved_pages_set = {
            r.page for r in (retrieval.results or [])
        }

        answer, _report = self.verifier.verify_and_revise(
            question=question,
            answer=answer,
            retrieved_pages=retrieved_pages_set,
            has_visual_evidence=bool(visual_context),
            textbook_context=context,
            visual_context=visual_context or "",
        )

        sources = get_source_pages(retrieval)
        self.renderer.print_answer(
            answer=answer,
            route_label=route_label,
            grounded=True,
            sources=sources,
        )

    def handle_vision_command(self, argument: str) -> None:
        """
        /vision            -> vision system status
        /vision <question> -> debug the visual pipeline for a question
        """
        if not argument:
            status = get_vision_status()

            table_content = (
                f"Enabled: {'yes' if status.get('vision_enabled') else 'no'}\n"
                f"Model: {status.get('vision_model')}\n"
                f"Endpoint: {status.get('vision_base_url')}\n"
                f"LM Studio reachable: {'yes' if status.get('lm_studio_reachable') else 'no'}\n"
                f"Vision model loaded: {'yes' if status.get('vision_model_loaded') else 'no'}\n"
                f"Cached analyses: {status.get('cached_analyses', 0)}\n"
                f"Visual chunks: {status.get('visual_chunk_count', 0)}\n"
                f"Visual pages: {status.get('visual_pages', [])}\n"
                f"Loaded image: {self._current_image_path.name if self._current_image_path else 'none'}"
            )

            from rich.panel import Panel
            from rich.text import Text
            from rich.box import ROUNDED

            self.renderer.console.print()
            self.renderer.console.print(
                Panel(
                    Text(table_content),
                    title="VISION STATUS (Qwen3-VL-8B)",
                    title_align="left",
                    box=ROUNDED,
                    border_style="cyan",
                    padding=(0, 1),
                )
            )
            self.renderer.console.print(
                "[dim]Debug a question: /vision <question>[/dim]"
            )
            self.renderer.console.print()
            return

        # Debug mode: run the visual pipeline for the given question.
        question = argument

        from Science.Biology.biology_retriever import retrieve_biology as _retrieve

        with self.renderer.thinking("Searching Biology Resource Book..."):
            retrieval = _retrieve(question)

        retrieved_pages = (
            [r.page for r in retrieval.results]
            if retrieval.results
            else None
        )

        decision = detect_visual_requirement(
            question=question,
            has_image=False,
            retrieved_pages=retrieved_pages,
        )

        if not decision.required:
            self.renderer.print_vision_debug(
                question=question,
                vision_required=False,
                reason=decision.reason,
                source_page=None,
                qwen_model=VISION_MODEL,
                processing_time=0.0,
                visual_type="\u2014",
                qwen_output="",
                passed_to_gpt_oss=False,
            )
            return

        target_page = decision.page_hint
        analysis = None

        if target_page is None and retrieval.results:
            from Science.Biology.vision import get_page_visual_info
            for result in retrieval.results[:6]:
                info = get_page_visual_info(result.page)
                if info and info.get("likely_visual"):
                    target_page = result.page
                    break

        if target_page is not None and self.vision is not None:
            with self.renderer.thinking(f"Analyzing page {target_page} (Qwen3-VL)..."):
                analysis = self.vision.analyze_page(
                    page_number=target_page,
                    question=question,
                )

            chunk = build_visual_chunk(analysis)
            if chunk:
                save_visual_chunks([chunk])
                attach_new_visual_chunk(chunk)

        if analysis is None:
            self.renderer.print_vision_debug(
                question=question,
                vision_required=True,
                reason=decision.reason,
                source_page=None,
                qwen_model=VISION_MODEL,
                processing_time=0.0,
                visual_type="\u2014",
                qwen_output="",
                passed_to_gpt_oss=False,
                error="No visual page identified for analysis.",
            )
            return

        self.renderer.print_vision_debug(
            question=question,
            vision_required=True,
            reason=decision.reason,
            source_page=analysis.page,
            qwen_model=VISION_MODEL,
            processing_time=analysis.processing_time,
            visual_type=analysis.visual_type,
            qwen_output=(
                analysis.raw_output
                if not analysis.error
                else (analysis.raw_output or "")
            ),
            passed_to_gpt_oss=not analysis.error
            and analysis.structured.get("visual_type") != "none",
            from_cache=analysis.from_cache,
            error=analysis.error,
        )

    def handle_image_command(self, image_path: str) -> None:
        """
        /image <path>

        Loads a student Biology image into the chat context.

        1. Validates the file exists and format is supported.
        2. Sends it to Qwen3-VL-8B via LM Studio.
        3. Stores image + visual analysis + extracted concepts in
           the chat context.
        4. The NEXT normal question is answered through the visual
           pipeline (image + question -> retrieval -> GPT-OSS).
        """
        path = Path(image_path.strip().strip('"').strip("'"))

        # 1. Validate file exists
        if not path.exists():
            self.renderer.print_error(
                f"Image file not found: {path}",
                title="Image Upload",
            )
            return

        # 2. Validate supported format
        supported = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
        if path.suffix.lower() not in supported:
            self.renderer.print_error(
                f"Unsupported image format '{path.suffix}'. "
                f"Supported: {', '.join(sorted(supported))}",
                title="Image Upload",
            )
            return

        if self.vision is None:
            self.renderer.print_error(
                "Vision is disabled. Enable it in vision_config.json.",
                title="Vision Disabled",
            )
            return

        # 3. Qwen3-VL analysis (stored, not answered)
        with self.renderer.thinking("Analyzing your image (Qwen3-VL)..."):
            analysis = self.vision.analyze_image(path)

        if analysis.error:
            self.renderer.print_error(
                analysis.error,
                title="Vision Error",
            )
            return

        # 4. Extract Biology concepts for retrieval
        with self.renderer.thinking("Extracting Biology concepts..."):
            concepts = self.vision.extract_concepts(analysis)

        # 5. Store in chat context
        self._current_image_path = path
        self._current_image_analysis = analysis
        self._current_image_concepts = concepts

        # Record debug info
        self._last_vision_debug = {
            "source": "student_image",
            "image_path": str(path),
            "qwen_invoked": True,
            "qwen_model": VISION_MODEL,
            "processing_time": analysis.processing_time,
            "visual_type": analysis.visual_type,
            "topic": analysis.structured.get("topic"),
            "labels": self._extract_labels(analysis.structured),
            "visual_evidence": analysis.raw_output,
            "retrieved_chunks": [],
            "combined_context": None,
            "passed_to_gpt_oss": False,
            "from_cache": False,
            "error": None,
        }

        # Show a short summary (not an answer)
        from rich.panel import Panel
        from rich.text import Text
        from rich.box import ROUNDED

        summary = (
            f"File: {path.name}\n"
            f"Visual type: {analysis.visual_type}\n"
            f"Topic: {analysis.structured.get('topic') or 'unclear'}\n"
            f"Concepts for retrieval: {', '.join(concepts[:6]) if concepts else '—'}\n\n"
            f"Ask a question about this image now, e.g.\n"
            f"  'What is shown in this image?'\n"
            f"  'What does label X represent?'"
        )

        self.renderer.console.print()
        self.renderer.console.print(
            Panel(
                Text(summary),
                title="\u2713 Image loaded & analyzed (Qwen3-VL-8B)",
                title_align="left",
                box=ROUNDED,
                border_style="green",
                padding=(0, 1),
            )
        )
        self.renderer.console.print()

    def _extract_labels(self, structured: dict) -> list[str]:
        """Extracts label strings from a visual analysis structure."""
        labels: list[str] = []

        components = structured.get("components")
        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict):
                    label = comp.get("label") or comp.get("name")
                    if label:
                        labels.append(str(label))

        direct = structured.get("labels")
        if isinstance(direct, list):
            labels.extend(str(l) for l in direct if l)

        return labels[:20]

    def process_image_question(self, question: str) -> None:
        """
        Answers a question about the loaded image through the
        full visual pipeline:

        image analysis (already done by Qwen)
        + question -> textbook retrieval -> GPT-OSS final answer.
        """
        analysis = self._current_image_analysis
        concepts = self._current_image_concepts

        # Retrieval query: question + image concepts
        retrieval_query = f"{question} {' '.join(concepts[:6])}".strip()

        with self.renderer.thinking("Searching Biology Resource Book..."):
            retrieval = retrieve_biology(retrieval_query)

        retrieved_chunks = [
            {
                "page": r.page,
                "text": r.text[:200],
            }
            for r in (retrieval.results or [])
        ]

        visual_context = self.vision.format_visual_context([analysis])

        # Combined context for debugging
        combined = (
            f"VISUAL CONTEXT:\n{visual_context[:1000]}\n\n"
            f"TEXTBOOK CONTEXT PAGES: "
            f"{sorted({r.page for r in (retrieval.results or [])})}"
        )

        # Record debug info BEFORE answering
        self._last_vision_debug = {
            "source": "student_image",
            "image_path": (
                str(self._current_image_path) if self._current_image_path else None
            ),
            "qwen_invoked": True,
            "qwen_model": VISION_MODEL,
            "processing_time": analysis.processing_time,
            "visual_type": analysis.visual_type,
            "topic": analysis.structured.get("topic"),
            "labels": self._extract_labels(analysis.structured),
            "visual_evidence": analysis.raw_output,
            "retrieved_chunks": retrieved_chunks,
            "combined_context": combined,
            "passed_to_gpt_oss": True,
            "from_cache": False,
            "error": None,
        }

        if retrieval.grounded:
            with self.renderer.thinking("Reviewing relevant textbook material..."):
                context = create_textbook_context(retrieval)
                answer = self.engine.answer(
                    question=question,
                    context=context,
                    mode=BiologyMode.TEXTBOOK,
                    visual_context=visual_context,
                )

            # Silent verification (visual evidence active)
            retrieved_pages_set = {
                r.page for r in (retrieval.results or [])
            }
            answer, _report = self.verifier.verify_and_revise(
                question=question,
                answer=answer,
                retrieved_pages=retrieved_pages_set,
                has_visual_evidence=True,
                textbook_context=context,
                visual_context=visual_context or "",
            )

            sources = get_source_pages(retrieval)
            self.renderer.print_answer(
                answer=answer,
                route_label="Biology",
                grounded=True,
                sources=sources,
            )
        else:
            with self.renderer.thinking("Preparing explanation..."):
                answer = self.engine.answer(
                    question=question,
                    context="",
                    mode=BiologyMode.GENERAL,
                    visual_context=visual_context,
                )

            # Silent verification (visual evidence active)
            answer, _report = self.verifier.verify_and_revise(
                question=question,
                answer=answer,
                retrieved_pages=None,
                has_visual_evidence=True,
                textbook_context="",
                visual_context=visual_context or "",
            )

            self.renderer.print_answer(
                answer=answer,
                route_label="Biology",
                grounded=False,
                note=(
                    "The image was analysed with Strud AI's visual analysis, "
                    "but no matching textbook evidence passed the grounding "
                    "check, so the explanation uses general Biology knowledge."
                ),
            )

    def handle_debug_routing(self) -> None:
        """
        /debug routing — shows how the last question was routed.
        """
        from rich.panel import Panel
        from rich.text import Text
        from rich.box import ROUNDED

        debug = self._last_route_debug

        if not debug:
            self.renderer.print_message(
                "No question has been routed yet in this session.",
                style="yellow",
            )
            return

        lines = [
            f"Question: {debug.get('question')}",
            f"Route: {debug.get('route')}",
            f"Reason: {debug.get('reason', '\u2014')}",
            f"Retrieval attempted: "
            f"{'YES' if debug.get('retrieval_attempted') else 'NO'}",
        ]

        if debug.get("retrieval_attempted"):
            lines.append(f"Grounded: {'YES' if debug.get('grounded') else 'NO'}")
            lines.append(f"Confidence: {debug.get('confidence', 0):.2f}")
            lines.append(f"Best page: {debug.get('best_page') or '\u2014'}")
            lines.append(f"Pages: {debug.get('pages') or []}")

        self.renderer.console.print()
        self.renderer.console.print(
            Panel(
                Text("\n".join(lines)),
                title="DEBUG \u2014 ROUTING",
                title_align="left",
                box=ROUNDED,
                border_style="cyan",
                padding=(0, 1),
            )
        )
        self.renderer.console.print()

    def handle_debug_vision(self) -> None:
        """
        /debug vision

        Shows the last vision operation in detail:
        image, Qwen invocation, timing, labels, topic, evidence,
        retrieved chunks, combined context, and whether the visual
        context reached GPT-OSS.
        """
        from rich.panel import Panel
        from rich.text import Text
        from rich.box import ROUNDED

        debug = self._last_vision_debug

        if not debug:
            self.renderer.print_message(
                "No vision operation has run yet in this session. "
                "Load an image with /image or ask a visual question first.",
                style="yellow",
            )
            return

        lines = [
            f"Image: {debug.get('image_path') or '\u2014'}",
            f"Qwen model: {debug.get('qwen_model')}",
            f"Qwen invoked: {'YES' if debug.get('qwen_invoked') else 'NO'}",
            f"Qwen processing time: {debug.get('processing_time', 0):.2f}s",
            f"Visual type: {debug.get('visual_type') or '\u2014'}",
            f"Topic: {debug.get('topic') or '\u2014'}",
            f"Labels: {', '.join(debug.get('labels') or []) or '\u2014'}",
            f"Passed to GPT-OSS: {'YES' if debug.get('passed_to_gpt_oss') else 'NO'}",
            f"From cache: {'YES' if debug.get('from_cache') else 'NO'}",
        ]

        if debug.get("error"):
            lines.append(f"Error: {debug['error']}")

        self.renderer.console.print()
        self.renderer.console.print(
            Panel(
                Text("\n".join(lines)),
                title="DEBUG \u2014 VISION ANALYSIS",
                title_align="left",
                box=ROUNDED,
                border_style="spring_green1",
                padding=(0, 1),
            )
        )

        # Visual evidence (Qwen raw output)
        evidence = debug.get("visual_evidence") or ""
        if evidence:
            self.renderer.console.print(
                Panel(
                    Text(evidence[:3500]),
                    title="Visual evidence (Qwen3-VL raw output)",
                    title_align="left",
                    box=ROUNDED,
                    border_style="dim cyan",
                    padding=(0, 1),
                )
            )

        # Retrieved textbook chunks
        chunks = debug.get("retrieved_chunks") or []
        if chunks:
            chunk_lines = [
                f"Page {c['page']}: {c['text']}..." for c in chunks[:8]
            ]
            self.renderer.console.print(
                Panel(
                    Text("\n\n".join(chunk_lines)),
                    title="Retrieved textbook chunks",
                    title_align="left",
                    box=ROUNDED,
                    border_style="dim cyan",
                    padding=(0, 1),
                )
            )

        # Combined context
        combined = debug.get("combined_context")
        if combined:
            self.renderer.console.print(
                Panel(
                    Text(combined[:2500]),
                    title="Final combined context",
                    title_align="left",
                    box=ROUNDED,
                    border_style="gold1",
                    padding=(0, 1),
                )
            )

        self.renderer.console.print()

    def run(self) -> None:
        """
        Starts the CLI application.
        """
        # 1. Initialize Biology Retriever ONCE at application startup
        with self.renderer.thinking("Initializing Biology Resource Book index..."):
            initialize_retriever()

        ret_status = get_retriever_status()
        textbook_loaded = ret_status.get("textbook_loaded", False)
        page_count = ret_status.get("page_count", 0)
        chunk_count = ret_status.get("chunk_count", 0)

        llm_connected = self.client.is_available()

        # Display startup banner with REAL state
        self.renderer.print_startup(
            textbook_status=textbook_loaded,
            llm_status=llm_connected,
            model_name=self.model,
            base_url=LM_STUDIO_BASE_URL,
            page_count=page_count,
            chunk_count=chunk_count,
        )

        if not llm_connected:
            self.renderer.print_error(
                "Could not connect to LM Studio.\n\n"
                "Please check:\n"
                "  1. LM Studio is running\n"
                "  2. Model 'openai/gpt-oss-20b' is loaded\n"
                "  3. Local server is active on http://localhost:1234/v1",
                title="LM Studio Connection Failed",
            )
            return

        # Main interactive loop
        while True:
            try:
                user_input = self.input_handler.get_input()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_continue = self.handle_command(user_input)
                    if not should_continue:
                        break
                    continue

                self.process_question(user_input)

            except (KeyboardInterrupt, EOFError):
                self.renderer.print_message("Goodbye! Happy studying 👋", style="cyan")
                break
            except Exception as err:
                self.renderer.print_error(str(err), title="Application Error")
