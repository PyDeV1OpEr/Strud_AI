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

import type { Attachment, Chat, Message } from "@/types";
import {
  createChat as makeChat,
  sendMessage as apiSendMessage,
  ApiError,
  generateTitle,
  fetchChats,
  persistTitle,
  moveChatToBin,
} from "@/lib/api";
import { chatStore } from "@/lib/store/chat-store";
import { deriveTitle } from "@/lib/title";
import { getUserId } from "@/lib/user-id";

interface PendingAttachment {
  file: File;
  previewUrl: string;
}

interface ChatStoreValue {
  chats: Chat[];
  activeChat: Chat | null;
  activeChatId: string | null;
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

  useEffect(() => {
    let cancelled = false;
    void fetchChats(getUserId()).then((serverChats) => {
      if (cancelled || serverChats.length === 0) return;
      const local = chatStore.getSnapshot();
      const serverIds = new Set(serverChats.map((chat) => chat.id));
      // Retain old browser-only chats while allowing durable server history
      // (including attachments) to be the source of truth for matching IDs.
      chatStore.set([...serverChats, ...local.filter((chat) => !serverIds.has(chat.id))]);
    }).catch(() => {
      // Offline cache remains usable while the backend is unavailable.
    });
    return () => { cancelled = true; };
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
    (chatId: string, message: Message, title?: string) => {
      chatStore.set(
        upsertMessage(chatStore.getSnapshot(), chatId, message, title),
      );
    },
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      const hasAttachments = pendingAttachments.length > 0;
      if ((!trimmed && !hasAttachments) || isGenerating) return;

      setError(null);
      setIsGenerating(true);
      setComposerValue("");

      // Resolve or create the chat for this message.
      const currentChats = chatStore.getSnapshot();
      let chatId = activeChatId;
      let isFirstMessage = false;
      let title: string | undefined;

      if (!chatId || !currentChats.some((chat) => chat.id === chatId)) {
        chatId = makeChat().id;
        isFirstMessage = true;
        title = trimmed ? deriveTitle(trimmed) : "Image question";
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

      appendMessage(chatId, userMessage, title);
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

      try {
        const response = await apiSendMessage({
          chatId,
          userId: getUserId(),
          message: trimmed,
          ...(title ? { title } : {}),
          ...(encodedAttachments.length ? { attachments: encodedAttachments } : {}),
        });

        appendMessage(
          chatId,
          {
            id: response.messageId || crypto.randomUUID(),
            chatId,
            role: "assistant",
            content: response.content,
            createdAt: nowIso(),
            ...(response.sources ? { sources: response.sources } : {}),
          },
          title,
        );
      } catch (caught) {
        const friendly =
          caught instanceof ApiError
            ? caught.friendly
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
      send,
    }),
    [
      chats,
      activeChat,
      activeChatId,
      isGenerating,
      error,
      pendingAttachments,
      composerValue,
      newChat,
      selectChat,
      deleteChat,
      addAttachment,
      removeAttachment,
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
