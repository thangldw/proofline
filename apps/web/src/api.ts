import type {
  DecisionTimeline,
  GroundedAnswer,
  IngestionJob,
  Memory,
  ModelRun,
  ModelRunFilters,
  Note,
  Overview,
  ProviderConfiguration,
  ProviderStatus,
  SearchHit,
  SearchScope,
  Source,
  SourceDeletionImpact,
  StudyCard,
  Workspace,
} from "./types";

const DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001";
let activeWorkspaceId = DEFAULT_WORKSPACE_ID;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Proofline-Workspace-ID": activeWorkspaceId,
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  setWorkspace: (workspaceId: string) => {
    activeWorkspaceId = workspaceId;
  },
  workspaces: () => request<Workspace[]>("/api/v1/workspaces"),
  overview: () => request<Overview>("/api/v1/overview"),
  sources: () => request<Source[]>("/api/v1/sources"),
  notes: () => request<Note[]>("/api/v1/notes"),
  studyCards: () => request<StudyCard[]>("/api/v1/study-cards"),
  createStudyCards: (sourceId: string) =>
    request<StudyCard[]>(`/api/v1/sources/${sourceId}/study-cards`, {
      method: "POST",
    }),
  reviewStudyCard: (cardId: string, rating: "again" | "hard" | "good" | "easy") =>
    request(`/api/v1/study-cards/${cardId}/reviews`, {
      method: "POST",
      body: JSON.stringify({ rating }),
    }),
  createNote: (title: string, content: string) =>
    request<Note>("/api/v1/notes", {
      method: "POST",
      body: JSON.stringify({ title, content }),
    }),
  updateNote: (id: string, title: string, content: string) =>
    request<Note>(`/api/v1/notes/${id}`, {
      method: "PUT",
      body: JSON.stringify({ title, content }),
    }),
  deletionImpact: (id: string) =>
    request<SourceDeletionImpact>(`/api/v1/sources/${id}/deletion-impact`),
  deleteSource: (id: string) =>
    request<void>(`/api/v1/sources/${id}`, { method: "DELETE" }),
  jobs: () => request<IngestionJob[]>("/api/v1/jobs?limit=200"),
  modelRuns: (filters: ModelRunFilters = {}) => {
    const params = new URLSearchParams({ limit: String(filters.limit ?? 100) });
    if (filters.status) params.set("status", filters.status);
    if (filters.operation) params.set("operation", filters.operation);
    if (filters.providerId) params.set("provider_id", filters.providerId);
    if (filters.parentRunId) params.set("parent_run_id", filters.parentRunId);
    return request<ModelRun[]>(`/api/v1/model/runs?${params.toString()}`);
  },
  modelRun: (id: string) => request<ModelRun>(`/api/v1/model/runs/${id}`),
  providerConfiguration: () =>
    request<ProviderConfiguration>("/api/v1/model/configuration"),
  saveProviderConfiguration: (configuration: Record<string, unknown>) =>
    request<ProviderConfiguration>("/api/v1/model/configuration", {
      method: "PUT",
      body: JSON.stringify(configuration),
    }),
  generationProviderStatus: () =>
    request<ProviderStatus>("/api/v1/model/provider?check_health=true"),
  embeddingProviderStatus: () =>
    request<ProviderStatus>(
      "/api/v1/model/embedding-provider?check_health=true",
    ),
  rerankingProviderStatus: () =>
    request<ProviderStatus>("/api/v1/model/reranking-provider"),
  retryJob: (id: string) =>
    request<IngestionJob>(`/api/v1/jobs/${id}/retry`, { method: "POST" }),
  source: (id: string) =>
    request<Source & { content: string }>(`/api/v1/sources/${id}`),
  sourceVersion: (sourceId: string, versionId: string) =>
    request<{ content: string }>(
      `/api/v1/sources/${sourceId}/versions/${versionId}`,
    ),
  memories: () => request<Memory[]>("/api/v1/memories"),
  extractMemories: (sourceId: string) =>
    request<Memory[]>(`/api/v1/sources/${sourceId}/extract-memories`, {
      method: "POST",
    }),
  decisionTimeline: (id: string) =>
    request<DecisionTimeline>(`/api/v1/decisions/${id}/timeline`),
  updateMemory: (
    id: string,
    changes: {
      status?: "candidate" | "active" | "accepted" | "rejected" | "obsolete";
      statement?: string;
      rationale?: string | null;
    },
  ) =>
    request<Memory>(`/api/v1/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  search: async (query: string, scope?: SearchScope) => {
    const params = new URLSearchParams({ q: query });
    for (const sourceId of scope?.sourceIds ?? [])
      params.append("source_id", sourceId);
    if (scope?.ingestedFrom) params.set("ingested_from", scope.ingestedFrom);
    if (scope?.ingestedBefore)
      params.set("ingested_before", scope.ingestedBefore);
    if (scope?.rerank) params.set("rerank", "true");
    return (
      await request<{ hits: SearchHit[] }>(
        `/api/v1/search?${params.toString()}`,
      )
    ).hits;
  },
  answer: (question: string, scope?: SearchScope) =>
    request<GroundedAnswer>("/api/v1/answers", {
      method: "POST",
      body: JSON.stringify({
        question,
        ...(scope?.sourceIds.length ? { source_ids: scope.sourceIds } : {}),
        ...(scope?.ingestedFrom ? { ingested_from: scope.ingestedFrom } : {}),
        ...(scope?.ingestedBefore
          ? { ingested_before: scope.ingestedBefore }
          : {}),
        ...(scope?.rerank ? { rerank: true } : {}),
      }),
    }),
  importSource: (title: string, content: string, uri?: string) =>
    request<Source>("/api/v1/sources", {
      method: "POST",
      body: JSON.stringify({ title, content, kind: "markdown", uri }),
    }),
  importGitRepository: (path: string) =>
    request<{
      commit_sha: string;
      created_count: number;
      unchanged_count: number;
      failed_count: number;
    }>("/api/v1/git-repositories", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
};
