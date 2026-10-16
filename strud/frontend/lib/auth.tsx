// ------------------------------------------------------------
// Strud AI — Google auth context (Supabase Auth)
//
// Real session management: restore on load, react to token refresh,
// sign-in via Google OAuth (PKCE), sign-out, and a clear error path.
// Everything downstream (chats, profile, provider settings) derives
// its ownership from session.user.id — never from browser input.
// ------------------------------------------------------------

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";

import { getSupabase } from "@/lib/supabase";
import { setAuthState } from "@/lib/auth-state";

export interface AuthValue {
  /** Supabase session, or null while signed out / not configured. */
  session: Session | null;
  user: User | null;
  /** True while the initial session is being restored. */
  initializing: boolean;
  loading: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

function friendlyAuthError(message: string): string {
  if (/provider is not enabled|unsupported provider/i.test(message)) {
    return "Google sign-in isn't enabled on the server yet. The owner needs to enable the Google provider in the Supabase dashboard.";
  }
  if (/redirect|url/i.test(message)) {
    return "Strud couldn't complete the Google redirect. Check the allowed redirect URLs in the Supabase auth settings.";
  }
  if (/network|fetch/i.test(message)) {
    return "Strud couldn't reach the auth server. Check your connection and try again.";
  }
  return "Google sign-in failed. Please try again.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const supabase = getSupabase();
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(supabase ? true : false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore + subscribe: pick up Google OAuth returns, token refreshes
  // and multi-tab sign-outs through the single auth state channel.
  useEffect(() => {
    if (!supabase) {
      setInitializing(false);
      return;
    }
    let cancelled = false;
    void supabase.auth
      .getSession()
      .then(({ data }) => {
        if (cancelled) return;
        setSession(data.session ?? null);
        setAuthState(data.session?.user.id ?? null, data.session?.access_token ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setSession(null);
      })
      .finally(() => {
        if (!cancelled) setInitializing(false);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (cancelled) return;
      setSession(nextSession ?? null);
      setInitializing(false);
      // Mirror for non-React modules and update the stored token.
      setAuthState(nextSession?.user.id ?? null, nextSession?.access_token ?? null);
      if (nextSession) void supabase.auth.setSession(nextSession);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [supabase]);

  const signInWithGoogle = useCallback(async () => {
    if (!supabase) {
      setError("Sign-in isn't available in this build (no Supabase configuration).");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const redirectTo =
        typeof window !== "undefined" ? window.location.origin : undefined;
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo },
      });
      if (oauthError) setError(friendlyAuthError(oauthError.message));
      // On success the browser redirects to Google; state resumes on return.
    } catch {
      setError("Google sign-in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [supabase]);

  const signOut = useCallback(async () => {
    if (!supabase) return;
    setLoading(true);
    try {
      const { error: signOutError } = await supabase.auth.signOut();
      if (signOutError) setError(friendlyAuthError(signOutError.message));
    } catch {
      setError("Signing out failed. Please try again.");
    } finally {
      setLoading(false);
    }
    // Bridge refresh only after the signOut promise settles.
    setAuthState(null, null);
  }, [supabase]);

  const value = useMemo<AuthValue>(
    () => ({
      session,
      user: session?.user ?? null,
      initializing,
      loading,
      error,
      signInWithGoogle,
      signOut,
      clearError: () => setError(null),
    }),
    [session, initializing, loading, error, signInWithGoogle, signOut],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
