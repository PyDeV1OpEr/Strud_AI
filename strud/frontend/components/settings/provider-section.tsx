"use client";

// AI Provider section — per-user Module Configuration.
//
// Providers:
//   • GPT-OSS (local) — an OpenAI-compatible local runtime (LM Studio).
//     No API key. Works on localhost deployments; a public HTTPS site
//     cannot reach http://localhost:1234 (browser mixed-content/CORS),
//     and the panel explains that instead of pretending.
//   • Qwen — OpenAI-compatible endpoint + key (DashScope compatible-mode
//     or a self-hosted vLLM/Ollama endpoint).
//   • Gemini — Google's documented OpenAI-compatible endpoint + key.
//   • Custom — any OpenAI-compatible chat-completions endpoint + key.
//
// Keys live ONLY in this browser for the signed-in account, are masked
// in the UI, and are sent straight to the provider — never to Strud's
// servers, never to Supabase.
//
// "Test Connection" makes a REAL request; success is never faked.

import { useEffect, useState } from "react";
import {
  Check,
  Eye,
  EyeOff,
  Key,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";

import type { ProviderId } from "@/types";
import {
  getProviderKey,
  loadProviderConfig,
  PROVIDER_PRESETS,
  saveProviderConfig,
  type ProviderConfig,
} from "@/lib/provider-config";
import { authState } from "@/lib/auth-state";
import { testProviderConnection } from "@/lib/api/providers";

const PROVIDER_ORDER: ProviderId[] = ["gptoss", "qwen", "gemini", "custom"];

type TestState = { status: "idle" | "running" | "ok" | "fail"; message?: string };

export function ProviderSection({ showToast }: { showToast: (msg: string) => void }) {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [replaceKey, setReplaceKey] = useState(true);
  const [masked, setMasked] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>({ status: "idle" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const userId = authState.userId;
    setSignedIn(Boolean(userId));
    if (!userId) {
      // Signed out: anonymous browser identity still scopes local config.
      void loadProviderConfig(getBrowserId()).then((loaded) => {
        if (!cancelled) {
          setConfig(loaded);
          setMasked(getProviderKey(getBrowserId()));
          setLoading(false);
        }
      });
    } else {
      void loadProviderConfig(userId).then((loaded) => {
        if (!cancelled) {
          setConfig(loaded);
          setMasked(getProviderKey(userId));
          setLoading(false);
        }
      });
    }
    return () => {
      cancelled = true;
    };
  }, []);

  function getBrowserId(): string {
    // Matches lib/user-id's anonymous id without importing the hook tree.
    try {
      return window.localStorage.getItem("strud.user-id.v1") ?? "local";
    } catch {
      return "local";
    }
  }

  if (loading || !config) {
    return (
      <div className="flex items-center gap-2 py-10 text-[13px] text-[var(--color-ink-muted)]">
        <Loader2 size={15} className="animate-spin" /> Loading provider settings…
      </div>
    );
  }

  const preset = PROVIDER_PRESETS[config.provider];
  const activeUserId = authState.userId ?? getBrowserId();

  const update = (patch: Partial<ProviderConfig>) => {
    setConfig((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      // When the provider changes, apply that preset's defaults.
      if (patch.provider && patch.provider !== current.provider) {
        const nextPreset = PROVIDER_PRESETS[patch.provider];
        next.modelId = nextPreset.defaultModel;
        next.baseUrl = nextPreset.defaultBaseUrl;
      }
      return next;
    });
    setTest({ status: "idle" });
  };

  const validateBeforeSave = (config: ProviderConfig): string | null => {
    const preset = PROVIDER_PRESETS[config.provider];
    if (preset.needsApiKey && !getProviderKey(activeUserId) && !(replaceKey && keyInput.trim())) {
      return `${preset.label} requires an API key.`;
    }
    if (preset.needsBaseUrl && !config.baseUrl.trim()) {
      return "API base URL is required for this provider.";
    }
    if (!config.modelId.trim()) {
      return "Model ID is required.";
    }
    return null;
  };

  const handleTest = async () => {
    const problem = validateBeforeSave(config);
    if (problem) return setTest({ status: "fail", message: problem });
    setTest({ status: "running" });
    // Use the currently typed key if a replace is in progress, else the saved one.
    const effectiveKey =
      replaceKey && keyInput.trim() ? keyInput.trim() : getProviderKey(activeUserId);
    const result = await testProviderConnection(config, effectiveKey);
    if (result.ok) setTest({ status: "ok", message: result.sample });
    else setTest({ status: "fail", message: result.error });
  };

  const handleSave = async () => {
    const problem = validateBeforeSave(config);
    if (problem) return showToast(problem);
    setSaving(true);
    try {
      const savedConfig = await saveProviderConfig(
        activeUserId,
        config,
        replaceKey ? keyInput.trim() || null : null,
        replaceKey,
      );
      setConfig(savedConfig);
      setMasked(getProviderKey(activeUserId));
      setKeyInput("");
      setReplaceKey(true);
      setTest({ status: "idle" });
      showToast("Provider saved");
    } catch {
      showToast("Couldn't save the provider configuration. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    void loadProviderConfig(activeUserId).then(setConfig);
    setKeyInput("");
    setTest({ status: "idle" });
  };

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[13px] leading-relaxed text-[var(--color-ink-muted)]">
        Choose which AI provider answers your questions. Your configuration and
        key are saved for your account — the key exists only in this browser and
        is sent directly to the provider.
      </p>

      {/* ---- provider selector ---- */}
      <div>
        <span className="mb-2 block text-[13px] font-medium text-[var(--color-ink)]">Provider</span>
        <div className="grid grid-cols-2 gap-2">
          {PROVIDER_ORDER.map((id) => {
            const preset = PROVIDER_PRESETS[id];
            const active = config.provider === id;
            return (
              <button
                key={id}
                onClick={() => update({ provider: id })}
                aria-pressed={active}
                className={`rounded-xl border px-3.5 py-3 text-left transition-colors ${
                  active
                    ? "border-emerald-400/50 bg-emerald-400/[0.08]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.03] hover:bg-white/[0.05]"
                }`}
              >
                <span className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-ink)]">
                  {preset.label}
                  {active && <Check size={13} className="text-emerald-400" />}
                </span>
                <span className="mt-0.5 block text-[11px] leading-snug text-[var(--color-ink-muted)]">
                  {preset.blurb}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ---- API key (only when required) ---- */}
      {preset.needsApiKey && (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-[var(--color-ink)]">API key</span>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type={masked && !replaceKey ? "password" : showKey ? "text" : "password"}
                  value={replaceKey ? keyInput : ""}
                  onChange={(event) => setKeyInput(event.target.value)}
                  placeholder={masked ? `Saved key ${masked} — type a new key to replace` : "Paste your provider API key"}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 pr-10 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((value) => !value)}
                  aria-label={showKey ? "Hide key" : "Show key"}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                >
                  {showKey ? <EyeOff size={14} strokeWidth={1.75} /> : <Eye size={14} strokeWidth={1.75} />}
                </button>
              </div>
            </div>
            {masked && (
              <label className="mt-1 flex w-fit items-center gap-2 text-[11px] text-[var(--color-ink-muted)]">
                <input
                  type="checkbox"
                  checked={replaceKey}
                  onChange={(event) => setReplaceKey(event.target.checked)}
                  className="accent-emerald-400"
                />
                Replace saved key {masked}
              </label>
            )}
            <span className="text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
              <Key size={11} className="mr-1 inline" aria-hidden="true" />
              Stored only in this browser{signedIn ? " for your account" : ""}. It
              never reaches Strud&apos;s servers — requests go directly to the
              provider. Usage is billed to your own account.
            </span>
          </label>
        </div>
      )}

      {!preset.needsApiKey && (
        <p className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2.5 text-[12px] leading-relaxed text-[var(--color-ink-muted)]">
          No API key needed — GPT-OSS runs on your machine. Start the local
          runtime (LM Studio) with <code className="text-[11px]">gpt-oss-20b</code> loaded
          and its server on <code className="text-[11px]">{preset.defaultBaseUrl}</code>.
        </p>
      )}

      {/* ---- base URL (when applicable) ---- */}
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-medium text-[var(--color-ink)]">
          API base URL {config.provider === "gptoss" ? "(local runtime)" : ""}
        </span>
        <input
          value={config.baseUrl}
          onChange={(event) => update({ baseUrl: event.target.value })}
          placeholder={preset.defaultBaseUrl || "https://…/v1"}
          spellCheck={false}
          className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
        />
        {config.provider === "gptoss" && typeof window !== "undefined" && window.location.protocol === "https:" && (
          <span className="text-[11px] leading-relaxed text-amber-200/90">
            This page is HTTPS, so browsers block calls to http://localhost
            (mixed content). Use GPT-OSS while Strud runs locally, or pick a
            cloud provider for the deployed site.
          </span>
        )}
      </label>

      {/* ---- model ---- */}
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-medium text-[var(--color-ink)]">Model ID</span>
        <input
          value={config.modelId}
          onChange={(event) => update({ modelId: event.target.value })}
          placeholder={preset.defaultModel || "e.g. gemini-2.5-flash"}
          spellCheck={false}
          className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
        />
      </label>

      {/* ---- advanced (temperature + budget) ---- */}
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--color-ink)]">Temperature</span>
          <input
            type="number"
            min={0}
            max={2}
            step={0.05}
            value={config.temperature}
            onChange={(event) => update({ temperature: Number(event.target.value) })}
            className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--color-ink)]">Max output tokens</span>
          <input
            type="number"
            min={256}
            max={32768}
            step={256}
            value={config.maxTokens}
            onChange={(event) => update({ maxTokens: Number(event.target.value) })}
            className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
          />
        </label>
      </div>

      {/* ---- test connection ---- */}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => void handleTest()}
          disabled={test.status === "running"}
          className="flex w-fit items-center gap-2 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.05] px-4 py-2 text-sm text-[var(--color-ink)] transition-colors hover:bg-white/[0.08] disabled:opacity-50"
        >
          {test.status === "running" ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} strokeWidth={1.75} />
          )}
          {test.status === "running" ? "Testing…" : "Test Connection"}
        </button>
        {test.status === "ok" && (
          <p className="flex items-center gap-1.5 text-[12px] text-emerald-300" role="status">
            <Check size={13} /> Connected — provider responded: “{test.message}”.
          </p>
        )}
        {test.status === "fail" && (
          <p className="flex items-start gap-1.5 rounded-lg border border-red-400/25 bg-red-500/[0.08] px-2.5 py-1.5 text-[12px] leading-relaxed text-red-200" role="alert">
            <X size={13} className="mt-0.5 shrink-0" /> {test.message}
          </p>
        )}
        {test.status !== "ok" && (
          <p className="text-[11px] text-[var(--color-ink-muted)]">
            Connection is not yet verified. Messages use the saved provider only
            after a successful test.
          </p>
        )}
      </div>

      {/* ---- actions ---- */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="rounded-xl bg-emerald-400/90 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-300 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save Configuration"}
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="rounded-xl px-4 py-2 text-sm text-[var(--color-ink-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
        >
          Reset
        </button>
      </div>

      {/* ---- grounded vs direct note ---- */}
      <p className="text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
        When the FastAPI backend is reachable, messages use its Biology
        retrieval pipeline (page-cited grounding). Otherwise answers come
        directly from the provider above as general knowledge — the UI always
        shows whether sources are present.
      </p>
    </div>
  );
}
