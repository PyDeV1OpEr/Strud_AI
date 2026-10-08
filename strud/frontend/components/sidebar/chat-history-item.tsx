"use client";

// Sidebar chat item — title, hover-revealed delete, exit animation.

import { useState } from "react";
import { motion } from "motion/react";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { createPortal } from "react-dom";

import type { Chat } from "@/types";

interface ChatHistoryItemProps {
  chat: Chat;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function ChatHistoryItem({
  chat,
  active,
  onSelect,
  onDelete,
}: ChatHistoryItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });

  const openMenu = (event: React.MouseEvent) => {
    event.stopPropagation();
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    setMenuPosition({ top: rect.bottom + 4, left: rect.left });
    setMenuOpen(true);
  };

  return (
    <>
      <motion.div
        layout="position"
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, height: 0, marginBottom: -2 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        className="group relative"
      >
        <button
          onClick={onSelect}
          className={`flex w-full items-center rounded-xl px-3 py-2 text-left text-[13px] transition-colors duration-150 ${
            active
              ? "bg-white/[0.08] text-[var(--color-ink)]"
              : "text-[var(--color-ink-secondary)] hover:bg-white/[0.05] hover:text-[var(--color-ink)]"
          }`}
        >
          <span className="truncate pr-7">{chat.title}</span>
        </button>

        {/* Hover options */}
        <button
          onClick={openMenu}
          aria-label={`Options for ${chat.title}`}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1 text-[var(--color-ink-muted)] opacity-0 transition-all duration-150 hover:bg-white/[0.08] hover:text-[var(--color-ink)] focus-visible:opacity-100 group-hover:opacity-100"
        >
          <MoreHorizontal size={15} strokeWidth={1.75} />
        </button>
      </motion.div>

      {menuOpen &&
        createPortal(
          <>
            <button
              aria-label="Close menu"
              className="fixed inset-0 z-40"
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen(false);
              }}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.12 }}
              style={{ top: menuPosition.top, left: menuPosition.left }}
              className="glass-strong fixed z-50 w-40 overflow-hidden rounded-xl p-1 shadow-2xl shadow-black/50"
            >
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  setMenuOpen(false);
                  onDelete();
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-red-400 transition-colors hover:bg-red-500/10"
              >
                <Trash2 size={14} strokeWidth={1.75} />
                Delete
              </button>
            </motion.div>
          </>,
          document.body,
        )}
    </>
  );
}
