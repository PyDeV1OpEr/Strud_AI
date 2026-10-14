"use client";

// Project create/edit + danger confirm dialogs, and a chat-rename dialog.
// All flows persist through the FastAPI backend (lib/api), never locally.

import { useState } from "react";
import type { Chat, Project } from "@/types";
import { Dialog, Button } from "@/components/ui/primitives";

// ---- Create / edit project -------------------------------------------

export function ProjectDialog({
  open,
  project,
  onClose,
  onSubmit,
}: {
  open: boolean;
  /** Existing project in edit mode; null creates a new one. */
  project: Project | null;
  onClose: () => void;
  onSubmit: (name: string, description: string) => void;
}) {
  // State is initialized on mount; the parent keys this dialog by
  // target/open-state so each open starts from the right values.
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");

  const editing = project !== null;
  const canSubmit = name.trim().length > 0;

  return (
    <Dialog open={open} onClose={onClose} title={editing ? "Edit project" : "New project"} labelledBy="project-dialog-title">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSubmit) return;
          onSubmit(name.trim(), description.trim());
        }}
        className="flex flex-col gap-3"
      >
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--color-ink)]">Name</span>
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={80}
            placeholder="e.g. Ecology revision"
            className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--color-ink)]">
            Description <span className="font-normal text-[var(--color-ink-muted)]">(optional)</span>
          </span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={500}
            rows={2}
            placeholder="What is this project for?"
            className="scroll-slim w-full resize-none rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
          />
        </label>
        <p className="text-xs text-[var(--color-ink-muted)]">
          {editing
            ? "Chats stay in the project with their messages and images."
            : "Group related chats together so they stay organised."}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={!canSubmit}>
            {editing ? "Save changes" : "Create project"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// ---- Delete project ----------------------------------------------------

export function DeleteProjectDialog({
  open,
  project,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  project: Project | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} labelledBy="delete-project-title">
      <h2 id="delete-project-title" className="text-base font-semibold text-[var(--color-ink)]">
        Delete “{project?.name}”?
      </h2>
      <p className="mt-1.5 text-[14px] text-[var(--color-ink-secondary)]">
        The project is removed, but its {project?.chatCount ?? 0}{" "}
        {(project?.chatCount ?? 0) === 1 ? "chat" : "chats"} stay safe and simply
        become ordinary chats. This cannot be undone.
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} autoFocus>
          Delete project
        </Button>
      </div>
    </Dialog>
  );
}

// ---- Rename chat ---------------------------------------------------------

export function RenameChatDialog({
  open,
  chat,
  onClose,
  onSubmit,
}: {
  open: boolean;
  chat: Chat | null;
  onClose: () => void;
  onSubmit: (title: string) => void;
}) {
  const [title, setTitle] = useState(chat?.title ?? "");

  const canSubmit = title.trim().length > 0 && title.trim() !== (chat?.title ?? "").trim();

  return (
    <Dialog open={open} onClose={onClose} title="Rename chat" labelledBy="rename-chat-title">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSubmit) return;
          onSubmit(title.trim());
        }}
        className="flex flex-col gap-3"
      >
        <input
          autoFocus
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={80}
          aria-labelledby="rename-chat-title"
          className="w-full rounded-xl border border-[var(--color-hairline-soft)] bg-white/[0.035] px-3 py-2 text-sm text-[var(--color-ink)] outline-none transition-colors focus:border-emerald-400/40 focus:bg-white/[0.05]"
        />
        <p className="text-xs text-[var(--color-ink-muted)]">
          The new title is saved on the backend and survives refreshes.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={!canSubmit}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
