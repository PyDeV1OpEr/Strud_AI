"use client";

// Single message presentation: user bubble vs assistant markdown.

import { useState } from "react";
import { motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { Check, Copy } from "lucide-react";

import type { Message } from "@/types";
import { normalizeEscapedBreakTags } from "@/lib/markdown";
import { SourceList } from "./source-list";

export function MessageRow({ message }: { message: Message }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.995 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30, mass: 0.7 }}
    >
      {message.role === "user" ? (
        <UserMessage message={message} />
      ) : (
        <AssistantMessage message={message} />
      )}
    </motion.div>
  );
}

// ------------------------------------------------------------
// User message
// ------------------------------------------------------------

interface UserMessageProps {
  message: Message;
}

function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-[78%] flex-col items-end gap-2">
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2">
            {message.attachments.map((attachment) => (
              <img
                key={attachment.id}
                src={attachment.url}
                alt={attachment.name}
                className="max-h-44 rounded-xl border border-[var(--color-hairline)] object-cover"
              />
            ))}
          </div>
        )}
        {message.content && (
          <div className="glass rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed text-[var(--color-ink)]">
            {message.content}
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------
// Assistant message
// ------------------------------------------------------------

interface AssistantMessageProps {
  message: Message;
}

function AssistantMessage({ message }: AssistantMessageProps) {
  const [copied, setCopied] = useState(false);
  const markdown = normalizeEscapedBreakTags(message.content);

  if (message.error) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-[15px] text-red-300">{message.error}</p>
      </div>
    );
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // Clipboard unavailable — fail silently, this is a convenience action.
    }
  };

  return (
    <div className="group flex flex-col items-start gap-1.5">
      <div className="markdown-body w-full max-w-full">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, rehypeSanitize]}
          components={{
            table: ({ children }) => (
              <div className="markdown-table-wrap">
                <table>{children}</table>
              </div>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>

      {message.sources && message.sources.length > 0 && (
        <SourceList sources={message.sources} />
      )}

      <button
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy response"}
        className="mt-0.5 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[var(--color-ink-muted)] opacity-0 transition-all duration-150 hover:bg-white/[0.06] hover:text-[var(--color-ink-secondary)] focus-visible:opacity-100 group-hover:opacity-100"
      >
        {copied ? (
          <>
            <Check size={13} strokeWidth={2} className="text-emerald-400" />
            Copied
          </>
        ) : (
          <>
            <Copy size={13} strokeWidth={1.75} />
            Copy
          </>
        )}
      </button>
    </div>
  );
}
