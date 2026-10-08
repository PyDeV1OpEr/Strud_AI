// ------------------------------------------------------------
// Strud AI — chat history grouping
// Groups chats into friendly time buckets for the sidebar.
// ------------------------------------------------------------

import type { Chat } from "@/types";

export interface ChatGroup {
  label: string;
  chats: Chat[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function groupChats(chats: Chat[], now = new Date()): ChatGroup[] {
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();

  const groups: Record<string, Chat[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    Older: [],
  };

  for (const chat of chats) {
    const updated = new Date(chat.updatedAt).getTime();
    if (updated >= startOfToday) {
      groups.Today.push(chat);
    } else if (updated >= startOfToday - DAY_MS) {
      groups.Yesterday.push(chat);
    } else if (updated >= startOfToday - 7 * DAY_MS) {
      groups["Previous 7 Days"].push(chat);
    } else {
      groups.Older.push(chat);
    }
  }

  return Object.entries(groups)
    .filter(([, list]) => list.length > 0)
    .map(([label, list]) => ({
      label,
      chats: list.sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    }));
}
