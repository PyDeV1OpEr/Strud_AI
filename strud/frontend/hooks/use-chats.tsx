"use client";

// ------------------------------------------------------------
// Strud AI — chat store (React bindings + local persistence)
//
// Chat history lives in an external store (lib/store/chat-store)
// read through useSyncExternalStore, which is SSR-safe without any
// setState-in-effect hydration pass. UI-only state (active chat,
// composer, attachments) stays in React state here.
// ------------------------------------------------------------

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import type { Attachment, Chat, Message, Source } from "@/types";
import {
  createChat as makeChat,
  sendMessage as apiSendMessage,
  ApiError,
  generateTitle,
  fetchChats,
  fetchChatMessages,
  persistMessage,
  persistChatRow,
  importLocalChat,
  persistTitle,
  moveChatToBin,
} from "@/lib/api";
import { chatStore } from "@/lib/store/chat-store";
import { deriveTitle } from "@/lib/title";
import { authState, subscribeAuthState } from "@/lib/auth-state";
import { isSupabaseConfigured } from "@/lib/supabase";
import { getUserId } from "@/lib/user-id";
import { getStoredChatPrefs, resolveOutputTokens } from "@/lib/preferences";
import {
  getProviderKey,
  loadProviderConfig,
  PROVIDER_PRESETS,
} from "@/lib/provider-config";
import {
  sendDirectChat,
  checkBackendHealth,
} from "@/lib/api/providers";
import { BACKEND_URL } from "@/lib/api/errors";

interface PendingAttachment {
  file: File;
  previewUrl: string;
}

let backendHealthCache: boolean | null = null;

/** Reachability of the FastAPI backend decides RAG vs direct-provider routing. */
async function isBackendReachable(): Promise<boolean> {
  if (backendHealthCache === null) {
    backendHealthCache = await checkBackendHealth(BACKEND_URL);
  }
  return backendHealthCache;
}

interface ChatStoreValue {
  chats: Chat[];
  activeChat: Chat | null;
  activeChatId: string | null;
  /** Active project context; null means the ordinary "all chats" scope. */
  activeProjectId: string | null;
  setActiveProject: (id: string | null) => void;
  isGenerating: boolean;
  error: string | null;
  pendingAttachments: PendingAttachment[];
  composerValue: string;

  setComposerValue: (value: string) => void;
  newChat: () => void;
  selectChat: (id: string) => void;
  deleteChat: (id: string) => Promise<boolean>;
  clearError: () => void;

  addAttachment: (file: File) => void;
  removeAttachment: (id: string) => void;

  /** Set when a send was blocked because the user must sign in first. */
  signInRequested: boolean;
  clearSignInRequested: () => void;
  /** Local (pre-sign-in) chats the user can import into their account. */
  importableLocalChats: Chat[] | null;
  importLocalChats: () => Promise<void>;
  dismissImportableLocalChats: () => void;

  send: (text: string) => Promise<void>;
}

const ChatStoreContext = createContext<ChatStoreValue | null>(null);

function nowIso(): string {
  return new Date().toISOString();
}

/** Pure reducer over the chat list used for every mutation. */
function upsertMessage(
  chats: Chat[],
  chatId: string,
  message: Message,
  title?: string,
  projectId?: string | null,
): Chat[] {
  const exists = chats.some((chat) => chat.id === chatId);
  return exists
    ? chats.map((chat) =>
        chat.id !== chatId
          ? chat
          : {
              ...chat,
              title: title ?? chat.title,
              updatedAt: nowIso(),
              messages: [...chat.messages, message],
            },
      )
    : [
        {
          id: chatId,
          title: title ?? "New chat",
          createdAt: nowIso(),
          updatedAt: nowIso(),
          ...(projectId ? { projectId } : {}),
          messages: [message],
        },
        ...chats,
      ];
}

