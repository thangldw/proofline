import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryView } from "./App";
import type { Memory, MemoryKind } from "./types";

const apiMock = vi.hoisted(() => ({ updateMemory: vi.fn() }));

vi.mock("./api", () => ({ api: apiMock }));

function memory(kind: MemoryKind, status = "candidate"): Memory {
  return {
    id: `${kind}-1`,
    source_id: "source-1",
    source_version_id: "version-1",
    source_title: "Architecture ADR",
    kind,
    title: `${kind} title`,
    statement: `${kind} statement`,
    rationale: `${kind} rationale`,
    status,
    confidence: 0.9,
    extraction_method: "model",
    model_run_id: "run-1",
    valid_from: null,
    valid_to: null,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:00Z",
    evidence: [{
      id: `${kind}-evidence`,
      source_id: "source-1",
      source_version_id: "version-1",
      quote: `${kind} source quote`,
      start_offset: 10,
      end_offset: 30,
      start_line: 4,
      end_line: 5,
    }],
  };
}

const memories = [
  memory("decision", "active"),
  memory("assumption"),
  memory("constraint", "accepted"),
  memory("alternative", "rejected"),
];

describe("MemoryView", () => {
  beforeEach(() => apiMock.updateMemory.mockReset());
  afterEach(() => cleanup());

  it("renders kind badges and filters by every generalized memory kind", () => {
    render(<MemoryView memories={memories} onEvidence={vi.fn()} onChanged={vi.fn()}/>);

    for (const kind of ["decision", "assumption", "constraint", "alternative"]) {
      expect(screen.getByLabelText(`Memory kind: ${kind}`)).toBeInTheDocument();
    }
    const kindFilters = screen.getByRole("group", { name: "Kind" });
    fireEvent.click(within(kindFilters).getByRole("button", { name: "Assumptions" }));

    expect(screen.getByText("assumption statement")).toBeInTheDocument();
    expect(screen.queryByText("decision statement")).not.toBeInTheDocument();
    expect(screen.queryByText("constraint statement")).not.toBeInTheDocument();
    expect(screen.queryByText("alternative statement")).not.toBeInTheDocument();
    expect(within(kindFilters).getByRole("button", { name: "Assumptions" })).toHaveAttribute("aria-pressed", "true");
  });

  it("combines status and kind filters honestly", () => {
    render(<MemoryView memories={memories} onEvidence={vi.fn()} onChanged={vi.fn()}/>);
    const kindFilters = screen.getByRole("group", { name: "Kind" });
    const statusFilters = screen.getByRole("group", { name: "Status" });

    fireEvent.click(within(statusFilters).getByRole("button", { name: "accepted" }));
    expect(screen.getByText("constraint statement")).toBeInTheDocument();
    expect(screen.queryByText("assumption statement")).not.toBeInTheDocument();
    fireEvent.click(within(kindFilters).getByRole("button", { name: "Assumptions" }));

    expect(screen.getByText("No memories match these filters. Import an ADR or change the selected kind and status.")).toBeInTheDocument();
  });

  it("reviews a memory through the generalized PATCH endpoint", async () => {
    const candidate = memories[1];
    apiMock.updateMemory.mockResolvedValue({ ...candidate, status: "accepted" });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<MemoryView memories={[candidate]} onEvidence={vi.fn()} onChanged={onChanged}/>);

    fireEvent.click(screen.getByRole("button", { name: "Accept assumption: assumption statement" }));

    await waitFor(() => expect(apiMock.updateMemory).toHaveBeenCalledWith(
      candidate.id,
      { status: "accepted" },
    ));
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("opens the exact evidence span for any memory kind", () => {
    const assumption = memories[1];
    const onEvidence = vi.fn();
    render(<MemoryView memories={[assumption]} onEvidence={onEvidence} onChanged={vi.fn()}/>);

    fireEvent.click(screen.getByRole("button", { name: "View proof · L4–5" }));

    expect(onEvidence).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "assumption-evidence",
        source_version_id: "version-1",
        start_offset: 10,
        end_offset: 30,
      }),
      "Architecture ADR",
    );
  });
});
