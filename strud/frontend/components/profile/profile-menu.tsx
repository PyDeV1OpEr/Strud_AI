"use client";

// Top-right circular profile button + glass dropdown.
// Signed in: the Google avatar (or initial fallback) opens the menu and
// Sign out lives inside; signed out: an explicit Sign in entry.

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CircleUserRound, Info, LogIn, Settings, LogOut, User } from "lucide-react";
import { useAuth } from "@/lib/auth";

interface ProfileMenuProps {
  onOpenProfile: () => void;
  onOpenSettings: () => void;
  onOpenAbout: () => void;
}

export function ProfileMenu({ onOpenProfile, onOpenSettings, onOpenAbout }: ProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { user, signOut, loading: authLoading } = useAuth();

  useEffect(() => {
    if (!open) return;
    const handlePointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const avatarUrl =
    (user?.user_metadata as { picture?: string; avatar_url?: string } | null)?.picture ??
    (user?.user_metadata as { avatar_url?: string } | null)?.avatar_url ??
    null;
  const displayName =
    (user?.user_metadata as { name?: string; full_name?: string } | null)?.name ??
    user?.email ??
    null;
  const initial = displayName ? displayName.charAt(0).toUpperCase() : "S";

  const items = [
    { icon: User, label: "Profile", action: onOpenProfile },
    { icon: Settings, label: "Settings", action: onOpenSettings },
    { icon: Info, label: "About Strud", action: onOpenAbout },
  ];

  return (
    <div ref={containerRef} className="relative">
      <motion.button
        onClick={() => setOpen((value) => !value)}
        whileTap={{ scale: 0.92 }}
        aria-label="Open profile menu"
        aria-expanded={open}
        className="glass-strong flex h-9 w-9 items-center justify-center rounded-full overflow-hidden text-[var(--color-ink-secondary)] transition-colors hover:text-[var(--color-ink)]"
      >
        {avatarUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt="" width={36} height={36} className="h-9 w-9 object-cover" />
        ) : (
          <CircleUserRound size={18} strokeWidth={1.75} />
        )}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: -6 }}
            transition={{ duration: 0.16, ease: [0.2, 0.9, 0.3, 1.2] }}
            className="glass-strong absolute right-0 top-11 z-50 w-52 origin-top-right overflow-hidden rounded-xl p-1 shadow-2xl shadow-black/50"
          >
            {user && (
              <div className="flex items-center gap-2.5 px-3 py-2">
                {avatarUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={avatarUrl} alt="" width={26} height={26} className="h-[26px] w-[26px] rounded-full object-cover" />
                ) : (
                  <span className="glass-strong flex h-[26px] w-[26px] items-center justify-center rounded-full text-[11px] font-semibold text-emerald-300">
                    {initial}
                  </span>
                )}
                <span className="min-w-0 truncate text-[12px] text-[var(--color-ink)]">
                  {displayName ?? "Signed in"}
                </span>
              </div>
            )}
            {items.map((item, index) => (
              <div key={item.label}>
                {user && index === 0 && (
                  <div className="mx-2 mb-1 mt-0.5 border-t border-[var(--color-hairline-soft)]" />
                )}
                <button
                  onClick={() => {
                    setOpen(false);
                    item.action();
                  }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
                >
                  <item.icon size={14} strokeWidth={1.75} />
                  {item.label}
                </button>
              </div>
            ))}
            <div className="mx-2 my-1 border-t border-[var(--color-hairline-soft)]" />
            {user ? (
              <button
                onClick={() => {
                  setOpen(false);
                  void signOut();
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
              >
                <LogOut size={14} strokeWidth={1.75} />
                {authLoading ? "Signing out…" : "Sign out"}
              </button>
            ) : (
              <button
                onClick={() => {
                  setOpen(false);
                  onOpenProfile();
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
              >
                <LogIn size={14} strokeWidth={1.75} />
                Sign in with Google
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
