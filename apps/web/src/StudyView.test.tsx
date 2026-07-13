import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StudyView } from "./App";
import type { Source, StudyCard } from "./types";

const apiMock = vi.hoisted(() => ({
  createStudyCards: vi.fn(),
  reviewStudyCard: vi.fn(),
}));
vi.mock("./api", () => ({ api: apiMock }));

const source: Source = {
  id: "source-1", title: "Queue lesson", kind: "note", uri: "note://1", status: "indexed",
  created_at: "2026-07-13T00:00:00Z", indexed_at: "2026-07-13T00:00:00Z",
  current_version_id: "version-1", version_count: 1, chunk_count: 1, decision_count: 0, memory_count: 0,
};
const card: StudyCard = {
  id: "card-1", workspace_id: "workspace-1", source_id: source.id,
  source_version_id: "version-123", source_title: source.title,
  question: "Why durable queues?", answer: "They preserve work.", quote_hash: "hash",
  start_offset: 25, end_offset: 44, start_line: 2, end_line: 2, state: "new",
  interval_days: 0, due_at: "2026-07-13T00:00:00Z", created_at: "2026-07-13T00:00:00Z",
  updated_at: "2026-07-13T00:00:00Z",
};

describe("StudyView", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("derives cards from a selected source", async () => {
    apiMock.createStudyCards.mockResolvedValue([card]);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<StudyView cards={[]} sources={[source]} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Derive cards" }));
    await waitFor(() => expect(apiMock.createStudyCards).toHaveBeenCalledWith(source.id));
    expect(await screen.findByText("1 evidence-backed card ready.")).toBeInTheDocument();
  });

  it("reveals exact evidence and records a rating", async () => {
    apiMock.reviewStudyCard.mockResolvedValue({});
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<StudyView cards={[card]} sources={[source]} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Reveal answer" }));
    expect(screen.getByText(card.answer)).toBeInTheDocument();
    expect(screen.getByText(/Exact evidence · L2–2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "good" }));
    await waitFor(() => expect(apiMock.reviewStudyCard).toHaveBeenCalledWith(card.id, "good"));
    expect(onChanged).toHaveBeenCalled();
  });
});
