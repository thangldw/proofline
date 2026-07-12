import type { GroundedAnswer, IngestionJob, Memory, Overview, SearchHit, SearchScope, Source, SourceDeletionImpact } from "./types";

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
  search: async (query: string, scope?: SearchScope) => {
    const params = new URLSearchParams({ q: query });
    for (const sourceId of scope?.sourceIds ?? []) params.append("source_id", sourceId);
    if (scope?.ingestedFrom) params.set("ingested_from", scope.ingestedFrom);
    if (scope?.ingestedBefore) params.set("ingested_before", scope.ingestedBefore);
    return (await request<{ hits: SearchHit[] }>(`/api/v1/search?${params.toString()}`)).hits;
  },
  answer: (question: string, scope?: SearchScope) =>
    request<GroundedAnswer>("/api/v1/answers", {
      method: "POST",
      body: JSON.stringify({
        question,
        ...(scope?.sourceIds.length ? { source_ids: scope.sourceIds } : {}),
        ...(scope?.ingestedFrom ? { ingested_from: scope.ingestedFrom } : {}),
        ...(scope?.ingestedBefore ? { ingested_before: scope.ingestedBefore } : {}),
      }),
    }),
  importSource: (title: string, content: string, uri?: string) =>
    request<Source>("/api/v1/sources", {
      method: "POST",
      body: JSON.stringify({ title, content, kind: "markdown", uri }),
    }),
};
