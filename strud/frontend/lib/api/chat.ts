// ------------------------------------------------------------
// Strud AI — chat API client
//
// All AI communication with the FastAPI backend. The backend owns
// retrieval, grounding, verification and vision; this module only
// transports requests and normalizes errors for the UI.
// ------------------------------------------------------------

import type { AIResponse, ChatRequest } from "@/types";
import { BACKEND_URL, ApiError, CONNECTION_ERROR } from "./errors";

const CHAT_TIMEOUT_MS = 300_000; // verification + vision can take a while

/** Sends a user message (and optional image attachments) to the real backend. */
export async function sendMessage(request: ChatRequest): Promise<AIResponse> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(CHAT_TIMEOUT_MS),
    });
  } catch (error) {
    console.error("[strud] chat request failed:", error);
    throw new ApiError(CONNECTION_ERROR, "network error");
  }

  if (!response.ok) {
    console.error(
      "[strud] chat request failed:",
      response.status,
      await response.text().catch(() => ""),
    );
    throw new ApiError(
      response.status === 503
        ? "The AI engine isn't responding right now. Please try again."
        : "Strud couldn't process that. Please try again.",
      `HTTP ${response.status}`,
    );
  }

  try {
    return (await response.json()) as AIResponse;
  } catch {
    throw new ApiError(
      "Strud returned an unexpected response.",
      "invalid JSON body",
    );
  }
}

/** Ask the backend to derive a concise chat title (best-effort). */
export async function generateTitle(
  chatId: string,
  message: string,
): Promise<string | null> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chatId, message }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) return null;
    const data = (await response.json()) as { title?: string };
    return data.title ?? null;
  } catch {
    return null;
  }
}
