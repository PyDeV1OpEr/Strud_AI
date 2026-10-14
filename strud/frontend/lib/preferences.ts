// ------------------------------------------------------------
// Strud AI — Preferences management (Appearance & Chat settings)
// ------------------------------------------------------------

import type { AppearancePreferences, ChatPreferences } from "@/types";

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
};

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
    return { ...DEFAULT_CHAT_PREFS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_CHAT_PREFS;
  }
}

export function saveChatPrefs(prefs: ChatPreferences): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CHAT_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // LocalStorage quota or disabled
  }
}
