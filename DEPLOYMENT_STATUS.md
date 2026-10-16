# DEPLOYMENT_STATUS.md

Persistent tracker for the "deploy Strud AI to public production (Vercel + Supabase + Render)" effort.
Secrets are **never** written here. Update after each stage so work can resume if the session ends.

Last updated: 2026-10-16 (stage 0 + stage 1 complete)

---

## Decisions locked with the owner (2026-10-16)

1. **Git**: pending local work is committed and pushed to `origin/main` (Vercel deploys from git).
2. **Supabase**: restore the existing paused project **"PyDeV1OpEr's Project"** (`frdfpvulvlubaysykyxn`, ap-southeast-2) — do not create a new one.
3. **Backend host**: prepare for **Render** (the FastAPI backend cannot run on Vercel — see Stage 0 findings).
4. **Mode A (public users)**: users enter their **own provider API key (Gemini first)** in Settings; the **FastAPI backend proxies** requests to Google's OpenAI-compatible endpoint. Keys stay server-side and per-user isolated — never bundled in the frontend.

---

## Stage 0 — Audit findings (complete)

### What exists (preserve; do not rebuild)

| Component | Location | Notes |
|---|---|---|
| Next.js 16 frontend | `strud/frontend` | App Router, React 19, Tailwind 4; backend URL env-driven via `NEXT_PUBLIC_BACKEND_URL` (`lib/api/errors.ts`), default `http://localhost:8000` |
| FastAPI backend | `strud/backend/api/main.py` | 999 lines; thin HTTP boundary over the existing pipeline (LangGraph tutoring workflow, memory store, retriever) |
| AI pipeline | repo root + `Science/Biology/` | semantic router → hybrid retrieval (TF-IDF + BM25 + MiniLM, RRF) → evidence sufficiency → GPT-OSS-20B via LM Studio → silent verification |
| Persistence | SQLite (`strud_cache/strud_memory_v3.db`) | chats, messages, memory, projects, quizzes, soft-delete, `ai_usage`; uploads in `strud_cache/uploads/`; additive migrations on startup |
| Knowledge base | `Science/Biology/books/Biology_ResourceBook.pdf` | **git-ignored** (copyright); index cached in `strud_cache/` (also git-ignored) |
| Auth | **none** | frontend mints an anonymous `user_id` in localStorage and trusts it server-side (`lib/user-id.ts`) |

### Hard production blockers found

1. **Backend cannot run on Vercel**: `langchain`/`langgraph`, `scikit-learn`, optional `sentence-transformers` (torch), `pymupdf`, SQLite file paths, and an in-process LM Studio dependency. → Deploy to **Render** (Dockerfile + render.yaml prepared).
2. **CORS is loopback-only** (`allow_origin_regex` for `localhost|127.0.0.1` in `strud/backend/api/main.py`) → must become env-driven (`STRUD_ALLOWED_ORIGINS`).
3. **No authentication / weak identity**: any caller may pass any `user_id` in the URL/body and read, modify, or delete that user's chats and memory. On the public internet this is a direct cross-user data-exposure vector. → Supabase Google sign-in + backend JWT verification + per-user scoping is required **before** public exposure; chat endpoints must reject missing/invalid tokens.
4. **Model layer assumes LM Studio** at `http://localhost:1234/v1` with hardcoded `api_key="lm-studio"` (`strud/backend/llm_chain.py`). A hosted backend must resolve keys/endpoints from env first (owner key), then per-user keys once auth exists.
5. **RAG assets are machine-local**: the textbook PDF and the prebuilt index live only on the owner's Mac and are git-ignored. Production retrieval needs an asset provisioning step (persistent disk + one-time index bake), with clear diagnostics when missing (the backend already reports `pdf_exists`/`textbookLoaded: false` in `/api/health` and `/api/rag/status`).
6. **Mode B (local GPT-OSS) cannot work from a hosted HTTPS site**: a browser on `https://…` cannot reach `http://localhost:1234/v1` (mixed content + CORS + browser sandbox). Keep local mode for the local TUI/local frontend only; document the limitation. Local companion/proxy is a follow-up, not required for beta.
7. Uploads are stored on local disk under `strud_cache/uploads/` and served by static-file mount — fine on Render with a persistent disk, not on Vercel.

### Environment inventory

- Frontend env: `NEXT_PUBLIC_BACKEND_URL` (only variable; no secrets ever in the frontend bundle).
- Backend: currently **zero env vars** — model config lives in `assistant_config.json` (`model` block). Production needs env-driven settings: allowed CORS origins, LLM base URL/key/provider, data directory.
- No `.env` files are committed (`.gitignore` excludes `.env`, `.env.*`).

---

## Stage 1 — Local checkpoint (complete)

- [x] Committed the pending thinking-selector / model-controls work locally and pushed to `origin/main` (owner-authorized).
- [x] Verified backend offline regression suites + frontend typecheck/build before pushing.

---

## Stage 2 — Frontend production readiness (Vercel)

Status: **in progress**

- [ ] Vercel project created & linked to `PyDeV1OpEr/Strud_AI` with root directory `strud/frontend`.
- [ ] `NEXT_PUBLIC_BACKEND_URL` set in Vercel (production + preview) once the Render backend URL exists.
- [ ] First deployment verified: routing, refresh behavior, no localhost assumptions in the bundle.
- [ ] Confirmed no secrets are bundled (only `NEXT_PUBLIC_*` variables are public by design).

**Notes**: A deployed frontend without a reachable backend shows the app's existing friendly connection error — shipping it early is safe (nothing leaks), but the beta is only complete when the backend is live.

