import type { GroundedAnswer, IngestionJob, Memory, Overview, SearchHit, Source, SourceDeletionImpact } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  overview: () => request<Overview>("/api/v1/overview"),
  sources: () => request<Source[]>("/api/v1/sources"),
  deletionImpact: (id: string) =>
    request<SourceDeletionImpact>(`/api/v1/sources/${id}/deletion-impact`),
  deleteSource: (id: string) =>
    request<void>(`/api/v1/sources/${id}`, { method: "DELETE" }),
  jobs: () => request<IngestionJob[]>("/api/v1/jobs?limit=200"),
  retryJob: (id: string) =>
    request<IngestionJob>(`/api/v1/jobs/${id}/retry`, { method: "POST" }),
  source: (id: string) => request<Source & { content: string }>(`/api/v1/sources/${id}`),
  sourceVersion: (sourceId: string, versionId: string) =>
    request<{ content: string }>(`/api/v1/sources/${sourceId}/versions/${versionId}`),
  memories: () => request<Memory[]>("/api/v1/memories"),
  extractMemories: (sourceId: string) =>
    request<Memory[]>(`/api/v1/sources/${sourceId}/extract-memories`, { method: "POST" }),
  updateMemory: (id: string, changes: { status?: "candidate" | "active" | "accepted" | "rejected" | "obsolete"; statement?: string; rationale?: string | null }) =>
    request<Memory>(`/api/v1/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  search: async (query: string) =>
    (await request<{ hits: SearchHit[] }>(`/api/v1/search?q=${encodeURIComponent(query)}`)).hits,
  answer: (question: string) =>
    request<GroundedAnswer>("/api/v1/answers", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  importSource: (title: string, content: string, uri?: string) =>
    request<Source>("/api/v1/sources", {
      method: "POST",
      body: JSON.stringify({ title, content, kind: "markdown", uri }),
    }),
};
