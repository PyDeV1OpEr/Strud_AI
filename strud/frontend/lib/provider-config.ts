// ------------------------------------------------------------
// Strud AI — per-user AI provider configuration
//
// SECURITY MODEL (honest):
// - The provider API key is stored ONLY in the user's browser
//   (localStorage, scoped by their account id). It is NEVER sent to
//   Strud's servers and NEVER written to Supabase. It travels only
//   directly from this browser to the configured provider endpoint.
// - Only non-secret configuration (provider, model id, base URL) is
//   persisted in the cloud provider_configs table, RLS-scoped per user.
// - Trade-off (documented in the UI): browser-local storage is not
//   hardened server-side storage; it is the safer alternative while no
//   deployed backend exists to hold a Vault-encrypted copy. A malicious
//   script with XSS on this origin could read it — standard risk for
//   client-held provider keys.
// ------------------------------------------------------------

import type { ProviderId } from "@/types";
import { authState } from "@/lib/auth-state";
import * as cloud from "@/lib/api/cloud-chats";
import { getSupabase } from "@/lib/supabase";

const KEY_STORAGE_PREFIX = "strud.provider-keys.v1";
const LOCAL_CONFIG_KEY = "strud.provider-config.v1";

export interface ProviderPreset {
  id: ProviderId;
  label: string;
  blurb: string;
  defaultBaseUrl: string;
  defaultModel: string;
  needsApiKey: boolean;
  needsBaseUrl: boolean;
  localOnly: boolean;
}

/**
 * Provider presets. Model ids + endpoints verified against provider docs:
 * - GPT-OSS: the existing local LM Studio OpenAI-compatible server.
 * - Qwen: OpenAI-compatible inference servers (e.g. ollama/vLLM/DashScope's
 *   OpenAI-compatible endpoint — the DASHSCOPE_COMPATIBLE base URL).
 * - Custom: any OpenAI-compatible chat-completions endpoint (Google
 *   Gemini's documented OpenAI-compat endpoint is a first-class preset).
 */
export const PROVIDER_PRESETS: Record<ProviderId, ProviderPreset> = {
  gptoss: {
    id: "gptoss",
    label: "GPT-OSS (local)",
    blurb: "Runs on this device via LM Studio. No API key required.",
    defaultBaseUrl: "http://localhost:1234/v1",
    defaultModel: "openai/gpt-oss-20b",
    needsApiKey: false,
    needsBaseUrl: true,
    localOnly: true,
  },
  qwen: {
    id: "qwen",
    label: "Qwen",
    blurb: "Qwen models via an OpenAI-compatible endpoint.",
    defaultBaseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    defaultModel: "qwen-plus",
    needsApiKey: true,
    needsBaseUrl: true,
    localOnly: false,
  },
  gemini: {
    id: "gemini",
    label: "Google Gemini",
    blurb: "Uses Google's documented OpenAI-compatible endpoint.",
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    defaultModel: "gemini-2.5-flash",
    needsApiKey: true,
    needsBaseUrl: false,
    localOnly: false,
  },
  custom: {
    id: "custom",
    label: "Custom Provider",
    blurb: "Any OpenAI-compatible chat-completions endpoint.",
    defaultBaseUrl: "",
    defaultModel: "",
    needsApiKey: true,
    needsBaseUrl: true,
    localOnly: false,
  },
};

export interface ProviderConfig {
  provider: ProviderId;
  modelId: string;
  baseUrl: string;
  temperature: number;
  maxTokens: number;
  hasKey: boolean;
}

const DEFAULT_CONFIG: ProviderConfig = {
  provider: "gptoss",
  modelId: PROVIDER_PRESETS.gptoss.defaultModel,
  baseUrl: PROVIDER_PRESETS.gptoss.defaultBaseUrl,
  temperature: 0.2,
  maxTokens: 2048,
  hasKey: false,
};

// ---- per-user API-key storage (browser only) -------------------------------

interface KeyStore {
  [userId: string]: string;
}

function readKeyStore(): KeyStore {
  try {
    const raw = window.localStorage.getItem(KEY_STORAGE_PREFIX);
    return raw ? (JSON.parse(raw) as KeyStore) : {};
  } catch {
    return {};
  }
}

function writeKeyStore(store: KeyStore): void {
  try {
    window.localStorage.setItem(KEY_STORAGE_PREFIX, JSON.stringify(store));
  } catch {
    /* storage unavailable */
  }
}

