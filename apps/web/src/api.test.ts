import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("search scope API contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("serializes the same scope using repeated search params and answer fields", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ hits: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: "insufficient_evidence",
        answer: "Insufficient evidence.",
        statements: [],
        citations: [],
        model_run_id: null,
        exclusions: [],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);
    const scope = {
      sourceIds: ["source-a", "source-b"],
      ingestedFrom: "2026-07-10T00:00:00.000Z",
      ingestedBefore: "2026-07-12T00:00:00.000Z",
    };

    await api.search("Why SQLite?", scope);
    await api.answer("Why SQLite?", scope);

    const searchUrl = new URL(fetchMock.mock.calls[0][0], "http://proofline.local");
    expect(searchUrl.pathname).toBe("/api/v1/search");
    expect(searchUrl.searchParams.get("q")).toBe("Why SQLite?");
    expect(searchUrl.searchParams.getAll("source_id")).toEqual(["source-a", "source-b"]);
    expect(searchUrl.searchParams.get("ingested_from")).toBe(scope.ingestedFrom);
    expect(searchUrl.searchParams.get("ingested_before")).toBe(scope.ingestedBefore);

    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      question: "Why SQLite?",
      source_ids: ["source-a", "source-b"],
      ingested_from: scope.ingestedFrom,
      ingested_before: scope.ingestedBefore,
    });
  });
});
