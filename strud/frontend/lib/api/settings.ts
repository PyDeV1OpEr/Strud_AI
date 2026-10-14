// ------------------------------------------------------------
// Strud AI — Control Center & Settings API Client
// ------------------------------------------------------------

import { BACKEND_URL, ApiError } from "./errors";
import type {
  ContributionCalendarData,
  DiagnosticsData,
  MemoryFact,
  ModelUsage,
  ModelsPayload,
  Profile,
  RagDocument,
  RagStatus,
  RagTestResponse,
  StorageStats,
  TimeseriesPoint,
  UsageRequestRecord,
  UsageSummary,
} from "@/types";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      if (err.detail) detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    } catch {
      // Keep default detail
    }
    throw new ApiError(detail, String(res.status));
  }
  return (await res.json()) as T;
}

// ---- AI Usage & Analytics -------------------------------------------------

export async function fetchUsageSummary(
  userId: string,
  range = "last_30_days",
  startDate?: string,
  endDate?: string,
): Promise<UsageSummary> {
  const params = new URLSearchParams({ user_id: userId, range });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const res = await fetch(`${BACKEND_URL}/api/analytics/summary?${params.toString()}`);
  return handleResponse<UsageSummary>(res);
}

export async function fetchUsageCalendar(
  userId: string,
  year?: number,
): Promise<ContributionCalendarData> {
  const params = new URLSearchParams({ user_id: userId });
  if (year) params.set("year", String(year));
  const res = await fetch(`${BACKEND_URL}/api/analytics/calendar?${params.toString()}`);
  return handleResponse<ContributionCalendarData>(res);
}

export async function fetchUsageTimeseries(
  userId: string,
  range = "last_30_days",
): Promise<TimeseriesPoint[]> {
  const params = new URLSearchParams({ user_id: userId, range });
  const res = await fetch(`${BACKEND_URL}/api/analytics/timeseries?${params.toString()}`);
  const data = await handleResponse<{ timeseries: TimeseriesPoint[] }>(res);
  return data.timeseries;
}

export async function fetchUsageModels(
  userId: string,
  range = "last_30_days",
): Promise<ModelUsage[]> {
  const params = new URLSearchParams({ user_id: userId, range });
  const res = await fetch(`${BACKEND_URL}/api/analytics/models?${params.toString()}`);
  const data = await handleResponse<{ models: ModelUsage[] }>(res);
  return data.models;
}

export async function fetchUsageRequests(
  userId: string,
  limit = 25,
): Promise<UsageRequestRecord[]> {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
  const res = await fetch(`${BACKEND_URL}/api/analytics/requests?${params.toString()}`);
  const data = await handleResponse<{ requests: UsageRequestRecord[] }>(res);
  return data.requests;
}

export async function exportUsageRecords(userId: string): Promise<UsageRequestRecord[]> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/analytics/export?${params.toString()}`, {
    method: "POST",
  });
  const data = await handleResponse<{ records: UsageRequestRecord[] }>(res);
  return data.records;
}

// ---- AI Models ------------------------------------------------------------

export async function fetchModelsInfo(): Promise<ModelsPayload> {
  const res = await fetch(`${BACKEND_URL}/api/models`);
  return handleResponse<ModelsPayload>(res);
}

export async function testModelConnection(
  modelId?: string,
  baseUrl?: string,
): Promise<{ ok: boolean; status: string; latencyMs: number | null; message: string; availableModels?: string[] }> {
  const res = await fetch(`${BACKEND_URL}/api/models/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ modelId, baseUrl }),
  });
  return handleResponse<{ ok: boolean; status: string; latencyMs: number | null; message: string; availableModels?: string[] }>(res);
}

export async function updateActiveModel(
  modelId?: string,
  temperature?: number,
  maxTokens?: number,
  baseUrl?: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BACKEND_URL}/api/models/active`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ modelId, temperature, maxTokens, baseUrl }),
  });
  return handleResponse<{ ok: boolean }>(res);
}

// ---- Knowledge Base & RAG Inspector ---------------------------------------

export async function fetchRagStatus(): Promise<RagStatus> {
  const res = await fetch(`${BACKEND_URL}/api/rag/status`);
  return handleResponse<RagStatus>(res);
}

export async function fetchRagDocuments(): Promise<RagDocument[]> {
  const res = await fetch(`${BACKEND_URL}/api/rag/documents`);
  const data = await handleResponse<{ documents: RagDocument[] }>(res);
  return data.documents;
}

export async function testRagQuery(query: string): Promise<RagTestResponse> {
  const res = await fetch(`${BACKEND_URL}/api/rag/test-query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return handleResponse<RagTestResponse>(res);
}

export async function reindexRag(): Promise<{ ok: boolean; chunkCount: number; pageCount: number }> {
  const res = await fetch(`${BACKEND_URL}/api/rag/reindex`, {
    method: "POST",
  });
  return handleResponse<{ ok: boolean; chunkCount: number; pageCount: number }>(res);
}

