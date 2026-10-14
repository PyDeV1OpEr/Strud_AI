"use client";

import { Keyboard, Monitor, Command } from "lucide-react";

const isMac =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);

const MOD = isMac ? "⌘" : "Ctrl";
const SHIFT = "⇧";

interface ShortcutEntry {
  keys: string[];
  label: string;
  description?: string;
}

interface ShortcutGroup {
  category: string;
  icon: React.ElementType;
  shortcuts: ShortcutEntry[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    category: "Navigation",
    icon: Monitor,
    shortcuts: [
      {
        keys: [MOD, "K"],
        label: "Open Settings",
        description: "Open the AI Control Center settings panel",
      },
      {
        keys: [MOD, SHIFT, "O"],
        label: "New Chat",
        description: "Start a fresh conversation",
      },
      {
        keys: [MOD, "B"],
        label: "Toggle Sidebar",
        description: "Show or hide the chat history sidebar",
      },
      {
        keys: [MOD, "/"],
        label: "Keyboard Shortcuts",
        description: "Jump to this keyboard shortcuts reference",
      },
    ],
  },
  {
    category: "Composing Messages",
    icon: Keyboard,
    shortcuts: [
      {
        keys: ["Enter"],
        label: "Send Message",
        description: "Submit your message (when Enter-to-send is enabled)",
      },
      {
        keys: [SHIFT, "Enter"],
        label: "New Line",
        description: "Insert a line break without sending",
      },
      {
        keys: [MOD, "Enter"],
        label: "Force Send",
        description: "Send regardless of Enter-to-send setting",
      },
      {
        keys: ["Esc"],
        label: "Cancel / Close",
        description: "Close dialogs, dismiss menus, or cancel generation",
      },
    ],
  },
  {
    category: "Chat Management",
    icon: Command,
    shortcuts: [
      {
        keys: [MOD, "Backspace"],
        label: "Delete Active Chat",
        description: "Move the current conversation to Recently Deleted",
      },
    ],
  },
];

function KeyBadge({ label }: { label: string }) {
  return (
    <kbd className="inline-flex min-w-[1.75rem] items-center justify-center rounded-md border border-white/15 bg-white/[0.06] px-1.5 py-0.5 font-mono text-[11px] font-semibold text-[var(--color-ink)] shadow-[0_1px_0_rgba(255,255,255,0.06)_inset]">
      {label}
    </kbd>
  );
}

export function KeyboardShortcutsSection() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h3 className="text-lg font-semibold text-[var(--color-ink)] flex items-center gap-2">
          <Keyboard size={20} className="text-emerald-400" />
          Keyboard Shortcuts
        </h3>
        <p className="text-xs text-[var(--color-ink-muted)]">
          {isMac ? "macOS shortcuts using ⌘ (Command)" : "Windows/Linux shortcuts using Ctrl"}. Global shortcuts work anywhere in the application.
        </p>
      </div>

      {SHORTCUT_GROUPS.map((group) => (
        <div
          key={group.category}
          className="rounded-2xl border border-[var(--color-hairline-soft)] bg-white/[0.03] p-5"
        >
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] flex items-center gap-1.5 mb-4">
            <group.icon size={14} className="text-emerald-400" />
            {group.category}
          </h4>

          <div className="flex flex-col divide-y divide-[var(--color-hairline-soft)]">
            {group.shortcuts.map((shortcut) => (
              <div
                key={shortcut.label}
                className="flex items-center justify-between py-3 gap-4"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-[var(--color-ink)]">{shortcut.label}</p>
                  {shortcut.description && (
                    <p className="text-[11px] text-[var(--color-ink-muted)] mt-0.5">
                      {shortcut.description}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {shortcut.keys.map((key, idx) => (
                    <span key={idx} className="flex items-center gap-1">
                      <KeyBadge label={key} />
                      {idx < shortcut.keys.length - 1 && (
                        <span className="text-[10px] text-[var(--color-ink-muted)]">+</span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 text-[11px] text-[var(--color-ink-muted)]">
        <p>
          All shortcuts are globally registered via <code className="text-emerald-300">keydown</code> listeners.
          Shortcuts are suppressed when focus is inside an input, textarea, or content-editable element.
        </p>
      </div>
    </div>
  );
}
