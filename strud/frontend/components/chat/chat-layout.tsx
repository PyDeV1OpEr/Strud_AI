"use client";

// Main application shell — sidebar + chat area + composer + dialogs.

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Menu } from "lucide-react";
import {
  fetchChats,
  fetchDeletedChats,
  restoreChat,
  permanentlyDeleteChat,
  emptyRecycleBin,
  fetchProjects,
  createProject,
  updateProject,
  deleteProject,
  moveChatToProject,
  fetchProfile,
  persistDisplayName,
  persistTitle,
} from "@/lib/api";
import { getUserId } from "@/lib/user-id";
import { chatStore } from "@/lib/store/chat-store";
import type { Chat, Project } from "@/types";
import { RecycleBin } from "./recycle-bin";

import { useChatStore } from "@/hooks/use-chats";
import { Sidebar } from "@/components/sidebar/sidebar";
import { ChatMessages } from "./chat-messages";
import { EmptyState } from "./empty-state";
import { ChatComposer } from "@/components/composer/chat-composer";
import { ProfileMenu } from "@/components/profile/profile-menu";
import { ProfileDialog, type UserProfile } from "@/components/profile/profile-dialog";
import { SignInDialog } from "@/components/profile/sign-in-dialog";
import { useAuth } from "@/lib/auth";
import * as cloudChats from "@/lib/api/cloud-chats";
import {
  AboutDialog,
  DeleteChatDialog,
} from "@/components/profile/dialogs";
import {
  ProjectDialog,
  DeleteProjectDialog,
  RenameChatDialog,
} from "@/components/sidebar/project-dialogs";
import { StrudLogo } from "@/components/profile/strud-logo";
import { Toast } from "@/components/ui/primitives";
import { SettingsControlCenter } from "@/components/settings/settings-control-center";
import { applyAppearanceToDOM, getStoredAppearance } from "@/lib/preferences";
import { isDemoMode, STRUD_REPO_URL } from "@/lib/demo";