export function ChatStoreProvider({ children }: { children: ReactNode }) {
  // Persistent history — read from the external store. React renders
  // with the empty server snapshot during hydration, then picks up the
  // localStorage contents in a post-hydration render (no mismatch).
  const chats = useSyncExternalStore(
    chatStore.subscribe,
    chatStore.getSnapshot,
    chatStore.getServerSnapshot,
  );

  const [signInRequested, setSignInRequested] = useState(false);
  const [importableLocalChats, setImportableLocalChats] = useState<Chat[] | null>(null);
  const [signedInUserId, setSignedInUserId] = useState<string | null>(
    typeof window !== "undefined" ? authState.userId : null,
  );

  useEffect(() => subscribeAuthState(() => setSignedInUserId(authState.userId)), []);

  // Cloud history load — keyed on the verified identity, so history loads
  // on sign-in (and reloads correctly after sign-out/sign-in cycling).
  useEffect(() => {
    let cancelled = false;
    const identity = getUserId();
    void fetchChats(identity).then((serverChats) => {
      if (cancelled) return;
      const local = chatStore.getSnapshot();
      const serverIds = new Set(serverChats.map((chat) => chat.id));
      // Retain old browser-only chats while allowing durable server history
      // (including attachments) to be the source of truth for matching IDs.
      chatStore.set([...serverChats, ...local.filter((chat) => !serverIds.has(chat.id))]);
      if (signedInUserId && authState.userId) {
        // Offer a one-time import of local-only (anonymous) chats.
        const candidates = local.filter(
          (chat) => !serverIds.has(chat.id) && chat.messages.length > 0,
        );
        setImportableLocalChats(candidates.length > 0 && !markerSeen() ? candidates : null);
      }
    }).catch(() => {
      // Offline cache remains usable while persistence is unavailable.
    });
    return () => { cancelled = true; };
  }, [signedInUserId]);

  function markerSeen(): boolean {
    try {
      return window.localStorage.getItem("strud.local-import-declined.v1") === authState.userId;
    } catch {
      return true;
    }
  }

  const importLocalChats = useCallback(async () => {
    const candidates = importableLocalChats;
    if (!candidates || !authState.userId) return;
    let imported = 0;
    for (const chat of candidates) {
      try {
        await importLocalChat(authState.userId, chat);
        imported += 1;
      } catch {
        // keep the chat local when its cloud copy fails
      }
    }
    const remaining = chatStore
      .getSnapshot()
      .filter((chat) => !candidates.some((candidate) => candidate.id === chat.id));
    const cloudCopies = await fetchChats(getUserId()).catch(() => [] as Chat[]);
    chatStore.set([...cloudCopies, ...remaining]);
    setImportableLocalChats(null);
    if (imported > 0) {
      setError(`Imported ${imported} local chat${imported === 1 ? "" : "s"} into your account.`);
      setTimeout(() => setError(null), 3000);
    }
  }, [importableLocalChats]);

  const dismissImportableLocalChats = useCallback(() => {
    try {
      if (authState.userId) {
        window.localStorage.setItem("strud.local-import-declined.v1", authState.userId);
      }
    } catch {
      /* storage unavailable */
    }
    setImportableLocalChats(null);
  }, []);

  // undefined = auto (follow the most recent chat), null = explicit
  // "new chat" view, string = explicitly selected chat.
  const [explicitActiveId, setActiveChatId] = useState<string | null | undefined>(
    undefined,
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<
    PendingAttachment[]
  >([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [composerValue, setComposerValue] = useState("");

  const activeChatId =
    explicitActiveId !== undefined ? explicitActiveId : (chats[0]?.id ?? null);

  // ---- chat lifecycle ----

  const newChat = useCallback(() => {
    setActiveChatId(null);
    setError(null);
  }, []);

  const selectChat = useCallback((id: string) => {
    setActiveChatId(id);
    setError(null);
    // Signed in: the authoritative per-chat history comes from the database
    // (the browser cache may hold only a recent window).
    if (!authState.userId) return;
    void fetchChatMessages(id, authState.userId)
      .then((messages: Message[] | null) => {
        if (!messages) return;
        chatStore.set(
          chatStore
            .getSnapshot()
            .map((entry) => (entry.id === id ? { ...entry, messages } : entry)),
        );
      })
      .catch(() => undefined);
  }, []);

  const deleteChat = useCallback(async (id: string) => {
    try {
      await moveChatToBin(id, getUserId());
      const next = chatStore.getSnapshot().filter((chat) => chat.id !== id);
      chatStore.set(next);
      setActiveChatId((active) => active === id ? (next[0]?.id ?? null) : active);
      return true;
    } catch {
      setError("Strud couldn't move that chat to the Recycle Bin.");
      return false;
    }
  }, []);

  // ---- attachments ----

  const addAttachment = useCallback((file: File) => {
    setPendingAttachments((current) => [
      ...current,
      { file, previewUrl: URL.createObjectURL(file) },
    ]);
  }, []);

  const removeAttachment = useCallback((id: string) => {
    setPendingAttachments((current) => {
      const target = current.find((a) => a.previewUrl === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((a) => a.previewUrl !== id);
    });
  }, []);

  // ---- sending ----

  const appendMessage = useCallback(
    (chatId: string, message: Message, title?: string, projectId?: string | null) => {
      chatStore.set(
        upsertMessage(chatStore.getSnapshot(), chatId, message, title, projectId),
      );
    },
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      const hasAttachments = pendingAttachments.length > 0;
      if ((!trimmed && !hasAttachments) || isGenerating) return;

      // ---- sign-in gate ------------------------------------------------
      // The UI stays explorable signed out, but nothing is sent to any AI
      // and nothing is written until the user authenticates.
      if (isSupabaseConfigured() && !authState.userId) {
        setSignInRequested(true);
        return;
      }

      setError(null);
      setIsGenerating(true);
      setComposerValue("");

      // Resolve or create the chat for this message.
      const currentChats = chatStore.getSnapshot();
      let chatId = activeChatId;
      let isFirstMessage = false;
      let chatProject: string | null = null;
      let title: string | undefined;

      if (!chatId || !currentChats.some((chat) => chat.id === chatId)) {
        chatId = makeChat().id;
        isFirstMessage = true;
        title = trimmed ? deriveTitle(trimmed) : "Image question";
        chatProject = activeProjectId;
      } else {
        const current = currentChats.find((chat) => chat.id === chatId);
        isFirstMessage = (current?.messages.length ?? 0) === 0;
        if (isFirstMessage && trimmed) {
          title = deriveTitle(trimmed);
        }
      }

      // Build the user message with attachment previews.
      const attachments: Attachment[] = pendingAttachments.map((a) => ({
        id: a.previewUrl,
        url: a.previewUrl,
        name: a.file.name,
        mimeType: a.file.type,
        size: a.file.size,
      }));

      const userMessage: Message = {
        id: crypto.randomUUID(),
        chatId,
        role: "user",
        content: trimmed,
        createdAt: nowIso(),
        ...(attachments.length ? { attachments } : {}),
      };

      appendMessage(chatId, userMessage, title, chatProject);
      setActiveChatId(chatId);
      setPendingAttachments([]);

      // Convert attachments to base64 for the backend contract.
      const encodedAttachments = await Promise.all(
        attachments.map(async (attachment, index) => {
          const file = pendingAttachments[index].file;
          const data = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
          });
          return {
            name: attachment.name,
            mimeType: attachment.mimeType,
            data,
          };
        }),
      );

      // Persist the chat row + user message when the account is cloud-backed
      // (the backend also keeps its own working copy when it serves the turn).
      const cloudUserId = authState.userId;
      if (cloudUserId) {
        void persistChatRow(chatId, cloudUserId, title ?? "New chat", chatProject, nowIso())
          .catch(() => undefined);
        void persistMessage(chatId, cloudUserId, {
          chatId,
          role: "user",
          content: trimmed,
          createdAt: userMessage.createdAt,
          ...(encodedAttachments.length && attachments.length
            ? {
                attachments: attachments.map((attachment) => ({
                  ...attachment,
                  url: `/api/uploads/${attachment.id}`,
                })),
              }
            : {}),
        }).catch(() => undefined);
      }

      try {
        let assistantContent: string;
        let sources: Source[] | undefined;

        // ---- route: backend (RAG + verification) vs direct provider -------
        const backendReachable = await isBackendReachable();

        const config = cloudUserId
          ? await loadProviderConfig(cloudUserId)
          : null;
        // GPT-OSS remains the backend/RAG route.  Every other selectable
        // provider is called directly, so choosing it changes the model that
        // answers rather than silently falling back to the server default.
        if (backendReachable && (!config || config.provider === "gptoss")) {
          // Per-message generation controls come from the user's persisted
          // chat preferences: the reasoning-effort selector and the output
          // budget (advanced override wins over the length preset).
          const prefs = getStoredChatPrefs();
          const outputTokens = resolveOutputTokens(prefs);
          const response = await apiSendMessage({
            chatId,
            userId: getUserId(),
            message: trimmed,
            ...(title ? { title } : {}),
            ...(chatProject ? { projectId: chatProject } : {}),
            ...(encodedAttachments.length ? { attachments: encodedAttachments } : {}),
            thinkingLevel: prefs.thinkingLevel,
            maxTokens: outputTokens,
          });
          assistantContent = response.content;
          sources = response.sources;
        } else {
          // Direct provider path: the user's own provider + key, browser →
          // provider. No proxy server involved. Ungrounded (no textbook
          // retrieval) — surfaced honestly instead of inventing sources.
          if (cloudUserId && config) {
            if (encodedAttachments.length > 0) {
              throw new ApiError(
                "Image attachments need the AI backend running (they use the vision + retrieval pipeline).",
                "attachments on direct path",
              );
            }
            const apiKey = getProviderKey(cloudUserId);
            const preset = PROVIDER_PRESETS[config.provider];
            if (preset.needsApiKey && !apiKey) {
              throw new ApiError(
                "Add your provider API key in Settings → AI Provider first.",
                "missing key for direct path",
              );
            }
            const history =
              chatStore.getSnapshot().find((entry) => entry.id === chatId)?.messages ?? [];
            const result = await sendDirectChat(
              config,
              apiKey,
              history.filter((message) => message.id !== userMessage.id),
              trimmed,
            );
            assistantContent = result.content;
          } else {
            throw new ApiError("Sign in to send messages.", "no session");
          }
        }

        appendMessage(
          chatId,
          {
            id: crypto.randomUUID(),
            chatId,
            role: "assistant",
            content: assistantContent,
            createdAt: nowIso(),
            ...(sources ? { sources } : {}),
          },
          title,
        );
        if (cloudUserId) {
          void persistMessage(chatId, cloudUserId, {
            chatId,
            role: "assistant",
            content: assistantContent,
            createdAt: nowIso(),
            ...(sources ? { sources } : {}),
          }).catch(() => undefined);
        }
      } catch (caught) {
        const friendly =
          caught instanceof ApiError
            ? caught.friendly
            : caught instanceof Error && caught.message
              ? caught.message
              : "Strud couldn't process that. Please try again.";
        setError(friendly);
        appendMessage(
          chatId,
          {
            id: crypto.randomUUID(),
            chatId,
            role: "assistant",
            content: "",
            createdAt: nowIso(),
            error: friendly,
          },
        );
      } finally {
        setIsGenerating(false);
      }

      // Non-blocking backend title generation (when connected).
      if (isFirstMessage && trimmed) {
        void generateTitle(chatId, trimmed).then((backendTitle) => {
          if (!backendTitle) return;
          const meaningful = backendTitle.trim();
          if (!meaningful || /^(new chat|untitled|chat \d+)$/i.test(meaningful)) return;
          chatStore.set(
            chatStore
              .getSnapshot()
              .map((chat) =>
                chat.id === chatId ? { ...chat, title: meaningful } : chat,
              ),
          );
          void persistTitle(chatId, getUserId(), meaningful);
        });
      }
    },
    [
      activeChatId,
      activeProjectId,
      isGenerating,
      pendingAttachments,
      appendMessage,
    ],
  );

  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === activeChatId) ?? null,
    [chats, activeChatId],
  );

  const value = useMemo<ChatStoreValue>(
    () => ({
      chats,
      activeChat,
      activeChatId,
      activeProjectId,
      setActiveProject: setActiveProjectId,
      isGenerating,
      error,
      pendingAttachments,
      composerValue,
      setComposerValue,
      newChat,
      selectChat,
      deleteChat,
      clearError: () => setError(null),
      addAttachment,
      removeAttachment,
      signInRequested,
      clearSignInRequested: () => setSignInRequested(false),
      importableLocalChats,
      importLocalChats,
      dismissImportableLocalChats,
      send,
    }),
    [
      chats,
      activeChat,
      activeChatId,
      activeProjectId,
      isGenerating,
      error,
      pendingAttachments,
      composerValue,
      newChat,
      selectChat,
      deleteChat,
      addAttachment,
      removeAttachment,
      signInRequested,
      importableLocalChats,
      importLocalChats,
      dismissImportableLocalChats,
      send,
    ],
  );

  return (
    <ChatStoreContext.Provider value={value}>
      {children}
    </ChatStoreContext.Provider>
  );
}

export function useChatStore(): ChatStoreValue {
  const context = useContext(ChatStoreContext);
  if (!context) {
    throw new Error("useChatStore must be used within ChatStoreProvider");
  }
  return context;
}
