# Vercel deployment runbook — frontend-only public demo

Strud AI ships in **two operating modes** (owner decision, final):

| Mode | What runs | Where |
| --- | --- | --- |
| **Complete application** | Next.js frontend + FastAPI backend + LM Studio models + Biology RAG | user's own computer |
| **Public demo** | Next.js frontend only, no AI inference | Vercel (`strud-ai.vercel.app`) |

The FastAPI backend is **not deployed to any host.** A cloud function can
use neither the local model server nor the full retrieval stack, so the
public site presents the interface honestly: it explains that live
Biology tutoring requires running Strud AI locally, and never sends
requests to a nonexistent backend or pretends a model answered.

## Frontend project (`strud-ai`)

Deploys from `strud/frontend` (CLI or connected Git). Environment
variables on Production:

| Variable | Value | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_DEMO_MODE` | `true` | Builds the honest demo state (`strud/frontend/lib/demo.ts`) |

Do **not** set `NEXT_PUBLIC_BACKEND_URL` on Vercel. In demo mode the
frontend performs zero backend/provider requests: the chat store skips
history sync, project sync, title generation and persistence, and a
submitted message gets a clear "local inference required" notice with
the repository link instead of a connection error.

Do **not** set Supabase variables for the demo; the public preview has
no sign-in-backed features either.

## Local / complete application

Follow the root [README.md](README.md) → *Local Setup*. In short:
local frontend `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`,
backend `uvicorn strud.backend.api.main:app --port 8000`, models served
by LM Studio on `http://localhost:1234/v1`.

## Removed hosted-backend configs

The repository previously carried hosted-backend deployment configs
**`vercel.json`** (Vercel Python runtime) and **`render.yaml`** (Render
blueprint). They were removed so an accidental push cannot spin up a
hosted backend that cannot actually serve answers. The backend remains
a local application (`strud/backend/`), and `Dockerfile` remains as an
optional local/self-hosting containerization. If you ever want remote
hosting, those files can be restored from Git history — but that is a
deliberate future decision, not part of this release.
