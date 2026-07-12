import type { Decision, Overview, SearchHit, Source } from "./types";

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
  source: (id: string) => request<Source & { content: string }>(`/api/v1/sources/${id}`),
  sourceVersion: (sourceId: string, versionId: string) =>
    request<{ content: string }>(`/api/v1/sources/${sourceId}/versions/${versionId}`),
  decisions: () => request<Decision[]>("/api/v1/decisions"),
  search: async (query: string) =>
    (await request<{ hits: SearchHit[] }>(`/api/v1/search?q=${encodeURIComponent(query)}`)).hits,
  importSource: (title: string, content: string, uri?: string) =>
    request<Source>("/api/v1/sources", {
      method: "POST",
      body: JSON.stringify({ title, content, kind: "markdown", uri }),
    }),
};