export function ChatLayout() {
  const store = useChatStore();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsInitialTab, setSettingsInitialTab] = useState<
    "profile" | "analytics" | "models" | "knowledge" | "memory" | "privacy" | "appearance" | "chat" | "diagnostics" | "shortcuts"
  >("profile");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recycleOpen, setRecycleOpen] = useState(false);
  const [deletedChats, setDeletedChats] = useState<Chat[]>([]);

  /* ---- projects + profile state ---- */
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectDialog, setProjectDialog] = useState<
    { mode: "create" } | { mode: "edit"; project: Project } | null
  >(null);
  const [deleteProjectTarget, setDeleteProjectTarget] = useState<Project | null>(null);
  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profile, setProfile] = useState<UserProfile>({
    displayName: "Student",
    email: null,
    avatar: null,
    joinedAt: null,
  });
  const [profileSaving, setProfileSaving] = useState(false);
  const [signInOpen, setSignInOpen] = useState(false);
  const auth = useAuth();

  // The send path raises a sign-in request; open the real OAuth dialog.
  useEffect(() => {
    if (store.signInRequested) {
      setSignInOpen(true);
      store.clearSignInRequested();
    }
  }, [store.signInRequested, store]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 2200);
  }, []);

  // Server sync: chats, projects, and the local profile. Offline usage
  // falls back to the cached state without any project features.
  // Demo mode has no backend at all — skip the sync entirely so the
  // preview never fires requests it cannot complete.
  useEffect(() => {
    if (isDemoMode()) return;
    let cancelled = false;
    void fetchProjects(getUserId())
      .then((loaded) => {
        if (!cancelled) setProjects(loaded);
      })
      .catch(() => {
        if (!cancelled)
          showToast("Projects need the backend running — showing cached state");
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  // ---- profile: signed-in (Google-verified) vs local anonymous ----------
  // Signed in: prepopulate from Google user metadata, then merge the
  // user's persisted editable fields (profiles table, RLS private).
  // Signed out: the backend local profile (or the Student default).
  useEffect(() => {
    let cancelled = false;
    if (auth.user) {
      const meta = auth.user.user_metadata as {
        name?: string;
        full_name?: string;
        email?: string;
        picture?: string;
        avatar_url?: string;
        email_verified?: boolean;
      };
      const googleProfile: UserProfile = {
        displayName: meta.full_name || meta.name || meta.email?.split("@")[0] || "Student",
        email: auth.user.email ?? meta.email ?? null,
        avatar: meta.picture ?? meta.avatar_url ?? null,
        joinedAt: auth.user.created_at ?? null,
      };
      // Persist the auto-populated profile once (upsert keeps manual edits).
      void cloudChats
        .cloudSaveProfile(auth.user.id, {
          displayName: googleProfile.displayName,
          email: googleProfile.email,
          avatar: googleProfile.avatar,
        })
        .catch(() => undefined);
      void cloudChats
        .cloudLoadProfile(auth.user.id)
        .then((stored) => {
          if (cancelled || !stored) {
            if (!cancelled) setProfile(googleProfile);
            return;
          }
          const storedRow = stored as { displayName?: string };
          setProfile({
            ...googleProfile,
            displayName: storedRow.displayName?.trim() || googleProfile.displayName,
          });
        })
        .catch(() => {
          if (!cancelled) setProfile(googleProfile);
        });
    } else {
      if (isDemoMode()) return; // no local profile store without a backend
      void fetchProfile(getUserId())
        .then((loaded) => {
          if (!cancelled) {
            setProfile((current) => ({ ...current, displayName: loaded.displayName }));
          }
        })
        .catch(() => {
          /* anonymous "Student" default is fine offline */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [auth.user]);

  const refreshProjectsAndChats = useCallback(async () => {
    const [loadedProjects, loadedChats] = await Promise.all([
      fetchProjects(getUserId()),
      fetchChats(getUserId()),
    ]);
    setProjects(loadedProjects);
    if (loadedChats.length > 0) chatStore.set(loadedChats);
  }, []);

  const refreshProjects = useCallback(async () => {
    setProjects(await fetchProjects(getUserId()));
  }, []);

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

  const handleSelectChat = (id: string) => {
    store.selectChat(id);
    setDrawerOpen(false);
  };

  const handleNewChat = useCallback(() => {
    store.newChat();
    setDrawerOpen(false);
  }, [store]);

  const handleSelectProject = async (id: string | null) => {
    store.setActiveProject(id);
    // Leaving project scope also leaves a project chat selection so the
    // auto-selection picks the newest ordinary chat.
    if (!id) store.newChat();
    else if (id) {
      // Jump to the newest chat inside the project, if any.
      const projectChats = chatStore
        .getSnapshot()
        .filter((chat) => chat.projectId === id);
      store.selectChat(projectChats[0]?.id ?? "");
      if (!projectChats[0]) store.newChat();
    }
    setDrawerOpen(false);
    void refreshProjects().catch(() => undefined);
  };

  const isEmpty = !store.activeChat || store.activeChat.messages.length === 0;

  /** Opens the confirmation dialog; removal happens after confirm. */
  const requestDeleteChat = (id: string) => setDeleteTarget(id);
  const openRecycleBin = () => { setRecycleOpen(true); void fetchDeletedChats(getUserId()).then(setDeletedChats).catch(() => showToast("Couldn't load Recycle Bin")); };

  // Project flows ---------------------------------------------------

  const submitProjectDialog = async (name: string, description: string) => {
    const editing =
      projectDialog?.mode === "edit" ? projectDialog.project : null;
    setProjectDialog(null);
    try {
      if (editing) {
        await updateProject(getUserId(), editing.id, name, description);
        showToast("Project updated");
      } else {
        await createProject(getUserId(), name, description);
        showToast("Project created");
      }
      await refreshProjectsAndChats();
    } catch {
      showToast("Couldn't save the project — is the backend running?");
    }
  };

  const confirmDeleteProject = async () => {
    const project = deleteProjectTarget;
    setDeleteProjectTarget(null);
    if (!project) return;
    try {
      await deleteProject(getUserId(), project.id);
      if (store.activeProjectId === project.id) store.setActiveProject(null);
      await refreshProjectsAndChats();
      showToast("Project deleted — its chats are now ordinary chats");
    } catch {
      showToast("Couldn't delete that project");
    }
  };

  const moveChat = async (chat: Chat, projectId: string | null) => {
    try {
      await moveChatToProject(chat.id, getUserId(), projectId);
      chatStore.set(
        chatStore
          .getSnapshot()
          .map((item) =>
            item.id === chat.id
              ? { ...item, projectId: projectId ?? undefined }
              : item,
          ),
      );
      await refreshProjects();
      if (store.activeProjectId && store.activeProjectId !== projectId) {
        store.newChat(); // chat left the current project view
      }
      showToast(projectId ? "Chat moved to project" : "Chat removed from project");
    } catch {
      showToast("Couldn't move that chat — is the backend running?");
    }
  };

  const submitRenameChat = async (title: string) => {
    const chat = renameTarget;
    setRenameTarget(null);
    if (!chat || !title) return;
    chatStore.set(
      chatStore
        .getSnapshot()
        .map((item) => (item.id === chat.id ? { ...item, title } : item)),
    );
    try {
      await persistTitle(chat.id, getUserId(), title);
    } catch {
      showToast("Renamed locally — couldn't reach the backend to save");
      return;
    }
    showToast("Chat renamed");
  };

  // Profile flow ----------------------------------------------------

  const submitProfile = async (displayName: string) => {
    setProfileSaving(true);
    try {
      if (auth.user) {
        // Signed in: persist to the RLS-protected profiles table (owner = sub).
        await cloudChats.cloudSaveProfile(auth.user.id, {
          displayName,
          email: auth.user.email ?? null,
          avatar:
            (auth.user.user_metadata as { picture?: string } | null)?.picture ?? null,
        });
        setProfile((current) => ({ ...current, displayName }));
      } else {
        const saved = await persistDisplayName(getUserId(), displayName);
        setProfile((current) => ({ ...current, displayName: saved.displayName }));
      }
      setProfileOpen(false);
      showToast("Profile updated");
    } catch {
      showToast(auth.user ? "Couldn't save your name. Try again." : "Couldn't save your name — is the backend running?");
    } finally {
      setProfileSaving(false);
    }
  };

  // Apply stored appearance preferences on mount (SSR-safe).
  useEffect(() => {
    applyAppearanceToDOM(getStoredAppearance());
  }, []);

  // Global keyboard shortcuts.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      const target = event.target as HTMLElement | null;
      const inInput = target?.matches("input, textarea, [contenteditable='true']");

      // Cmd/Ctrl+K → Open Settings Control Center
      if (mod && event.key === "k" && !inInput) {
        event.preventDefault();
        setSettingsOpen(true);
        return;
      }

      // Cmd/Ctrl+Shift+O → New Chat
      if (mod && event.shiftKey && event.key === "O") {
        event.preventDefault();
        handleNewChat();
        return;
      }

      // Cmd/Ctrl+B → Toggle sidebar drawer (mobile) / no-op on desktop
      if (mod && event.key === "b" && !inInput) {
        event.preventDefault();
        setDrawerOpen((prev) => !prev);
        return;
      }

      // Cmd/Ctrl+/ → Jump to Keyboard Shortcuts tab inside Settings
      if (mod && event.key === "/" && !inInput) {
        event.preventDefault();
        setSettingsOpen(true);
        setSettingsInitialTab("shortcuts");
        return;
      }

      // Cmd/Ctrl+Backspace → Delete active chat
      if (mod && event.key === "Backspace" && !deleteTarget && !inInput) {
        if (!store.activeChatId) return;
        event.preventDefault();
        setDeleteTarget(store.activeChatId);
        return;
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [deleteTarget, store.activeChatId, handleNewChat]);

  const sidebarProps = {
    chats: store.chats,
    activeChatId: store.activeChatId,
    projects,
    activeProjectId: store.activeProjectId,
    onCreateProject: () => setProjectDialog({ mode: "create" }),
    onSelectProject: (id: string | null) => void handleSelectProject(id),
    onEditProject: (project: Project) => setProjectDialog({ mode: "edit", project }),
    onDeleteProject: (project: Project) => setDeleteProjectTarget(project),
    onMoveChatToProject: (chat: Chat, projectId: string | null) => void moveChat(chat, projectId),
    onNewChat: handleNewChat,
    onSelectChat: handleSelectChat,
    onRenameChat: (chat: Chat) => setRenameTarget(chat),
    onDeleteChat: requestDeleteChat,
    onOpenSettings: () => setSettingsOpen(true),
    onOpenAbout: () => setAboutOpen(true),
    onOpenRecycleBin: openRecycleBin,
  };

  return (
    <div className="flex h-dvh gap-2.5 p-2.5">
      {/* ---- Sidebar: inline on desktop ------------------------------- */}
      <aside className="hidden w-72 shrink-0 lg:block">
        <Sidebar {...sidebarProps} />
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
              <Sidebar {...sidebarProps} />
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
              {store.activeProjectId && (
                <span className="text-[13px] text-[var(--color-ink-muted)]">
                  {projects.find((p) => p.id === store.activeProjectId)?.name}
                </span>
              )}
            </div>
          </div>
          <ProfileMenu
            onOpenProfile={() => setProfileOpen(true)}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenAbout={() => setAboutOpen(true)}
          />
        </header>

        {/* Public-demo notice: an honest frontend-only preview state. */}
        {isDemoMode() && (
          <div
            role="status"
            className="mx-3 mb-1 flex flex-wrap items-baseline gap-x-2 rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.04] px-4 py-2.5 text-[12.5px] leading-relaxed text-[var(--color-ink-secondary)]"
          >
            <span className="font-medium text-[var(--color-ink)]">
              Public preview.
            </span>
            <span>
              Live AI tutoring runs locally — the{" "}
              <a
                href={STRUD_REPO_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="text-emerald-300 underline decoration-emerald-400/40 underline-offset-2 hover:text-emerald-200"
              >
                GitHub repository ↗
              </a>{" "}
              has the complete setup guide.
            </span>
          </div>
        )}

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
              isGenerating={store.isGenerating}
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
              isGenerating={store.isGenerating}
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

        {/* Local chats import banner: never auto-uploaded; explicit consent only. */}
        {store.importableLocalChats && store.importableLocalChats.length > 0 && (
          <div className="glass-strong pointer-events-auto fixed inset-x-4 bottom-24 z-40 mx-auto flex max-w-md flex-col gap-2 rounded-2xl p-3.5 sm:left-6 sm:right-auto">
            <p className="text-[13px] font-medium text-[var(--color-ink)]">
              Import {store.importableLocalChats.length} local chat{store.importableLocalChats.length === 1 ? "" : "s"}?
            </p>
            <p className="text-[12px] leading-relaxed text-[var(--color-ink-muted)]">
              Chats made before you signed in are stored only in this browser.
              Importing copies them into your account — nothing is uploaded
              without your confirmation.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={store.dismissImportableLocalChats}
                className="rounded-lg px-3 py-1.5 text-[12px] text-[var(--color-ink-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-ink)]"
              >
                Not now
              </button>
              <button
                onClick={() => void store.importLocalChats()}
                className="rounded-lg bg-emerald-400/90 px-3 py-1.5 text-[12px] font-medium text-emerald-950 hover:bg-emerald-300"
              >
                Import to my account
              </button>
            </div>
          </div>
        )}
      </main>

      {/* ---- Dialogs ------------------------------------------------------ */}
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
      <SettingsControlCenter
        key={settingsOpen ? `settings-${settingsInitialTab}` : "settings-closed"}
        open={settingsOpen}
        initialTab={settingsInitialTab}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsInitialTab("profile");
        }}
        onChatsCleared={() => {
          void fetchChats(getUserId()).then((chats) => {
            chatStore.set(chats);
            store.newChat();
          }).catch(() => undefined);
        }}
      />
      <ProfileDialog
        key={profileOpen ? `profile-open-${profile.displayName}` : "profile-closed"}
        open={profileOpen}
        userId={getUserId()}
        profile={profile}
        signedIn={Boolean(auth.user)}
        saving={profileSaving}
        onClose={() => setProfileOpen(false)}
        onSave={(displayName) => void submitProfile(displayName)}
      />
      <SignInDialog
        open={signInOpen}
        onClose={() => setSignInOpen(false)}
      />
      <ProjectDialog
        key={
          projectDialog
            ? `project-${projectDialog.mode}-${projectDialog.mode === "edit" ? projectDialog.project.id : "new"}`
            : "project-closed"
        }
        open={projectDialog !== null}
        project={projectDialog?.mode === "edit" ? projectDialog.project : null}
        onClose={() => setProjectDialog(null)}
        onSubmit={(name, description) => void submitProjectDialog(name, description)}
      />
      <DeleteProjectDialog
        open={deleteProjectTarget !== null}
        project={deleteProjectTarget}
        onCancel={() => setDeleteProjectTarget(null)}
        onConfirm={() => void confirmDeleteProject()}
      />
      <RenameChatDialog
        key={renameTarget ? `rename-${renameTarget.id}` : "rename-closed"}
        open={renameTarget !== null}
        chat={renameTarget}
        onClose={() => setRenameTarget(null)}
        onSubmit={(title) => void submitRenameChat(title)}
      />
      <RecycleBin open={recycleOpen} chats={deletedChats} onClose={() => setRecycleOpen(false)} onRestore={async (id) => { await restoreChat(id, getUserId()); const refreshed = await fetchChats(getUserId()); chatStore.set(refreshed); store.selectChat(id); setDeletedChats((items) => items.filter((chat) => chat.id !== id)); showToast("Chat restored"); }} onPermanentDelete={async (id) => { await permanentlyDeleteChat(id, getUserId()); setDeletedChats((items) => items.filter((chat) => chat.id !== id)); showToast("Chat permanently deleted"); }} onEmpty={async () => { await emptyRecycleBin(getUserId()); setDeletedChats([]); showToast("Recycle Bin emptied"); void refreshProjects().catch(() => undefined); }} />
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
                void refreshProjects().catch(() => undefined);
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
