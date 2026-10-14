// Stable anonymous identity for this local deployment. It prevents separate
// browsers from sharing the server's durable chat and memory records.
const STORAGE_KEY = "strud.user-id.v1";

export function getUserId(): string {
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
