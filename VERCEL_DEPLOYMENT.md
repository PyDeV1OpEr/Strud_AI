# Vercel deployment runbook

The Next.js frontend and the FastAPI backend are **separate Vercel
projects** backed by the same repository (`PyDeV1OpEr/Strud_AI`).

| Project | URL | Built from |
| --- | --- | --- |
| `strud-ai` (frontend) | https://strud-ai.vercel.app | CLI deploys from `strud/frontend` |
| `strud-backend` (backend) | https://strud-backend.vercel.app | CLI deploys from the repository root |

## Backend architecture

`vercel.json` at the repository root maps every `/api/*` request to the
existing FastAPI app (`strud.backend.api.main:app`) via `@vercel/python`.
The runtime installs the requirements file **nearest the entrypoint**
(`strud/backend/requirements.txt`), so that file carries the backend's
full import graph — not the repository-root one.

Environment variables on the `strud-backend` project (Production):

| Variable | Value | Purpose |
| --- | --- | --- |
| `STRUD_ALLOWED_ORIGINS` | `https://strud-ai.vercel.app` | CORS; loopback origins always allowed |
| `STRUD_DATA_DIR` | `/tmp/strud-data` | Writable scratch dir for SQLite/index/uploads |
| `SUPABASE_URL` | `https://frdfpvulvlubaysykyxn.supabase.co` | Enables Supabase JWT auth + cloud knowledge base |

## Manual steps still required (dashboard)

1. **`SUPABASE_SERVICE_ROLE_KEY`** — set it on `strud-backend`
   (Production). With it, the backend downloads the canonical Biology
   PDF from the private `strud-knowledge-base` bucket instead of relying
   on files bundled at deploy time, and `STRUD_ADMIN_USER_IDS` unlocks
   the admin upload/re-index endpoints. Do not use a legacy JWT here
   unless the backend code expects it — this is a Storage
   service_role/scoped key.
2. **`STRUD_ADMIN_USER_IDS`** — the administrator's Supabase user UUID.
3. **Git auto-deploy** — connecting the repository with
   `vercel git connect` did not attach a Git integration to
   `strud-backend` (a repo can back multiple projects; verify under
   Settings → Git). Until then, redeploy the backend with
   `vercel deploy --prod --yes` from the repository root.
4. Optional server-side model — set `LLM_BASE_URL`, `LLM_API_KEY`,
   `LLM_MODEL_ID` (e.g. Gemini's OpenAI-compatible endpoint). Without
   these the backend has no reachable LLM and `/api/chat` returns 503.

## Redeploying

```sh
# backend (repository root; respects .gitignore)
vercel deploy --prod --yes
# frontend (after changing strud/frontend or backend-linked env vars)
cd strud/frontend && vercel --prod
# or re-build the last frontend deployment with updated env vars
vercel redeploy <last-production-deployment-url>
```

Note: a **CLI deploy of the backend bundles the local Biology PDF**
from `Science/Biology/books/` (not Git files — uploads only). Pushing
commits does **not** trigger backend deploys until the Git integration
in step 3. A future Git-based build will NOT contain the PDF, so the
Supabase service-key configuration above becomes required for
`textbookLoaded: true`.

## Frontend

- `NEXT_PUBLIC_BACKEND_URL=https://strud-backend.vercel.app`
  (Production env var; rebuild the frontend to bake it in).
- Local development stays on `strud/frontend/.env.local`
  (`http://localhost:8000`).

## Known limitations

- **Ephemeral user data:** chats/projects/profile/uploads live in SQLite
  under `/tmp` inside a function instance. They survive warm reuse of an
  instance but NOT instance recycling, cold starts after idle, or
  deployments. Durable storage needs a Supabase (or similar) migration
  of `strud/backend/memory_store.py`.
- **Cold-start retrieval:** the first request after an idle period
  re-downloads (with the service key) and re-chunks/indexes the textbook
  (~20 s locally; TF-IDF/BM25 legs only — sentence-transformers is not
  installed on hosts and retrieval auto-degrades to the sparse legs).
- `chat` requires a reachable OpenAI-compatible endpoint: a Vercel
  function cannot reach your Mac's LM Studio (`localhost:1234`). The
  browser's direct local-provider mode stays device-local.
- Rate limiting is in-memory per function instance (20 req/min default).
- Frontend Vercel preview URLs are not in `STRUD_ALLOWED_ORIGINS`;
  add a preview URL explicitly when testing one.
