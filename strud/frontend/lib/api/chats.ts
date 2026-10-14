// ------------------------------------------------------------
// Strud AI — chat persistence API
//
// Backend chat persistence with localStorage retained as an offline cache.
// ------------------------------------------------------------

import type { Attachment, Chat, Message } from "@/types";
import { loadChats, saveChats } from "@/lib/store/local-chats";
import { BACKEND_URL } from "./errors";

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

type StoredChat = {
  chat_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{ role: "user" | "assistant"; content: string; created_at: string; attachments?: Attachment[] }>;
};

/** Load server-owned history; localStorage remains a graceful offline cache. */
export async function fetchChats(userId: string): Promise<Chat[]> {
  const response = await fetch(`${BACKEND_URL}/api/chats?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(`Could not load chats (${response.status})`);
  const body = (await response.json()) as { chats?: StoredChat[] };
  return (body.chats ?? []).map((chat) => ({
    id: chat.chat_id,
    title: chat.title || "New chat",
    createdAt: chat.created_at,
    updatedAt: chat.updated_at,
    messages: chat.messages.map((message, index): Message => ({
      id: `${chat.chat_id}:${message.created_at}:${index}`,
      chatId: chat.chat_id,
      role: message.role,
      content: message.content,
      createdAt: message.created_at,
      attachments: (message.attachments ?? []).map((attachment) => ({
        ...attachment,
        url: attachment.url.startsWith("http") ? attachment.url : `${BACKEND_URL}${attachment.url}`,
      })),
    })),
  }));
}

export async function persistTitle(chatId: string, userId: string, title: string): Promise<void> {
  await fetch(`${BACKEND_URL}/api/chats/${encodeURIComponent(chatId)}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, title }),
  });
}

async function chatMutation(path: string, method: "POST" | "DELETE", userId: string): Promise<void> {
  const response = await fetch(`${BACKEND_URL}${path}?user_id=${encodeURIComponent(userId)}`, { method });
  if (!response.ok) throw new Error(`Chat update failed (${response.status})`);
}

export async function fetchDeletedChats(userId: string): Promise<Chat[]> {
  const response = await fetch(`${BACKEND_URL}/api/chats/deleted?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(`Could not load Recycle Bin (${response.status})`);
  const body = (await response.json()) as { chats?: StoredChat[] };
  return (body.chats ?? []).map((chat) => ({
    id: chat.chat_id, title: chat.title || "New chat", createdAt: chat.created_at, updatedAt: chat.updated_at,
    messages: chat.messages.map((message, index) => ({ id: `${chat.chat_id}:${message.created_at}:${index}`, chatId: chat.chat_id, role: message.role, content: message.content, createdAt: message.created_at, attachments: (message.attachments ?? []).map((attachment) => ({ ...attachment, url: attachment.url.startsWith("http") ? attachment.url : `${BACKEND_URL}${attachment.url}` })) })),
  }));
}

export const moveChatToBin = (chatId: string, userId: string) => chatMutation(`/api/chats/${encodeURIComponent(chatId)}`, "DELETE", userId);
export const restoreChat = (chatId: string, userId: string) => chatMutation(`/api/chats/${encodeURIComponent(chatId)}/restore`, "POST", userId);
export const permanentlyDeleteChat = (chatId: string, userId: string) => chatMutation(`/api/chats/${encodeURIComponent(chatId)}/permanent`, "DELETE", userId);
export const emptyRecycleBin = (userId: string) => chatMutation("/api/chats/deleted/all", "DELETE", userId);
