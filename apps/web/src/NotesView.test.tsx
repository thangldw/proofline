import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotesView } from "./App";
import type { Note } from "./types";

const apiMock = vi.hoisted(() => ({
  createNote: vi.fn(),
  updateNote: vi.fn(),
  noteBacklinks: vi.fn(),
}));
vi.mock("./api", () => ({ api: apiMock }));

const note: Note = {
  id: "note-1",
  workspace_id: "workspace-1",
  title: "Queue design",
  content: "Use durable queues. #architecture",
  uri: "note://note-1",
  current_version_id: "version-1",
  version_count: 1,
  created_at: "2026-07-13T00:00:00Z",
  indexed_at: "2026-07-13T00:00:00Z",
  tags: [
    {
      name: "architecture",
      start_offset: 20,
      end_offset: 33,
      start_line: 1,
      end_line: 1,
    },
  ],
  links: [],
};

describe("NotesView", () => {
  beforeEach(() => apiMock.noteBacklinks.mockResolvedValue([]));

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("captures a plain Markdown note and refreshes the indexed inventory", async () => {
    apiMock.createNote.mockResolvedValue(note);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<NotesView notes={[]} onChanged={onChanged} />);

    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Queue design" },
    });
    fireEvent.change(screen.getByLabelText("Markdown note"), {
      target: { value: "Use durable queues. #architecture" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Capture note" }));

    await waitFor(() =>
      expect(apiMock.createNote).toHaveBeenCalledWith(
        "Queue design",
        "Use durable queues. #architecture",
      ),
    );
    expect(onChanged).toHaveBeenCalled();
    expect(await screen.findByText("Note captured and indexed.")).toBeInTheDocument();
  });

  it("saves edits as revisions", async () => {
    apiMock.updateNote.mockResolvedValue({ ...note, version_count: 2 });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<NotesView notes={[note]} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: /Queue design/ }));
    fireEvent.change(screen.getByLabelText("Markdown note"), {
      target: { value: "Use durable queues with retries." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));

    await waitFor(() =>
      expect(apiMock.updateNote).toHaveBeenCalledWith(
        note.id,
        note.title,
        "Use durable queues with retries.",
      ),
    );
    expect(await screen.findByText("Saved immutable revision 2.")).toBeInTheDocument();
  });

  it("shows deterministic note metadata and exact-version backlinks", async () => {
    apiMock.noteBacklinks.mockResolvedValue([
      {
        target_title: note.title,
        quote: "[[Queue design]]",
        start_offset: 4,
        end_offset: 20,
        start_line: 2,
        end_line: 2,
        resolved_source_id: note.id,
        source_id: "linking-note",
        source_version_id: "version-backlink",
        source_title: "Worker rollout",
      },
    ]);
    render(<NotesView notes={[note]} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Queue design/ }));
    expect(await screen.findByText("#architecture")).toBeInTheDocument();
    expect(await screen.findByText(/Worker rollout · L2–2 · version-/)).toBeInTheDocument();
  });
});
