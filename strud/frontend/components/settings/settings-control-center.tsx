"use client";

// STRUD AI — Settings Control Center (FreeBuff AI inspired layout)
// Full-screen dialog with left sidebar grouping and scroll-locked content panel.

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  X,
  User,
  BarChart3,
  Cpu,
  BookOpen,
  Brain,
  Shield,
  Palette,
  MessageSquare,
  Activity,
  Keyboard,
  ChevronRight,
} from "lucide-react";
import { getUserId } from "@/lib/user-id";

// All section components
import { ProfileSection } from "./profile-section";
import { AnalyticsSection } from "./analytics-section";
import { ModelsSection } from "./models-section";
import { KnowledgeBaseSection } from "./knowledge-base-section";
import { MemorySection } from "./memory-section";
import { PrivacySection } from "./privacy-section";
import { AppearanceSection } from "./appearance-section";
import { ChatPreferencesSection } from "./chat-preferences-section";
import { DiagnosticsSection } from "./diagnostics-section";
import { KeyboardShortcutsSection } from "./keyboard-shortcuts-section";

// ---- Tab Definitions -------------------------------------------------------

type TabId =
  | "profile"
  | "analytics"
  | "models"
  | "knowledge"
  | "memory"
  | "privacy"
  | "appearance"
  | "chat"
  | "diagnostics"
  | "shortcuts";

interface TabDef {
  id: TabId;
  label: string;
  icon: React.ElementType;
  group: "GENERAL" | "AI & DATA" | "SYSTEM";
}

const TABS: TabDef[] = [
  // GENERAL group
  { id: "profile", label: "Profile", icon: User, group: "GENERAL" },
  { id: "appearance", label: "Appearance", icon: Palette, group: "GENERAL" },
  { id: "chat", label: "Chat Preferences", icon: MessageSquare, group: "GENERAL" },

  // AI & DATA group
  { id: "analytics", label: "Usage & Analytics", icon: BarChart3, group: "AI & DATA" },
  { id: "models", label: "Model Control", icon: Cpu, group: "AI & DATA" },
  { id: "knowledge", label: "Knowledge Base", icon: BookOpen, group: "AI & DATA" },
  { id: "memory", label: "Memory & Context", icon: Brain, group: "AI & DATA" },
  { id: "privacy", label: "Privacy & Data", icon: Shield, group: "AI & DATA" },

  // SYSTEM group
  { id: "diagnostics", label: "System Diagnostics", icon: Activity, group: "SYSTEM" },
  { id: "shortcuts", label: "Keyboard Shortcuts", icon: Keyboard, group: "SYSTEM" },
];

const GROUPS = ["GENERAL", "AI & DATA", "SYSTEM"] as const;

// ---- Props -----------------------------------------------------------------

interface SettingsControlCenterProps {
  open: boolean;
  onClose: () => void;
  initialTab?: TabId;
  onChatsCleared?: () => void;
}

// ---- Main Component --------------------------------------------------------

