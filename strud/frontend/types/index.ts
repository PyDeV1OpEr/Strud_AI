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
  /** Project association; absent means an ordinary (unassigned) chat. */
  projectId?: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  chatCount: number;
}

export interface Profile {
  displayName: string;
  avatar?: string;
  responseStyle?: "concise" | "balanced" | "detailed" | "socratic";
  explanationDetail?: "standard" | "deep" | "quick";
  studyFocus?: "exam" | "conceptual" | "revision";
  memoryEnabled?: boolean;
  customInstructions?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface User {
  id: string;
  name: string;
}

export interface UsageSummary {
  tokens_today: number;
  tokens_this_week: number;
  tokens_this_month: number;
  tokens_last_month: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  avg_tokens_per_request: number;
  avg_latency_ms: number | null;
  range: string;
  start_date: string;
  end_date: string;
  timezone: string;
}

export interface CalendarDay {
  date: string;
  weekday: number;
  month: number;
  day: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  request_count: number;
  intensity: number; // 0 to 4
  status: "tracked" | "unavailable";
}

export interface ContributionCalendarData {
  year: number;
  timezone: string;
  total_tokens: number;
  total_requests: number;
  first_tracked_date: string | null;
  days: CalendarDay[];
  intensity_scale: Record<string, string>;
}

export interface TimeseriesPoint {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  requests: number;
}

export interface ModelUsage {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  request_count: number;
  successful_requests: number;
}

export interface UsageRequestRecord {
  id: number;
  chat_id: string | null;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  token_counting_method: string;
  request_status: "success" | "failed";
  duration_ms: number | null;
  created_at: string;
  created_at_local?: string;
}

export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  baseUrl: string;
  temperature: number;
  maxTokens: number;
  /** Largest output budget the configuration permits (newer key). */
  maxOutputTokens?: number;
  /** Real context window from the model server; null when unknown. */
  contextWindow: number | null;
  /** Whether the configured model supports gpt-oss-style effort levels. */
  reasoningEffortSupport?: boolean;
  status: "online" | "model_not_loaded" | "offline";
  capabilities: {
    text: boolean;
    vision: boolean;
  };
}

export interface ModelsPayload {
  activeModel: ModelConfig;
  visionModel: ModelConfig;
  availableModels: string[];
  serverConnected: boolean;
}

export interface RagStatus {
  initialized: boolean;
  pdf_exists: boolean;
  textbook_loaded: boolean;
  page_count: number;
  chunk_count: number;
  tfidf_available: boolean;
  bm25_available: boolean;
  retrieval_mode: string;
  rrf_weights: Record<string, number>;
  semantic_available: boolean;
  embedding_model: string;
  grounding_threshold: number;
  visual_chunks: number;
}

export interface RagDocument {
  name: string;
  sizeBytes: number;
  pageCount: number | null;
  isPrimary: boolean;
  chunkCount: number | null;
  status: "indexed" | "ready" | "error";
}

export interface RagTestChunk {
  index: number;
  page: number;
  text: string;
  tfidfScore: number;
  bm25Score: number;
  semanticScore: number;
  rrfScore: number;
  confidence: number;
}

export interface RagTestResponse {
  query: string;
  grounded: boolean;
  confidence: number;
  bestPage: number | null;
  reason: string;
  latencyMs: number;
  resultsCount: number;
  chunks: RagTestChunk[];
}

export interface MemoryFact {
  id: number;
  content: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface StorageStats {
  database_size_bytes: number;
  checkpoints_size_bytes: number;
  uploads_size_bytes: number;
  uploads_count: number;
  active_chats_count: number;
  deleted_chats_count: number;
  messages_count: number;
  memories_count: number;
  quiz_sessions_count: number;
  usage_records_count: number;
}

export interface DiagnosticCheck {
  name: string;
  status: "healthy" | "degraded" | "unavailable" | "unknown";
  details: string;
  latencyMs: number | null;
}

export interface DiagnosticsData {
  status: "healthy" | "degraded" | "unavailable";
  appVersion: string;
  gitCommit: string;
  checks: DiagnosticCheck[];
  recentFailures24h: number;
}

export type ThemeOption = "dark" | "light" | "system" | "oled" | "midnight" | "forest";
export type AccentOption = "emerald" | "cyan" | "violet" | "amber" | "rose";
export type FontSizeOption = "sm" | "md" | "lg";
export type DensityOption = "comfortable" | "compact";

export interface AppearancePreferences {
  theme: ThemeOption;
  accent: AccentOption;
  fontSize: FontSizeOption;
  density: DensityOption;
  reducedMotion: boolean;
}

export interface ChatPreferences {
  enterToSend: boolean;
  showSourcesDefault: boolean;
  smoothTyping: boolean;
  /** Reasoning effort for the configured model (gpt-oss effort levels). */
  thinkingLevel: ThinkingLevel;
  /** Response length preset; names an output-token budget. */
  responseLength: ResponseLengthPreset;
  /** Advanced override of the per-message output budget; null = preset. */
  advancedOutputTokens: number | null;
}

export type ThinkingLevel = "low" | "medium" | "high";
export type ResponseLengthPreset = "short" | "balanced" | "long" | "maximum";

/** AI provider modes in Settings → AI Provider. */
export type ProviderId = "gptoss" | "qwen" | "gemini" | "custom";

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
  /** Applied only when the chat row is first created server-side. */
  projectId?: string;
  attachments?: {
    name: string;
    mimeType: string;
    /** base64-encoded image data */
    data: string;
  }[];
  /** Reasoning effort sent for THIS message (mapped server-side). */
  thinkingLevel?: ThinkingLevel;
  /** Per-message output token budget override (validated server-side). */
  maxTokens?: number;
}
