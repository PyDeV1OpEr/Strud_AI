// ------------------------------------------------------------
// Strud AI — chat persistence API
//
// Local persistence while the backend has no chat database. Kept
// behind this module so backend-side persistence can replace it
// later without touching components or hooks.
// ------------------------------------------------------------

import type { Chat } from "@/types";
import { loadChats, saveChats } from "@/lib/store/local-chats";

export function getChats(): Chat[] {
  return loadChats().sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export function persistChats(chats: Chat[]): void {
  saveChats(chats);
}

export function createChat(title = "New chat"): Chat {
  const now = new Date().toISOString();
  const chat: Chat = {
    id: crypto.randomUUID(),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
  return chat;
}