---

## Stage 3 — Supabase (project restore + tables + auth)

Status: **in progress**

Project: `frdfpvulvlubaysykyxn` — "PyDeV1OpEr's Project" (was INACTIVE/paused; free tier).

- [ ] Project restored to ACTIVE.
- [ ] Schema migration applied (mirrors the SQLite persistence model: chats, messages, memory, projects, usage, settings) — status below.
- [ ] Row Level Security enabled with per-owner policies (owner identified by `auth.uid()` once auth is wired; service role used by the trusted backend for privileged paths).
- [ ] Google OAuth: requires **owner-provided credentials** (cannot be invented):
      - Create a Google Cloud OAuth client (Web application) with redirect URIs:
        - `https://<project-ref>.supabase.co/auth/v1/callback`
        - plus the frontend origin(s) once the Vercel URL is known.
      - In Supabase → Authentication → Providers → Google: enable, paste Client ID + Client Secret.
      - Set Supabase Auth URL configuration: Site URL = deployed frontend URL, additional redirect URLs = frontend origin(s).
- [ ] Frontend + backend integration with Supabase Auth (JWT carries `sub`; backend verifies and scopes every private-data query by it). **This is the biggest remaining engineering task and is planned as its own stage; do not treat the schema/RLS work above as "auth works".**

Credentials owner must provide (nothing stored here): Google OAuth Client ID/Secret — enter them directly in the Supabase dashboard, never in this repo.

---

## Stage 4 — Backend deployment readiness (Render)

Status: **in progress / partially prepared**

- [x] Audit: backend cannot run on Vercel; Render chosen.
- [ ] `Dockerfile` + `render.yaml` added (root repo, backend service) — prepared to support a rendered deploy.
- [ ] env-driven CORS (`STRUD_ALLOWED_ORIGINS`) implemented; loopback regex retained as default for local dev.
- [ ] Provider-key support via env (`LLM_BASE_URL`, `LLM_API_KEY`, provider presets incl. Gemini OpenAI-compat endpoint) — Mode A foundation. Per-user keys in Settings come after auth integration.
- [ ] Rate limiting + request-size/upload validation review.
- [ ] Owner actions required (no connector for Render; free tier web service):
      1. Push latest `main` (done in Stage 1 for this session's commit).
      2. At https://dashboard.render.com → New → Web Service → connect `PyDeV1OpEr/Strud_AI`.
      3. Runtime: Docker; Dockerfile path `/Dockerfile`; instance type: Free (backend boots; first /api/chat latency with free instances is cold-start heavy).
      4. Persistent disk mounted at `/data` and set env `STRUD_DATA_DIR=/data`.
      5. Set env vars (values owner-provided, kept out of repo): `STRUD_ALLOWED_ORIGINS=https://<vercel-domain>,…`, `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`.
      6. Verify `GET /api/health` returns `ok: true` over HTTPS.

**Caveat (honest)**: the textbook PDF is copyrighted and git-ignored, so the index cannot be baked into the image from the repo. The deploy must either (a) know the index assets are uploaded to the mounted persistent disk before first use, or (b) accept the `textbookLoaded: false` degraded state, in which Biology RAG answers are labelled ungrounded. Until the index is provisioned, **Biology RAG is NOT production-ready** — do not announce RAG-verified answers.

---

## Stage 5 — AI provider modes

- [x] Decision: Mode A = user-provided provider keys proxied server-side; Gemini/OpenAI-compatible endpoint support via env first, per-user keys after auth.
- [x] Per-user API-key storage/isolation designed (Supabase table + backend scoping by verified JWT `sub`), planned as a follow-on stage with auth. No keys in the frontend bundle or shared tables; keys are never logged.
- [x] Connection test + useful provider errors (invalid key / quota / network / model availability) planned as part of the auth-locked stage.
- [x] Mode B (local GPT-OSS) preserved for local deployments; hosted-site limitation documented above.
- [x] Pricing note for users: each user's provider usage is billed to their own key/account — Strud never uses their quota for anything else, and the owner's personal API key/quota is never shared with users.

---

## Stage 6 — Biology RAG production readiness

- [x] Local index lifecycle verified: cached in `strud_cache/`, built once, loaded on later starts; no model downloads or rebuilds on every request.
- [ ] Owner-facing bake + upload runbook (not yet documented into the repo docs).
- [ ] Retrieval evaluation rerun post-deploy (blocked until the backend is live and index is provisioned).

---

## Stage 7 — Verification matrix (none of these may be claimed without evidence)

| # | Check | Status |
|---|---|---|
| 1 | Frontend builds | pending re-run on deployed branch |
| 2 | Backend starts | pending (local ✓) |
| 3 | Google auth works | blocked (needs owner OAuth creds) |
| 4 | Create + retrieve chat (signed-in) | pending |
| 5 | Data persists across sessions | pending |
| 6 | Accounts can't access each other's data | pending |
| 7 | API-key mode connects | pending |
| 8 | Invalid keys / quotas give useful errors | pending |
| 9 | Biology RAG returns pages | pending |
| 10 | Desktop + mobile smoke | pending |

---

## Errors log

(empty — appended as encountered)

## Exact next steps (resume from here)

1. Finish Stage 2: create/link the Vercel project, deploy, verify.
2. Restore the Supabase project; apply migrations + RLS.
3. Finish Stage 4 backend config + Mode A foundation in code; rerun offline test suites.
4. Provide/collect the Google OAuth client + the Render deploy (owner manual actions, listed above).
