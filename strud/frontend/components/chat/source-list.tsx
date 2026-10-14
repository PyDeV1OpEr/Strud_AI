"use client";

// Collapsible "Sources" section — subtle, trustworthy, clutter-free.

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BookOpen, ChevronDown } from "lucide-react";

import type { Source } from "@/types";
import { getStoredChatPrefs } from "@/lib/preferences";

export function SourceList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(() => getStoredChatPrefs().showSourcesDefault);

  return (
    <div className="mt-1 w-full">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3 py-1.5 text-xs text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
      >
        <BookOpen size={13} strokeWidth={1.75} className="text-emerald-400/80" />
        Sources
        <span className="text-[var(--color-ink-muted)]">
          ({sources.reduce((sum, source) => sum + source.pages.length, 0)})
        </span>
        <ChevronDown
          size={13}
          strokeWidth={1.75}
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.ul
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="mt-2 overflow-hidden"
          >
            {sources.map((source) => (
              <li
                key={source.label}
                className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.025] px-3.5 py-2.5 text-[13px]"
              >
                <p className="flex items-center gap-2 font-medium text-[var(--color-ink)]">
                  <BookOpen size={13} strokeWidth={1.75} className="text-emerald-400/80" />
                  {source.label}
                </p>
                <p className="mt-1 pl-[21px] text-[var(--color-ink-muted)]">
                  Page {source.pages.join(", Page ")}
                </p>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
