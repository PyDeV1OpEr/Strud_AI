# IMPLEMENTATION_STATUS.md

Persistent progress tracker for the "make Strud AI fully functional" completion effort.
Git: branch `main`, clean tree at `bfe6c48` before this effort.

## Follow-up: targeted frontend fixes (multiline input + focus glow)

Three minimal edits, all verified live:

1. **Multiline submissions preserved** — root cause: user bubbles rendered `message.content` as plain inline text; HTML collapses newlines. Fix: `whitespace-pre-wrap` on the bubble in `components/chat/message.tsx` (user content stays literal — no Markdown hard-break conversion). Backend round-trip verified byte-for-byte (`\n`, `\n\n`, bullets intact through API + SQLite).
2. **Green glow removed** — root cause: the global unlayered `:focus-visible { outline: 2px solid rgb(110 231 183 / .6) }` in `styles/globals.css` beat every layered `outline-none` utility, painting a green box around the focused composer textarea (Chromium treats text fields as focus-visible on click). Fix: `textarea:focus-visible, input:focus-visible { outline: none }` — buttons/selects keep their outline; composer shell + all settings/search inputs already carry their own border-based focus styles.
3. **Consistent focus border** — root cause: the intended `focus-within:border-emerald-400/30` Tailwind utility never applied (unlayered `.glass-strong` border shorthand outranks `@layer utilities`). Fix: `.composer-shell:focus-within` rule in `styles/globals.css` (emerald 32% border, `border-color`-only 160ms transition → no layout shift; `transition-property` limited to `border-color`; suppressed under `prefers-reduced-motion`).

Checks: `tsc --noEmit` clean, eslint 0 errors on touched files, `tests/markdown-rendering.mjs` pass, production `next build` pass, live browser verification of focus states + real Enter-submit of a 7-line message (blank line + bullets intact in bubble, assistant markdown unaffected). The test chat created during verification was moved to the Recycle Bin (reversible).

Limitation: this preview webview's window never takes OS focus (`document.hasFocus() === false`), so the search input's `:focus` border transition could not be observed live; the rule exists in the served CSS, has the same cascade proven on the composer, and the pre-existing `focus:border-emerald-400/40` class on that input was untouched.

## Final-completion-check addendum — pre-existing critical bug found & fixed

**`config.py:_load_assistant_config` never merged the `model` block.** The Models-page "Save Model Configuration" (model id, base URL, temperature, max tokens) wrote `assistant_config.json` correctly but every runtime read dropped the block and used defaults — the setting looked saved while having **no effect on any request**, and changes did not survive restarts either. Fixed by merging the `model` dict alongside the other blocks; verified with a write→runtime-read round trip (`update_model_config(max_tokens=…) → LLM_MAX_TOKENS` reflects the persisted value), backend suites rerun green afterwards, and the user's original `max_tokens: 2000` restored in `assistant_config.json`.

## Stage 0 — Audit (done)

### Feature inventory (classification)

| Element | State |
|---|---|
| Chat request path (graph: route→retrieve→tutor→validate→persist), history, memory extraction, quiz routing | Working (verified live) |
| Usage tracking (provider tokens, latency, per-model) in SQLite `ai_usage` | Working (verified live) |
| Recycle Bin (soft delete/restore/permanent/empty), projects, attachments | Working |
| Profile (backend persisted), memory manager (list/add/delete/clear/toggle) | Working |
| RAG status / documents / query test / reindex endpoints | Working (verified live) |
| Privacy: storage stats, clean orphan uploads, full-data export, clear history | Working |
| Diagnostics endpoint + section | Working |
| Appearance prefs: theme (dark/light/system/oled/midnight/forest), accent, font size, density, reduced motion | Working, persisted, applied pre-hydration (no flash) |
| Chat prefs: enter-to-send, auto-expand sources, smooth typing | Working |
| Models section: server test, temperature, max tokens, base URL save | Working (verified live) |
| Keyboard shortcuts (⌘K, ⌘⇧O, ⌘B, ⌘/, ⌘⌫) | Registered & matching docs |
| **Thinking/reasoning-effort selector in composer** | **Was missing → built (this effort)** |
| **Response length / per-message output-token budget reaching the model** | **Was missing → built (this effort)** |
| Model `contextWindow` in `/api/models` | **Was hardcoded 8192 → now real value from LM Studio (verified: 131072)** |

## Stage 1 — Model controls verified (external research)

