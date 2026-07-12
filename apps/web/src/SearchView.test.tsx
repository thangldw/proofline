import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchView } from "./App";
import type { GroundedAnswer, SearchHit } from "./types";

const apiMock = vi.hoisted(() => ({
  search: vi.fn(),
  answer: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

const hits: SearchHit[] = [{
  chunk_id: "evidence-a",
  source_id: "source-a",
  source_version_id: "version-a",
  source_title: "ADR-001",
  content: "SQLite keeps the local queue operational without external services.",
  start_offset: 10,
  end_offset: 77,
  start_line: 3,
  end_line: 4,
  rank: 1,
  retrieval_channels: ["lexical"],
  lexical_rank: 1,
  semantic_rank: null,
  semantic_score: null,
  fused_score: null,
}];

const groundedAnswer: GroundedAnswer = {
  status: "grounded",
  answer: "The local queue uses SQLite.",
  model_run_id: "run-12345678",
  statements: [
    { text: "SQLite was selected for the local queue.", kind: "direct", evidence_ids: ["evidence-a"] },
    { text: "This avoids an external broker.", kind: "inference", evidence_ids: ["evidence-b"] },
  ],
  citations: [
    {
      evidence_id: "evidence-a",
      source_id: "source-a",
      source_version_id: "version-a",
      source_title: "ADR-001",
      content: "SQLite keeps the local queue operational without external services.",
      start_offset: 10,
      end_offset: 77,
      start_line: 3,
      end_line: 4,
    },
    {
      evidence_id: "evidence-b",
      source_id: "source-b",
      source_version_id: "version-b",
      source_title: "Architecture notes",
      content: "No broker is required in local mode.",
      start_offset: 100,
      end_offset: 136,
      start_line: 8,
      end_line: 8,
    },
  ],
};

function submitSearch() {
  fireEvent.change(screen.getByRole("textbox", { name: "Search engineering memory" }), {
    target: { value: "Why SQLite?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

describe("SearchView provenance", () => {
  beforeEach(() => {
    apiMock.search.mockReset();
    apiMock.answer.mockReset();
  });

  afterEach(() => cleanup());

  it("maps each statement only to its declared citations", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    const onEvidence = vi.fn();
    render(<SearchView onEvidence={onEvidence}/>);

    submitSearch();

    const direct = await screen.findByRole("article", { name: "Answer statement: direct" });
    const inference = screen.getByRole("article", { name: "Answer statement: inference" });
    expect(within(direct).getByRole("button", { name: "ADR-001 · L3–4" })).toBeInTheDocument();
    expect(within(direct).queryByText("Architecture notes · L8–8")).not.toBeInTheDocument();
    expect(within(inference).getByRole("button", { name: "Architecture notes · L8–8" })).toBeInTheDocument();
    expect(within(inference).queryByText("ADR-001 · L3–4")).not.toBeInTheDocument();

    fireEvent.click(within(direct).getByRole("button", { name: "ADR-001 · L3–4" }));
    expect(onEvidence).toHaveBeenCalledWith(expect.objectContaining({ id: "evidence-a" }), "ADR-001");
  });

  it("fails closed when a statement references an unresolved citation", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue({
      ...groundedAnswer,
      statements: [{ text: "Unsupported statement", kind: "direct", evidence_ids: ["missing"] }],
      citations: [groundedAnswer.citations[0]],
    });
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    expect(await screen.findByRole("alert")).toHaveTextContent("Citation integrity failed");
    expect(screen.getByText("integrity failure")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Answer citation integrity failed" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evidence-backed answer" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^grounded$/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Unsupported statement")).not.toBeInTheDocument();
    expect(screen.queryByText(groundedAnswer.answer)).not.toBeInTheDocument();
  });

  it("preserves raw retrieval results when answer generation fails", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockRejectedValue(new Error("Provider timed out"));
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    expect(await screen.findByText(hits[0].content)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Provider timed out");
    expect(screen.getByRole("status")).toHaveTextContent("Showing raw retrieval results");
    await waitFor(() => expect(screen.getByRole("button", { name: "Search" })).toBeEnabled());
  });
});
