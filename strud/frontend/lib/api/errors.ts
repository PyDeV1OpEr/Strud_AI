// ------------------------------------------------------------
// Strud AI — API error type + backend URL
// ------------------------------------------------------------

/** Base URL of the FastAPI backend (env-configured, never hardcoded). */
export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  /** User-safe message; technical details go to the console. */
  readonly friendly: string;

  constructor(friendly: string, technical?: string) {
    super(technical ?? friendly);
    this.friendly = friendly;
  }
}

export const CONNECTION_ERROR =
  "Strud couldn't connect to the AI backend. Make sure the backend is running and try again.";
