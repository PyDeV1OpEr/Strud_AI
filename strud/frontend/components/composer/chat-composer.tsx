"use client";

// Floating glass composer — the most important interaction surface.

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowUp, Paperclip, X } from "lucide-react";

import type { Attachment } from "@/types";

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  attachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
  onSelectAttachment: (file: File) => void;
}

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_IMAGE_BYTES = 8 * 1024 * 1024; // 8 MB

export function ChatComposer({
  value,
  onChange,
  onSend,
  disabled,
  attachments,
  onRemoveAttachment,
  onSelectAttachment,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rejectNote, setRejectNote] = useState<string | null>(null);

  // Auto-resize up to a max height.
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [value]);

  const canSend = (value.trim().length > 0 || attachments.length > 0) && !disabled;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) onSend();
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setRejectNote("Only PNG, JPEG or WebP images are supported.");
        setTimeout(() => setRejectNote(null), 2600);
        continue;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setRejectNote("Image is too large. Try one under 8 MB.");
        setTimeout(() => setRejectNote(null), 2600);
        continue;
      }
      onSelectAttachment(file);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[850px] px-4 pb-4 sm:px-6">
      {/* Rejected-file note */}
      {rejectNote && (
        <p className="mb-2 text-center text-xs text-amber-300/90" role="status">
          {rejectNote}
        </p>
      )}

      {/* Attachment previews */}
      {attachments.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-2">
          {attachments.map((attachment) => (
            <motion.div
              key={attachment.id}
              initial={{ opacity: 0, scale: 0.9, y: 6 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.16 }}
              className="group relative h-16 w-16 overflow-hidden rounded-xl border border-[var(--color-hairline)]"
            >
              <img
                src={attachment.url}
                alt={attachment.name}
                className="h-full w-full object-cover"
              />
              <button
                onClick={() => onRemoveAttachment(attachment.id)}
                aria-label={`Remove ${attachment.name}`}
                className="absolute right-1 top-1 rounded-full bg-black/60 p-0.5 text-white opacity-0 backdrop-blur transition-opacity hover:bg-black/80 group-hover:opacity-100 focus-visible:opacity-100"
              >
                <X size={12} strokeWidth={2} />
              </button>
            </motion.div>
          ))}
        </div>
      )}

      {/* Input shell */}
      <div className="glass-strong flex items-end gap-1.5 rounded-[26px] p-2 pl-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.35)] transition-colors focus-within:border-emerald-400/30">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          multiple
          className="hidden"
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          aria-label="Attach an image"
          className="mb-0.5 rounded-full p-2.5 text-[var(--color-ink-muted)] transition-colors hover:bg-white/[0.07] hover:text-[var(--color-ink)]"
        >
          <Paperclip size={18} strokeWidth={1.75} />
        </button>

        <label className="sr-only" htmlFor="strud-composer">
          Ask Strud anything
        </label>
        <textarea
          id="strud-composer"
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={(event) => {
            const files = event.clipboardData.files;
            if (files.length > 0) {
              event.preventDefault();
              handleFiles(files);
            }
          }}
          placeholder="Ask Strud anything..."
          className="scroll-slim max-h-[180px] flex-1 resize-none bg-transparent py-2.5 text-[15px] leading-relaxed text-[var(--color-ink)] outline-none placeholder:text-[var(--color-ink-muted)]"
        />

        <motion.button
          onClick={onSend}
          disabled={!canSend}
          aria-label="Send message"
          whileTap={canSend ? { scale: 0.82 } : undefined}
          whileHover={canSend ? { scale: 1.06 } : undefined}
          transition={{ type: "spring", stiffness: 500, damping: 26 }}
          className={`mb-0.5 flex h-9 w-9 items-center justify-center rounded-full transition-all duration-150 ${
            canSend
              ? "bg-emerald-400 text-emerald-950 shadow-[0_1px_0_rgba(255,255,255,0.3)_inset]"
              : "bg-white/[0.06] text-[var(--color-ink-muted)]"
          }`}
        >
          <ArrowUp size={17} strokeWidth={2.2} />
        </motion.button>
      </div>

      <p className="mt-2 text-center text-[11px] text-[var(--color-ink-muted)]">
        Strud can make mistakes. Verify important information against your
        resource book.
      </p>
    </div>
  );
}
