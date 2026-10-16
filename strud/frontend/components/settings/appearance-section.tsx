"use client";

import { useState } from "react";
import { Check, Moon, Sparkles, Sliders } from "lucide-react";
import {
  getStoredAppearance,
  saveAppearance,
} from "@/lib/preferences";
import type {
  AccentOption,
  AppearancePreferences,
  DensityOption,
  FontSizeOption,
  ThemeOption,
} from "@/types";

interface AppearanceSectionProps {
  showToast: (msg: string) => void;
}

const THEMES: { id: ThemeOption; label: string; desc: string; previewBg: string }[] = [
  { id: "light", label: "Light", desc: "Clean light background for bright rooms", previewBg: "bg-[#f8fafc]" },
  { id: "system", label: "System", desc: "Follows your OS dark / light setting", previewBg: "bg-gradient-to-br from-[#f8fafc] to-[#0a0b0e]" },
  { id: "dark", label: "Dark Glass", desc: "Default dark glassmorphism", previewBg: "bg-[#070708]" },
  { id: "oled", label: "OLED Black", desc: "Pure pitch black background", previewBg: "bg-[#000000]" },
  { id: "midnight", label: "Midnight Blue", desc: "Deep navy night aesthetic", previewBg: "bg-[#060913]" },
  { id: "forest", label: "Deep Forest", desc: "Biological deep pine green", previewBg: "bg-[#040d08]" },
];

const ACCENTS: { id: AccentOption; label: string; colorClass: string; borderClass: string }[] = [
  { id: "emerald", label: "Emerald", colorClass: "bg-emerald-400", borderClass: "border-emerald-400" },
  { id: "cyan", label: "Cyan", colorClass: "bg-cyan-400", borderClass: "border-cyan-400" },
  { id: "violet", label: "Violet", colorClass: "bg-violet-400", borderClass: "border-violet-400" },
  { id: "amber", label: "Amber", colorClass: "bg-amber-400", borderClass: "border-amber-400" },
  { id: "rose", label: "Rose", colorClass: "bg-rose-400", borderClass: "border-rose-400" },
];

export function AppearanceSection({ showToast }: AppearanceSectionProps) {
  const [prefs, setPrefs] = useState<AppearancePreferences>(getStoredAppearance);

  const update = (partial: Partial<AppearancePreferences>) => {
    const updated = { ...prefs, ...partial };
    setPrefs(updated);
    saveAppearance(updated);
    showToast("Appearance preference applied");
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)]">Appearance</h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Customize STRUD&apos;s interface theme, accent highlights, font sizing, and motion.
        </p>
      </div>

      {/* Theme Cards */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Moon size={14} className="text-emerald-400" />
          Color Theme
        </h4>
        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {THEMES.map((t) => {
            const isSelected = prefs.theme === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => update({ theme: t.id })}
                className={`relative flex items-center gap-3.5 rounded-xl border p-3.5 text-left transition-all ${
                  isSelected
                    ? "border-emerald-400/50 bg-emerald-400/10 shadow-[0_0_12px_rgba(52,211,153,0.12)]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] hover:bg-white/[0.04]"
                }`}
              >
                <div className={`h-8 w-8 shrink-0 rounded-lg border shadow-inner ${t.previewBg} ${t.id === "light" ? "border-black/20" : "border-white/20"}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-[var(--color-ink)]">{t.label}</p>
                  <p className="mt-0.5 text-[11px] text-[var(--color-ink-muted)] truncate">{t.desc}</p>
                </div>
                {isSelected && <Check size={16} className="text-emerald-400 shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Accent Highlights */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Sparkles size={14} className="text-cyan-400" />
          Accent Glow & Buttons
        </h4>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {ACCENTS.map((a) => {
            const isSelected = prefs.accent === a.id;
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => update({ accent: a.id })}
                className={`flex items-center gap-2.5 rounded-xl border p-2.5 transition-all ${
                  isSelected
                    ? "border-white/30 bg-white/[0.08]"
                    : "border-[var(--color-hairline-soft)] bg-white/[0.02] hover:bg-white/[0.04]"
                }`}
              >
                <span className={`h-4 w-4 shrink-0 rounded-full ${a.colorClass}`} />
                <span className="text-xs font-medium text-[var(--color-ink)]">{a.label}</span>
                {isSelected && <Check size={13} className="ml-auto text-[var(--color-ink)]" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Typography & Density */}
      <div className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5 flex flex-col gap-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5">
          <Sliders size={14} className="text-violet-400" />
          Typography & Layout Density
        </h4>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Font Size */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-[var(--color-ink-secondary)]">Reading Font Size</span>
            <div className="grid grid-cols-3 gap-1.5 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-1">
              {[
                { id: "sm", label: "Compact", pt: "14px" },
                { id: "md", label: "Standard", pt: "16px" },
                { id: "lg", label: "Large", pt: "18px" },
              ].map((fs) => (
                <button
                  key={fs.id}
                  type="button"
                  onClick={() => update({ fontSize: fs.id as FontSizeOption })}
                  className={`flex flex-col items-center rounded-lg py-1.5 text-xs transition-colors ${
                    prefs.fontSize === fs.id
                      ? "bg-white/[0.1] font-semibold text-[var(--color-ink)] shadow-sm"
                      : "text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                  }`}
                >
                  <span>{fs.label}</span>
                  <span className="text-[10px] text-[var(--color-ink-muted)]">{fs.pt}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Chat Density */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-[var(--color-ink-secondary)]">Chat Density</span>
            <div className="grid grid-cols-2 gap-1.5 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] p-1">
              {[
                { id: "comfortable", label: "Comfortable", desc: "Spacious breathing room" },
                { id: "compact", label: "Compact", desc: "More messages per screen" },
              ].map((cd) => (
                <button
                  key={cd.id}
                  type="button"
                  onClick={() => update({ density: cd.id as DensityOption })}
                  className={`flex flex-col items-center rounded-lg py-1.5 text-xs transition-colors ${
                    prefs.density === cd.id
                      ? "bg-white/[0.1] font-semibold text-[var(--color-ink)] shadow-sm"
                      : "text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                  }`}
                >
                  <span>{cd.label}</span>
                  <span className="text-[10px] text-[var(--color-ink-muted)] truncate max-w-[120px]">{cd.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Motion Preference */}
        <div className="mt-2 flex items-center justify-between rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.02] px-3.5 py-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-medium text-[var(--color-ink)]">Reduce Animations</span>
            <span className="text-[11px] text-[var(--color-ink-muted)]">
              Disable decorative interface transitions and scale effects for performance or accessibility.
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={prefs.reducedMotion}
            onClick={() => update({ reducedMotion: !prefs.reducedMotion })}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              prefs.reducedMotion ? "bg-emerald-500" : "bg-white/10"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                prefs.reducedMotion ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
}
