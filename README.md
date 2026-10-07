# Strud AI 🧬

**A retrieval-grounded, exam-aware AI study assistant for G.C.E. Advanced Level Biology — with a full local LLM fine-tuning pipeline.**

Strud AI is not a thin wrapper around a chat API. It is an end-to-end, privacy-first tutoring system: a local LLM serves the conversation, a hybrid retrieval engine grounds every biology answer in the official A-Level resource books, an internal "answer intelligence" layer shapes *how* each answer is taught, and a silent verification service checks every reply against retrieved evidence before the student ever sees it.

---

## ✨ Highlights

- **📚 Retrieval-Grounded Answers** — Every biology response is anchored to page-cited passages from the official G.C.E. A-Level Biology resource books (hybrid BM25 + semantic retrieval with scikit-learn). Unsupported claims are caught before they reach the student.
- **🧠 Answer Intelligence Layer** — A structured internal planner (Pydantic-optional dataclass schemas) decides answer *type*, *depth* (from `very_short` to `deep_dive`), *tutoring mode* (Socratic, quiz, correction, revision, exam prep), and resolves follow-ups against real conversational memory.
- **✅ Silent Answer Verification** — A `VerificationService` audits every draft answer for relevance, evidence support, question coverage, citation validity, and repetition — and internally revises failed answers up to a configured limit. The student only sees the final, checked reply.
- **🛡️ Prompt-Injection Guard** — Dedicated module hardening the assistant against instruction-injection attempts.
- **🎯 Behaviour Fine-Tuning Pipeline** — A complete MLX (Apple Silicon) LoRA fine-tuning workflow on `openai/gpt-oss-20b`: a curated, behaviour-only SFT dataset, experiment configs, benchmark evals, and reproducible result logs.
- **💬 Human-Grade Conversation** — Semantic routing separates casual chat from subject matter, so Strud talks like a real tutor instead of answering everything like a textbook.
- **🖥️ Modern TUI** — A polished terminal experience (Rich + prompt-toolkit): themed rendering, streaming replies, and graceful input handling.

---

## 🏗️ Architecture

```
                         ┌──────────────────────────┐
        user input ─────►│  CLI (cli/)              │
                         │  Rich TUI + streaming    │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │  Semantic Router         │  casual chat vs. biology?
                         │  (semantic_router.py)    │  domain + intent decision
                         └────────────┬─────────────┘
                                      ▼
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│ Answer Intelligence│   │ Biology Retrieval      │   │ Evidence Sufficiency   │
│ (answer_intel...)  │   │ (Science/Biology/)     │   │ (evidence_suff...)     │
│ plan: type, depth, │   │ hybrid BM25 + semantic │   │ is the corpus evidence │
│ mode, follow-ups   │   │ over A-Level textbooks │   │ enough to answer?      │
└─────────┬─────────┘   └───────────┬────────────┘   └───────────┬───────────┘
          │                         │                            │
          ▼                         ▼                            ▼
        ┌─────────────────────────────────────────────────────────────┐
        │  LLM Client (llm_client.py) — local OpenAI-compatible server │
        └──────────────────────────────┬──────────────────────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  Verification Service    │  silent final check
                          │  (answer_verification.py)│  + internal revision
                          └────────────┬─────────────┘
                                       ▼
                              student sees the answer
```

**Module map**

| Module | Role |
|---|---|
| [main.py](main.py) | Entry point — wires services together and launches the CLI |
| [config.py](config.py) | Central configuration (models, limits, feature flags) |
| [question_router.py](question_router.py) | Fast rule-based question classification |
| [semantic_router.py](semantic_router.py) | Embedding-based routing between chat and subject domains |
| [answer_intelligence.py](answer_intelligence.py) | Internal answer planning, depth control, conversation memory |
| [answer_verification.py](answer_verification.py) | Silent evidence-based answer checking and revision |
| [evidence_sufficiency.py](evidence_sufficiency.py) | Decides whether retrieved evidence can support an answer |
| [injection_guard.py](injection_guard.py) | Prompt-injection defence |
| [llm_client.py](llm_client.py) | Client for a local OpenAI-compatible LLM server |
| [Science/Biology/](Science/Biology/) | Biology engine, hybrid retriever, and vision (diagram) pipeline |
| [cli/](cli/) | Rich-based terminal UI: interface, input handling, rendering |
| [experiments/](experiments/) | Fine-tuning configs, dataset builder, benchmarks, results |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A local OpenAI-compatible LLM server (e.g. [LM Studio](https://lmstudio.ai)) serving a chat model at `http://localhost:1234/v1`

### Installation

```bash
git clone https://github.com/PyDeV1OpEr/Strud_AI.git
cd Strud_AI
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Optional (strongly recommended, used automatically when present):

```bash
pip install pydantic   # structured answer-plan validation
```

### Run

```bash
python main.py
```

Place your A-Level Biology resource-book PDFs under `Science/Biology/books/` — the retriever indexes them on first use. *(Books are copyright material and are git-ignored; supply your own copies.)*

---

## 🧪 Fine-Tuning Experiments

The [experiments/](experiments/) directory contains a complete, reproducible LoRA behaviour-tuning pipeline for `openai/gpt-oss-20b` on Apple Silicon (MLX backend):

- [experiments/scripts/build_strud_dataset.py](experiments/scripts/build_strud_dataset.py) — generates a curated, behaviour-only ChatML SFT dataset (persona, tutoring moves, honesty, quiz flow — *not* memorised biology facts, which stay with RAG)
- [experiments/configs/strud_gptoss20b.yaml](experiments/configs/strud_gptoss20b.yaml) — training config (LoRA r=16, cosine schedule, gradient checkpointing). Point `STRUD_BASE_MODEL` at your local checkpoint before training
- [experiments/evals/strud_benchmark.py](experiments/evals/strud_benchmark.py) — behavioural benchmark (casual handling, exam-panic empathy, explanation depth, meta-leak checks)
- [experiments/results/](experiments/results/) — baseline vs. tuned benchmark scores

This design decision is worth noting: **facts live in the retriever, behaviour lives in the fine-tune.** The SFT data deliberately avoids teaching biology content, preventing hallucinated "memorised" textbook knowledge.

---

## 🧾 Testing

```bash
python tests/test_intelligence_upgrade.py
python tests/test_hybrid_retrieval.py
python tests/test_conversation_architecture.py
python tests/test_vision_pipeline.py
```

Benchmarks for grounding quality live in [tests/benchmark_grounding.py](tests/benchmark_grounding.py) and [tests/benchmark_retrieval.py](tests/benchmark_retrieval.py).

---

## 🔒 Privacy by Design

- The LLM runs **locally** — no conversation ever leaves the machine.
- Textbooks, model checkpoints, and run artefacts are git-ignored and never uploaded.
- The injection guard and verification layer operate entirely offline.

---

## 🛣️ Roadmap

- [ ] Additional A-Level science domains (Physics, Chemistry) on the existing router/retriever framework
- [ ] Quiz progress tracking and spaced-repetition scheduling
- [ ] Richer diagram understanding via the vision pipeline
- [ ] Web UI alongside the TUI

---

## 📄 License

This project is for personal, educational use. Third-party textbook PDFs remain the property of their publishers and are never distributed with this repository.

---

*Built by [PyDeV1OpEr](https://github.com/PyDeV1OpEr) — a project about making an AI that teaches the way a good tutor does: grounded, honest, and patient.*
