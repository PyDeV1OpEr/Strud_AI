"use client";

// Strud AI — sidebar (floating glass navigation panel)

import { useMemo, useState, useSyncExternalStore } from "react";
import {
  FolderOpen,
  FolderPlus,
  Info,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import { motion } from "motion/react";

import type { Chat, Project } from "@/types";
import { groupChats } from "@/lib/group-chats";
import { ChatHistoryItem } from "./chat-history-item";
import { StrudLogo } from "@/components/profile/strud-logo";

const subscribeNever = () => () => {};

interface SidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  /* ---- projects ---- */
  projects: Project[];
  activeProjectId: string | null;
  onCreateProject: () => void;
  onSelectProject: (id: string | null) => void;
  onEditProject: (project: Project) => void;
  onDeleteProject: (project: Project) => void;
  onMoveChatToProject: (chat: Chat, projectId: string | null) => void;
  /* ---- footer / chats ---- */
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onRenameChat: (chat: Chat) => void;
  onDeleteChat: (id: string) => void;
  onOpenSettings: () => void;
  onOpenAbout: () => void;
  onOpenRecycleBin: () => void;
}

export function Sidebar({
  chats,
  activeChatId,
  projects,
  activeProjectId,
  onCreateProject,
  onSelectProject,
  onEditProject,
  onDeleteProject,
  onMoveChatToProject,
  onNewChat,
  onSelectChat,
  onRenameChat,
  onDeleteChat,
  onOpenSettings,
  onOpenAbout,
  onOpenRecycleBin,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const [openMenuFor, setOpenMenuFor] = useState<Project | null>(null);

  // Time-bucket grouping needs the client clock. This SSR-safe flag is
  // false during prerender/hydration and true on the client afterwards,
  // keeping the prerender deterministic without setState-in-effect.
  const mounted = useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );

  // Chats shown depend on the scope: inside a project show only its
  // chats; otherwise show the ordinary, unassigned chats.
  const scopedChats = useMemo(
    () =>
      activeProjectId
        ? chats.filter((chat) => chat.projectId === activeProjectId)
        : chats.filter((chat) => !chat.projectId),
    [chats, activeProjectId],
  );

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? null,
    [projects, activeProjectId],
  );

  // Live counts from the chat list stay correct even between backend
  // project refreshes (e.g. right after the first message in a project).
  const liveCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const chat of chats) {
      if (!chat.projectId) continue;
      counts.set(chat.projectId, (counts.get(chat.projectId) ?? 0) + 1);
    }
    return counts;
  }, [chats]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return scopedChats;
    return scopedChats.filter((chat) => chat.title.toLowerCase().includes(q));
  }, [scopedChats, query]);

  const groups = useMemo(
    () => (mounted ? groupChats(filtered) : []),
    [filtered, mounted],
  );

  return (
    <div className="glass-strong flex h-full w-72 flex-col rounded-2xl overflow-hidden">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
        <StrudLogo size={30} />
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">
            Strud
          </p>
          <p className="text-[11px] text-[var(--color-ink-muted)]">
            AI Biology Assistant
          </p>
        </div>
      </div>

      {/* New chat */}
      <div className="px-3 pb-2">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2.5 rounded-xl bg-emerald-400/90 px-3.5 py-2.5 text-sm font-semibold text-emerald-950 shadow-[0_1px_0_rgba(255,255,255,0.25)_inset] transition-colors duration-150 hover:bg-emerald-300"
        >
          <Plus size={17} strokeWidth={2.2} />
          New Chat
        </button>
      </div>

      {/* Projects */}
      <div className="px-2">
        <div className="flex items-center justify-between px-2 pb-1">
          <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-ink-muted)]">
            Projects
          </p>
          <button
            onClick={onCreateProject}
            aria-label="Create a new project"
            title="New project"
            className="rounded-lg p-1 text-[var(--color-ink-muted)] transition-colors hover:bg-white/[0.08] hover:text-[var(--color-ink)]"
          >
            <FolderPlus size={14} strokeWidth={1.75} />
          </button>
        </div>
        {projects.length === 0 ? (
          <button
            onClick={onCreateProject}
            className="mb-2 w-full rounded-xl px-3 py-2 text-left text-[13px] text-[var(--color-ink-muted)] transition-colors hover:bg-white/[0.05] hover:text-[var(--color-ink-secondary)]"
          >
            No projects yet — create one to group chats.
          </button>
        ) : (
          <ul className="mb-1">
            {projects.map((project) => {
              const active = project.id === activeProjectId;
              return (
                <li key={project.id} className="relative group/proj">
                  <button
                    onClick={() => onSelectProject(active ? null : project.id)}
                    aria-pressed={active}
                    className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[13px] transition-colors ${
                      active
                        ? "bg-white/[0.08] text-[var(--color-ink)]"
                        : "text-[var(--color-ink-secondary)] hover:bg-white/[0.05] hover:text-[var(--color-ink)]"
                    }`}
                  >
                    <FolderOpen size={15} strokeWidth={1.75} className="shrink-0 text-[var(--color-ink-muted)]" />
                    <span className="truncate pr-14">{project.name}</span>
                    <span className="ml-auto text-[11px] text-[var(--color-ink-muted)]">
                      {liveCounts.get(project.id) ?? project.chatCount}
                    </span>
                  </button>
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      setOpenMenuFor(openMenuFor?.id === project.id ? null : project);
                    }}
                    aria-label={`Options for ${project.name}`}
                    aria-expanded={openMenuFor?.id === project.id}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1 text-[var(--color-ink-muted)] opacity-0 transition-all duration-150 hover:bg-white/[0.08] hover:text-[var(--color-ink)] focus-visible:opacity-100 group-hover/proj:opacity-100"
                  >
                    <MoreHorizontal size={14} strokeWidth={1.75} />
                  </button>
                  {openMenuFor?.id === project.id && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95, y: -4 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.12 }}
                      className="glass-strong absolute right-1.5 top-full z-30 mt-1 w-40 overflow-hidden rounded-xl p-1 shadow-2xl shadow-black/50"
                    >
                      <button
                        onClick={() => {
                          setOpenMenuFor(null);
                          onEditProject(project);
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
                      >
                        <Pencil size={14} strokeWidth={1.75} />
                        Rename / edit
                      </button>
                      <button
                        onClick={() => {
                          setOpenMenuFor(null);
                          onDeleteProject(project);
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-red-400 transition-colors hover:bg-red-500/10"
                      >
                        <Trash2 size={14} strokeWidth={1.75} />
                        Delete project
                      </button>
                    </motion.div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Search */}
      <div className="px-3 pb-2 pt-1">
        <label className="relative block">
          <span className="sr-only">Search chats</span>
          <Search
            size={15}
            strokeWidth={1.75}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-muted)]"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={activeProject ? "Search in project" : "Search chats"}
            className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] py-2 pl-9 pr-3 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05] outline-none"
          />
        </label>
      </div>

      {/* History */}
      <nav
        aria-label="Chat history"
        className="scroll-slim flex-1 overflow-y-auto px-2 pb-2"
      >
        {activeProject && (
          <button
            onClick={() => {
              onSelectProject(null);
              setQuery("");
            }}
            className="mb-1 flex w-full items-center gap-1.5 px-2 py-1 text-[12px] text-emerald-300/90 transition-colors hover:text-emerald-300"
            aria-label={`Stop viewing ${activeProject.name} and show all chats`}
          >
            <X size={13} strokeWidth={2} />
            Exit “{activeProject.name}”
          </button>
        )}
        {groups.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <MessageSquare size={20} strokeWidth={1.5} className="text-[var(--color-ink-muted)]" />
            <p className="text-[13px] text-[var(--color-ink-muted)]">
              {query.trim()
                ? "No chats found"
                : activeProject
                  ? "No chats in this project yet."
                  : "No chats yet. Start with a Biology question."}
            </p>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.label} className="mb-2">
              <p className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-[var(--color-ink-muted)]">
                {group.label}
              </p>
              <ul>
                {group.chats.map((chat) => (
                  <li key={chat.id}>
                    <ChatHistoryItem
                      chat={chat}
                      active={chat.id === activeChatId}
                      projects={projects}
                      showMoveToProject={
                        !activeProject && chat.projectId === undefined
                      }
                      onSelect={() => onSelectChat(chat.id)}
                      onRename={() => onRenameChat(chat)}
                      onDelete={() => onDeleteChat(chat.id)}
                      onMoveToProject={(projectId) =>
                        onMoveChatToProject(chat, projectId)
                      }
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--color-hairline-soft)] p-2">
        <button onClick={onOpenRecycleBin} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-ink)]"><Trash2 size={15} strokeWidth={1.75}/> Recently Deleted</button>
        <button
          onClick={onOpenSettings}
          className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
        >
          <Settings size={15} strokeWidth={1.75} />
          Settings
        </button>
        <button
          onClick={onOpenAbout}
          className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-[var(--color-ink-secondary)] transition-colors hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
        >
          <Info size={15} strokeWidth={1.75} />
          About Strud
        </button>
      </div>
    </div>
  );
}
