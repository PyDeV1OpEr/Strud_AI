// ------------------------------------------------------------
// Strud AI — chat persistence API
//
// Backend chat persistence with localStorage retained as an offline cache.
// ------------------------------------------------------------

import type { Attachment, Chat, Message, Project } from "@/types";
import { loadChats, saveChats } from "@/lib/store/local-chats";
import { BACKEND_URL } from "./errors";
import { authState } from "@/lib/auth-state";
import * as cloud from "./cloud-chats";

/**
 * Dispatch: when the user is signed in with Google, chat data persists in
 * Supabase (RLS-scoped to their account); otherwise the original backend HTTP
 * behavior applies (local deployments). localStorage stays an offline cache
 * in both modes.
 */
const signedIn = (): boolean => authState.userId !== null;

function jsonHeaders(token: string | null): HeadersInit {
  return token
    ? { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
    : { "Content-Type": "application/json" };
}

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
  project_id?: string | null;
  created_at: string;
  updated_at: string;
  messages: Array<{ role: "user" | "assistant"; content: string; created_at: string; attachments?: Attachment[] }>;
};

type StoredProject = {
  project_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  chat_count: number;
};

function toChat(chat: StoredChat): Chat {
  return {
    id: chat.chat_id,
    title: chat.title || "New chat",
    projectId: chat.project_id ?? undefined,
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
  };
}

function toProject(project: StoredProject): Project {
  return {
    id: project.project_id,
    name: project.name,
    description: project.description,
    createdAt: project.created_at,
    updatedAt: project.updated_at,
    chatCount: project.chat_count,
  };
}

/** Load server-owned history; localStorage remains a graceful offline cache. */
export async function fetchChats(userId: string): Promise<Chat[]> {
  if (signedIn()) {
    return cloud.cloudFetchChats(cloud.requireCloudUser());
  }
  const response = await fetch(`${BACKEND_URL}/api/chats?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(`Could not load chats (${response.status})`);
  const body = (await response.json()) as { chats?: StoredChat[] };
  return (body.chats ?? []).map(toChat);
}

/** Full message history for one cloud chat (used on chat switching). */
export async function fetchChatMessages(chatId: string, _userId: string): Promise<Message[] | null> {
  void _userId;
  if (!signedIn()) return null; // backend mode loads messages inline
  return cloud.cloudFetchMessages(chatId, cloud.requireCloudUser());
}

/** Persist one message row for the signed-in user's chat. */
export async function persistMessage(
  chatId: string,
  userId: string,
  message: Omit<Message, "id"> & { id?: string },
): Promise<void> {
  if (signedIn()) {
    await cloud.cloudInsertMessage(chatId, cloud.requireCloudUser(), message);
  }
}

/** Ensure a chat row exists server-side with the given title. */
export async function persistChatRow(
  chatId: string,
  userId: string,
  title: string,
  projectId: string | null,
  createdAt: string,
): Promise<void> {
  if (signedIn()) {
    await cloud.cloudUpsertChat(chatId, cloud.requireCloudUser(), { title, projectId, at: createdAt });
  }
}

/** Sign-in import: migrate a local anonymous chat into the signed-in account. */
export async function importLocalChat(
  userId: string,
  chat: Chat,
): Promise<void> {    await cloud.cloudUpsertChat(chat.id, requireCloud(), {
      title: chat.title,
      projectId: chat.projectId ?? null,
      at: chat.createdAt,
    });
  const client = (await import("@/lib/supabase")).getSupabase();
  const rows = chat.messages.map((message) => ({
    user_id: requireCloud(),
    chat_id: chat.id,
    role: message.role,
    content: message.content,
    attachments_json: message.attachments ?? [],
    sources_json: message.sources ?? [],
    error: message.error ?? null,
    created_at: message.createdAt,
  }));
  if (rows.length) await client!.from("conversations").insert(rows);
}

function requireCloud(): string {
  const user = cloud.requireCloudUser();
  return user;
}

// ---- Projects ------------------------------------------------------------

export async function fetchProjects(userId: string): Promise<Project[]> {
  if (signedIn()) {
    const client = (await import("@/lib/supabase")).getSupabase();
    if (!client) throw new Error("Supabase is not configured.");
    const { data, error } = await client
      .from("projects")
      .select("project_id, name, description, created_at, updated_at")
      .eq("user_id", cloud.requireCloudUser())
      .order("updated_at", { ascending: false });
    if (error) throw new Error(error.message);
    const rows = (data ?? []) as {
      project_id: string;
      name: string;
      description: string;
      created_at: string;
      updated_at: string;
    }[];
    return rows.map((row) => ({
      id: row.project_id,
      name: row.name,
      description: row.description,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      chatCount: 0,
    }));
  }
  const response = await fetch(`${BACKEND_URL}/api/projects?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(`Could not load projects (${response.status})`);
  const body = (await response.json()) as { projects?: StoredProject[] };
  return (body.projects ?? []).map(toProject);
}

export async function createProject(userId: string, name: string, description = ""): Promise<Project> {
  if (signedIn()) {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const client = (await import("@/lib/supabase")).getSupabase();
    if (!client) throw new Error("Supabase is not configured.");
    const { error } = await client.from("projects").insert({
      user_id: cloud.requireCloudUser(),
      project_id: id,
      name,
      description,
      created_at: now,
      updated_at: now,
    });
    if (error) throw new Error(error.message);
    return { id, name, description, createdAt: now, updatedAt: now, chatCount: 0 };
  }
  const response = await fetch(`${BACKEND_URL}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, name, description }),
  });
  if (!response.ok) throw new Error(`Could not create the project (${response.status})`);
  const body = (await response.json()) as { project?: StoredProject };
  if (!body.project) throw new Error("Backend returned no project.");
  return toProject(body.project);
}

export async function updateProject(userId: string, projectId: string, name: string, description = ""): Promise<void> {
  if (signedIn()) {
    const client = (await import("@/lib/supabase")).getSupabase();
    if (!client) throw new Error("Supabase is not configured.");
    const { error } = await client
      .from("projects")
      .update({ name, description, updated_at: new Date().toISOString() })
      .match({ user_id: cloud.requireCloudUser(), project_id: projectId });
    if (error) throw new Error(error.message);
    return;
  }
  const response = await fetch(`${BACKEND_URL}/api/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, name, description }),
  });
  if (!response.ok) throw new Error(`Could not update the project (${response.status})`);
}

