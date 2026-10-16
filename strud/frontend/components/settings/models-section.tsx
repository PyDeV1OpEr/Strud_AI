"use client";

import { useEffect, useState } from "react";
import {
  Cpu,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Zap,
  Sliders,
  Eye,
  Server,
  Save,
  RotateCcw,
} from "lucide-react";
import { fetchModelsInfo, testModelConnection, updateActiveModel } from "@/lib/api";
import type { ModelsPayload } from "@/types";

interface ModelsSectionProps {
  showToast: (msg: string) => void;
}

export function ModelsSection({ showToast }: ModelsSectionProps) {
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state
  const [selectedModel, setSelectedModel] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [isCustom, setIsCustom] = useState(false);
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(2048);
  // Largest budget the backend configuration permits; the slider bound is
  // resolved from /api/models (maxOutputTokens), never hardcoded small.
  const [maxTokenCeiling, setMaxTokenCeiling] = useState(32768);
  const [baseUrl, setBaseUrl] = useState("http://localhost:1234/v1");

  // Connection test state
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    status: string;
    latencyMs: number | null;
    message: string;
  } | null>(null);

  const applyModelData = (res: ModelsPayload) => {
    setData(res);
    const activeId = res.activeModel.id;
    if (res.availableModels.includes(activeId)) {
      setSelectedModel(activeId);
      setIsCustom(false);
    } else {
      setSelectedModel("custom");
      setCustomModel(activeId);
      setIsCustom(true);
    }
    setTemperature(res.activeModel.temperature ?? 0.2);
    setMaxTokens(res.activeModel.maxTokens ?? 2048);
    setMaxTokenCeiling(Math.max(res.activeModel.maxOutputTokens ?? res.activeModel.maxTokens ?? 32768, (res.activeModel.maxTokens ?? 2048)));
    setBaseUrl(res.activeModel.baseUrl || "http://localhost:1234/v1");
  };

  useEffect(() => {
    let cancelled = false;
    void fetchModelsInfo()
      .then((res) => {
        if (!cancelled) {
          applyModelData(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          showToast("Could not load model configuration");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const handleTestConnection = async () => {
    const targetModel = isCustom ? customModel : selectedModel;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testModelConnection(targetModel, baseUrl);
      setTestResult(res);
      if (res.ok) {
        showToast(`Connected! Latency: ${res.latencyMs}ms`);
      } else {
        showToast(res.message);
      }
    } catch (err: unknown) {
      setTestResult({
        ok: false,
        status: "error",
        latencyMs: null,
        message: err instanceof Error ? err.message : "Connection failed",
      });
      showToast("Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    const targetModel = isCustom ? customModel : selectedModel;
    if (!targetModel.trim()) {
      showToast("Please specify a model ID");
      return;
    }
    setSaving(true);
    try {
      await updateActiveModel(targetModel, temperature, maxTokens, baseUrl);
      showToast("Model configuration saved successfully");
      const refreshed = await fetchModelsInfo();
      applyModelData(refreshed);
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : "Failed to update model settings");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setTemperature(0.2);
    setMaxTokens(2048);
    setBaseUrl("http://localhost:1234/v1");
    if (data?.availableModels && data.availableModels.length > 0) {
      setSelectedModel(data.availableModels[0]);
      setIsCustom(false);
    }
    showToast("Values reset to defaults (click Save to apply)");
  };

  // Money-like presets for the token budget, capped by the ceiling.
  const tokenPresets = [1024, 2048, 4096, 8192, 16384].filter(
    (value) => value <= maxTokenCeiling,
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-[var(--color-ink-muted)]">
        <RefreshCw size={24} className="animate-spin text-emerald-400" />
        <p className="mt-3 text-xs">Inspecting model services...</p>
      </div>
    );
  }

  const isOnline = data?.serverConnected && data?.activeModel?.status === "online";
  const isLoaded = data?.activeModel?.status !== "model_not_loaded";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
          <Cpu size={20} className="text-emerald-400" />
          AI Model Control Center
        </h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Manage local LLM inference engines, adjust sampling hyperparameters, and test latency.
        </p>
      </div>

      {/* Live Provider & Server Status Card */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.05] border border-white/10">
              <Server size={18} className="text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--color-ink)]">
                  {data?.activeModel?.provider || "LM Studio (Local)"}
                </span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    isOnline
                      ? "bg-emerald-400/15 text-emerald-300 border border-emerald-400/30"
                      : isLoaded && data?.serverConnected
                      ? "bg-amber-400/15 text-amber-300 border border-amber-400/30"
                      : "bg-red-400/15 text-red-300 border border-red-400/30"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      isOnline ? "bg-emerald-400 animate-pulse" : isLoaded && data?.serverConnected ? "bg-amber-400" : "bg-red-400"
                    }`}
                  />
                  {isOnline
                    ? "Online & Ready"
                    : isLoaded && data?.serverConnected
                    ? "Model Not Loaded"
                    : "Server Offline"}
                </span>
              </div>
              <p className="text-xs text-[var(--color-ink-muted)] mt-0.5">
                Target endpoint: <code className="text-emerald-300/80">{baseUrl}</code>
                {data?.activeModel?.reasoningEffortSupport && (
                  <span className="ml-2">· reasoning effort supported</span>
                )}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-3.5 py-2 text-xs font-medium text-[var(--color-ink)] hover:bg-white/[0.09] transition-colors disabled:opacity-50"
          >
            {testing ? (
              <RefreshCw size={14} className="animate-spin text-emerald-400" />
            ) : (
              <Zap size={14} className="text-amber-400" />
            )}
            {testing ? "Testing Latency..." : "Test Connection"}
          </button>
        </div>

        {/* Live Test Feedback Banner */}
        {testResult && (
          <div
            className={`mt-4 rounded-xl border p-3.5 text-xs transition-all ${
              testResult.ok
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
                : "border-red-400/30 bg-red-400/10 text-red-200"
            }`}
          >
            <div className="flex items-start gap-2.5">
              {testResult.ok ? (
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {testResult.ok ? "Connection Successful" : "Connection Issue Detected"}
                  {testResult.latencyMs !== null && (
                    <span className="ml-2 font-mono text-[11px] opacity-80">
                      ({testResult.latencyMs} ms)
                    </span>
                  )}
                </p>
                <p className="mt-1 opacity-90 leading-relaxed">{testResult.message}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Active Model Selection */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Cpu size={14} className="text-emerald-400" />
          Primary Reasoning & Tutoring Model
        </h4>
        <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
          Select the active model loaded in LM Studio or provide a custom GGUF identifier.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {data?.availableModels?.map((modelId) => {
            const isSelected = !isCustom && selectedModel === modelId;
            return (
              <button
                key={modelId}
                type="button"
                onClick={() => {
                  setSelectedModel(modelId);
                  setIsCustom(false);
                }}
                className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                  isSelected
                    ? "border-emerald-400/50 bg-emerald-400/10 shadow-[0_0_12px_rgba(52,211,153,0.12)]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] hover:bg-white/[0.04]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-[var(--color-ink)] truncate">{modelId}</p>
                  <p className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">
                    Detected in LM Studio
                  </p>
                </div>
                {isSelected && <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />}
              </button>
            );
          })}

          {/* Custom Model Option */}
          <button
            type="button"
            onClick={() => setIsCustom(true)}
            className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-all ${
              isCustom
                ? "border-emerald-400/50 bg-emerald-400/10 shadow-[0_0_12px_rgba(52,211,153,0.12)]"
                : "border-[var(--color-hairline-soft)] bg-white/[0.02] hover:bg-white/[0.04]"
            }`}
          >
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-[var(--color-ink)]">Custom Model Identifier</p>
              <p className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">
                Specify another local identifier
              </p>
            </div>
            {isCustom && <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />}
          </button>
        </div>

        {isCustom && (
          <div className="mt-3.5">
            <label className="text-xs text-[var(--color-ink-muted)] block mb-1">
              Custom Model ID
            </label>
            <input
              type="text"
              value={customModel}
              onChange={(e) => setCustomModel(e.target.value)}
              placeholder="e.g. qwen2.5-7b-instruct"
              className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2 text-xs text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] focus:border-emerald-400/50 focus:outline-none"
            />
          </div>
        )}
      </div>

      {/* Sampling Parameters */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Sliders size={14} className="text-cyan-400" />
          Sampling Parameters & Hyperparameters
        </h4>

        <div className="mt-5 flex flex-col gap-5">
          {/* Temperature Slider */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-medium text-[var(--color-ink)]">Temperature</span>
                <span className="ml-2 font-mono text-xs text-emerald-400 font-semibold">
                  {temperature.toFixed(2)}
                </span>
              </div>
              <span className="text-[11px] text-[var(--color-ink-muted)]">
                {temperature <= 0.3
                  ? "Precise & Factual (Recommended for Biology)"
                  : temperature <= 0.7
                  ? "Balanced Dialogue"
                  : "Creative & Varied"}
              </span>
            </div>
            <input
              type="range"
              min="0.0"
              max="1.5"
              step="0.05"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-white/10 accent-emerald-400"
            />
            <div className="flex justify-between text-[10px] text-[var(--color-ink-muted)] px-0.5">
              <span>0.0 (Deterministic)</span>
              <span>0.7 (Standard)</span>
              <span>1.5 (High Entropy)</span>
            </div>
          </div>

          {/* Max Output Tokens */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-medium text-[var(--color-ink)]">Default Max Output Tokens</span>
                <span className="ml-2 font-mono text-xs text-cyan-400 font-semibold">
                  {maxTokens.toLocaleString()} tokens
                </span>
              </div>
              <div className="flex gap-1.5">
                {tokenPresets.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setMaxTokens(preset)}
                    className={`rounded-md px-2 py-0.5 text-[10px] border transition-colors ${
                      maxTokens === preset
                        ? "border-cyan-400/50 bg-cyan-400/15 text-cyan-300"
                        : "border-white/10 bg-white/[0.03] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                    }`}
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>
            <input
              type="range"
              min="256"
              max={String(maxTokenCeiling)}
              step="256"
              value={maxTokens}
              onChange={(e) => setMaxTokens(parseInt(e.target.value, 10))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-white/10 accent-cyan-400"
            />
            <div className="flex justify-between text-[10px] text-[var(--color-ink-muted)] px-0.5">
              <span>256</span>
              <span>Standard default: 2,048</span>
              <span>{maxTokenCeiling.toLocaleString()}</span>
            </div>
            {typeof data?.activeModel?.contextWindow === "number" && data.activeModel.contextWindow > 0 ? (
              <p className="text-[10px] text-[var(--color-ink-muted)]">
                Model context window: <span className="text-[var(--color-ink-secondary)]">{data.activeModel.contextWindow.toLocaleString()} tokens</span> — output + prompt (system, history, textbook context, question) must fit inside it.
              </p>
            ) : (
              <p className="text-[10px] text-[var(--color-ink-muted)]">
                Model context window: <span className="text-amber-300/80">unknown</span> (set your context length in LM Studio; very large output budgets need a matching context window).
              </p>
            )}
          </div>

          {/* Endpoint Base URL */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--color-ink)]">
              LM Studio API Base URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2 font-mono text-xs text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] focus:border-emerald-400/50 focus:outline-none"
            />
            <p className="text-[11px] text-[var(--color-ink-muted)]">
              Default local endpoint is <code className="text-emerald-300">http://localhost:1234/v1</code>.
            </p>
          </div>
        </div>
      </div>

      {/* Vision Engine Overview */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Eye size={14} className="text-violet-400" />
          Biological Vision & Diagram Engine
        </h4>
        <div className="mt-3 flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
          <div>
            <p className="text-xs font-semibold text-[var(--color-ink)]">
              {data?.visionModel?.name || "Qwen3 VL 8B"}
            </p>
            <p className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">
              Analyzes biology diagrams, microscopy slides, floral formulas, and anatomical figures.
            </p>
          </div>
          <span className="rounded-full bg-violet-400/15 border border-violet-400/30 px-2.5 py-0.5 text-[10px] font-medium text-violet-300">
            Multimodal Active
          </span>
        </div>
      </div>

      {/* Bottom Action Bar */}
      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={handleReset}
          className="inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-medium text-[var(--color-ink-muted)] hover:text-[var(--color-ink)] transition-colors"
        >
          <RotateCcw size={14} />
          Reset Defaults
        </button>

        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-400/90 hover:bg-emerald-300 px-4 py-2 text-xs font-semibold text-emerald-950 transition-colors shadow-sm disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <Save size={14} />
          )}
          {saving ? "Saving..." : "Save Model Configuration"}
        </button>
      </div>
    </div>
  );
}
