// ------------------------------------------------------------
// Strud AI — auth state bridge
//
// Non-React modules (lib/api, user-id) need the current authenticated
// identity without hooks. AuthProvider mirrors changes here, so API
// calls can dispatch between cloud persistence and the legacy local
// backend using the real session — never client-invented IDs.
// ------------------------------------------------------------

export interface AuthRef {
  /** Google-account subject (auth.uid) when signed in, else null. */
  userId: string | null;
  /** Supabase access token for backend requests, else null. */
  accessToken: string | null;
}

export const authState: AuthRef = {
  userId: null,
  accessToken: null,
};

const listeners = new Set<() => void>();

export function setAuthState(userId: string | null, accessToken: string | null): void {
  authState.userId = userId;
  authState.accessToken = accessToken;
  listeners.forEach((listener) => listener());
}

export function subscribeAuthState(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
