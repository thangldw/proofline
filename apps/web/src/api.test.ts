import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("search scope API contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("serializes the same scope using repeated search params and answer fields", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ hits: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "insufficient_evidence",
            answer: "Insufficient evidence.",
            statements: [],
            citations: [],
            model_run_id: null,
            exclusions: [],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const scope = {
      sourceIds: ["source-a", "source-b"],
      ingestedFrom: "2026-07-10T00:00:00.000Z",
      ingestedBefore: "2026-07-12T00:00:00.000Z",
    };

    await api.search("Why SQLite?", scope);
    await api.answer("Why SQLite?", scope);

    const searchUrl = new URL(
      fetchMock.mock.calls[0][0],
      "http://proofline.local",
    );
    expect(searchUrl.pathname).toBe("/api/v1/search");
    expect(searchUrl.searchParams.get("q")).toBe("Why SQLite?");
    expect(searchUrl.searchParams.getAll("source_id")).toEqual([
      "source-a",
      "source-b",
    ]);
    expect(searchUrl.searchParams.get("ingested_from")).toBe(
      scope.ingestedFrom,
    );
    expect(searchUrl.searchParams.get("ingested_before")).toBe(
      scope.ingestedBefore,
    );

    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      question: "Why SQLite?",
      source_ids: ["source-a", "source-b"],
      ingested_from: scope.ingestedFrom,
      ingested_before: scope.ingestedBefore,
    });
  });

  it("sends the selected workspace on subsequent requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ sources: 0, chunks: 0, decisions: 0, memories: 0, evidence: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    api.setWorkspace("workspace-platform");
    await api.overview();

    expect(fetchMock.mock.calls[0][1].headers["X-Proofline-Workspace-ID"]).toBe(
      "workspace-platform",
    );
  });

  it("serializes decision review filters and mutation payloads", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.decisionReviews({
      state: "open",
      anchorState: "changed",
      severity: "warning",
      limit: 25,
    });
    await api.updateDecisionReview("review-1", {
      action: "waive",
      reason: "time-boxed exception",
    });
    await api.reanchorDecisionReview("review-1", {
      expected_current_source_version_id: "version-current",
      start_offset: 12,
      end_offset: 31,
      reason: "reviewed exact replacement",
    });
    await api.resolveDecisionReview("review-1", {
      action: "supersede_decision",
      replacement_decision_id: "decision-2",
      reason: "replacement accepted",
    });

    const listUrl = new URL(fetchMock.mock.calls[0][0], "http://proofline.local");
    expect(listUrl.pathname).toBe("/api/v1/decision-reviews");
    expect(Object.fromEntries(listUrl.searchParams)).toEqual({
      state: "open",
      anchor_state: "changed",
      severity: "warning",
      limit: "25",
    });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/decision-reviews/review-1");
    expect(fetchMock.mock.calls[1][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      action: "waive",
      reason: "time-boxed exception",
    });
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/v1/decision-reviews/review-1/reanchor",
    );
    expect(fetchMock.mock.calls[3][0]).toBe(
      "/api/v1/decision-reviews/review-1/resolve",
    );
  });

  it("maps content-free API error objects to stable messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "review_state_conflict" } }),
          {
            status: 409,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(
      api.updateDecisionReview("review-1", { action: "acknowledge" }),
    ).rejects.toThrow("review_state_conflict");
  });
});
