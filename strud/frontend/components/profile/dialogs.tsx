"use client";

// About / Settings / Delete-chat dialog surfaces.

import { Dialog, Button } from "@/components/ui/primitives";
import { isDemoMode, STRUD_REPO_URL } from "@/lib/demo";

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
      <div className="flex flex-col gap-5">
        {/* Branding */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="glass flex h-14 w-14 items-center justify-center rounded-2xl">
            <span className="bg-gradient-to-br from-emerald-300 to-emerald-500 bg-clip-text text-2xl font-bold text-transparent">
              S
            </span>
          </div>
          <div>
            <h2 id="about-title" className="text-lg font-semibold text-[var(--color-ink)]">
              STRUD AI
            </h2>
            <p className="text-xs text-emerald-400 mt-0.5 font-mono">v0.2.0</p>
          </div>
          <p className="text-[13px] leading-relaxed text-[var(--color-ink-secondary)] max-w-[280px]">
            Your A/L Biology learning assistant — intelligent explanations grounded in your curriculum resources.
          </p>
        </div>

        {/* Tech Stack */}
        <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 flex flex-col gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)]">
            Built With
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {(
              [
                ["Frontend", "Next.js 16 + React 19"],
                ["Styling", "Tailwind CSS v4"],
                ["Backend", "FastAPI + Python"],
                ["AI Engine", "LM Studio (Local LLM)"],
                ["Vision", "Qwen3 VL 8B"],
                ["Database", "SQLite (Persistent)"],
              ] as [string, string][]
            ).map(([label, value]) => (
              <div key={label} className="flex flex-col gap-0.5">
                <span className="text-[10px] text-[var(--color-ink-muted)]">{label}</span>
                <span className="font-medium text-[var(--color-ink)]">{value}</span>
              </div>
            ))}
          </div>
        </div>

        {isDemoMode() && (
          <div className="rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-4 text-[12.5px] leading-relaxed text-[var(--color-ink-secondary)]">
            <p className="font-medium text-[var(--color-ink)]">Public preview</p>
            <p className="mt-1">
              This is the frontend-only web preview. The AI engine does not run
              hosted — answer generation needs the local FastAPI backend plus
              GPT-OSS 20B / Qwen3-VL 8B served by LM Studio on your machine.
              Setup instructions are in the repository README.
            </p>
            <a
              href={STRUD_REPO_URL}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-2 inline-flex text-emerald-300 underline decoration-emerald-400/40 underline-offset-2 hover:text-emerald-200"
            >
              PyDeV1OpEr/Strud_AI ↗
            </a>
          </div>
        )}

        <p className="text-center text-[11px] text-[var(--color-ink-muted)]">
          Running fully locally — your data never leaves your device.
        </p>
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
        Move this chat to the Recycle Bin?
      </h2>
      <p className="mt-1.5 text-[14px] text-[var(--color-ink-secondary)]">
        {chatTitle ? `“${chatTitle}” will be kept in Recently Deleted until you permanently remove it.` : "This conversation can be restored from Recently Deleted."}
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} autoFocus>
          Move to Bin
        </Button>
      </div>
    </Dialog>
  );
}
