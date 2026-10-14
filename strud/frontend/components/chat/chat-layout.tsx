"use client";

// Main application shell — sidebar + chat area + composer + dialogs.

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Menu } from "lucide-react";
import { fetchChats, fetchDeletedChats, restoreChat, permanentlyDeleteChat, emptyRecycleBin } from "@/lib/api";
import { getUserId } from "@/lib/user-id";
import { chatStore } from "@/lib/store/chat-store";
import type { Chat } from "@/types";
import { RecycleBin } from "./recycle-bin";

import { useChatStore } from "@/hooks/use-chats";
import { Sidebar } from "@/components/sidebar/sidebar";
import { ChatMessages } from "./chat-messages";
import { EmptyState } from "./empty-state";
import { ChatComposer } from "@/components/composer/chat-composer";
import { ProfileMenu } from "@/components/profile/profile-menu";
import {
  AboutDialog,
  SettingsDialog,
  DeleteChatDialog,
} from "@/components/profile/dialogs";
import { StrudLogo } from "@/components/profile/strud-logo";
import { Toast } from "@/components/ui/primitives";

export function ChatLayout() {
  const store = useChatStore();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recycleOpen, setRecycleOpen] = useState(false);
  const [deletedChats, setDeletedChats] = useState<Chat[]>([]);

  // Sidebar hidden by default below lg.
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const apply = () => {
      // Desktop keeps the panel inline; mobile closes the drawer.
      if (media.matches) setDrawerOpen(false);
    };
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  const deleteTargetChat = store.chats.find(
    (chat) => chat.id === deleteTarget,
  );

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 2200);
  };

  const handleSelectChat = (id: string) => {
    store.selectChat(id);
    setDrawerOpen(false);
  };

  const handleNewChat = () => {
    store.newChat();
    setDrawerOpen(false);
  };

  const isEmpty = !store.activeChat || store.activeChat.messages.length === 0;

  /** Opens the confirmation dialog; removal happens after confirm. */
  const requestDeleteChat = (id: string) => setDeleteTarget(id);
  const openRecycleBin = () => { setRecycleOpen(true); void fetchDeletedChats(getUserId()).then(setDeletedChats).catch(() => showToast("Couldn't load Recycle Bin")); };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key !== "Backspace" || deleteTarget) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, [contenteditable='true']")) return;
      if (!store.activeChatId) return;
      event.preventDefault();
      setDeleteTarget(store.activeChatId);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [deleteTarget, store.activeChatId]);

  return (
    <div className="flex h-dvh gap-2.5 p-2.5">
      {/* ---- Sidebar: inline on desktop ------------------------------- */}
      <aside className="hidden w-72 shrink-0 lg:block">
        <Sidebar
          chats={store.chats}
          activeChatId={store.activeChatId}
          onNewChat={handleNewChat}
          onSelectChat={store.selectChat}
          onDeleteChat={requestDeleteChat}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenAbout={() => setAboutOpen(true)}
          onOpenRecycleBin={openRecycleBin}
        />
      </aside>

      {/* ---- Sidebar: drawer on mobile/tablet -------------------------- */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              aria-label="Close sidebar"
              onClick={() => setDrawerOpen(false)}
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
            />
            <motion.aside
              initial={{ x: "-108%" }}
              animate={{ x: 0 }}
              exit={{ x: "-108%" }}
              transition={{ type: "spring", stiffness: 420, damping: 38 }}
              className="fixed inset-y-2.5 left-2.5 z-50 w-[290px] lg:hidden"
            >
              <Sidebar
                chats={store.chats}
                activeChatId={store.activeChatId}
                onNewChat={handleNewChat}
                onSelectChat={handleSelectChat}
                onDeleteChat={requestDeleteChat}
                onOpenSettings={() => {
                  setDrawerOpen(false);
                  setSettingsOpen(true);
                }}
                onOpenAbout={() => {
                  setDrawerOpen(false);
                  setAboutOpen(true);
                }}
                onOpenRecycleBin={() => { setDrawerOpen(false); openRecycleBin(); }}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ---- Main column ------------------------------------------------ */}
      <main className="relative flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-3 py-2.5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="Open sidebar"
              className="glass rounded-xl p-2 text-[var(--color-ink-secondary)] transition-colors hover:text-[var(--color-ink)] lg:hidden"
            >
              <Menu size={18} strokeWidth={1.75} />
            </button>
            {/* Compact brand for desktop while chatting */}
            <div className="hidden items-center gap-2 lg:flex">
              <StrudLogo size={22} />
            </div>
          </div>
          <ProfileMenu
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenAbout={() => setAboutOpen(true)}
          />
        </header>

        {/* Messages / empty state */}
        {isEmpty ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1" />
            <div className="flex-1">
              <EmptyState
                onSuggestion={(text) => {
                  store.setComposerValue(text);
                }}
              />
            </div>
            <div className="flex-1" />
            <ChatComposer
              value={store.composerValue}
              onChange={store.setComposerValue}
              onSend={() => void store.send(store.composerValue)}
              disabled={store.isGenerating}
              attachments={store.pendingAttachments.map((a) => ({
                id: a.previewUrl,
                url: a.previewUrl,
                name: a.file.name,
                mimeType: a.file.type,
                size: a.file.size,
              }))}
              onRemoveAttachment={store.removeAttachment}
              onSelectAttachment={store.addAttachment}
            />
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1">
              <ChatMessages
                key={store.activeChat?.id ?? "empty"}
                chat={store.activeChat}
                isGenerating={store.isGenerating}
              />
            </div>
            <ChatComposer
              value={store.composerValue}
              onChange={store.setComposerValue}
              onSend={() => void store.send(store.composerValue)}
              disabled={store.isGenerating}
              attachments={store.pendingAttachments.map((a) => ({
                id: a.previewUrl,
                url: a.previewUrl,
                name: a.file.name,
                mimeType: a.file.type,
                size: a.file.size,
              }))}
              onRemoveAttachment={store.removeAttachment}
              onSelectAttachment={store.addAttachment}
            />
          </>
        )}

        {/* Network/error toast */}
        {store.error && (
          <Toast message={store.error} />
        )}
      </main>

      {/* ---- Dialogs ------------------------------------------------------ */}
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
      <RecycleBin open={recycleOpen} chats={deletedChats} onClose={() => setRecycleOpen(false)} onRestore={async (id) => { await restoreChat(id, getUserId()); const refreshed = await fetchChats(getUserId()); chatStore.set(refreshed); store.selectChat(id); setDeletedChats((items) => items.filter((chat) => chat.id !== id)); showToast("Chat restored"); }} onPermanentDelete={async (id) => { await permanentlyDeleteChat(id, getUserId()); setDeletedChats((items) => items.filter((chat) => chat.id !== id)); showToast("Chat permanently deleted"); }} onEmpty={async () => { await emptyRecycleBin(getUserId()); setDeletedChats([]); showToast("Recycle Bin emptied"); }} />
      <DeleteChatDialog
        open={deleteTarget !== null}
        chatTitle={deleteTargetChat?.title ?? ""}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            void store.deleteChat(deleteTarget).then((moved) => {
              if (moved) {
                setDrawerOpen(false);
                showToast("Moved to Recycle Bin");
              }
            });
          }
          setDeleteTarget(null);
        }}
      />
      <Toast message={toast} />
    </div>
  );
}
