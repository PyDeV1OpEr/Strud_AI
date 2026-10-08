"use client";

// Minimal shadcn/ui-style primitives kept dependency-free.
// Glass-styled, accessible, animated with CSS transitions.

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

// ---- Button ------------------------------------------------------------

type ButtonVariant = "primary" | "ghost" | "danger";

const buttonStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-emerald-400/90 text-emerald-950 hover:bg-emerald-300 shadow-[0_1px_0_rgba(255,255,255,0.25)_inset]",
  ghost:
    "text-[var(--color-ink-secondary)] hover:text-[var(--color-ink)] hover:bg-white/[0.06]",
  danger:
    "bg-red-500/90 text-white hover:bg-red-400",
};

export function Button({
  variant = "ghost",
  className = "",
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-xl text-sm font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-45 ${buttonStyles[variant]} ${className}`}
      {...props}
    />
  );
}

// ---- Dialog ------------------------------------------------------------

export function Dialog({
  open,
  onClose,
  title,
  children,
  labelledBy,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  labelledBy?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
    >
      <button
        aria-label="Close dialog"
        className="absolute inset-0 bg-black/55 animate-[fade-in_160ms_ease-out]"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className="glass-strong relative z-10 w-full max-w-md rounded-2xl p-5 shadow-2xl shadow-black/50 animate-[dialog-in_200ms_cubic-bezier(0.2,0.9,0.3,1.2)]"
      >
        {title && (
          <div className="mb-3 flex items-center justify-between">
            <h2
              id={labelledBy}
              className="text-base font-semibold text-[var(--color-ink)]"
            >
              {title}
            </h2>
            <button
              onClick={onClose}
              aria-label="Close"
              className="rounded-lg p-1.5 text-[var(--color-ink-muted)] hover:bg-white/[0.06] hover:text-[var(--color-ink)] transition-colors"
            >
              <X size={16} strokeWidth={1.75} />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

// ---- Toast ---------------------------------------------------------------

export function Toast({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="status"
      className="glass-strong fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full px-4 py-2 text-sm text-[var(--color-ink)] shadow-xl shadow-black/40 animate-[toast-in_200ms_ease-out]"
    >
      {message}
    </div>
  );
}
