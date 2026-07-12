import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, SourcesView } from "./App";
import type { IngestionJob, Source } from "./types";

const apiMock = vi.hoisted(() => ({
  overview: vi.fn(),
  sources: vi.fn(),
  decisions: vi.fn(),
  jobs: vi.fn(),
  extractDecisions: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

const source: Source = {
  id: "source-1",
  title: "ADR-001",
  kind: "markdown",
  uri: "file://adr-001.md",
  status: "indexed",
  created_at: "2026-07-12T10:00:00Z",
  indexed_at: "2026-07-12T10:00:01Z",
  current_version_id: "version-1",
  version_count: 1,
  chunk_count: 2,
  decision_count: 1,
};

function job(overrides: Partial<IngestionJob> = {}): IngestionJob {
  return {
    id: "job-1",
    source_id: source.id,
    source_version_id: "version-1",
    kind: "source_ingestion",
    state: "succeeded",
    stage: "ready",
    attempts: 1,
    error_code: null,
    error_detail: null,
    retryable: false,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:01Z",
    ...overrides,
  };
}

describe("source ingestion diagnostics", () => {
  beforeEach(() => {
    for (const mock of Object.values(apiMock)) mock.mockReset();
  });

  afterEach(() => cleanup());

  it("shows the latest successful job as ready instead of an older failure", () => {
    render(<SourcesView
      sources={[source]}
      jobs={[
        job(),
        job({
          id: "old-job",
          state: "failed",
          stage: "indexing",
          error_code: "old_failure",
          updated_at: "2026-07-12T09:00:00Z",
        }),
      ]}
      onChanged={vi.fn()}
    />);

    expect(screen.getByText("succeeded · ready")).toBeInTheDocument();
    expect(screen.getByText("Attempt 1 · Not retryable")).toBeInTheDocument();
    expect(screen.queryByText("old_failure")).not.toBeInTheDocument();
  });

  it("shows safe failed-job fields without rendering attached source content", () => {
    const failedJob = {
      ...job({
        state: "failed",
        stage: "indexing",
        attempts: 2,
        error_code: "parser_failed",
        error_detail: "Parser rejected an unsupported encoding",
        retryable: true,
      }),
      content: "PRIVATE SOURCE CONTENT MUST NOT APPEAR",
    } as IngestionJob;

    render(<SourcesView sources={[source]} jobs={[failedJob]} onChanged={vi.fn()}/>);

    expect(screen.getByText("failed · indexing")).toBeInTheDocument();
    expect(screen.getByText("Attempt 2 · Retryable")).toBeInTheDocument();
    expect(screen.getByText("parser_failed")).toBeInTheDocument();
    expect(screen.getByText("Parser rejected an unsupported encoding")).toBeInTheDocument();
    expect(screen.queryByText("PRIVATE SOURCE CONTENT MUST NOT APPEAR")).not.toBeInTheDocument();
  });

  it("marks the global index degraded when a latest source job failed", async () => {
    apiMock.overview.mockResolvedValue({ sources: 1, chunks: 2, decisions: 1, evidence: 1 });
    apiMock.sources.mockResolvedValue([source]);
    apiMock.decisions.mockResolvedValue([]);
    apiMock.jobs.mockResolvedValue([job({ state: "failed", stage: "indexing" })]);

    render(<App/>);

    expect(await screen.findByText("Index degraded")).toBeInTheDocument();
    expect(screen.queryByText("Index ready")).not.toBeInTheDocument();
  });

  it("catches extraction failures and displays the safe API error", async () => {
    apiMock.extractDecisions.mockRejectedValue(new Error("AI provider is disabled"));
    render(<SourcesView sources={[source]} jobs={[job()]} onChanged={vi.fn()}/>);

    fireEvent.click(screen.getByRole("button", { name: "Extract AI candidates from ADR-001" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("AI provider is disabled");
  });
});
