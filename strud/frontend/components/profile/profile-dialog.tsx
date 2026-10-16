"use client";

// Profile dialog.
// Signed in: the verified Google identity is shown and pre-populated
// (name, email, picture, join date) — editable fields persist to the
// RLS-protected `profiles` table for this authenticated user only.
// Signed out: the legacy local anonymous profile UI.

import { useEffect, useState } from "react";
import { LogOut, UserRound } from "lucide-react";
import { Dialog, Button } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

export interface UserProfile {
  displayName: string;
  email: string | null;
  avatar: string | null;
  joinedAt: string | null;
}

function formatJoined(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
  });
}

export function ProfileDialog({
  open,
  userId,
  profile,
  signedIn,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  userId: string;
  profile: UserProfile;
  signedIn: boolean;
  saving: boolean;
  onClose: () => void;
  onSave: (displayName: string) => void;
}) {
  const { signOut, loading: authLoading } = useAuth();
  // Initialized on mount; the parent keys this dialog on open status so
  // each open starts from the currently saved name.
  const [name, setName] = useState(profile.displayName);
  useEffect(() => setName(profile.displayName), [profile.displayName]);

  const changed = name.trim() !== profile.displayName.trim();
  const canSave = name.trim().length > 0 && changed && !saving;
  const joined = formatJoined(profile.joinedAt);
  const initial =
    (name.trim() || profile.displayName).trim().charAt(0).toUpperCase() || "S";

  return (
    <Dialog open={open} onClose={onClose} title="Profile" labelledBy="profile-title">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          {profile.avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.avatar}
              alt=""
              width={48}
              height={48}
              className="h-12 w-12 rounded-full border border-[var(--color-hairline-soft)] object-cover"
            />
          ) : (
            <div className="glass-strong flex h-12 w-12 items-center justify-center rounded-full text-base font-semibold text-emerald-300">
              {initial}
            </div>
          )}
          <div className="min-w-0">
            <p className="truncate text-[15px] font-medium text-[var(--color-ink)]">
              {name.trim() || "Student"}
            </p>
            {signedIn ? (
              <p className="truncate text-[11px] text-[var(--color-ink-muted)]">
                {profile.email ?? "Google account"}
              </p>
            ) : (
              <p className="truncate text-[11px] text-[var(--color-ink-muted)]">
                Local anonymous profile
              </p>
            )}
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

          {signedIn ? (
            <>
              {joined && (
                <div className="flex items-center gap-2 rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.03] px-3.5 py-2.5">
                  <UserRound size={15} strokeWidth={1.75} className="shrink-0 text-[var(--color-ink-muted)]" />
                  <span className="text-[11px] text-[var(--color-ink-muted)]">
                    Member since {joined}
                  </span>
                </div>
              )}
              <p className="px-0.5 text-xs text-[var(--color-ink-muted)]">
                Name, email and picture come from your verified Google account.
                Only the display name above is editable, and it saves to your
                private Strud profile.
              </p>
              <div className="flex items-center justify-between gap-2">
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    void signOut();
                    onClose();
                  }}
                  disabled={authLoading}
                >
                  <LogOut size={14} strokeWidth={1.75} />
                  {authLoading ? "Signing out…" : "Sign out"}
                </Button>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={onClose}>
                    Cancel
                  </Button>
                  <Button variant="primary" type="submit" disabled={!canSave}>
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
        </form>
      </div>
    </Dialog>
  );
}
