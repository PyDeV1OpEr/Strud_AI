// ------------------------------------------------------------
// Strud AI — local persistence adapter (development fallback)
//
// Chats are stored in localStorage so a refresh never loses history.
// This module is the ONLY place that touches localStorage; the API
// layer in lib/api decides between this and the backend. When the
// backend persistence comes online, swap `USE_BACKEND` in lib/api.
// ------------------------------------------------------------

import type { Chat } from "@/types";

const STORAGE_KEY = "strud.chats.v1";

export function loadChats(): Chat[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Chat[]) : [];
  } catch {
    return [];
  }
}

export function saveChats(chats: Chat[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  } catch {
    // Storage full / unavailable — history simply won't persist.
  }
}