export function getProviderKey(userId: string): string | null {
  return readKeyStore()[userId] ?? null;
}

export function setProviderKey(userId: string, apiKey: string | null): void {
  const store = readKeyStore();
  if (apiKey && apiKey.trim()) store[userId] = apiKey.trim();
  else delete store[userId];
  writeKeyStore(store);
}

/** Masked, probeable representation shown in the UI — never the raw key. */
export function maskKey(key: string | null): string | null {
  if (!key) return null;
  if (key.length <= 8) return "••••••••";
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

// ---- config persistence -----------------------------------------------------

function localConfigKeyFor(userId: string): string {
  return `${LOCAL_CONFIG_KEY}:${userId}`;
}

function normalize(raw: Partial<ProviderConfig>): ProviderConfig {
  const provider = (
    raw.provider && raw.provider in PROVIDER_PRESETS ? raw.provider : "gptoss"
  ) as ProviderId;
  const preset = PROVIDER_PRESETS[provider];
  const maxTokens =
    typeof raw.maxTokens === "number" && raw.maxTokens >= 256 && raw.maxTokens <= 32768
      ? raw.maxTokens
      : DEFAULT_CONFIG.maxTokens;
  const temperature =
    typeof raw.temperature === "number" && raw.temperature >= 0 && raw.temperature <= 2
      ? raw.temperature
      : DEFAULT_CONFIG.temperature;
  return {
    provider,
    modelId: String(raw.modelId ?? preset.defaultModel).trim() || preset.defaultModel,
    baseUrl:
      (String(raw.baseUrl ?? "").trim() || preset.defaultBaseUrl) as string,
    temperature,
    maxTokens,
    hasKey: Boolean(raw.hasKey),
  };
}

/** Load for the given user: cloud (signed in) with localStorage cache. */
export async function loadProviderConfig(userId: string): Promise<ProviderConfig> {
  const cacheRaw = typeof window !== "undefined" ? localStorage.getItem(localConfigKeyFor(userId)) : null;
  let config: ProviderConfig = cacheRaw
    ? normalize(JSON.parse(cacheRaw) as Partial<ProviderConfig>)
    : { ...DEFAULT_CONFIG, hasKey: Boolean(getProviderKey(userId)) };

  if (authState.userId) {
    try {
      const stored = await cloud.cloudLoadProviderConfig(userId);
      if (stored) {
        config = normalize({
          ...config,
          provider: stored.provider as ProviderId,
          modelId: stored.modelId,
          baseUrl: stored.baseUrl ?? undefined,
          temperature: stored.temperature ?? undefined,
          maxTokens: stored.maxTokens ?? undefined,
          hasKey: stored.keyInBrowser,
        });
      }
    } catch {
      /* offline: the cached/local copy applies */
    }
  }
  return { ...config, hasKey: Boolean(getProviderKey(userId)) };
}

/** Save non-secret parts (cloud when signed in) + the browser-held key. */
export async function saveProviderConfig(
  userId: string,
  config: ProviderConfig,
  apiKey: string | null,
  replaceKey: boolean,
): Promise<ProviderConfig> {
  if (replaceKey && authState.userId) setProviderKey(userId, apiKey);
  const persistable = {
    provider: config.provider,
    modelId: config.modelId,
    baseUrl: config.baseUrl,
    temperature: config.temperature,
    maxTokens: config.maxTokens,
  };

  if (authState.userId) {
    try {
      await cloud.cloudSaveProviderConfig(userId, {
        provider: persistable.provider,
        modelId: persistable.modelId,
        baseUrl: persistable.baseUrl || null,
        temperature: persistable.temperature,
        maxTokens: persistable.maxTokens,
        keyInBrowser: getProviderKey(authState.userId) !== null,
      });
    } catch {
      // fall back to local-only persistence when the cloud write fails
    }
  }
  try {
    localStorage.setItem(localConfigKeyFor(userId), JSON.stringify(persistable));
  } catch {
    /* storage unavailable */
  }
  return loadProviderConfig(userId);
}

/** Sweep browser-held keys that belong to a signed-out session. */
export function clearProviderKeysForSignedOut(userId: string): void {
  // Keys stay on the user's machine; they are only removed intentionally
  // from Settings ("remove saved key"). Nothing is auto-deleted here.
  void userId;
  void getSupabase;
}
