# Strud AI — Frontend

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

Without a backend running, the app works in **local preview mode**: messages get
a friendly placeholder response so the entire UI is usable offline.

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
│   ├── chat/                # Layout shell, message list, bubbles, sources, typing
│   ├── composer/            # Glass composer + image attachment handling
│   ├── sidebar/             # Brand, new chat, search, grouped history
│   ├── profile/             # Logo, profile menu, About/Settings dialogs
│   └── ui/                  # Primitives (Button/Dialog/Toast) + animations
├── hooks/
│   └── use-chats.tsx        # ChatStoreProvider — single source of app state
├── lib/
│   ├── api/                 # THE network boundary (fetch + local preview mode)
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
- **Persistence** is localStorage (`strud.chats.v1`) through
  `lib/store/local-chats.ts` — the only module that touches storage. When the
  backend later exposes chat CRUD, only this layer changes.

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

The adapter drives the REAL pipeline headlessly: it instantiates the same
`StrudCLI` orchestration the terminal app uses — injection guard, identity,
semantic router, hybrid retrieval, evidence sufficiency, Qwen3-VL vision,
GPT-OSS-20B generation, and silent verification — through a capturing
renderer. It reuses `LLMClient`, `BiologyEngine`, and the retriever unchanged;
no AI logic lives in the frontend.

Per-chat conversation memory is preserved: each chat id gets its own headless
session (own `BiologyEngine` history + `ConversationMemory`), exactly like a
separate CLI run.

## Accessibility & responsiveness

- Semantic landmarks, labelled controls, and keyboard-operable menus/dialogs.
- Mobile: the sidebar becomes an animated drawer opened from the header.
- Desktop (≥ md): a floating glass sidebar docked inline.
- `prefers-reduced-motion` disables entry/exit animations globally.