export function SettingsControlCenter({
  open,
  onClose,
  initialTab = "profile",
  onChatsCleared,
}: SettingsControlCenterProps) {
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const userId = getUserId();



  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2500);
  }, []);

  // Escape key to close
  useEffect(() => {
    if (!open) return;
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handle);
    // Trap focus in panel
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", handle);
  }, [open, onClose]);

  // Render the active section
  const renderSection = () => {
    switch (activeTab) {
      case "profile":
        return <ProfileSection userId={userId} showToast={showToast} onSaved={() => showToast("Profile saved")} />;
      case "analytics":
        return <AnalyticsSection userId={userId} showToast={showToast} />;
      case "models":
        return <ModelsSection showToast={showToast} />;
      case "knowledge":
        return <KnowledgeBaseSection showToast={showToast} />;
      case "memory":
        return <MemorySection showToast={showToast} />;
      case "privacy":
        return <PrivacySection showToast={showToast} onChatsCleared={onChatsCleared} />;
      case "appearance":
        return <AppearanceSection showToast={showToast} />;
      case "chat":
        return <ChatPreferencesSection showToast={showToast} />;
      case "diagnostics":
        return <DiagnosticsSection showToast={showToast} />;
      case "shortcuts":
        return <KeyboardShortcutsSection />;
      default:
        return null;
    }
  };

  const activeTabDef = TABS.find((t) => t.id === activeTab);

  return (
    <AnimatePresence>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Settings Control Center"
        >
          {/* Backdrop */}
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            aria-label="Close settings"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Main Panel */}
          <motion.div
            ref={panelRef}
            tabIndex={-1}
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={{ duration: 0.22, ease: [0.2, 0.9, 0.3, 1.15] }}
            className="glass-strong relative z-10 flex h-[88vh] max-h-[780px] w-full max-w-5xl overflow-hidden rounded-2xl shadow-2xl shadow-black/60 outline-none border border-white/[0.06]"
          >
            {/* ---- Left Sidebar ---- */}
            <aside className="flex w-56 shrink-0 flex-col border-r border-white/[0.06] bg-white/[0.02]">
              {/* Sidebar Header */}
              <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-400/15 border border-emerald-400/20">
                  <span className="bg-gradient-to-br from-emerald-300 to-emerald-500 bg-clip-text text-base font-bold text-transparent">
                    S
                  </span>
                </div>
                <div>
                  <p className="text-xs font-bold text-[var(--color-ink)]">STRUD AI</p>
                  <p className="text-[10px] text-[var(--color-ink-muted)]">Control Center</p>
                </div>
              </div>

              {/* Tab Groups */}
              <nav className="flex flex-1 flex-col gap-5 overflow-y-auto p-3 scroll-slim">
                {GROUPS.map((group) => {
                  const groupTabs = TABS.filter((t) => t.group === group);
                  return (
                    <div key={group}>
                      <p className="mb-1.5 px-2 text-[9px] font-bold uppercase tracking-widest text-[var(--color-ink-muted)]">
                        {group}
                      </p>
                      <div className="flex flex-col gap-0.5">
                        {groupTabs.map((tab) => {
                          const isActive = activeTab === tab.id;
                          const Icon = tab.icon;
                          return (
                            <button
                              key={tab.id}
                              type="button"
                              onClick={() => setActiveTab(tab.id)}
                              className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[12px] font-medium transition-colors ${
                                isActive
                                  ? "bg-emerald-400/15 text-emerald-300 border border-emerald-400/20"
                                  : "text-[var(--color-ink-secondary)] hover:bg-white/[0.06] hover:text-[var(--color-ink)] border border-transparent"
                              }`}
                              aria-current={isActive ? "page" : undefined}
                            >
                              <Icon
                                size={15}
                                strokeWidth={isActive ? 2.2 : 1.75}
                                className={isActive ? "text-emerald-400" : "text-[var(--color-ink-muted)]"}
                              />
                              <span className="flex-1 truncate">{tab.label}</span>
                              {isActive && (
                                <ChevronRight size={12} className="text-emerald-400/60 shrink-0" />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </nav>

              {/* Sidebar Footer — version */}
              <div className="border-t border-white/[0.06] px-4 py-3">
                <p className="text-[10px] text-[var(--color-ink-muted)]">
                  STRUD AI v0.2.0 · Local-First
                </p>
              </div>
            </aside>

            {/* ---- Content Area ---- */}
            <div className="flex min-w-0 flex-1 flex-col">
              {/* Content Header */}
              <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
                <div>
                  <h2 className="text-base font-semibold text-[var(--color-ink)] flex items-center gap-2">
                    {activeTabDef && (
                      <activeTabDef.icon size={17} className="text-emerald-400" />
                    )}
                    {activeTabDef?.label ?? "Settings"}
                  </h2>
                  <p className="text-[11px] text-[var(--color-ink-muted)] mt-0.5">
                    {activeTabDef?.group}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="rounded-xl p-2 text-[var(--color-ink-muted)] hover:bg-white/[0.07] hover:text-[var(--color-ink)] transition-colors"
                >
                  <X size={18} strokeWidth={1.75} />
                </button>
              </div>

              {/* Scrollable Section Body */}
              <div
                key={activeTab}
                className="flex-1 overflow-y-auto p-6 scroll-slim"
              >
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.18, ease: "easeOut" }}
                  >
                    {renderSection()}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>

            {/* ---- Internal Toast ---- */}
            <AnimatePresence>
              {toast && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  className="absolute bottom-5 left-1/2 z-20 -translate-x-1/2 rounded-full bg-[var(--glass-bg)] border border-white/10 px-4 py-2 text-xs text-[var(--color-ink)] shadow-xl shadow-black/40 backdrop-blur-xl"
                >
                  {toast}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
