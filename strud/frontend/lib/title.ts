// ------------------------------------------------------------
// Strud AI — chat title heuristics
// Derives a concise title from the first user message without
// blocking the chat (backend AI titles arrive later if enabled).
// ------------------------------------------------------------

const STOP_WORDS = new Set([
  "a", "an", "the", "please", "can", "you", "me", "my", "i", "is",
  "are", "was", "were", "what", "whats", "how", "why", "when", "which",
  "explain", "describe", "tell", "about", "of", "in", "on", "for", "to",
  "and", "do", "does", "with", "give", "giveee", "help", "understand",
]);

/** Turns "Explain the process of photosynthesis" into "Photosynthesis". */
export function deriveTitle(message: string): string {
  const cleaned = message
    .replace(/[?!.]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();

  const words = cleaned.split(" ").filter(Boolean);
  const meaningful: string[] = [];

  for (const word of words) {
    const lower = word.toLowerCase().replace(/[^a-z0-9-]/g, "");
    if (!lower || STOP_WORDS.has(lower)) continue;
    meaningful.push(word);
    if (meaningful.length >= 5) break;
  }

  // Capitalise the first meaningful word for a clean title look.
  const title = meaningful
    .map((word, index) =>
      index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word,
    )
    .join(" ")
    .trim();
  if (!title) return cleaned.slice(0, 40) || "New chat";
  return title.length > 48 ? `${title.slice(0, 45)}…` : title;
}
