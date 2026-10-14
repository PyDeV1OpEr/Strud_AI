"use client";

// Strud AI — sidebar (floating glass navigation panel)

import { useMemo, useState, useSyncExternalStore } from "react";
import { Plus, Search, Settings, Info, MessageSquare, Trash2 } from "lucide-react";

import type { Chat } from "@/types";
import { groupChats } from "@/lib/group-chats";
import { ChatHistoryItem } from "./chat-history-item";
import { StrudLogo } from "@/components/profile/strud-logo";

const subscribeNever = () => () => {};

interface SidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onOpenSettings: () => void;
  onOpenAbout: () => void;
  onOpenRecycleBin: () => void;
}

export function Sidebar({
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onOpenSettings,
  onOpenAbout,
  onOpenRecycleBin,
}: SidebarProps) {
  const [query, setQuery] = useState("");

  // Time-bucket grouping needs the client clock. This SSR-safe flag is
  // false during prerender/hydration and true on the client afterwards,
  // keeping the prerender deterministic without setState-in-effect.
  const mounted = useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((chat) => chat.title.toLowerCase().includes(q));
  }, [chats, query]);

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

      {/* Search */}
      <div className="px-3 pb-2">
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
            placeholder="Search chats"
            className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] py-2 pl-9 pr-3 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05] outline-none"
          />
        </label>
      </div>

      {/* History */}
      <nav
        aria-label="Chat history"
        className="scroll-slim flex-1 overflow-y-auto px-2 pb-2"
      >
        {groups.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <MessageSquare size={20} strokeWidth={1.5} className="text-[var(--color-ink-muted)]" />
            <p className="text-[13px] text-[var(--color-ink-muted)]">
              {query.trim()
                ? "No chats found"
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
                      onSelect={() => onSelectChat(chat.id)}
                      onDelete={() => onDeleteChat(chat.id)}
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
