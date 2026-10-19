// ------------------------------------------------------------
// Strud AI — public demo configuration
//
// The Vercel deployment is a FRONTEND-ONLY PREVIEW of Strud AI.
// It has no hosted AI backend: the FastAPI application, the local
// model server (LM Studio) and the Biology retrieval pipeline all
// run on the user's own machine, as documented in the README.
//
// `NEXT_PUBLIC_DEMO_MODE=true` is set as a Vercel build-time
// environment variable (never a secret) to switch the app from the
// fully functional local configuration to the honest demo state.
// ------------------------------------------------------------

/**
 * Absolute URL of the project's source — used by the demo surfaces to
 * point visitors at the real, reproducible local application.
 */
export const STRUD_REPO_URL = "https://github.com/PyDeV1OpEr/Strud_AI";

/** Read at build time by Next.js (`NEXT_PUBLIC_*`). Safe for SSR. */
export function isDemoMode(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === "true";
}

/**
 * The reply shown when a visitor sends a message in the public demo.
 * This is a system notice about the deployment — it is never presented
 * as an AI answer and no inference is claimed or simulated.
 */
export const DEMO_GATE_MESSAGE = [
  "**Public preview — local inference required.**",
  "",
  "This is a frontend-only demonstration of Strud AI. It does not include",
  "a hosted inference backend, so no AI answer can be generated here.",
  "",
  "Strud runs fully on your own computer: the FastAPI backend, the",
  "GPT-OSS 20B model served by LM Studio, and the Biology textbook",
  "retrieval pipeline. Clone the repository and follow the setup guide",
  `to use the real application → **[${STRUD_REPO_URL}](${STRUD_REPO_URL})**`,
].join("\n");
