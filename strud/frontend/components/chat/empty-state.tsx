"use client";

// Welcome state when a chat has no messages.

import { motion } from "motion/react";
import { Leaf } from "lucide-react";

const SUGGESTIONS = [
  "Explain photosynthesis",
  "Explain DNA replication",
  "What is mitosis?",
  "Compare DNA and RNA",
];

export function EmptyState({
  onSuggestion,
}: {
  onSuggestion: (text: string) => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-4 pb-24">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="flex flex-col items-center text-center"
      >
        <div className="glass-strong mb-5 flex h-14 w-14 items-center justify-center rounded-2xl">
          <Leaf
            size={26}
            strokeWidth={1.6}
            className="text-emerald-300"
          />
        </div>

        <h1 className="text-[26px] font-semibold tracking-tight text-[var(--color-ink)]">
          What are you curious about?
        </h1>
        <p className="mt-1.5 text-[15px] text-[var(--color-ink-secondary)]">
          Ask Strud anything about Biology.
        </p>

        <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onSuggestion(suggestion)}
              className="glass rounded-full px-4 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-all duration-150 hover:bg-white/[0.08] hover:text-[var(--color-ink)]"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
