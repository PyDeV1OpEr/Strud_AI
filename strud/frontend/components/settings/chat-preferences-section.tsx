"use client";

import { useState } from "react";
import { CornerDownLeft, BookOpen, Zap } from "lucide-react";
import { getStoredChatPrefs, saveChatPrefs } from "@/lib/preferences";
import type { ChatPreferences } from "@/types";

interface ChatPreferencesSectionProps {
  showToast: (msg: string) => void;
}

export function ChatPreferencesSection({ showToast }: ChatPreferencesSectionProps) {
  const [prefs, setPrefs] = useState<ChatPreferences>(getStoredChatPrefs);

  const toggle = (key: keyof ChatPreferences) => {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    saveChatPrefs(updated);
    showToast("Chat preference saved");
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)]">Chat Preferences</h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Configure composer keyboard behavior, source citation display, and response presentation.
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
    </div>
  );
}
