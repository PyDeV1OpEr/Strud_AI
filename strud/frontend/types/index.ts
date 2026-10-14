// ------------------------------------------------------------
// Strud AI — core domain types
// The frontend is model-agnostic; the backend owns AI behaviour.
// ------------------------------------------------------------

export type Role = "user" | "assistant";

export interface Attachment {
  id: string;
  /** Client-side object URL for preview; backend returns a stored URL */
  url: string;
  name: string;
  mimeType: string;
  size: number;
}

export interface Message {
  id: string;
  chatId: string;
  role: Role;
  content: string;
  createdAt: string;
  attachments?: Attachment[];
  /** Populated on assistant messages when the backend provides citations */
  sources?: Source[];
  error?: string;
}

export interface Source {
  label: string;
  pages: number[];
}

export interface Chat {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: Message[];
}

export interface User {
  id: string;
  name: string;
}

/** Response body from POST /api/chat */
export interface AIResponse {
  messageId: string;
  content: string;
  sources?: Source[];
}

/** Request body for POST /api/chat */
export interface ChatRequest {
  chatId: string;
  /** Stable per-browser identity used to scope server-side memory. */
  userId: string;
  message: string;
  attachments?: {
    name: string;
    mimeType: string;
    /** base64-encoded image data */
    data: string;
  }[];
}
