// ------------------------------------------------------------
// Strud AI — Supabase browser client
//
// One shared client for Google sign-in + RLS-protected reads/writes
// of the authenticated user's own data. The anon (publishable) key
// here is public by design: it identifies the project and carries NO
// privileged access — every user-owned row is guarded by RLS
// (user_id = auth.uid()).
// ------------------------------------------------------------

"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

let client: SupabaseClient | null = null;

/** Is this build configured for Supabase (auth + cloud persistence)? */
export function isSupabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_KEY);
}

/**
 * Browser Supabase client, created lazily (SSR-safe). Returns null when
 * the app runs without Supabase configuration — the UI then degrades to
 * the legacy local-only behaviour instead of failing.
 */
export function getSupabase(): SupabaseClient | null {
  if (!isSupabaseConfigured()) return null;
  if (!client) {
    client = createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: "pkce",
      },
    });
  }
  return client;
}
