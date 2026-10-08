"use client";

// "Strud is thinking" three-dot rhythm.

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-3 py-1">
      <div
        aria-hidden="true"
        className="flex items-center gap-1.5"
      >
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="h-1.5 w-1.5 rounded-full bg-emerald-300/90"
            style={{
              animation: `typing-bounce 1.15s ease-in-out ${index * 0.15}s infinite`,
            }}
          />
        ))}
      </div>
      <span className="text-[13px] text-[var(--color-ink-muted)]">
        Strud is thinking
      </span>
    </div>
  );
}