/** Deleting a project keeps its chats — they return to ordinary chats. */
export async function deleteProject(userId: string, projectId: string): Promise<void> {
  if (signedIn()) {
    const client = (await import("@/lib/supabase")).getSupabase();
    if (!client) throw new Error("Supabase is not configured.");
    const { error } = await client
      .from("projects")
      .delete()
      .match({ user_id: cloud.requireCloudUser(), project_id: projectId });
    if (error) throw new Error(error.message);
    return;
  }
  const response = await fetch(`${BACKEND_URL}/api/projects/${encodeURIComponent(projectId)}?user_id=${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`Could not delete the project (${response.status})`);
}

export async function moveChatToProject(chatId: string, userId: string, projectId: string | null): Promise<void> {
  if (signedIn()) {
    const client = (await import("@/lib/supabase")).getSupabase();
    if (!client) throw new Error("Supabase is not configured.");
    const { error } = await client
      .from("chats")
      .update({ project_id: projectId })
      .match({ user_id: cloud.requireCloudUser(), chat_id: chatId });
    if (error) throw new Error(error.message);
    return;
  }
  const response = await fetch(`${BACKEND_URL}/api/chats/${encodeURIComponent(chatId)}/project`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, projectId: projectId ?? null }),
  });
  if (!response.ok) throw new Error(`Could not move that chat (${response.status})`);
}

export async function persistTitle(chatId: string, userId: string, title: string): Promise<void> {
  if (signedIn()) {
    await cloud.cloudPersistTitle(chatId, cloud.requireCloudUser(), title);
    return;
  }
  await fetch(`${BACKEND_URL}/api/chats/${encodeURIComponent(chatId)}/title`, {
    method: "PATCH",
    headers: jsonHeaders(authState.accessToken),
    body: JSON.stringify({ userId, title }),
  });
}

async function chatMutation(path: string, method: "POST" | "DELETE", userId: string): Promise<void> {
  const response = await fetch(`${BACKEND_URL}${path}?user_id=${encodeURIComponent(userId)}`, { method });
  if (!response.ok) throw new Error(`Chat update failed (${response.status})`);
}

export async function fetchDeletedChats(userId: string): Promise<Chat[]> {
  if (signedIn()) {
    return cloud.cloudFetchDeletedChats(cloud.requireCloudUser());
  }
  const response = await fetch(`${BACKEND_URL}/api/chats/deleted?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(`Could not load Recycle Bin (${response.status})`);
  const body = (await response.json()) as { chats?: StoredChat[] };
  return (body.chats ?? []).map(toChat);
}

export const moveChatToBin = async (chatId: string, userId: string) => {
  if (signedIn()) {
    await cloud.cloudBinChat(chatId, cloud.requireCloudUser());
    return;
  }
  return chatMutation(`/api/chats/${encodeURIComponent(chatId)}`, "DELETE", userId);
};
export const restoreChat = async (chatId: string, userId: string) => {
  if (signedIn()) {
    await cloud.cloudRestoreChat(chatId, cloud.requireCloudUser());
    return;
  }
  return chatMutation(`/api/chats/${encodeURIComponent(chatId)}/restore`, "POST", userId);
};
export const permanentlyDeleteChat = async (chatId: string, userId: string) => {
  if (signedIn()) {
    await cloud.cloudPurgeChat(chatId, cloud.requireCloudUser());
    return;
  }
  return chatMutation(`/api/chats/${encodeURIComponent(chatId)}/permanent`, "DELETE", userId);
};
export const emptyRecycleBin = async (userId: string) => {
  if (signedIn()) {
    await cloud.cloudEmptyBin(cloud.requireCloudUser());
    return;
  }
  return chatMutation("/api/chats/deleted/all", "DELETE", userId);
};
