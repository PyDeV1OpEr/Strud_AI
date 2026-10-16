// ------------------------------------------------------------
// Strud AI — direct provider requests (OpenAI-compatible)
//
// When the FastAPI backend isn't reachable (public deployments without
// a rendered backend), chat works browser-direct against the user's
// own configured provider. The API key travels ONLY from this browser
// to that endpoint — it is never proxied through Strud's servers.
//
// Honesty note: this path runs without the Python retrieval pipeline,
// so answers are labelled ungrounded unless the backend serves the
// request. The UI surfaces that state instead of inventing sources.
// ------------------------------------------------------------

import type { Message, Source } from "@/types";
import type { ProviderConfig } from "@/lib/provider-config";

const SYSTEM_PROMPT = [
  "You are Strud AI, a patient, encouraging G.C.E. A-Level Biology tutor.",
  "Explain clearly and correctly, structured with short sections where useful.",
  "If you are not certain, say so honestly — never invent textbook page numbers;",
  "this answer is generated from general knowledge, not the textbook index.",
].join(" ");

const DIRECT_TIMEOUT_MS = 120_000;

export interface DirectChatResult {
  content: string;
  usage?: { inputTokens?: number; outputTokens?: number };
}

function providerError(status: number, detail: string): string {
  if (status === 401 || status === 403) {
    return "The provider rejected the API key. Check the key in Settings → AI Provider.";
  }
  if (status === 404) return "That model wasn't found at the endpoint. Check the model ID (and base URL).";
  if (status === 429) return "The provider's quota or rate limit was reached. Try again in a moment.";
  if (status >= 500) return "The provider had a server problem. Try again shortly.";
  if (status === 400) return "The provider rejected the request. Check the model ID and settings.";
  return `Provider error (${status}). ${detail.slice(0, 160)}`;
}

/** True chat send, browser → provider. Returns content + usage if available. */
export async function sendDirectChat(
  config: ProviderConfig,
  apiKey: string | null,
  history: Message[],
  question: string,
  maxTokensOverride?: number,
): Promise<DirectChatResult> {
  const endpoint = `${config.baseUrl.replace(/\/+$/, "")}/chat/completions`;
  const messages: { role: string; content: string }[] = [
    { role: "system", content: SYSTEM_PROMPT },
    // Bounded recent history keeps follow-ups coherent without unbounded cost.
    ...history
      .filter((message) => !message.error && (message.content.trim() || message.role === "user"))
      .slice(-8)
      .map((message) => ({ role: message.role, content: message.content })),
  ];
  if (question.trim()) messages.push({ role: "user", content: question });

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify({
        model: config.modelId,
        messages,
        temperature: config.temperature,
        max_tokens: maxTokensOverride ?? config.maxTokens,
        stream: false,
      }),
      signal: AbortSignal.timeout(DIRECT_TIMEOUT_MS),
    });
  } catch {
    // Network/CORS/mixed-content failures surface identically in the
    // catch-all; the message adapts for local GPT-OSS endpoints.
    if (/^http:/.test(endpoint) && window.location.protocol === "https:") {
      throw new Error(
        "This page is HTTPS, so the browser blocks calls to http:// (mixed content). Run Strud on localhost for GPT-OSS, or use a cloud provider.",
      );
    }
    throw new Error(
      "Couldn't reach the provider. Check the endpoint URL, your connection, and the provider's CORS settings.",
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(providerError(response.status, detail));
  }

  const data = (await response.json()) as {
    choices?: { message?: { content?: string } }[];
    usage?: { prompt_tokens?: number; completion_tokens?: number };
  };
  const content =
    data.choices?.[0]?.message?.content ??
    (() => {
      throw new Error("The provider returned an unexpected response format.");
    })();
  return {
    content: String(content).trim(),
    usage: data.usage
      ? { inputTokens: data.usage.prompt_tokens, outputTokens: data.usage.completion_tokens }
      : undefined,
  };
}

/**
 * REAL connection test: a tiny completion round-trip against the exact
 * configured endpoint + key + model. Never reports success without a
 * genuine 200 from the provider.
 */
export async function testProviderConnection(
  config: ProviderConfig,
  apiKey: string | null,
): Promise<{ ok: true; sample: string } | { ok: false; error: string }> {
  try {
    const result = await sendDirectChat(
      { ...config, maxTokens: 32 },
      apiKey,
      [],
      "Reply with the single word: ready",
      32,
    );
    return { ok: true, sample: result.content.slice(0, 60) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Unknown error." };
  }
}

/** Shared detector: is the FastAPI backend reachable right now? */
export async function checkBackendHealth(backendUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${backendUrl}/api/health`, {
      method: "GET",
      signal: AbortSignal.timeout(4000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export type { Source };
