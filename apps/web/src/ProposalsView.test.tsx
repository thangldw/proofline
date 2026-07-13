import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProposalsView } from "./App";
import type { ActionProposal } from "./types";

const apiMock = vi.hoisted(() => ({
  createActionProposal: vi.fn(),
  reviewActionProposal: vi.fn(),
}));
vi.mock("./api", () => ({ api: apiMock }));

const proposal: ActionProposal = {
  id: "proposal-1", workspace_id: "workspace-1", goal: "What should change?",
  body: "Add bounded retries.", status: "candidate", model_run_id: "model-run-123",
  created_at: "2026-07-13T00:00:00Z", updated_at: "2026-07-13T00:00:00Z",
  citations: [{
    id: "citation-1", source_id: "source-1", source_version_id: "version-123",
    chunk_id: "chunk-1", source_title: "Queue evidence", quote: "Retries reduce loss.",
    quote_hash: "hash", start_offset: 0, end_offset: 20, start_line: 1, end_line: 1,
  }],
};

describe("ProposalsView", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("requests a grounded proposal", async () => {
    apiMock.createActionProposal.mockResolvedValue(proposal);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<ProposalsView proposals={[]} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Goal or decision to plan"), {
      target: { value: proposal.goal },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create proposal" }));
    await waitFor(() => expect(apiMock.createActionProposal).toHaveBeenCalledWith(proposal.goal));
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows immutable evidence and records human acceptance", async () => {
    apiMock.reviewActionProposal.mockResolvedValue({ ...proposal, status: "accepted" });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<ProposalsView proposals={[proposal]} onChanged={onChanged} />);
    expect(screen.getByText("Retries reduce loss.")).toBeInTheDocument();
    expect(screen.getByText(/Immutable version version-/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Accept proposal" }));
    await waitFor(() =>
      expect(apiMock.reviewActionProposal).toHaveBeenCalledWith(proposal.id, "accepted"),
    );
    expect(await screen.findByText(/no source content was changed/)).toBeInTheDocument();
  });
});
