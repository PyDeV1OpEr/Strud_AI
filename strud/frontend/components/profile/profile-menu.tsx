"use client";

// Top-right circular profile button + glass dropdown.

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CircleUserRound, Info, Settings, User } from "lucide-react";

interface ProfileMenuProps {
  onOpenProfile: () => void;
  onOpenSettings: () => void;
  onOpenAbout: () => void;
}

export function ProfileMenu({ onOpenProfile, onOpenSettings, onOpenAbout }: ProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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
        className="glass-strong flex h-9 w-9 items-center justify-center rounded-full text-[var(--color-ink-secondary)] transition-colors hover:text-[var(--color-ink)]"
      >
        <CircleUserRound size={18} strokeWidth={1.75} />
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: -6 }}
            transition={{ duration: 0.16, ease: [0.2, 0.9, 0.3, 1.2] }}
            className="glass-strong absolute right-0 top-11 z-50 w-44 origin-top-right overflow-hidden rounded-xl p-1 shadow-2xl shadow-black/50"
          >
            {items.map((item, index) => (
              <div key={item.label}>
                {index === 1 && (
                  <div className="mx-2 my-1 border-t border-[var(--color-hairline-soft)]" />
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
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
