"use client";

// About / Settings / Delete-chat dialog surfaces.

import { Dialog, Button } from "@/components/ui/primitives";

// ---- About ------------------------------------------------------------

export function AboutDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} labelledBy="about-title">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="glass flex h-14 w-14 items-center justify-center rounded-2xl">
          {/* Reuse the letter mark */}
          <span className="bg-gradient-to-br from-emerald-300 to-emerald-500 bg-clip-text text-2xl font-bold text-transparent">
            S
          </span>
        </div>
        <h2 id="about-title" className="text-lg font-semibold">
          Strud AI
        </h2>
        <p className="text-[14px] leading-relaxed text-[var(--color-ink-secondary)]">
          Your Biology learning assistant.
          <br />
          Built to help you understand Biology through intelligent
          explanations grounded in your learning resources.
        </p>
        <p className="text-xs text-[var(--color-ink-muted)]">Version 0.1.0</p>
      </div>
    </Dialog>
  );
}

// ---- Settings ------------------------------------------------------------

export function SettingsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Settings"
      labelledBy="settings-title"
    >
      <div className="flex flex-col gap-3 text-[14px] text-[var(--color-ink-secondary)]">
        <div className="flex items-center justify-between rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-3">
          <div>
            <p className="font-medium text-[var(--color-ink)]">Appearance</p>
            <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
              Glass dark theme
            </p>
          </div>
          <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-xs text-emerald-300">
            Dark
          </span>
        </div>
        <p className="px-1 text-xs text-[var(--color-ink-muted)]">
          More options will arrive with later versions.
        </p>
      </div>
      <div className="mt-4 flex justify-end">
        <Button variant="ghost" onClick={onClose}>
          Done
        </Button>
      </div>
    </Dialog>
  );
}

// ---- Delete chat ----------------------------------------------------------

export function DeleteChatDialog({
  open,
  chatTitle,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  chatTitle: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} labelledBy="delete-title">
      <h2 id="delete-title" className="text-base font-semibold text-[var(--color-ink)]">
        Delete this chat?
      </h2>
      <p className="mt-1.5 text-[14px] text-[var(--color-ink-secondary)]">
        {chatTitle ? `“${chatTitle}” will be permanently removed.` : "This conversation will be permanently removed."}
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm}>
          Delete
        </Button>
      </div>
    </Dialog>
  );
}
