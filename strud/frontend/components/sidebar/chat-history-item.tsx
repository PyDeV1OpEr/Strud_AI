"use client";

// Sidebar chat item — title, hover-revealed options (rename, move,
// delete), exit animation. Menus render through a positioned portal so
// they can never be clipped by the sidebar's overflow.

import { useState } from "react";
import { motion } from "motion/react";
import { MoreHorizontal, MoveRight, Pencil, Trash2 } from "lucide-react";
import { createPortal } from "react-dom";

import type { Chat, Project } from "@/types";

interface ChatHistoryItemProps {
  chat: Chat;
  active: boolean;
  projects: Project[];
  /** Server-connected chats only; legacy local chats can't be moved yet. */
  showMoveToProject: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
}

export function ChatHistoryItem({
  chat,
  active,
  projects,
  showMoveToProject,
  onSelect,
  onRename,
  onDelete,
  onMoveToProject,
}: ChatHistoryItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });

  const openMenu = (event: React.MouseEvent) => {
    event.stopPropagation();
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    setMenuPosition({ top: rect.bottom + 4, left: rect.left });
    setMenuOpen(true);
    setMoveOpen(false);
  };

  const closeMenu = () => {
    setMenuOpen(false);
    setMoveOpen(false);
  };

  // Targets exclude the chat's current project (moving there is pointless).
  const moveToTargets = projects.filter(
    (project) => project.id !== chat.projectId,
  );

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
          aria-expanded={menuOpen}
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
                closeMenu();
              }}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.12 }}
              style={{ top: menuPosition.top, left: menuPosition.left }}
              className="glass-strong fixed z-50 w-44 overflow-hidden rounded-xl p-1 shadow-2xl shadow-black/50"
            >
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  closeMenu();
                  onRename();
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
              >
                <Pencil size={14} strokeWidth={1.75} />
                Rename
              </button>

              {showMoveToProject && moveToTargets.length > 0 && (
                <div
                  onMouseLeave={() => setMoveOpen(false)}
                  className="relative"
                >
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      setMoveOpen(true);
                    }}
                    aria-expanded={moveOpen}
                    className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
                  >
                    <span className="flex items-center gap-2">
                      <MoveRight size={14} strokeWidth={1.75} />
                      Move to project
                    </span>
                  </button>
                  {moveOpen && (
                    <motion.div
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.12 }}
                      className="glass-strong absolute left-full top-0 ml-1 w-44 max-h-48 overflow-y-auto scroll-slim rounded-xl p-1 shadow-2xl shadow-black/50"
                    >
                      {moveToTargets.map((project) => (
                        <button
                          key={project.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            closeMenu();
                            onMoveToProject(project.id);
                          }}
                          className="flex w-full items-center gap-2 truncate rounded-lg px-3 py-2 text-left text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
                        >
                          {project.name}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </div>
              )}

              <button
                onClick={(event) => {
                  event.stopPropagation();
                  closeMenu();
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
