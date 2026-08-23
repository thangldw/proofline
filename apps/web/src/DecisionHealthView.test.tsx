import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { DecisionHealthView } from "./DecisionHealthView";
import type {
  DecisionHealthOverview,
  DecisionReview,
  DecisionReviewDetail,
} from "./types";

const apiMock = vi.hoisted(() => ({
  setWorkspace: vi.fn(),
  workspaces: vi.fn(),
  overview: vi.fn(),
  decisionHealthOverview: vi.fn(),
  decisionReviews: vi.fn(),
  decisionImpacts: vi.fn(),
  decisionImpactSummary: vi.fn(),
  decisionReview: vi.fn(),
  refreshDecisionReviews: vi.fn(),
  updateDecisionReview: vi.fn(),
  reanchorDecisionReview: vi.fn(),
  resolveDecisionReview: vi.fn(),
  sources: vi.fn(),
  notes: vi.fn(),
  studyCards: vi.fn(),
  studioArtifacts: vi.fn(),
  actionProposals: vi.fn(),
  memories: vi.fn(),
  jobs: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

const overview: DecisionHealthOverview = {
  healthy_accepted: 3,
  review_required: 1,
  overdue: 0,
  waived: 2,
};

const review: DecisionReview = {
  id: "review-1",
  workspace_id: "workspace-1",
  decision_id: "decision-1",
  decision_status: "accepted",
  evidence_id: "evidence-1",
  cited_source_version_id: "version-old",
  current_source_version_id: "version-current",
  finding_fingerprint: "a".repeat(64),
  anchor_state: "changed",
  severity: "warning",
  policy_hash: "b".repeat(64),
  candidate_start_offset: 12,
  candidate_end_offset: 31,
  candidate_start_line: 3,
  candidate_end_line: 3,
  state: "open",
  resolution: null,
  actor: "local_system",
  note: null,
  opened_at: "2026-08-23T00:00:00Z",
  updated_at: "2026-08-23T00:00:00Z",
  closed_at: null,
};

const impact = {
  root_review_id: "review-1",
  root_review_fingerprint: "a".repeat(64),
  root_decision_id: "decision-1",
  root_decision_title: "Queue storage",
  impacted_decision_id: "decision-3",
  impacted_decision_title: "Worker topology",
  depth: 2,
  decision_path: ["decision-1", "decision-2", "decision-3"],
  relation_path: ["relation-1", "relation-2"],
  relation_kinds: ["based_on", "implements"] as const,
  evaluated_at: "2026-08-23T12:00:00Z",
  fingerprint: "e".repeat(64),
};

const impactSummary = {
  root_review_count: 1,
  impacted_decision_count: 1,
  finding_count: 1,
  max_depth: 2,
  evaluated_at: "2026-08-23T12:00:00Z",
};

const detail: DecisionReviewDetail = {
  review,
  decision: {
    id: "decision-1",
    title: "Queue ADR",
    statement: "Use SQLite.",
    status: "accepted",
  },
  cited: {
    source_version_id: "version-old",
    content_sha256: "c".repeat(64),
    start_offset: 10,
    end_offset: 31,
    start_line: 3,
    end_line: 3,
    quote: "Decision: Use SQLite.",
  },
  current: {
    source_version_id: "version-current",
    content_sha256: "d".repeat(64),
    candidate: {
      start_offset: 12,
      end_offset: 31,
      start_line: 3,
      end_line: 3,
      quote: "Decision: Use NATS.",
    },
  },
  policy: { blocking: true, hash: "b".repeat(64) },
  audit_events: [
    {
      id: "audit-1",
      actor: "local_system",
      action: "decision_review_opened",
      before: {},
      after: { state: "open" },
      created_at: "2026-08-23T00:00:00Z",
    },
  ],
};

function renderView() {
  return render(
    <DecisionHealthView
      overview={overview}
      workspaceId="workspace-1"
      onOverviewChanged={vi.fn().mockResolvedValue(undefined)}
    />,
  );
}

describe("DecisionHealthView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.decisionReviews.mockResolvedValue([review]);
    apiMock.decisionImpacts.mockResolvedValue([impact]);
    apiMock.decisionImpactSummary.mockResolvedValue(impactSummary);
    apiMock.decisionReview.mockResolvedValue(detail);
    apiMock.refreshDecisionReviews.mockResolvedValue({
      opened: 0,
      superseded: 0,
      resolved: 0,
      updated: 0,
      unchanged: 1,
    });
    apiMock.updateDecisionReview.mockResolvedValue(review);
    apiMock.reanchorDecisionReview.mockResolvedValue(review);
    apiMock.resolveDecisionReview.mockResolvedValue(review);
  });

  afterEach(() => cleanup());

  it("renders metrics and loads exact evidence only after opening a review", async () => {
    renderView();

    expect(screen.getByText("Healthy accepted").previousSibling).toHaveTextContent("3");
    expect(screen.getByText("Review required").previousSibling).toHaveTextContent("1");
    expect(await screen.findByText("Transitively impacted")).toBeInTheDocument();
    expect(screen.getByText("Transitively impacted").previousSibling).toHaveTextContent("1");
    expect(screen.getByText("Queue storage → Worker topology")).toBeInTheDocument();
    expect(screen.getByText("decision-1 → decision-2 → decision-3")).toBeInTheDocument();
    expect(apiMock.decisionReview).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Open review review-1" }));

    expect(apiMock.decisionReview).toHaveBeenCalledWith("review-1");
    const drawer = await screen.findByRole("dialog", { name: "Decision review detail" });
    expect(within(drawer).getByText("Accepted · review required")).toBeInTheDocument();
    expect(within(drawer).getByText("Decision: Use SQLite.")).toBeInTheDocument();
    expect(within(drawer).getByText("Decision: Use NATS.")).toBeInTheDocument();
  });

  it("applies metadata filters without rendering quotes in the inbox", async () => {
    renderView();
    await screen.findByRole("button", { name: "Open review review-1" });

    fireEvent.change(screen.getByLabelText("Review state"), {
      target: { value: "open" },
    });
    fireEvent.change(screen.getByLabelText("Anchor state"), {
      target: { value: "changed" },
    });
    fireEvent.change(screen.getByLabelText("Severity"), {
      target: { value: "warning" },
    });

    await waitFor(() =>
      expect(apiMock.decisionReviews).toHaveBeenLastCalledWith({
        state: "open",
        anchorState: "changed",
        severity: "warning",
        limit: 100,
      }),
    );
    expect(screen.queryByText("Decision: Use SQLite.")).not.toBeInTheDocument();
  });

  it("acknowledges without confirmation and enforces waiver reason", async () => {
    renderView();
    fireEvent.click(await screen.findByRole("button", { name: "Open review review-1" }));
    const drawer = await screen.findByRole("dialog", { name: "Decision review detail" });

    fireEvent.click(within(drawer).getByRole("button", { name: "Acknowledge" }));
    await waitFor(() =>
      expect(apiMock.updateDecisionReview).toHaveBeenCalledWith("review-1", {
        action: "acknowledge",
      }),
    );
    fireEvent.change(within(drawer).getByLabelText("Waiver reason"), {
      target: { value: "time-boxed exception" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Waive" }));
    await waitFor(() =>
      expect(apiMock.updateDecisionReview).toHaveBeenCalledWith("review-1", {
        action: "waive",
        reason: "time-boxed exception",
      }),
    );
  });

  it("confirms evidence and lifecycle mutations", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderView();
    fireEvent.click(await screen.findByRole("button", { name: "Open review review-1" }));
    const drawer = await screen.findByRole("dialog", { name: "Decision review detail" });

    fireEvent.change(within(drawer).getByLabelText("Re-anchor reason"), {
      target: { value: "reviewed exact replacement" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Re-anchor candidate" }));
    await waitFor(() =>
      expect(apiMock.reanchorDecisionReview).toHaveBeenCalledWith("review-1", {
        expected_current_source_version_id: "version-current",
        start_offset: 12,
        end_offset: 31,
        reason: "reviewed exact replacement",
      }),
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "Mark obsolete" }));
    await waitFor(() =>
      expect(apiMock.resolveDecisionReview).toHaveBeenCalledWith("review-1", {
        action: "obsolete_decision",
        reason: "Decision no longer applies.",
      }),
    );
    expect(confirm).toHaveBeenCalledTimes(2);
    confirm.mockRestore();
  });

  it("renders loading, empty, and safe error states", async () => {
    let resolveReviews: (value: DecisionReview[]) => void = () => undefined;
    apiMock.decisionReviews.mockReturnValue(
      new Promise<DecisionReview[]>((resolve) => {
        resolveReviews = resolve;
      }),
    );
    renderView();
    expect(screen.getByRole("status")).toHaveTextContent("Loading decision reviews");
    resolveReviews([]);
    expect(await screen.findByText("No reviews match these filters.")).toBeInTheDocument();

    cleanup();
    apiMock.decisionReviews.mockRejectedValue(new Error("review_state_conflict"));
    render(
      <DecisionHealthView
        overview={overview}
        workspaceId="workspace-2"
        onOverviewChanged={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("review_state_conflict");
  });

  it("renders transitive impact empty and isolated error states", async () => {
    apiMock.decisionImpacts.mockResolvedValue([]);
    apiMock.decisionImpactSummary.mockResolvedValue({
      ...impactSummary,
      root_review_count: 0,
      impacted_decision_count: 0,
      finding_count: 0,
      max_depth: 0,
    });
    renderView();
    expect(await screen.findByText("No transitive impacts.")).toBeInTheDocument();

    cleanup();
    apiMock.decisionImpacts.mockRejectedValue(new Error("impact_graph_unavailable"));
    render(
      <DecisionHealthView
        overview={overview}
        workspaceId="workspace-2"
        onOverviewChanged={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert", { name: "Transitive impact error" })).toHaveTextContent(
      "impact_graph_unavailable",
    );
  });

  it("makes Decision Health the default view with the active-review badge", async () => {
    apiMock.workspaces.mockResolvedValue([
      { id: "workspace-1", slug: "default", title: "Default", created_at: "now" },
    ]);
    apiMock.overview.mockResolvedValue({
      sources: 0,
      chunks: 0,
      decisions: 0,
      memories: 0,
      evidence: 0,
    });
    apiMock.decisionHealthOverview.mockResolvedValue({ ...overview, review_required: 2 });
    for (const method of [
      "sources",
      "notes",
      "studyCards",
      "studioArtifacts",
      "actionProposals",
      "memories",
      "jobs",
    ] as const) {
      apiMock[method].mockResolvedValue([]);
    }

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Decision Health" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decision Health 2" })).toBeInTheDocument();
  });
});
