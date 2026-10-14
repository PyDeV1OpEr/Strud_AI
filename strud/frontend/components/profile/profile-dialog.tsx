"use client";

// Profile dialog — view/edit the local per-browser identity.
// This is an anonymous, local profile backed by the FastAPI backend;
// there is intentionally no password or account system here.

import { useState } from "react";
import { UserRound } from "lucide-react";
import { Dialog, Button } from "@/components/ui/primitives";

export function ProfileDialog({
  open,
  userId,
  displayName,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  userId: string;
  displayName: string;
  saving: boolean;
  onClose: () => void;
  onSave: (displayName: string) => void;
}) {
  // Initialized on mount; the parent keys this dialog on open status so
  // each open starts from the currently saved name.
  const [name, setName] = useState(displayName);

  const changed = name.trim() !== displayName.trim();
  const canSave = name.trim().length > 0 && changed && !saving;

  return (
    <Dialog open={open} onClose={onClose} title="Profile" labelledBy="profile-title">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="glass-strong flex h-12 w-12 items-center justify-center rounded-full text-base font-semibold text-emerald-300">
            {(name.trim() || displayName).trim().charAt(0).toUpperCase() || "S"}
          </div>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-medium text-[var(--color-ink)]">
              {name.trim() || "Student"}
            </p>
            <p className="text-[11px] text-[var(--color-ink-muted)]">
              Local anonymous profile
            </p>
          </div>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSave) return;
            onSave(name.trim());
          }}
          className="flex flex-col gap-3"
        >
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-[var(--color-ink)]">
              Display name
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={60}
              aria-labelledby="profile-title"
              className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
            />
          </label>

          <div className="flex items-center gap-2 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2.5">
            <UserRound size={15} strokeWidth={1.75} className="shrink-0 text-[var(--color-ink-muted)]" aria-label="Browser identity" />
            <span className="truncate text-[11px] text-[var(--color-ink-muted)]" title={userId}>
              <span aria-hidden="true">ID: </span>{userId}
            </span>
          </div>

          <p className="px-0.5 text-xs text-[var(--color-ink-muted)]">
            Strud runs fully locally. This name scopes your chats and memory on
            this device only — there are no accounts or passwords.
          </p>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={!canSave}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </div>
    </Dialog>
  );
}
