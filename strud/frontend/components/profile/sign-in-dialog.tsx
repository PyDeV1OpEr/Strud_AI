"use client";

// Sign-in dialog — a real Google OAuth entry point (Supabase Auth).
// Shown from the profile menu and automatically when a signed-out
// user tries to send a message. The unsent draft stays untouched in
// the composer; after sign-in the user can send it immediately.

import { motion } from "motion/react";
import { Sparkles } from "lucide-react";
import { Dialog } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

export function SignInDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { signInWithGoogle, loading, error, clearError } = useAuth();

  return (
    <Dialog open={open} onClose={onClose} labelledBy="sign-in-title">
      <div
        className="flex flex-col items-center gap-4 px-2 pb-1 pt-2 text-center"
        onPointerEnter={clearError}
      >
        <div className="glass-strong flex h-14 w-14 items-center justify-center rounded-2xl text-emerald-300">
          <Sparkles size={22} strokeWidth={1.75} />
        </div>
        <div>
          <h2
            id="sign-in-title"
            className="text-[17px] font-semibold text-[var(--color-ink)]"
          >
            Continue with Google
          </h2>
          <p className="mt-1 max-w-[34ch] text-[13px] leading-relaxed text-[var(--color-ink-muted)]">
            Sign in to send messages, and to keep your chat history, memories
            and provider settings synced to your account.
          </p>
        </div>

        {error && (
          <motion.p
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full rounded-xl border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-[12.5px] leading-relaxed text-red-200"
            role="alert"
          >
            {error}
          </motion.p>
        )}

        <motion.button
          type="button"
          onClick={() => void signInWithGoogle()}
          disabled={loading}
          whileTap={{ scale: 0.97 }}
          className="flex w-full items-center justify-center gap-2.5 rounded-xl bg-white py-2.5 text-sm font-medium text-slate-900 transition-opacity hover:bg-white/90 disabled:pointer-events-none disabled:opacity-55"
        >
          {!loading && (
            <svg aria-hidden="true" viewBox="0 0 48 48" className="h-5 w-5">
              <path
                fill="#EA4335"
                d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
              />
              <path
                fill="#4285F4"
                d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
              />
              <path
                fill="#FBBC05"
                d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
              />
              <path
                fill="#34A853"
                d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
              />
            </svg>
          )}
          {loading ? "Opening Google…" : "Continue with Google"}
        </motion.button>

        <p className="max-w-[36ch] text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
          Your account identifies your private chats, memories and settings on
          Strud&apos;s servers. Your AI provider keys, if you add any, always stay in
          your browser.
        </p>
      </div>
    </Dialog>
  );
}
