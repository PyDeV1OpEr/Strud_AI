// ------------------------------------------------------------
// Strud AI — Preferences management (Appearance & Chat settings)
// ------------------------------------------------------------

import type { AppearancePreferences, ChatPreferences, ResponseLengthPreset, ThinkingLevel } from "@/types";

const APPEARANCE_KEY = "strud_appearance_prefs_v1";
const CHAT_PREFS_KEY = "strud_chat_prefs_v1";

export const DEFAULT_APPEARANCE: AppearancePreferences = {
  theme: "dark",
  accent: "emerald",
  fontSize: "md",
  density: "comfortable",
  reducedMotion: false,
};

export const DEFAULT_CHAT_PREFS: ChatPreferences = {
  enterToSend: true,
  showSourcesDefault: true,
  smoothTyping: true,
  thinkingLevel: "medium",
  responseLength: "balanced",
  advancedOutputTokens: null,
};

// ---- Response length presets & output budget resolution -------------------

export const RESPONSE_LENGTH_PRESETS: Record<
  ResponseLengthPreset,
  { label: string; tokens: number; description: string }
> = {
  short: { label: "Short", tokens: 1024, description: "Quick answers and definitions" },
  balanced: { label: "Balanced", tokens: 2000, description: "Default study-ready explanations" },
  long: { label: "Long", tokens: 4096, description: "Detailed lessons and multi-part answers" },
  maximum: { label: "Maximum", tokens: 8192, description: "Longest deep-dive budget" },
};

/** Absolute guard for the advanced field; the backend enforces its own ceiling. */
export const OUTPUT_TOKENS_MIN = 256;
export const OUTPUT_TOKENS_MAX = 32768;

function isThinkingLevel(value: unknown): value is ThinkingLevel {
  return value === "low" || value === "medium" || value === "high";
}

function isResponseLength(value: unknown): value is ResponseLengthPreset {
  return value === "short" || value === "balanced" || value === "long" || value === "maximum";
}

/** Validates the advanced numeric budget; invalid values fall back to null. */
export function sanitizeAdvancedOutputTokens(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return null;
  const int = Math.round(parsed);
  if (int < OUTPUT_TOKENS_MIN || int > OUTPUT_TOKENS_MAX) return null;
  return int;
}

/**
 * The effective per-message output budget: the advanced override when it is
 * valid, otherwise the tokens named by the selected response-length preset.
 */
export function resolveOutputTokens(prefs: ChatPreferences): number {
  const advanced = sanitizeAdvancedOutputTokens(prefs.advancedOutputTokens);
  if (advanced !== null) return advanced;
  const preset = isResponseLength(prefs.responseLength)
    ? prefs.responseLength
    : DEFAULT_CHAT_PREFS.responseLength;
  return RESPONSE_LENGTH_PRESETS[preset].tokens;
}

/** Returns a fully valid ChatPreferences object merged over defaults. */
export function normalizeChatPrefs(raw: Partial<ChatPreferences> | null): ChatPreferences {
  if (!raw) return { ...DEFAULT_CHAT_PREFS };
  return {
    enterToSend: raw.enterToSend ?? DEFAULT_CHAT_PREFS.enterToSend,
    showSourcesDefault: raw.showSourcesDefault ?? DEFAULT_CHAT_PREFS.showSourcesDefault,
    smoothTyping: raw.smoothTyping ?? DEFAULT_CHAT_PREFS.smoothTyping,
    thinkingLevel: isThinkingLevel(raw.thinkingLevel) ? raw.thinkingLevel : DEFAULT_CHAT_PREFS.thinkingLevel,
    responseLength: isResponseLength(raw.responseLength) ? raw.responseLength : DEFAULT_CHAT_PREFS.responseLength,
    advancedOutputTokens: sanitizeAdvancedOutputTokens(raw.advancedOutputTokens),
  };
}

export function getStoredAppearance(): AppearancePreferences {
  if (typeof window === "undefined") return DEFAULT_APPEARANCE;
  try {
    const raw = localStorage.getItem(APPEARANCE_KEY);
    if (!raw) return DEFAULT_APPEARANCE;
    return { ...DEFAULT_APPEARANCE, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

export function saveAppearance(prefs: AppearancePreferences): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(APPEARANCE_KEY, JSON.stringify(prefs));
    applyAppearanceToDOM(prefs);
  } catch {
    // LocalStorage quota or disabled
  }
}

export function applyAppearanceToDOM(prefs: AppearancePreferences): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;

  let resolvedTheme = prefs.theme;
  if (resolvedTheme === "system") {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      resolvedTheme = "dark";
    } else {
      resolvedTheme = "light";
    }
  }

  root.setAttribute("data-theme", resolvedTheme);
  root.setAttribute("data-accent", prefs.accent);
  root.setAttribute("data-font-size", prefs.fontSize);
  root.setAttribute("data-density", prefs.density);

  if (resolvedTheme === "light") {
    root.classList.remove("dark");
  } else {
    root.classList.add("dark");
  }

  if (prefs.reducedMotion) {
    root.classList.add("reduce-motion");
  } else {
    root.classList.remove("reduce-motion");
  }
}

export function getStoredChatPrefs(): ChatPreferences {
  if (typeof window === "undefined") return DEFAULT_CHAT_PREFS;
  try {
    const raw = localStorage.getItem(CHAT_PREFS_KEY);
    if (!raw) return DEFAULT_CHAT_PREFS;
    return normalizeChatPrefs(JSON.parse(raw));
  } catch {
    return DEFAULT_CHAT_PREFS;
  }
}

export function saveChatPrefs(prefs: ChatPreferences): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CHAT_PREFS_KEY, JSON.stringify(normalizeChatPrefs(prefs)));
  } catch {
    // LocalStorage quota or disabled
  }
}
