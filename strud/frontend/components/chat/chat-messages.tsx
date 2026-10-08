"use client";

// Chat message list with smart scrolling and typing indicator.

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowDown } from "lucide-react";

import type { Chat } from "@/types";
import { MessageRow } from "./message";
import { TypingIndicator } from "./typing-indicator";

interface ChatMessagesProps {
  chat: Chat | null;
  isGenerating: boolean;
}

export function ChatMessages({ chat, isGenerating }: ChatMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const lastCount = useRef(0);

  const messages = chat?.messages ?? [];

  // Smooth-follow new content unless the user deliberately scrolled up.
  // The component is remounted per chat (see key in chat-layout), so a
  // chat switch naturally resets userScrolledUp and scrolls to bottom.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const previous = lastCount.current;
    lastCount.current = messages.length;

    if (messages.length === 0) return;
    if (messages.length > previous && !userScrolledUp) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length, userScrolledUp]);

  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setUserScrolledUp(distanceFromBottom > 140);
  };

  return (
    <div className="relative h-full">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="scroll-slim h-full overflow-y-auto"
      >
        <div className="mx-auto flex w-full max-w-[850px] flex-col gap-5 px-4 pb-8 pt-6 sm:px-6">
          {messages.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))}

          {isGenerating && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <TypingIndicator />
            </motion.div>
          )}

          <div ref={bottomRef} className="h-px" />
        </div>
      </div>

      {userScrolledUp && (
        <button
          onClick={() => {
            setUserScrolledUp(false);
            bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
          }}
          aria-label="Jump to latest message"
          className="glass-strong absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full p-2.5 text-[var(--color-ink-secondary)] shadow-xl shadow-black/40 transition-colors hover:text-[var(--color-ink)]"
        >
          <ArrowDown size={16} strokeWidth={1.75} />
        </button>
      )}
    </div>
  );
}
