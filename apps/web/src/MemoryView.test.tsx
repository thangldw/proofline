import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryView } from "./App";
import type { Memory, MemoryKind } from "./types";

const apiMock = vi.hoisted(() => ({
  updateMemory: vi.fn(),
  decisionTimeline: vi.fn(),
}));

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
    evidence: [
      {
        id: `${kind}-evidence`,
        source_id: "source-1",
        source_version_id: "version-1",
        quote: `${kind} source quote`,
        start_offset: 10,
        end_offset: 30,
        start_line: 4,
        end_line: 5,
      },
    ],
  };
}

const memories = [
  memory("decision", "active"),
  memory("assumption"),
  memory("constraint", "accepted"),
  memory("alternative", "rejected"),
];

describe("MemoryView", () => {
  beforeEach(() => {
    apiMock.updateMemory.mockReset();
    apiMock.decisionTimeline.mockReset();
  });
  afterEach(() => cleanup());

  it("renders kind badges and filters by every generalized memory kind", () => {
    render(
      <MemoryView
        memories={memories}
        onEvidence={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    for (const kind of [
      "decision",
      "assumption",
      "constraint",
      "alternative",
    ]) {
      expect(screen.getByLabelText(`Memory kind: ${kind}`)).toBeInTheDocument();
    }
    const kindFilters = screen.getByRole("group", { name: "Kind" });
    fireEvent.click(
      within(kindFilters).getByRole("button", { name: "Assumptions" }),
    );

    expect(screen.getByText("assumption statement")).toBeInTheDocument();
    expect(screen.queryByText("decision statement")).not.toBeInTheDocument();
    expect(screen.queryByText("constraint statement")).not.toBeInTheDocument();
    expect(screen.queryByText("alternative statement")).not.toBeInTheDocument();
    expect(
      within(kindFilters).getByRole("button", { name: "Assumptions" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("combines status and kind filters honestly", () => {
    render(
      <MemoryView
        memories={memories}
        onEvidence={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    const kindFilters = screen.getByRole("group", { name: "Kind" });
    const statusFilters = screen.getByRole("group", { name: "Status" });

    fireEvent.click(
      within(statusFilters).getByRole("button", { name: "accepted" }),
    );
    expect(screen.getByText("constraint statement")).toBeInTheDocument();
    expect(screen.queryByText("assumption statement")).not.toBeInTheDocument();
    fireEvent.click(
      within(kindFilters).getByRole("button", { name: "Assumptions" }),
    );

    expect(
      screen.getByText(
        "No memories match these filters. Import an ADR or change the selected kind and status.",
      ),
    ).toBeInTheDocument();
  });

  it("reviews a memory through the generalized PATCH endpoint", async () => {
    const candidate = memories[1];
    apiMock.updateMemory.mockResolvedValue({
      ...candidate,
      status: "accepted",
    });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryView
        memories={[candidate]}
        onEvidence={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Status for assumption: assumption statement",
      }),
      {
        target: { value: "accepted" },
      },
    );

    await waitFor(() =>
      expect(apiMock.updateMemory).toHaveBeenCalledWith(candidate.id, {
        status: "accepted",
      }),
    );
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("shows temporal decision transitions without hiding source evidence", async () => {
    const decision = memories[0];
    apiMock.decisionTimeline.mockResolvedValue({
      decision: { ...decision, valid_from: "2026-07-14T04:30:00Z" },
      incoming: [],
      outgoing: [
        {
          id: "relation-1",
          source_decision_id: decision.id,
          target_decision_id: "older",
          kind: "supersedes",
          valid_from: "2026-07-14T04:30:00Z",
          valid_to: null,
          created_by: "local_user",
          created_at: "2026-07-14T04:30:00Z",
        },
      ],
    });
    render(
      <MemoryView
        memories={[decision]}
        onEvidence={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "View timeline" }));
    await waitFor(() =>
      expect(apiMock.decisionTimeline).toHaveBeenCalledWith(decision.id),
    );
    expect(screen.getByText(/Valid 2026-07-14/)).toBeInTheDocument();
    expect(screen.getByText(/supersedes/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /View proof/ }),
    ).toBeInTheDocument();
  });

  it("saves a governed statement and rationale correction", async () => {
    const assumption = memories[1];
    apiMock.updateMemory.mockResolvedValue({
      ...assumption,
      statement: "Corrected assumption",
      rationale: "Updated rationale",
    });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryView
        memories={[assumption]}
        onEvidence={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Edit assumption: assumption statement",
      }),
    );
    const form = screen.getByRole("form", { name: "Edit assumption memory" });
    expect(
      within(form).getByRole("textbox", { name: "Statement" }),
    ).toHaveValue("assumption statement");
    expect(
      within(form).getByRole("textbox", { name: "Rationale" }),
    ).toHaveValue("assumption rationale");
    fireEvent.change(within(form).getByRole("textbox", { name: "Statement" }), {
      target: { value: "  Corrected assumption  " },
    });
    fireEvent.change(within(form).getByRole("textbox", { name: "Rationale" }), {
      target: { value: " Updated rationale " },
    });
    fireEvent.click(
      within(form).getByRole("button", { name: "Save correction" }),
    );

    await waitFor(() =>
      expect(apiMock.updateMemory).toHaveBeenCalledWith(assumption.id, {
        statement: "Corrected assumption",
        rationale: "Updated rationale",
      }),
    );
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("cancels a correction without mutating memory", () => {
    const assumption = memories[1];
    render(
      <MemoryView
        memories={[assumption]}
        onEvidence={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Edit assumption: assumption statement",
      }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Statement" }), {
      target: { value: "Discard this edit" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByRole("form", { name: "Edit assumption memory" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("assumption statement")).toBeInTheDocument();
    expect(apiMock.updateMemory).not.toHaveBeenCalled();
  });

  it("keeps the correction form and reports PATCH failures inline", async () => {
    const assumption = memories[1];
    apiMock.updateMemory.mockResolvedValue(assumption);
    const onChanged = vi
      .fn()
      .mockRejectedValue(
        new Error("Correction conflicted with a newer revision"),
      );
    render(
      <MemoryView
        memories={[assumption]}
        onEvidence={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Edit assumption: assumption statement",
      }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Statement" }), {
      target: { value: "Uncommitted correction" },
    });
    fireEvent.submit(
      screen.getByRole("form", { name: "Edit assumption memory" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Correction conflicted with a newer revision",
    );
    expect(
      screen.getByRole("form", { name: "Edit assumption memory" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Statement" })).toHaveValue(
      "Uncommitted correction",
    );
  });

  it("validates a non-empty corrected statement before PATCH", async () => {
    const assumption = memories[1];
    render(
      <MemoryView
        memories={[assumption]}
        onEvidence={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Edit assumption: assumption statement",
      }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Statement" }), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Statement is required",
    );
    expect(apiMock.updateMemory).not.toHaveBeenCalled();
  });

  it.each(["candidate", "active"] as const)(
    "reverses an accepted memory back to %s",
    async (nextStatus) => {
      const accepted = memory("constraint", "accepted");
      apiMock.updateMemory.mockResolvedValue({
        ...accepted,
        status: nextStatus,
      });
      const onChanged = vi.fn().mockResolvedValue(undefined);
      render(
        <MemoryView
          memories={[accepted]}
          onEvidence={vi.fn()}
          onChanged={onChanged}
        />,
      );
      const status = screen.getByRole("combobox", {
        name: "Status for constraint: constraint statement",
      });
      expect(
        within(status)
          .getAllByRole("option")
          .map((option) => option.getAttribute("value")),
      ).toEqual(["candidate", "active", "accepted", "rejected", "obsolete"]);

      fireEvent.change(status, { target: { value: nextStatus } });

      await waitFor(() =>
        expect(apiMock.updateMemory).toHaveBeenCalledWith(accepted.id, {
          status: nextStatus,
        }),
      );
      expect(onChanged).toHaveBeenCalledOnce();
    },
  );

  it("opens the exact evidence span for any memory kind", () => {
    const assumption = memories[1];
    const onEvidence = vi.fn();
    render(
      <MemoryView
        memories={[assumption]}
        onEvidence={onEvidence}
        onChanged={vi.fn()}
      />,
    );

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
