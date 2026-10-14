// ------------------------------------------------------------
// Strud AI — profile API client
//
// Edits the local per-browser profile in the backend. This is an
// anonymous local identity, NOT an authenticated account.
// ------------------------------------------------------------

import type { Profile } from "@/types";
import { BACKEND_URL } from "./errors";

export async function fetchProfile(userId: string): Promise<Profile> {
  const response = await fetch(
    `${BACKEND_URL}/api/profile?user_id=${encodeURIComponent(userId)}`,
  );
  if (!response.ok) return { displayName: "Student" };
  const body = (await response.json()) as { display_name?: string };
  return { displayName: body.display_name?.trim() || "Student" };
}

export async function persistDisplayName(
  userId: string,
  displayName: string,
): Promise<Profile> {
  const response = await fetch(`${BACKEND_URL}/api/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, displayName }),
  });
  if (!response.ok) throw new Error(`Could not save the name (${response.status})`);
  const body = (await response.json()) as { display_name?: string };
  if (!body.display_name) throw new Error("Backend returned no display name.");
  return { displayName: body.display_name };
}