// ---- Memory & Context -----------------------------------------------------

export async function fetchMemories(userId: string): Promise<MemoryFact[]> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/memory?${params.toString()}`);
  const data = await handleResponse<{ facts: MemoryFact[] }>(res);
  return data.facts;
}

export async function addMemory(
  userId: string,
  content: string,
  source = "explicit",
): Promise<{ ok: boolean; id: number }> {
  const res = await fetch(`${BACKEND_URL}/api/memory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, content, source }),
  });
  return handleResponse<{ ok: boolean; id: number }>(res);
}

export async function deleteMemory(userId: string, memoryId: number): Promise<{ ok: boolean }> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/memory/${memoryId}?${params.toString()}`, {
    method: "DELETE",
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function clearAllMemories(userId: string): Promise<{ ok: boolean; clearedCount: number }> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/memory/all?${params.toString()}`, {
    method: "DELETE",
  });
  return handleResponse<{ ok: boolean; clearedCount: number }>(res);
}

export async function updateMemorySettings(
  userId: string,
  memoryEnabled: boolean,
): Promise<{ ok: boolean; memoryEnabled: boolean }> {
  const res = await fetch(`${BACKEND_URL}/api/memory/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, memoryEnabled }),
  });
  return handleResponse<{ ok: boolean; memoryEnabled: boolean }>(res);
}

// ---- Profile & Personalization --------------------------------------------

interface RawBackendProfile {
  display_name?: string;
  avatar?: string;
  response_style?: Profile["responseStyle"];
  explanation_detail?: Profile["explanationDetail"];
  study_focus?: Profile["studyFocus"];
  memory_enabled?: boolean;
  custom_instructions?: string;
  created_at?: string;
  updated_at?: string;
}

export async function fetchProfileFull(userId: string): Promise<Profile> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/profile?${params.toString()}`);
  const data = await handleResponse<RawBackendProfile>(res);
  return {
    displayName: data.display_name ?? "Student",
    avatar: data.avatar ?? "emerald",
    responseStyle: data.response_style ?? "balanced",
    explanationDetail: data.explanation_detail ?? "standard",
    studyFocus: data.study_focus ?? "exam",
    memoryEnabled: Boolean(data.memory_enabled ?? true),
    customInstructions: data.custom_instructions ?? "",
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

export async function updateProfileFull(userId: string, profile: Partial<Profile>): Promise<Profile> {
  const res = await fetch(`${BACKEND_URL}/api/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userId,
      displayName: profile.displayName || "Student",
      avatar: profile.avatar || "emerald",
      responseStyle: profile.responseStyle || "balanced",
      explanationDetail: profile.explanationDetail || "standard",
      studyFocus: profile.studyFocus || "exam",
      memoryEnabled: profile.memoryEnabled ?? true,
      customInstructions: profile.customInstructions || "",
    }),
  });
  const data = await handleResponse<RawBackendProfile>(res);
  return {
    displayName: data.display_name ?? profile.displayName ?? "Student",
    avatar: data.avatar ?? profile.avatar,
    responseStyle: data.response_style ?? profile.responseStyle,
    explanationDetail: data.explanation_detail ?? profile.explanationDetail,
    studyFocus: data.study_focus ?? profile.studyFocus,
    memoryEnabled: Boolean(data.memory_enabled ?? true),
    customInstructions: data.custom_instructions ?? profile.customInstructions,
  };
}

// ---- Privacy & Data Management --------------------------------------------

export async function fetchStorageStats(userId: string): Promise<StorageStats> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/privacy/storage-info?${params.toString()}`);
  return handleResponse<StorageStats>(res);
}

export async function cleanOrphanedUploads(): Promise<{ removed_count: number; freed_bytes: number }> {
  const res = await fetch(`${BACKEND_URL}/api/privacy/clean-uploads`, {
    method: "POST",
  });
  return handleResponse<{ removed_count: number; freed_bytes: number }>(res);
}

export async function exportFullData(userId: string): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`${BACKEND_URL}/api/privacy/export-data?${params.toString()}`, {
    method: "POST",
  });
  return handleResponse<Record<string, unknown>>(res);
}

export async function clearAllUserChats(
  userId: string,
  permanent = false,
): Promise<{ ok: boolean; clearedCount: number; permanent: boolean }> {
  const res = await fetch(`${BACKEND_URL}/api/privacy/clear-history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, permanent }),
  });
  return handleResponse<{ ok: boolean; clearedCount: number; permanent: boolean }>(res);
}

// ---- System Diagnostics ---------------------------------------------------

export async function fetchDiagnostics(): Promise<DiagnosticsData> {
  const res = await fetch(`${BACKEND_URL}/api/diagnostics`);
  return handleResponse<DiagnosticsData>(res);
}
