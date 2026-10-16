"use client";

import { useState } from "react";
import {
  AlignLeft,
  BookOpen,
  Brain,
  CornerDownLeft,
  Gauge,
  RotateCcw,
  Zap,
} from "lucide-react";
import {
  DEFAULT_CHAT_PREFS,
  OUTPUT_TOKENS_MAX,
  OUTPUT_TOKENS_MIN,
  RESPONSE_LENGTH_PRESETS,
  getStoredChatPrefs,
  resolveOutputTokens,
  saveChatPrefs,
  sanitizeAdvancedOutputTokens,
} from "@/lib/preferences";
import type { ChatPreferences, ResponseLengthPreset } from "@/types";

interface ChatPreferencesSectionProps {
  showToast: (msg: string) => void;
}

const PRESET_ORDER: ResponseLengthPreset[] = ["short", "balanced", "long", "maximum"];

export function ChatPreferencesSection({ showToast }: ChatPreferencesSectionProps) {
  const [prefs, setPrefs] = useState<ChatPreferences>(getStoredChatPrefs);
  // Draft for the advanced token input — only applied when valid.
  const [advancedDraft, setAdvancedDraft] = useState<string>(
    prefs.advancedOutputTokens === null ? "" : String(prefs.advancedOutputTokens),
  );
  const [advancedError, setAdvancedError] = useState<string | null>(null);

  const commit = (updated: ChatPreferences, message: string) => {
    setPrefs(updated);
    saveChatPrefs(updated);
    showToast(message);
  };

  const toggle = (key: keyof ChatPreferences) => {
    const updated = { ...prefs, [key]: !prefs[key] } as ChatPreferences;
    commit(updated, "Chat preference saved");
  };

  const applyPresetLength = (preset: ResponseLengthPreset) => {
    const updated: ChatPreferences = {
      ...prefs,
      responseLength: preset,
      // Selecting a preset clears any advanced override so the label is
      // always true about what will be sent.
      advancedOutputTokens: null,
    };
    setAdvancedDraft("");
    setAdvancedError(null);
    commit(updated, `Response length set to ${RESPONSE_LENGTH_PRESETS[preset].label} (${RESPONSE_LENGTH_PRESETS[preset].tokens.toLocaleString()} tokens)`);
  };

  const applyAdvanced = () => {
    const value = sanitizeAdvancedOutputTokens(advancedDraft);
    if (value === null) {
      setAdvancedError(
        `Enter a whole number between ${OUTPUT_TOKENS_MIN.toLocaleString()} and ${OUTPUT_TOKENS_MAX.toLocaleString()}.`,
      );
      return;
    }
    setAdvancedError(null);
    const longPreset = PRESET_ORDER[PRESET_ORDER.length - 1];
    const isBeyondPreset = value > RESPONSE_LENGTH_PRESETS[longPreset].tokens;
    commit(
      { ...prefs, advancedOutputTokens: value },
      isBeyondPreset
        ? `Custom budget: ${value.toLocaleString()} output tokens per message`
        : `Advanced budget set: ${value.toLocaleString()} tokens`,
    );
  };

  const resetGenerationPrefs = () => {
    setAdvancedDraft("");
    setAdvancedError(null);
    const updated: ChatPreferences = {
      ...prefs,
      thinkingLevel: DEFAULT_CHAT_PREFS.thinkingLevel,
      responseLength: DEFAULT_CHAT_PREFS.responseLength,
      advancedOutputTokens: null,
    };
    commit(updated, "Response settings reset to recommended defaults");
  };

  const effectiveTokens = resolveOutputTokens(prefs);
  const longMaximum = RESPONSE_LENGTH_PRESETS.maximum.tokens;
  const advancedBeyond = prefs.advancedOutputTokens !== null && prefs.advancedOutputTokens > longMaximum;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)]">Chat Preferences</h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Configure composer keyboard behavior, citations, response length, and reasoning effort.
        </p>
      </div>

      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-4">
        {/* Enter to Send Toggle */}
        <div className="flex items-center justify-between rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-white/[0.05] p-2 text-emerald-400">
              <CornerDownLeft size={18} />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-semibold text-[var(--color-ink)]">
                Press Enter to Send
              </span>
              <span className="text-[11px] text-[var(--color-ink-muted)] leading-relaxed">
                When enabled, pressing <kbd className="rounded bg-white/10 px-1 py-0.5 font-mono text-[10px]">Enter</kbd> sends your message immediately, and <kbd className="rounded bg-white/10 px-1 py-0.5 font-mono text-[10px]">Shift + Enter</kbd> inserts a newline. When disabled, pressing Enter creates a new paragraph.
              </span>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={prefs.enterToSend}
            onClick={() => toggle("enterToSend")}
            className={`relative ml-4 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              prefs.enterToSend ? "bg-emerald-500" : "bg-white/10"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                prefs.enterToSend ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Show Sources by Default */}
        <div className="flex items-center justify-between rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-white/[0.05] p-2 text-cyan-400">
              <BookOpen size={18} />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-semibold text-[var(--color-ink)]">
                Auto-Expand Biology Textbook Citations
              </span>
              <span className="text-[11px] text-[var(--color-ink-muted)] leading-relaxed">
                Display the Biology Resource Book source page badges immediately on responses rather than requiring a click to expand.
              </span>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={prefs.showSourcesDefault}
            onClick={() => toggle("showSourcesDefault")}
            className={`relative ml-4 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              prefs.showSourcesDefault ? "bg-cyan-500" : "bg-white/10"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                prefs.showSourcesDefault ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Smooth Typing Effect */}
        <div className="flex items-center justify-between rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-white/[0.05] p-2 text-amber-400">
              <Zap size={18} />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-semibold text-[var(--color-ink)]">
                Fluid Response Rendering
              </span>
              <span className="text-[11px] text-[var(--color-ink-muted)] leading-relaxed">
                Smooth visual streaming animation when assistant explanations complete, rendering content progressively.
              </span>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={prefs.smoothTyping}
            onClick={() => toggle("smoothTyping")}
            className={`relative ml-4 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              prefs.smoothTyping ? "bg-amber-500" : "bg-white/10"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                prefs.smoothTyping ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>

      {/* ---- Response length & output budget ---- */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
              <AlignLeft size={14} className="text-emerald-400" />
              Response Length
            </h4>
            <p className="mt-1 text-[11px] text-[var(--color-ink-muted)]">
              How much output the model may produce per answer. Applies to your next message — existing answers are not changed.
            </p>
          </div>
          <button
            type="button"
            onClick={resetGenerationPrefs}
            title="Reset response length and thinking level"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] font-medium text-[var(--color-ink-muted)] transition-colors hover:bg-white/[0.05] hover:text-[var(--color-ink)]"
          >
            <RotateCcw size={13} />
            Reset
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PRESET_ORDER.map((preset) => {
            const meta = RESPONSE_LENGTH_PRESETS[preset];
            const isSelected =
              prefs.responseLength === preset && prefs.advancedOutputTokens === null;
            return (
              <button
                key={preset}
                type="button"
                onClick={() => applyPresetLength(preset)}
                aria-pressed={isSelected}
                className={`flex flex-col items-start gap-0.5 rounded-xl border p-3 text-left transition-all ${
                  isSelected
                    ? "border-emerald-400/50 bg-emerald-400/10"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] hover:bg-white/[0.05]"
                }`}
              >
                <span className="text-xs font-semibold text-[var(--color-ink)]">{meta.label}</span>
                <span className="text-[10px] font-mono text-emerald-300/90">
                  {meta.tokens.toLocaleString()} tokens
                </span>
                <span className="text-[10px] leading-snug text-[var(--color-ink-muted)]">
                  {meta.description}
                </span>
              </button>
            );
          })}
        </div>

        {/* Advanced numeric budget */}
        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-3.5">
          <div className="flex items-center gap-1.5">
            <Gauge size={14} className="text-cyan-400" />
            <span className="text-xs font-medium text-[var(--color-ink)]">
              Advanced output-token budget
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[var(--color-ink-muted)] leading-relaxed">
            Override the preset with an exact budget (very large answers need one — verified against
            your model at send time). Leave empty to follow the selected preset.
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <input
              type="number"
              inputMode="numeric"
              min={OUTPUT_TOKENS_MIN}
              max={OUTPUT_TOKENS_MAX}
              step={256}
              value={advancedDraft}
              onChange={(event) => {
                setAdvancedDraft(event.target.value);
                setAdvancedError(null);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  applyAdvanced();
                }
              }}
              placeholder={`e.g. 12000 (preset is 2000)`}
              aria-label="Advanced output token budget"
              className="w-36 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3 py-2 font-mono text-xs text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] focus:border-emerald-400/50 focus:outline-none"
            />
            <button
              type="button"
              onClick={applyAdvanced}
              className="rounded-xl bg-emerald-400/90 px-3.5 py-2 text-xs font-semibold text-emerald-950 transition-colors hover:bg-emerald-300"
            >
              Apply
            </button>
          </div>
          {advancedError ? (
            <p className="mt-2 text-[11px] text-red-300" role="alert">
              {advancedError}
            </p>
          ) : (
            <p className="mt-2 text-[11px] text-[var(--color-ink-muted)]">
              {advancedBeyond
                ? `Custom: ${prefs.advancedOutputTokens?.toLocaleString()} tokens — requests beyond the preset Maximum are clipped to what the configured model accepts, and Strud tells you when that happens.`
                : `Effective budget right now: ${effectiveTokens.toLocaleString()} output tokens per message.`}
            </p>
          )}
        </div>
      </div>

      {/* ---- Thinking effort ---- */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Brain size={14} className="text-violet-400" />
          Thinking Level
        </h4>
        <p className="text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
          The daily selector lives in the chat composer (next to the attachment button) so you can
          change it per message. It maps to the configured model&apos;s built-in reasoning-effort
          control and never switches the model itself. Default level:
        </p>
        <div className="grid grid-cols-3 gap-2">
          {(["low", "medium", "high"] as const).map((level) => (
            <button
              key={level}
              type="button"
              onClick={() => {
                commit({ ...prefs, thinkingLevel: level }, `Default thinking level: ${level}`);
              }}
              aria-pressed={prefs.thinkingLevel === level}
              className={`rounded-xl border py-2 text-xs transition-colors ${
                prefs.thinkingLevel === level
                  ? "border-emerald-400/50 bg-emerald-400/10 font-semibold text-[var(--color-ink)]"
                  : "border-[var(--color-hairline-soft)] bg-white/[0.02] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              <span className="capitalize">{level}</span>
            </button>
          ))}
        </div>
        <p className="text-[10px] text-[var(--color-ink-muted)]">
          Changing it here changes the level pre-selected the next time the composer opens.
        </p>
      </div>
    </div>
  );
}
