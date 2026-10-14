"use client";

import { useState } from "react";
import { RotateCcw, Trash2 } from "lucide-react";
import type { Chat } from "@/types";
import { Dialog, Button } from "@/components/ui/primitives";

export function RecycleBin({ open, chats, onClose, onRestore, onPermanentDelete, onEmpty }: {
  open: boolean; chats: Chat[]; onClose: () => void;
  onRestore: (id: string) => Promise<void>; onPermanentDelete: (id: string) => Promise<void>; onEmpty: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState<string | "all" | null>(null);
  const [preview, setPreview] = useState<Chat | null>(null);
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    if (!confirming) return;
    setBusy(true);
    try { if (confirming === "all") await onEmpty(); else await onPermanentDelete(confirming); setConfirming(null); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={onClose} labelledBy="recycle-title">
    <div className="flex items-center justify-between gap-3"><h2 id="recycle-title" className="text-base font-semibold">Recently Deleted</h2>{chats.length > 0 && <Button variant="danger" onClick={() => setConfirming("all")}>Empty Bin</Button>}</div>
    {preview ? <div className="mt-4"><Button variant="ghost" onClick={() => setPreview(null)}>Back to Recycle Bin</Button><p className="mt-3 font-medium">{preview.title}</p><div className="mt-3 max-h-72 space-y-3 overflow-y-auto text-sm">{preview.messages.map((message) => <div key={message.id} className="rounded-lg bg-white/[0.04] p-2.5"><p>{message.content}</p>{message.attachments?.map((attachment) => <img key={attachment.id} src={attachment.url} alt={attachment.name} className="mt-2 max-h-36 rounded-lg" />)}</div>)}</div></div> : confirming ? <div className="mt-4"><p className="text-sm text-[var(--color-ink-secondary)]">{confirming === "all" ? `Permanently delete ${chats.length} conversations? This cannot be undone.` : "Permanently delete this conversation? This cannot be undone."}</p><div className="mt-4 flex justify-end gap-2"><Button variant="ghost" disabled={busy} onClick={() => setConfirming(null)}>Cancel</Button><Button variant="danger" disabled={busy} autoFocus onClick={() => void confirm()}>{busy ? "Deleting…" : "Delete permanently"}</Button></div></div> : chats.length === 0 ? <p className="mt-5 text-sm text-[var(--color-ink-muted)]">Your Recycle Bin is empty.</p> : <ul className="mt-4 max-h-80 space-y-2 overflow-y-auto">{chats.map((chat) => <li key={chat.id} className="rounded-xl border border-[var(--color-hairline-soft)] p-3"><button onClick={() => setPreview(chat)} className="max-w-full truncate text-left text-sm font-medium hover:text-emerald-300">{chat.title}</button><p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">Deleted conversation · {chat.messages.length} messages</p><div className="mt-3 flex gap-2"><Button variant="ghost" disabled={busy} onClick={() => void onRestore(chat.id)}><RotateCcw size={14}/> Restore</Button><Button variant="danger" disabled={busy} onClick={() => setConfirming(chat.id)}><Trash2 size={14}/> Delete</Button></div></li>)}</ul>}
  </Dialog>;
}
