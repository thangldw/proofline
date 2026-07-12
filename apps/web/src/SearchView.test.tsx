import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchView } from "./App";
import type { GroundedAnswer, SearchHit, Source } from "./types";

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
  fused_score: 0.0164,
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

const sources: Source[] = [{
  id: "source-a",
  title: "ADR-001",
  kind: "markdown",
  uri: "file:///adr-001.md",
  status: "indexed",
  created_at: "2026-07-10T00:00:00Z",
  indexed_at: "2026-07-11T00:00:00Z",
  current_version_id: "version-a",
  version_count: 1,
  chunk_count: 1,
  decision_count: 1,
  memory_count: 1,
}, {
  id: "source-b",
  title: "Architecture notes",
  kind: "markdown",
  uri: "file:///architecture.md",
  status: "indexed",
  created_at: "2026-07-10T00:00:00Z",
  indexed_at: "2026-07-12T00:00:00Z",
  current_version_id: "version-b",
  version_count: 1,
  chunk_count: 1,
  decision_count: 0,
  memory_count: 0,
}];

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

  it("passes one identical source and ingestion-time scope to search and answer", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    render(<SearchView sources={sources} onEvidence={vi.fn()}/>);

    fireEvent.click(screen.getByText("Search scope · all indexed sources"));
    fireEvent.click(screen.getByRole("checkbox", { name: "ADR-001" }));
    fireEvent.change(screen.getByLabelText("Indexed from"), {
      target: { value: "2026-07-10T09:30" },
    });
    fireEvent.change(screen.getByLabelText("Indexed before"), {
      target: { value: "2026-07-12T18:00" },
    });
    submitSearch();

    const expectedScope = {
      sourceIds: ["source-a"],
      ingestedFrom: new Date("2026-07-10T09:30").toISOString(),
      ingestedBefore: new Date("2026-07-12T18:00").toISOString(),
    };
    await waitFor(() => expect(apiMock.search).toHaveBeenCalledWith("Why SQLite?", expectedScope));
    expect(apiMock.answer).toHaveBeenCalledWith("Why SQLite?", expectedScope);
    const summary = screen.getByLabelText("Active search scope");
    expect(summary).toHaveTextContent("Scoped search");
    expect(summary).toHaveTextContent("ADR-001");
    expect(summary).toHaveTextContent("Indexed from 2026-07-10T09:30 until before 2026-07-12T18:00");
  });

  it("supports selecting multiple sources and clearing the complete scope", () => {
    render(<SearchView sources={sources} onEvidence={vi.fn()}/>);
    fireEvent.click(screen.getByText("Search scope · all indexed sources"));
    fireEvent.click(screen.getByRole("checkbox", { name: "ADR-001" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Architecture notes" }));
    fireEvent.change(screen.getByLabelText("Indexed before"), {
      target: { value: "2026-07-12T18:00" },
    });

    expect(screen.getByText("Search scope · 3 active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear scope" }));

    expect(screen.getByRole("checkbox", { name: "ADR-001" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Architecture notes" })).not.toBeChecked();
    expect(screen.getByLabelText("Indexed before")).toHaveValue("");
    expect(screen.getByLabelText("Active search scope")).toHaveTextContent("All indexed sources");
    expect(screen.getByLabelText("Active search scope")).toHaveTextContent("Any ingestion time");
  });

  it("rejects an inverted indexed-time range before either request", async () => {
    render(<SearchView sources={sources} onEvidence={vi.fn()}/>);
    fireEvent.click(screen.getByText("Search scope · all indexed sources"));
    fireEvent.change(screen.getByLabelText("Indexed from"), {
      target: { value: "2026-07-13T09:00" },
    });
    fireEvent.change(screen.getByLabelText("Indexed before"), {
      target: { value: "2026-07-12T09:00" },
    });
    submitSearch();

    expect(await screen.findByRole("alert")).toHaveTextContent("Indexed from must be earlier than indexed before");
    expect(apiMock.search).not.toHaveBeenCalled();
    expect(apiMock.answer).not.toHaveBeenCalled();
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

  it("keeps lexical-only retrieval diagnostics collapsed and does not imply semantic data", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    await screen.findByText(hits[0].content);
    const summary = screen.getByText("Why this result?");
    expect(summary.tagName).toBe("SUMMARY");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(summary);
    expect(details).toHaveAttribute("open");
    expect(within(details!).getByText("lexical")).toBeInTheDocument();
    expect(within(details!).getByText("#1")).toBeInTheDocument();
    expect(within(details!).getByText("version-")).toHaveAttribute("title", "version-a");
    expect(within(details!).getByText("Lines 3–4 · offsets 10:77")).toBeInTheDocument();
    expect(within(details!).queryByText("Semantic rank")).not.toBeInTheDocument();
    expect(within(details!).queryByText("Semantic score")).not.toBeInTheDocument();
    expect(within(details!).getByText("RRF score").nextElementSibling).toHaveTextContent("0.0164");
  });

  it("shows available hybrid ranks and scores without fabricating metadata", async () => {
    const hybridHit: SearchHit = {
      ...hits[0],
      chunk_id: "hybrid-evidence",
      source_version_id: "version-hybrid-1234",
      retrieval_channels: ["lexical", "semantic"],
      lexical_rank: 2,
      semantic_rank: 1,
      semantic_score: 0.8765,
      fused_score: 0.0321,
    };
    apiMock.search.mockResolvedValue([hybridHit]);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    await screen.findByText(hybridHit.content);
    const summary = screen.getByText("Why this result?");
    fireEvent.click(summary);
    const details = summary.closest("details")!;
    expect(within(details).getByText("lexical + semantic")).toBeInTheDocument();
    expect(within(details).getByText("Lexical rank").nextElementSibling).toHaveTextContent("#2");
    expect(within(details).getByText("Semantic rank").nextElementSibling).toHaveTextContent("#1");
    expect(within(details).getByText("Semantic score").nextElementSibling).toHaveTextContent("0.8765");
    expect(within(details).getByText("RRF score").nextElementSibling).toHaveTextContent("0.0321");
    expect(within(details).getByText("version-")).toHaveAttribute("title", "version-hybrid-1234");
  });

  it("still opens the exact raw evidence span alongside retrieval diagnostics", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    const onEvidence = vi.fn();
    render(<SearchView onEvidence={onEvidence}/>);

    submitSearch();
    fireEvent.click(await screen.findByRole("button", { name: "Lines 3–4" }));

    expect(onEvidence).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "evidence-a",
        source_id: "source-a",
        source_version_id: "version-a",
        quote: hits[0].content,
        start_offset: 10,
        end_offset: 77,
        start_line: 3,
        end_line: 4,
      }),
      "ADR-001",
    );
  });

  it("shows a non-error context-budget notice for excluded evidence", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue({
      status: "insufficient_evidence",
      answer: "The retained context is insufficient for a grounded answer.",
      statements: [],
      citations: [],
      model_run_id: null,
      exclusions: [
        { evidence_id: "abc12345-full-id", reason: "context_budget" },
        { evidence_id: "def67890-full-id", reason: "context_budget" },
      ],
    });
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    const notice = await screen.findByRole("status", { name: "Context budget notice" });
    expect(notice).toHaveTextContent("2 retrieved spans were excluded by the context budget");
    expect(within(notice).getByText("abc12345")).toHaveAttribute("title", "abc12345-full-id");
    expect(within(notice).getByText("def67890")).toHaveAttribute("title", "def67890-full-id");
    expect(notice).not.toHaveClass("error-banner");
  });

  it("remains compatible with answers that omit exclusions", async () => {
    apiMock.search.mockResolvedValue(hits);
    apiMock.answer.mockResolvedValue(groundedAnswer);
    render(<SearchView onEvidence={vi.fn()}/>);

    submitSearch();

    await screen.findByRole("heading", { name: "Evidence-backed answer" });
    expect(screen.queryByRole("status", { name: "Context budget notice" })).not.toBeInTheDocument();
  });
});
