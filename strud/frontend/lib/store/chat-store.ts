// ------------------------------------------------------------
// Strud AI — external chat store
//
// A minimal external store over localStorage so React can read it
// with useSyncExternalStore (SSR-safe, no setState-in-effect).
// The API layer (lib/api) remains the persistence boundary.
// ------------------------------------------------------------

import type { Chat } from "@/types";
import { loadChats, saveChats } from "@/lib/store/local-chats";

type Listener = () => void;

/** Stable server snapshot — React requires getServerSnapshot to be referentially cached. */
const EMPTY_CHATS: Chat[] = [];

class ChatStore {
  private chats: Chat[] | null = null; // lazy: read localStorage on first client snapshot
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): Chat[] => {
    if (this.chats === null) {
      this.chats = loadChats().sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      );
    }
    return this.chats;
  };

  /** Server snapshot: deterministic empty history during prerender. */
  getServerSnapshot = (): Chat[] => EMPTY_CHATS;

  set = (next: Chat[]): void => {
    this.chats = next;
    saveChats(next);
    for (const listener of this.listeners) listener();
  };
}

export const chatStore = new ChatStore();