- LM Studio `/v1/chat/completions` does **not** support `reasoning_effort` (bug-tracker issue #988).
- Correct per-request mechanism for `openai/gpt-oss-20b`: trained system-prompt instruction `Reasoning: low|medium|high` (OpenAI gpt-oss model card, arxiv 2508.10925).
- Budget parameter supported by LM Studio chat completions: `max_tokens` (finite integer; includes gpt-oss reasoning tokens).

## Stage 2 — Output limits + thinking level (DONE)

Backend:
- `strud/backend/models/schemas.py`: `ChatRequestBody.thinkingLevel` + `ChatRequestBody.maxTokens` (validated 1–32768); `ModelActiveUpdateBody.maxTokens` ceiling raised to 32768.
- `strud/backend/tutoring_graph.py`: `tutor_node` applies a per-message budget via `model.bind(max_tokens=…)` (validated against the configured ceiling `LLM_MAX_OUTPUT_LIMIT`) and prepends `Reasoning: low|medium|high` (validated set) as the first system-prompt line — the model's own native effort mechanism. Model ID never changes; usage recording unchanged; per-turn state reset added so the checkpoint never carries stale values.
- `config.py`: `LLM_MAX_OUTPUT_LIMIT` (assistant_config `model.max_output_tokens_limit`, default 32768), `VALID_THINKING_LEVELS`; `update_model_config` ceiling raised.
- `strud/backend/api/main.py`: forwards `thinkingLevel`/`maxTokens` into the graph; `/api/models` now reports the real context window (LM Studio `/api/v0/models`), `maxOutputTokens`, and `reasoningEffortSupport` (null/"unknown" when unavailable — never a fabricated number).

Frontend:
- New `components/composer/thinking-selector.tsx`: compact anchored popover (opens upward/downward by space, viewport-clamped, outside-click/Escape close, arrow-key cycling, visible focus, animation, touch-friendly).
- `chat-composer.tsx`: selector sits in the composer bar.
- `lib/preferences.ts`: `thinkingLevel`, `responseLength` presets (Short=1024 / Balanced=2000 / Long=4096 / Maximum=8192), `advancedOutputTokens` with sanitization (256–32768), `resolveOutputTokens()`; all persisted and validated on read.
- `hooks/use-chats.tsx`: every send now includes `thinkingLevel` + resolved `maxTokens`.
- `chat-preferences-section.tsx`: response-length preset cards, advanced numeric budget with validation + reset, thinking-level default picker.
- `models-section.tsx`: token slider/presets scale to the backend-reported ceiling; honest "unknown" context window message; extra presets up to 16384.

Verified live (LM Studio gpt-oss-20b): POST /api/chat with `thinkingLevel:high, maxTokens:10000` → HTTP 200 in 53s, grounded answer with real page citations (Biology Resource Book pages 8, 60–66), provider-reported usage recorded (in 1098 / out 643). Model identity unchanged.

## Stage 3 — Readability & appearance polish (DONE)

- `styles/globals.css`: glass blur reduced (12→8px, 16→10px), translucent surfaces thickened (0.86→0.92 / 0.94→0.96 alpha), light-theme muted text darkened for contrast (64748b → 5b6472), secondary text bumped; assistant markdown capped at 70ch for comfortable reading.
- Existing theme/accent/density/font-size controls all verified as real DOM-applied, persistence-safe settings.

## Stage 4 — Settings audit fixes (DONE)

- Fixed two pre-existing test failures in `strud/backend/test_projects_profile.py` (tests asserted the old minimal profile contract; updated to the AI Control Center contract — intent preserved, behavior unchanged).
- Removed dead state/unused icons in `models-section.tsx`, `appearance-section.tsx`.

## Stage 5 — Analytics verification (DONE, no changes needed)

- Calendar: backend generates every day of the target year with `tracked` vs `unavailable` (pre-inception) distinction, correct weekday math & leap years; frontend renders 12 month grids with day inspectors, year navigation, JSON export. Covered by `tests/test_ai_control_center.py` (12/12 OK).

## Test results

- `pytest strud/backend -q` → **19 passed**
- `python -m unittest tests.test_ai_control_center` → **OK (12 tests)**
- `python tests/test_memory_and_quiz.py` → **34 passed, 0 failed**
- `strud/frontend` `npx tsc --noEmit` → **clean**
- `npx eslint components/ hooks/ lib/` → **0 errors** (8 pre-existing warnings: `<img>` advisory, etc.)
- `node tests/markdown-rendering.mjs` → **passed**
- `npm run build` → **passes** (needed stale `.next` removal; the failure reproduces on clean HEAD with a stale `.next`, i.e., pre-existing environment issue, not this effort's code)
- Live end-to-end chat + analytics used a real LM Studio session (details above).

Suites NOT run (require the built index + timing): `tests/test_hybrid_retrieval.py`, `tests/benchmark_*.py`, `eval_*.py` — pipeline behavior unchanged by this effort, but rerun before shipping retrieval changes.

## Known limitations (honest)

1. **Restart the backend to pick up changes** — an older uvicorn instance is still listening on port 8000 (PID 82771); the old one runs the pre-change code (contextWindow 8192, no per-message controls). Kill/restart it to use everything. The port-3000 dev server picked up frontend changes via Turbopack hot reload (verified serving the new UI).
2. **Streaming**: LM Studio supports it, but the pipeline returns complete answers; web UI remains non-streaming (as before, honestly documented in README).
3. **Document add/remove/re-index-with-new-files** in Knowledge Base remains unsupported (single primary textbook by design); status/test-query/reindex are real and working.
4. A per-request output budget above the preset "Maximum" is numeric-validated (up to 32768) and no artificial clamp is applied beyond the configured ceiling; if the model's context window is smaller, LM Studio enforces it — the Models page now shows the real window so oversized budgets are detectable in the UI.
5. Thinking effort uses the gpt-oss prompt mechanism (verified supported for the configured model). If the owner swaps the model to one without effort levels, `/api/models` reports `reasoningEffortSupport:false`; the selector still persists but the honest banner should show it as informational — the backend only prepends the `Reasoning:` line (harmless instruction for non-reasoning models).

## Authenticated cloud completion — October 16, 2026

### Completed in code

- Added Supabase Google OAuth session restoration, sign-in, sign-out, profile metadata hydration, and a sign-in gate that retains the unsent composer draft.
- Added per-account chat/project/profile persistence clients and a consent-based local-chat import path. Cloud rows are queried only through the logged-in Supabase client and are additionally protected by RLS.
- Added real provider configuration UI for GPT-OSS local mode, Qwen-compatible endpoints, Gemini OpenAI-compatible endpoints, and custom OpenAI-compatible endpoints. Connection tests issue a real small completion. Non-local providers are now actually used for chat rather than silently falling back to GPT-OSS; GPT-OSS continues through the existing backend Biology RAG path.
- Provider API keys remain browser-local, per authenticated user, masked in the UI, excluded from Supabase and backend logs, and sent only to the configured provider. Non-secret provider settings are persisted in `provider_configs` and restored on later sessions.
- Added strict backend bearer-token verification: signature, expiry, issuer, audience, and subject are required. JWKS verification supports Supabase asymmetric signing algorithms; legacy HS256 requires the configured trusted secret. The verified subject overwrites every supplied `user_id`/`userId`.
- Registered the previously incomplete auth middleware and protected attachment reads by verified ownership.
- Added `supabase/migrations/202610160001_authenticated_provider_config.sql`, an additive migration for provider configuration plus missing cloud message/profile columns. It enables RLS and applies owner-only policies; it has **not** been applied from this repository.

### Verification performed

- `./.venv/bin/python -m pytest strud/backend -q` — **25 passed** (includes JWT claim and forged-user-id authorization coverage).
- `./.venv/bin/python -m unittest tests.test_ai_control_center` — **12 passed**.
- `./.venv/bin/python tests/test_memory_and_quiz.py` — **34 passed, 0 failed**.
- `strud/frontend`: `npx tsc --noEmit` — passed; `npm run lint` — passed with six existing `<img>`/unused-symbol warnings; `npm run build` — passed.

### Manual production actions still required

1. In Supabase SQL Editor (or the linked Supabase CLI), review and apply `supabase/migrations/202610160001_authenticated_provider_config.sql`. Do not use a destructive reset.
2. Configure Google OAuth credentials in Supabase Auth, enable Google, and add `https://strud-ai.vercel.app` plus any preview domains to the redirect allow-list. The Google callback is `https://frdfpvulvlubaysykyxn.supabase.co/auth/v1/callback`.
3. Set the deployed backend `SUPABASE_URL=https://frdfpvulvlubaysykyxn.supabase.co`; use the project JWT secret only for legacy HS256 projects, otherwise the backend verifies the public JWKS. Set `STRUD_ALLOWED_ORIGINS=https://strud-ai.vercel.app` and deploy the backend.
4. Set `NEXT_PUBLIC_BACKEND_URL` in Vercel to the HTTPS backend URL, then redeploy. Local GPT-OSS cannot be reached by an HTTPS site over `http://localhost`; use it with local Strud or use a cloud provider.
