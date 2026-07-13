import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StudioView } from "./StudioView";
import type { Source, StudioArtifact } from "./types";

const apiMock = vi.hoisted(() => ({
  createStudioArtifact: vi.fn(),
  deleteStudioArtifact: vi.fn(),
}));
vi.mock("./api", () => ({ api: apiMock }));

const source: Source = {
  id: "source-1", title: "Queue architecture", kind: "markdown", uri: "file://queue.md",
  status: "indexed", created_at: "2026-07-13T00:00:00Z", indexed_at: "2026-07-13T00:00:00Z",
  current_version_id: "version-123", version_count: 1, chunk_count: 1, decision_count: 1, memory_count: 1,
};

const artifact: StudioArtifact = {
  id: "artifact-1", workspace_id: "workspace-1", source_id: source.id,
  source_version_id: "version-123", source_title: source.title, kind: "report",
  title: "Report · Queue architecture", status: "ready", generation_method: "deterministic-v1",
  created_at: "2026-07-13T00:00:00Z", updated_at: "2026-07-13T00:00:00Z",
  content: {
    format: "report", summary: "A grounded report.",
    items: [{ title: "Durability", body: "Queues preserve work.", citation: 0 }],
  },
  citations: [{
    id: "citation-1", source_id: source.id, source_version_id: "version-123",
    source_title: source.title, ordinal: 0, quote: "Queues preserve work.", quote_hash: "hash",
    start_offset: 10, end_offset: 31, start_line: 2, end_line: 2,
  }],
};

describe("StudioView", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("creates a selected Studio artifact from the active source", async () => {
    apiMock.createStudioArtifact.mockResolvedValue(artifact);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<StudioView artifacts={[]} sources={[source]} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Report" }));
    await waitFor(() => expect(apiMock.createStudioArtifact).toHaveBeenCalledWith(source.id, "report"));
    expect(await screen.findByText(/ready with 1 exact citations/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("opens exact immutable evidence from a saved artifact", () => {
    render(<StudioView artifacts={[artifact]} sources={[source]} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Evidence 1" }));
    expect(screen.getAllByText("Queues preserve work.")).toHaveLength(2);
    expect(screen.getByText(/EXACT EVIDENCE · L2–2/)).toBeInTheDocument();
    expect(screen.getByText(/Immutable version version-/)).toBeInTheDocument();
  });
});
