// Identity for scoping server data.
//
// Signed in: the verified Google account subject (auth.uid) — every
// Supabase/RLS query and backend request is scoped by it.
// Signed out: a stable anonymous per-browser id preserved from the
// original local deployment, so pre-existing local history survives.

import { authState } from "@/lib/auth-state";

const STORAGE_KEY = "strud.user-id.v1";

function anonymousId(): string {
  if (typeof window === "undefined") return "server";
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const userId = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, userId);
    return userId;
  } catch {
    // localStorage can be disabled; a per-page id still avoids a shared user.
    return crypto.randomUUID();
  }
}

export function getUserId(): string {
  return authState.userId ?? anonymousId();
}

/** True when the current identity is the signed-in Google account. */
export function isSignedIn(): boolean {
  return authState.userId !== null;
}
