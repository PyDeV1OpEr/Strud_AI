# DEPLOYMENT_STATUS.md

Persistent tracker for the "deploy Strud AI to public production (Vercel + Supabase + Render)" effort.
Secrets are **never** written here. Update after each stage so work can resume if the session ends.

Last updated: 2026-10-16 (stages 0–4 complete; stage 7 matrix active)

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

## Stage 2 — Frontend production readiness (Vercel) — COMPLETE, VERIFIED

- [x] Project `strud-ai` created on Vercel (`prj_WTgJRpMTrgODYsxwlT2vHkvv8Xle`, scope “Mohammed Unais' projects”).
- [x] Production deployment **Ready** → **https://strud-ai.vercel.app** (HTTP 200, Next.js HTML served).
- [x] Root cause fixed for the first 404: project had framework preset “Other”; switched to Next.js and redeployed (`vercel project update strud-ai --framework nextjs`).
- [x] Assets verified: CSS + JS chunks serve 200; no `localhost` in served HTML.
- [x] No secrets reachable in the frontend — only `NEXT_PUBLIC_BACKEND_URL` is a public variable and it is NOT yet set (see below).
- [x] Vercel MCP connector scope blocked repo-linking (403 “re-authenticate to scope”); deployment done through the Vercel CLI after an owner-authorized device login. Git integration must be connected once in the dashboard to enable push-based deploys: https://vercel.com/dashboard → strud-ai → Settings → Git.
- [ ] `NEXT_PUBLIC_BACKEND_URL` on Vercel (production) — blocked on the Render backend URL; run:
      `vercel env add NEXT_PUBLIC_BACKEND_URL production` then redeploy. Without it the UI gracefully shows its existing connection-error state (no crash), but chat cannot work from the deployed site.

---

## Stage 3 — Supabase (project restore + tables + auth) — SCHEMA + RLS COMPLETE

Project: `frdfpvulvlubaysykyxn` — “PyDeV1OpEr's Project” → **ACTIVE_HEALTHY** again (restore succeeded).

- [x] Project restored to ACTIVE.
- [x] Migration `strud_core_tables` applied: `chats`, `projects`, `profiles`, `conversations`, `user_memory`, `quiz_sessions`, `quiz_attempts`, `ai_usage`, plus `provider_keys` (per-user provider API keys; secret bytes go into Supabase Vault, table stores only the vault secret id).
- [x] Migration `strud_rls_policies` applied: RLS enabled on ALL 9 tables; `chats_owner_all` … `ai_usage_owner_read` policies enforce `user_id = auth.uid()::text`; **`provider_keys` has intentionally NO policies** (service-role-only; security advisor flags it as INFO by design).
- [x] Verified via `pg_tables`: rowsecurity = true on all 9 tables; security advisor shows no findings other than the intentional `provider_keys` INFO and a password-protection WARN that is irrelevant to sign-in-with-Google-only.
- [x] Backend SQLite live-data path remains untouched (zero data loss); the Postgres mirror is the persistence layer the backend switches to in the auth stage.
- [ ] Google OAuth: requires **owner-provided credentials** (cannot be invented):
      - Create a Google Cloud OAuth client (Web application) with redirect URIs:
        - `https://<project-ref>.supabase.co/auth/v1/callback`
        - plus the frontend origin(s) once the Vercel URL is known.
      - In Supabase → Authentication → Providers → Google: enable, paste Client ID + Client Secret.
      - Set Supabase Auth URL configuration: Site URL = deployed frontend URL, additional redirect URLs = frontend origin(s).
- [ ] Frontend + backend integration with Supabase Auth (JWT carries `sub`; backend verifies and scopes every private-data query by it). **This is the biggest remaining engineering task and is planned as its own stage; do not treat the schema/RLS work above as "auth works".**

Credentials owner must provide (nothing stored here): Google OAuth Client ID/Secret — enter them directly in the Supabase dashboard, never in this repo.

---

## Stage 4 — Backend deployment readiness (Render) — CONFIG CODE COMPLETE

Status: production config implemented and locally verified; **Render deployment itself is an owner action (no Render connector).**

- [x] Audit: backend cannot run on Vercel; Render chosen.
- [x] `Dockerfile` added (python:3.12-slim; installs both requirements files; serves uvicorn on `$PORT`).
- [x] `render.yaml` added (web service, Docker runtime, free plan, `/api/health` health check; secrets as `sync:false`).
- [x] env-driven CORS implemented: `STRUD_ALLOWED_ORIGINS` (comma-separated origins) + retained loopback regex for local dev.
- [x] Rate limiting implemented + verified by test (`/api/title` → 429 after STRUD_RATE_LIMIT_PER_MINUTE calls, default 20/min per IP; applied to POST `/api/chat` and `/api/title`; health/GET excluded).
- [x] Upload cap env-configurable: `STRUD_MAX_UPLOAD_BYTES` (default 8 MB, unchanged).
- [x] Data directory env-driven: `STRUD_DATA_DIR` → all SQLite/index/upload paths (config.py) resolve under it (maps to a mounted disk).
- [x] Provider-key support (Mode A foundation) implemented & verified end-to-end locally:
      env `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_ID` override assistant_config.json (env > file precedence, including after `update_model_config`). `LLMClient` and LangChain `ChatOpenAI` send the real Bearer key when set; local LM Studio behavior unchanged when unset. Provider-shaped errors added: 401/403 → “provider rejected the API key”, 429 → “quota/rate limit”. The key is never logged.
- [ ] Docker image build NOT verified locally — Docker is not installed on this machine. First verification happens at the Render deploy.
- [x] Owner actions (exact steps):
      1. Push latest `main` (done in Stage 1 for this session's commit).
      2. At https://dashboard.render.com → New → Web Service → connect `PyDeV1OpEr/Strud_AI`.
      3. Runtime: Docker; Dockerfile path `/Dockerfile`; instance type: Free (backend boots; first /api/chat latency with free instances is cold-start heavy).
      4. Persistent disk mounted at `/data` and set env `STRUD_DATA_DIR=/data`.
      5. Set env vars (values owner-provided, kept out of repo): `STRUD_ALLOWED_ORIGINS=https://<vercel-domain>,…`, `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`.
      6. Verify `GET /api/health` returns `ok: true` over HTTPS.

**Caveat (honest, unchanged)**: the textbook PDF is copyrighted and git-ignored, so the index cannot be baked into the image from the repo. Until index assets are provisioned into the volume at `/data`, `/api/health` will report `textbookLoaded: false` and **Biology RAG is NOT production-ready** — do not announce RAG-verified answers (the pipeline runs in its documented ungrounded fallback mode).

**Free-tier note**: Render free instances have no persistent disk — user data is ephemeral (resets on restart/redeploy). Persistent disk requires Render Starter (+$7/mo) and the owner's explicit approval (none requested yet).

---

## Stage 5 — AI provider modes

- [x] Decision: Mode A = user-provided provider keys proxied server-side; Gemini/OpenAI-compatible endpoint support via env first, per-user keys after auth.
- [x] Per-user API-key storage/isolation designed (Supabase table + backend scoping by verified JWT `sub`), planned as a follow-on stage with auth. No keys in the frontend bundle or shared tables; keys are never logged.
- [x] Useful provider errors implemented (invalid key → 401/403 message, quota/rate → 429 message, network/timeout messages kept); a live provider connection test needs a real user key (owner/each user).
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
| 1 | Frontend builds | ✅ verified — local build + Vercel production build both OK |
| 2 | Backend starts | ✅ locally (uvicorn, offline suites 19 passed incl. persistence); Docker/Render boot pending |
| 3 | Google auth works | ⛔ blocked (needs owner OAuth creds) |
| 4 | Create + retrieve chat (signed-in) | ⛔ blocked on auth + Postgres backend integration |
| 5 | Data persists across sessions | pending — backend runs SQLite; Postgres switch is the auth stage |
| 6 | Accounts can't access each other's data | pending — RLS in place; e2e test needs auth wired |
| 7 | API-key mode connects | ⏸️ env mechanism verified locally; real provider call needs a real key (owner) |
| 8 | Invalid keys / quotas give useful errors | ✅ provider-shaped error mapping implemented (401/403/429); live provider test pending |
| 9 | Biology RAG returns pages | ⛔ blocked (index assets not yet provisioned to a hosted backend) |
| 10 | Desktop + mobile smoke | ✅ deployed site serves; interactive device smoke pending |

Offline suites rerun after ALL backend edits this stage: `pytest strud/backend -q` → **19 passed**; env-precedence, bearer-header, rate-limit (429 after 20/min), and Gemini endpoint-shape checks all verified locally.

---

## Errors log

1. Vercel MCP connector → repo link: 403 “Not authorized: … scope mohammed-unais-projects” — token scope issue, not a config error. Worked around with the Vercel CLI + owner-authorized device login.
2. First production deploy served edge 404: project created with framework preset “Other” → fixed to Next.js, redeployed, verified 200.

## Exact next steps (resume from here)

1. Owner: deploy the backend on Render with the runbook above; then set `NEXT_PUBLIC_BACKEND_URL` on Vercel and redeploy the frontend.
2. Owner: provide Google OAuth credentials (Stage 3 list).
3. Engineering (next session): backend Supabase Postgres integration + JWT verification on protected endpoints (the largest remaining task — schema/RLS is already live and ready), then per-user provider-key storage via `provider_keys` + Vault, and frontend sign-in.
4. Engineering: provision the Biology index onto the Render volume and rerun retrieval evaluation before claiming ANY grounded answers.
