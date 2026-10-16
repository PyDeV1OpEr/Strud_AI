"use client";

// Thinking-level selector — a compact popover anchored to the composer.
// The underlying model is fixed by the app owner; only Strud's reasoning
// effort changes. The value is forwarded with every message and mapped
// server-side to the configured model's supported effort mechanism
// (gpt-oss's trained "Reasoning: low|medium|high" system instruction).

import { useCallback, useEffect, useId, useRef, useState } from "react";

function readStoredLevel(): ThinkingLevel {
  if (typeof window === "undefined") return "medium";
  const stored = getStoredChatPrefs().thinkingLevel;
  return stored === "low" || stored === "medium" || stored === "high" ? stored : "medium";
}
import { AnimatePresence, motion } from "motion/react";
import { Brain, Lightbulb, Sparkles, Zap, Check } from "lucide-react";

import { getStoredChatPrefs, saveChatPrefs } from "@/lib/preferences";
import type { ThinkingLevel } from "@/types";

interface ThinkingOption {
  id: ThinkingLevel;
  label: string;
  description: string;
  icon: React.ElementType;
  iconClass: string;
}

const OPTIONS: ThinkingOption[] = [
  {
    id: "low",
    label: "Low thinking",
    description: "Faster responses for simple questions and quick lookups.",
    icon: Zap,
    iconClass: "text-amber-400",
  },
  {
    id: "medium",
    label: "Medium thinking",
    description: "Balanced reasoning for everyday study questions.",
    icon: Lightbulb,
    iconClass: "text-cyan-400",
  },
  {
    id: "high",
    label: "High thinking",
    description: "Deeper reasoning for complex Biology questions and multistep problems.",
    icon: Brain,
    iconClass: "text-emerald-400",
  },
];

const POPOVER_MAX_HEIGHT = 340;

export function ThinkingSelector() {
  // Initialized from persisted prefs. The stored value can differ between
  // server render ("medium") and the client, so the button marks itself
  // hydration-tolerant instead of pushing state within an effect.
  const [level, setLevel] = useState<ThinkingLevel>(readStoredLevel);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; bottom?: number; top?: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const choose = useCallback((next: ThinkingLevel) => {
    setLevel(next);
    const prefs = getStoredChatPrefs();
    saveChatPrefs({ ...prefs, thinkingLevel: next });
    setOpen(false);
  }, []);

  // Anchor the popover above the button; open downward when there is not
  // enough room, and clamp horizontally to the viewport so it never clips.
  const updatePosition = useCallback(() => {
    const button = buttonRef.current;
    if (!button || typeof window === "undefined") return;
    const rect = button.getBoundingClientRect();
    const viewportH = window.innerHeight;
    const viewportW = document.documentElement.clientWidth;
    const gap = 8;
    const popoverW = 264;
    const spaceAbove = rect.top;
    const openUp = spaceAbove >= Math.min(POPOVER_MAX_HEIGHT, 280) + gap;

    let left = rect.left + rect.width / 2 - popoverW / 2;
    left = Math.min(Math.max(left, 8), Math.max(8, viewportW - popoverW - 8));

    setPosition(
      openUp
        ? { left, bottom: viewportH - rect.top + gap }
        : { left, top: rect.bottom + gap },
    );
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const current = OPTIONS.findIndex((o) => o.id === level);
        const delta = event.key === "ArrowUp" ? -1 : 1;
        const next = OPTIONS[(current + delta + OPTIONS.length) % OPTIONS.length];
        choose(next.id);
        buttonRef.current?.focus();
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        popoverRef.current?.contains(target) ||
        buttonRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, level, choose, updatePosition]);

  const current = OPTIONS.find((o) => o.id === level) ?? OPTIONS[1];
  const CurrentIcon = current.icon;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        suppressHydrationWarning
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          // Re-read the persisted level so a default changed in Settings
          // (while the composer is mounted) is reflected immediately.
          const stored = getStoredChatPrefs().thinkingLevel;
          if (stored === "low" || stored === "medium" || stored === "high") {
            setLevel(stored);
          }
          setOpen((v) => !v);
        }}
        title="Thinking level — how much reasoning Strud applies to the next answer"
        className={`flex items-center gap-1.5 rounded-full border py-1.5 pl-2.5 pr-2 text-[12px] font-medium transition-colors ${
          open
            ? "border-emerald-400/40 bg-white/[0.08] text-[var(--color-ink)]"
            : "border-[var(--color-hairline-soft)] bg-white/[0.03] text-[var(--color-ink-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
        } focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400/60`}
      >
        <CurrentIcon size={14} strokeWidth={1.9} className={current.iconClass} />
        <span className="whitespace-nowrap">{current.label.replace(" thinking", "")}</span>
        <span className="text-[var(--color-ink-muted)]" aria-hidden>
          ▾
        </span>
      </button>

      <AnimatePresence>
        {open && position && (
          <motion.div
            ref={popoverRef}
            role="listbox"
            id={listId}
            aria-label="Thinking level"
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.98 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="glass-strong fixed z-[70] w-[264px] overflow-hidden rounded-2xl shadow-2xl shadow-black/50"
            style={{ left: position.left, bottom: position.bottom, top: position.top }}
          >
            <div className="px-3.5 pb-1.5 pt-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-ink-muted)]">
                Thinking level
              </p>
            </div>
            <div className="flex flex-col p-1.5 pt-0">
              {OPTIONS.map((option) => {
                const Icon = option.icon;
                const isSelected = option.id === level;
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => choose(option.id)}
                    className={`flex w-full items-start gap-2.5 rounded-xl p-2.5 text-left transition-colors ${
                      isSelected
                        ? "bg-emerald-400/10"
                        : "hover:bg-white/[0.05]"
                    } focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400/60`}
                  >
                    <Icon
                      size={16}
                      strokeWidth={1.9}
                      className={`mt-0.5 shrink-0 ${option.iconClass}`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-ink)]">
                        {option.label}
                        {isSelected && <Check size={13} className="text-emerald-400" />}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-[var(--color-ink-muted)]">
                        {option.description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="border-t border-[var(--color-hairline-soft)] px-3.5 py-2">
              <p className="flex items-center gap-1.5 text-[10px] leading-snug text-[var(--color-ink-muted)]">
                <Sparkles size={11} className="shrink-0 text-emerald-400/80" />
                Applies to your next message. The model itself stays the same.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
