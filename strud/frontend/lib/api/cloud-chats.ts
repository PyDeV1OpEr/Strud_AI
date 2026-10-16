// ------------------------------------------------------------
// Strud AI — cloud chat persistence (Supabase + RLS)
//
// All queries run with the browser Supabase client, so every row read
// or written is guarded server-side by RLS (user_id = auth.uid()).
// Ownership always comes from the verified session — userId is a
// consistency check in WHERE clauses, never a trust boundary.
// ------------------------------------------------------------

import type { Attachment, Chat, Message, Source } from "@/types";
import { getSupabase } from "@/lib/supabase";
import { authState } from "@/lib/auth-state";

type StoredChat = {
  chat_id: string;
  title: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

type StoredMessage = {
  id: number;
  chat_id: string;
  role: "user" | "assistant";
  content: string;
  attachments_json: Attachment[] | null;
  sources_json: Source[] | null;
  error: string | null;
  created_at: string;
};

const CHAT_LIMIT = 100;

function requireClient() {
  const client = getSupabase();
  if (!client) throw new Error("Supabase is not configured in this build.");
  return client;
}

function toMessage(raw: StoredMessage): Message {
  const attachments = (raw.attachments_json ?? []).map((attachment) => ({
    ...attachment,
    url: attachment.url.startsWith("http")
      ? attachment.url
      : `/api/uploads/${attachment.url.split("/").pop() ?? ""}`,
  }));
  return {
    id: `${raw.chat_id}:${raw.id}`,
    chatId: raw.chat_id,
    role: raw.role,
    content: raw.content,
    createdAt: raw.created_at,
    ...(attachments.length ? { attachments } : {}),
    ...(raw.sources_json && raw.sources_json.length ? { sources: raw.sources_json } : {}),
    ...(raw.error ? { error: raw.error } : {}),
  };
}

function toChat(raw: StoredChat, messages: Message[]): Chat {
  return {
    id: raw.chat_id,
    title: raw.title || "New chat",
    ...(raw.project_id ? { projectId: raw.project_id } : {}),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    messages,
  };
}

async function fetchMessagesForChats(chatIds: string[], userId: string): Promise<Map<string, Message[]>> {
  const grouped = new Map<string, Message[]>();
  if (chatIds.length === 0) return grouped;
  const client = requireClient();
  const { data, error } = await client
    .from("conversations")
    .select("id, chat_id, role, content, attachments_json, sources_json, error, created_at")
    .eq("user_id", userId)
    .in("chat_id", chatIds.slice(0, 60))
    .order("id", { ascending: true })
    .limit(1200);
  if (error) throw new Error(error.message);
  for (const raw of (data ?? []) as StoredMessage[]) {
    const list = grouped.get(raw.chat_id) ?? [];
    list.push(toMessage(raw));
    grouped.set(raw.chat_id, list);
  }
  return grouped;
}

/** Paginated owner-only chat list with messages (newest chats first). */
export async function cloudFetchChats(userId: string): Promise<Chat[]> {
  const client = requireClient();
  const { data: chatRows, error } = await client
    .from("chats")
    .select("chat_id, title, project_id, created_at, updated_at, deleted_at")
    .eq("user_id", userId)
    .is("deleted_at", null)
    .order("updated_at", { ascending: false })
    .limit(CHAT_LIMIT);
  if (error) throw new Error(error.message);

  const ids = (chatRows ?? []).map((row) => (row as StoredChat).chat_id);
  const grouped = await fetchMessagesForChats(ids, userId);
  return (chatRows ?? [])
    .map((row) => {
      const stored = row as StoredChat;
      return toChat(stored, grouped.get(stored.chat_id) ?? []);
    });
}

export async function cloudFetchDeletedChats(userId: string): Promise<Chat[]> {
  const client = requireClient();
  const { data: chatRows, error } = await client
    .from("chats")
    .select("chat_id, title, project_id, created_at, updated_at, deleted_at")
    .eq("user_id", userId)
    .not("deleted_at", "is", null)
    .order("deleted_at", { ascending: false })
    .limit(CHAT_LIMIT);
  if (error) throw new Error(error.message);

  const ids = (chatRows ?? []).map((row) => (row as StoredChat).chat_id);
  const grouped = await fetchMessagesForChats(ids, userId);
  return (chatRows ?? [])
    .map((row) => {
      const stored = row as StoredChat;
      return toChat(stored, grouped.get(stored.chat_id) ?? []);
    });
}

/** Full message history for one chat (chat switching loads the correct messages). */
export async function cloudFetchMessages(chatId: string, userId: string): Promise<Message[]> {
  const client = requireClient();
  const { data, error } = await client
    .from("conversations")
    .select("id, chat_id, role, content, attachments_json, sources_json, error, created_at")
    .eq("user_id", userId)
    .eq("chat_id", chatId)
    .order("id", { ascending: true });
  if (error) throw new Error(error.message);
  return ((data ?? []) as StoredMessage[]).map(toMessage);
}

export async function cloudInsertMessage(
  chatId: string,
  userId: string,
  message: Omit<Message, "id"> & { id?: string },
): Promise<void> {
  const client = requireClient();
  const { error } = await client.from("conversations").insert({
    user_id: userId,
    chat_id: chatId,
    role: message.role,
    content: message.content,
    attachments_json: message.attachments ?? [],
    sources_json: message.sources ?? [],
    error: message.error ?? null,
    created_at: message.createdAt,
  });
  if (error) throw new Error(error.message);
}

export async function cloudUpsertChat(
  chatId: string,
  userId: string,
  patch: { title: string; projectId?: string | null; at: string },
): Promise<void> {
  const client = requireClient();
  const { error } = await client.from("chats").upsert({
    user_id: userId,
    chat_id: chatId,
    title: patch.title || "New chat",
    project_id: patch.projectId ?? null,
    created_at: patch.at,
    updated_at: patch.at,
  });
  if (error) throw new Error(error.message);
}

export async function cloudTouchChat(chatId: string, userId: string): Promise<void> {
  const client = requireClient();
  const { error } = await client
    .from("chats")
    .update({ updated_at: new Date().toISOString() })
    .match({ user_id: userId, chat_id: chatId });
  if (error) throw new Error(error.message);
}

export async function cloudPersistTitle(chatId: string, userId: string, title: string): Promise<void> {
  const client = requireClient();
  const { error } = await client
    .from("chats")
    .update({ title: title || "New chat" })
    .match({ user_id: userId, chat_id: chatId });
  if (error) throw new Error(error.message);
}

export async function cloudBinChat(chatId: string, userId: string): Promise<void> {
  const client = requireClient();
  const { error } = await client
    .from("chats")
    .update({ deleted_at: new Date().toISOString() })
    .match({ user_id: userId, chat_id: chatId });
  if (error) throw new Error(error.message);
}

export async function cloudRestoreChat(chatId: string, userId: string): Promise<void> {
  const client = requireClient();
  const { error } = await client
    .from("chats")
    .update({ deleted_at: null })
    .match({ user_id: userId, chat_id: chatId });
  if (error) throw new Error(error.message);
}

export async function cloudPurgeChat(chatId: string, userId: string): Promise<void> {
  const client = requireClient();
  await client.from("conversations").delete().match({ user_id: userId, chat_id: chatId });
  const { error } = await client.from("chats").delete().match({ user_id: userId, chat_id: chatId });
  if (error) throw new Error(error.message);
}

export async function cloudEmptyBin(userId: string): Promise<void> {
  const client = requireClient();
  const ids = await cloudListBinIds(userId);
  if (ids.length === 0) return;
  await client.from("conversations").delete().match({ user_id: userId }).in("chat_id", ids);
  const { error } = await client.from("chats").delete().match({ user_id: userId }).in("chat_id", ids);
  if (error) throw new Error(error.message);
}

async function cloudListBinIds(userId: string): Promise<string[]> {
  const client = requireClient();
  const { data, error } = await client
    .from("chats")
    .select("chat_id")
    .eq("user_id", userId)
    .not("deleted_at", "is", null);
  if (error) throw new Error(error.message);
  return (data ?? []).map((row) => (row as { chat_id: string }).chat_id);
}

// ---- provider configuration (non-secret parts) ----------------------------

export interface StoredProviderConfig {
  provider: string;
  modelId: string;
  baseUrl: string | null;
  temperature: number | null;
  maxTokens: number | null;
  keyInBrowser: boolean;
}

export async function cloudLoadProviderConfig(userId: string): Promise<StoredProviderConfig | null> {
  const client = requireClient();
  const { data, error } = await client
    .from("provider_configs")
    .select("provider, model_id, base_url, temperature, max_tokens, key_in_browser")
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const row = data as {
    provider: string;
    model_id: string;
    base_url: string | null;
    temperature: number | null;
    max_tokens: number | null;
    key_in_browser: boolean;
  };
  return {
    provider: row.provider,
    modelId: row.model_id,
    baseUrl: row.base_url,
    temperature: row.temperature,
    maxTokens: row.max_tokens,
    keyInBrowser: row.key_in_browser,
  };
}

export async function cloudSaveProviderConfig(
  userId: string,
  config: StoredProviderConfig,
): Promise<void> {
  const client = requireClient();
  const { error } = await client.from("provider_configs").upsert({
    user_id: userId,
    provider: config.provider,
    model_id: config.modelId,
    base_url: config.baseUrl,
    temperature: config.temperature,
    max_tokens: config.maxTokens,
    key_in_browser: config.keyInBrowser,
  });
  if (error) throw new Error(error.message);
}

// ---- profile ---------------------------------------------------------------

export interface CloudProfile {
  displayName: string;
  email: string | null;
  avatar: string | null;
  createdAt: string | null;
}

export async function cloudLoadProfile(userId: string): Promise<CloudProfile | null> {
  const client = requireClient();
  const { data, error } = await client
    .from("profiles")
    .select("display_name, avatar, created_at")
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const row = data as { display_name: string; avatar: string | null; created_at: string | null };
  return { displayName: row.display_name, email: null, avatar: row.avatar, createdAt: row.created_at };
}

export async function cloudSaveProfile(
  userId: string,
  patch: { displayName: string; email: string | null; avatar: string | null },
): Promise<void> {
  const client = requireClient();
  const { error } = await client
    .from("profiles")
    .upsert({
      user_id: userId,
      display_name: patch.displayName,
      email: patch.email,
      avatar: patch.avatar,
    });
  if (error) throw new Error(error.message);
}

/** Guard mirroring the RLS boundary: never operate without a session. */
export function requireCloudUser(): string {
  if (!authState.userId) {
    throw new Error("Sign in required.");
  }
  return authState.userId;
}
