# Strud AI — Frontend

[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/) [![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111111)](https://react.dev/) [![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/) [![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

A premium, dark-first glassmorphism chat interface for **Strud**, an AI-powered
Biology learning assistant. Built with Next.js, React, TypeScript, Tailwind CSS,
Lucide icons, and Motion for React.

> **Model-agnostic by design.** The frontend never talks to an LLM directly —
> every AI capability funnels through `POST /api/chat`, so the backend can swap
> models, retrieval, or vision services without a single frontend change.

---

## Quick start

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000 (or the port Next.js prints)
```

| Script            | Purpose                          |
| ----------------- | -------------------------------- |
| `npm run dev`     | Dev server (Turbopack, hot reload) |
| `npm run build`   | Production build + typecheck     |
| `npm run lint`    | ESLint                           |
| `npm run start`   | Serve the production build       |
| `npm run test:markdown` | Markdown rendering regressions (offline) |

The app requires the FastAPI backend for AI responses and durable chat operations.
If the backend is unavailable, the frontend keeps its local cache and displays a
friendly connection error.

## Environment variables

| Variable                  | Default                 | Purpose                         |
| ------------------------- | ----------------------- | ------------------------------- |
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |

Set them in `frontend/.env.local`:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

The frontend always talks to the FastAPI backend — there is no mock mode. If
the backend is down, messages show a friendly connection error instead.

## Architecture

```
frontend/
├── app/                     # Next.js App Router (layout + page)
├── components/
│   ├── chat/                # Messages, sources, typing, and Recycle Bin
│   ├── composer/            # Glass composer + image attachment handling
│   ├── sidebar/             # Brand, new chat, search, grouped history
│   ├── profile/             # Logo, profile menu, About/Settings dialogs
│   └── ui/                  # Primitives (Button/Dialog/Toast) + animations
├── hooks/
│   └── use-chats.tsx        # ChatStoreProvider — single source of app state
├── lib/
│   ├── api/                 # Network boundary for chat, history, and bin operations
│   ├── store/               # External store + localStorage persistence
│   ├── group-chats.ts       # Today / Yesterday / Previous 7 Days / Older
│   └── title.ts             # Chat title derivation
├── styles/                  # Design tokens, glass utilities, markdown styles
└── types/                   # Shared TypeScript contracts
```

### State model

- **Chat history** lives in an external store
  (`lib/store/chat-store.ts`) read through `useSyncExternalStore`. This keeps
  prerender deterministic (empty server snapshot) and hydration mismatch-free,
  with no setState-in-effect passes.
- **UI state** (active chat, composer text, pending attachments, errors) stays
  in React state inside `hooks/use-chats.tsx`, exposed via
  `ChatStoreProvider` / `useChatStore()`.
- **Persistence** is server-backed through `lib/api/chats.ts`: SQLite stores chat
  metadata, messages, titles, soft-deletion state, and attachment references.
  `localStorage` remains an offline cache rather than the source of truth.

### Component flow

```
app/page.tsx
└── ChatLayout (components/chat/chat-layout.tsx)
    ├── Sidebar — brand, New Chat, search, grouped history, delete-confirm
    ├── ChatMessages — message list, smart scroll-follow, typing indicator
    │   └── MessageRow — user bubbles, markdown assistant replies, Sources, copy
    ├── ChatComposer — Enter-to-send, image attach (png/jpeg/webp ≤ 8 MB), preview
    └── ProfileMenu — About + Settings dialogs
```

## Backend API contract

The frontend expects the FastAPI adapter in `../backend/` to expose:

### `POST /api/chat`

Request:

```json
{
  "chatId": "uuid",
  "message": "Explain the Krebs cycle",
  "attachments": [{ "name": "cell.png", "mimeType": "image/png", "data": "<base64>" }]
}
```

Response:

```json
{
  "messageId": "uuid",
  "content": "Markdown answer…",
  "sources": [{ "label": "Biology Resource Book", "pages": [42, 44] }]
}
```

`sources` is optional; when present it renders the collapsible Sources chip.
Non-2xx responses surface as a friendly inline error message on the reply.

### `POST /api/title`

```json
{ "chatId": "uuid", "message": "first user message" }
```
→ `{ "title": "Photosynthesis basics" }` (best-effort; local fallback on failure).

### `GET /api/health`

Used by the adapter to confirm LM Studio reachability.

### Chat persistence and Recycle Bin

- `PATCH /api/chats/{chat_id}/title` persists a generated chat title.
- `GET /api/chats?user_id=...` returns active chats and durable messages.
- `GET /api/chats/deleted?user_id=...` returns Recently Deleted chats.
- `DELETE /api/chats/{chat_id}?user_id=...` moves a chat to the bin.
- `POST /api/chats/{chat_id}/restore?user_id=...` restores the original chat ID.
- `DELETE /api/chats/{chat_id}/permanent?user_id=...` permanently removes a bin item.
- `DELETE /api/chats/deleted/all?user_id=...` empties the bin.
- `GET /api/uploads/{filename}` serves validated persisted image uploads.

The backend creates and migrates `strud_cache/strud_memory_v3.db` additively. It
does not delete user-level memory when a chat is permanently deleted.

## Running with the real backend

```bash
# 1. Start LM Studio (serving openai/gpt-oss-20b) on http://localhost:1234
# 2. Install adapter deps and run it (the repo's .venv already has the
#    pipeline dependencies; add fastapi + uvicorn if missing)
cd backend
pip install -r requirements.txt
# from the repository root (the directory containing config.py):
.venv/bin/python -m uvicorn strud.backend.api.main:app --port 8000
# 3. Start the frontend
cd ../frontend
npm run dev
```

## Backend architecture (LangChain + LangGraph + persistent memory)

Since the memory overhaul, `POST /api/chat` is served by a **LangGraph
tutoring workflow** (`strud/backend/tutoring_graph.py`) instead of the
headless CLI session:

```
load_context ─> route ─┬─> score_answer    (deterministic quiz scoring)
                       ├─> new_quiz ─> retrieve ─┐
                       ├─> quiz_answer ──────────┤
                       ├─> remember ─────────────┤
                       ├─> recall (direct)       ├─> tutor (LLM)
                       ├─> forget (direct)       │      v
                       ├─> quiz_history (direct) │   validate (identity
                       ├─> biology ─> retrieve ──┘   redaction + page guard)
                       └─> general ─> tutor ──────> finalize_quiz ─> persist
```

Components:

- **LangChain** (`strud/backend/llm_chain.py`): `ChatOpenAI` adapter over
  LM Studio (or any OpenAI-compatible endpoint) and a `BioTextbookRetriever`
  wrapping the existing TF-IDF + dense + rerank pipeline as a standard
  LangChain retriever.
- **LangGraph** (`strud/backend/tutoring_graph.py`): the tutoring workflow
  above with typed state and a `SqliteSaver` checkpointer
  (`strud_cache/strud_checkpoints.db`) so conversation state survives
  backend restarts.
- **Memory layers** (`strud/backend/memory_store.py`, SQLite via stdlib,
  `strud_cache/strud_memory_v3.db`):
  - `conversations` — durable per-chat history (layer A)
  - `user_memory` — cross-chat facts/preferences, user-scoped (layer B)
  - `quiz_sessions` + `quiz_attempts` — structured quiz records (layer C).
    Scores are ALWAYS computed from these records, never from the model's
    recollection. Unverifiable attempts are recorded as `skipped`, never
    guessed.
- **Identity defense in depth**: trusted system prompt + deterministic
  post-generation redaction of internal model/provider names (`validate`
  node) + the existing `injection_guard` for genuine override attempts.
  This is resistance, not a guarantee — see Limitations.

Per-user isolation is enforced in the store layer (every query is scoped by
`user_id`). The local frontend creates a stable per-browser id; a multi-user
deployment should replace it with an authenticated identity.

Extra endpoints: `GET /api/memory`, `DELETE /api/memory/{id}`,
`GET /api/quizzes`, `GET /api/quizzes/{quiz_id}/score`,
`DELETE /api/quizzes/{quiz_id}`.

### Switching the model (e.g. to GLM)

The model is externalized config: edit `assistant_config.json` → `"model"`
→ `"id"` (and `base_url` if not LM Studio), then restart the backend.
When LM Studio loads a different model, copy the exact id it reports from
`GET http://localhost:1234/v1/models`. No code changes needed.

## Running the backend

```bash
# 1. Start LM Studio and load the configured model (see assistant_config.json)
# 2. Install backend deps (from the repo root)
.venv/bin/pip install -r requirements.txt strud/backend/requirements.txt
# 3. Run the API
.venv/bin/python -m uvicorn strud.backend.api.main:app --port 8000
# 4. Frontend
cd strud/frontend && npm install && npm run dev   # http://localhost:3000
```

## Tests

```bash
# Offline deterministic suite (no LLM needed; ~5s)
.venv/bin/python tests/test_memory_and_quiz.py

# Legacy suites still pass:
.venv/bin/python tests/test_intelligence_upgrade.py   # 174 checks, needs LM Studio
.venv/bin/python tests/test_hybrid_retrieval.py       # 31 checks, needs index

# Live E2E evaluation of the tutoring graph (needs LM Studio; ~5 min)
.venv/bin/python tests/eval_tutoring_graph.py
```

The live eval covers the verification checklist: mechanism answer quality,
identity/injection resistance, out-of-scope handling, quiz 2/3 score from
stored records, cross-chat memory, and persistence across a simulated
restart.

## Limitations (honest)

- **Prompt injection cannot be fully prevented** by any prompt-based
  system. Strud layers deterministic guards (injection regexes, output
  redaction, page-citation guard) with a trusted system prompt, but a
  sufficiently capable model could still be manipulated by novel attacks.
  Test known patterns (see live eval) and keep secrets out of model context.
- **Quiz verdict extraction is heuristic.** The tutor's feedback is parsed
  for the confirmed-correct letter. When the model phrases the verdict in
  an unforeseen way, the attempt is recorded as `skipped` (honest no-score)
  rather than guessed. The feedback prompt mandates a fixed verdict format
  to keep this rare.
- **Memory retrieval is recency-ordered, not semantic.** All stored facts
  (up to 10) are injected into the prompt for the model to filter by
  relevance. Vector search over memory is a future enhancement.
- **Local browser identity is not authentication.** The per-browser id keeps
  local users separated, but real auth is required before exposing this
  beyond loopback.
- **Vision questions bypass the graph's retrieval scoring**; image context
  flows through the legacy vision pipeline and the answer is generated by
  the graph tutor with the visual context in the session.

## Accessibility & responsiveness

- Semantic landmarks, labelled controls, and keyboard-operable menus/dialogs.
- Mobile: the sidebar becomes an animated drawer opened from the header.
- Desktop (≥ md): a floating glass sidebar docked inline.
- `prefers-reduced-motion` disables entry/exit animations globally.
