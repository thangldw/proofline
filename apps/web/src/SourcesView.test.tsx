import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, SourcesView } from "./App";
import type { IngestionJob, Source } from "./types";

const apiMock = vi.hoisted(() => ({
  overview: vi.fn(),
  sources: vi.fn(),
  memories: vi.fn(),
  jobs: vi.fn(),
  extractMemories: vi.fn(),
  retryJob: vi.fn(),
  deletionImpact: vi.fn(),
  deleteSource: vi.fn(),
  sourceVersion: vi.fn(),
  workspaces: vi.fn(),
  setWorkspace: vi.fn(),
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
  memory_count: 4,
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
    request_hash: "request-hash-must-not-render",
    max_attempts: 3,
    error_code: null,
    error_detail: null,
    retryable: false,
    created_at: "2026-07-12T10:00:00Z",
    updated_at: "2026-07-12T10:00:01Z",
    started_at: "2026-07-12T10:00:00Z",
    finished_at: "2026-07-12T10:00:01Z",
    ...overrides,
  };
}

const deletionImpact = {
  source_id: source.id,
  title: source.title,
  current_version_id: source.current_version_id,
  versions: 2,
  chunks: 4,
  embeddings: 6,
  decisions: 8,
  memories: 18,
  evidence: 10,
  ingestion_jobs_to_detach: 12,
  audit_events_to_delete: 14,
  fts_rows: 16,
};

describe("source ingestion diagnostics", () => {
  beforeEach(() => {
    for (const mock of Object.values(apiMock)) mock.mockReset();
    apiMock.workspaces.mockResolvedValue([
      {
        id: "00000000-0000-0000-0000-000000000001",
        slug: "local",
        title: "Local workspace",
        created_at: "2026-07-13T00:00:00Z",
      },
    ]);
  });

  afterEach(() => cleanup());

  it("shows the latest successful job as ready instead of an older failure", () => {
    render(
      <SourcesView
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
      />,
    );

    expect(screen.getByText("succeeded · ready")).toBeInTheDocument();
    expect(screen.getByText("Attempt 1/3 · Not retryable")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === "SPAN" &&
          element.textContent === "2 chunks · 4 memories",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Memories found")).toBeInTheDocument();
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

    render(
      <SourcesView sources={[source]} jobs={[failedJob]} onChanged={vi.fn()} />,
    );

    expect(screen.getByText("failed · indexing")).toBeInTheDocument();
    expect(screen.getByText("Attempt 2/3 · Retryable")).toBeInTheDocument();
    expect(screen.getByText("parser_failed")).toBeInTheDocument();
    expect(
      screen.getByText("Parser rejected an unsupported encoding"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry ingestion for ADR-001" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE SOURCE CONTENT MUST NOT APPEAR"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("request-hash-must-not-render"),
    ).not.toBeInTheDocument();
  });

  it("marks the global index degraded when a latest source job failed", async () => {
    apiMock.overview.mockResolvedValue({
      sources: 1,
      chunks: 2,
      decisions: 1,
      memories: 4,
      evidence: 1,
    });
    apiMock.sources.mockResolvedValue([source]);
    apiMock.memories.mockResolvedValue([]);
    apiMock.jobs.mockResolvedValue([
      job({ state: "failed", stage: "indexing" }),
    ]);

    render(<App />);

    expect(await screen.findByText("Index degraded")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Memories 4" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Index ready")).not.toBeInTheDocument();
  });

  it("does not let a newer detached success hide an orphan dead letter", async () => {
    apiMock.overview.mockResolvedValue({
      sources: 0,
      chunks: 0,
      decisions: 0,
      memories: 0,
      evidence: 0,
    });
    apiMock.sources.mockResolvedValue([]);
    apiMock.memories.mockResolvedValue([]);
    apiMock.jobs.mockResolvedValue([
      job({
        id: "detached-success",
        source_id: null,
        updated_at: "2026-07-12T11:00:00Z",
      }),
      job({
        id: "unresolved-dead-letter",
        source_id: null,
        state: "dead_letter",
        retryable: false,
        updated_at: "2026-07-12T10:00:00Z",
      }),
    ]);

    render(<App />);

    expect(await screen.findByText("Index degraded")).toBeInTheDocument();
  });

  it("catches extraction failures and displays the safe API error", async () => {
    apiMock.extractMemories.mockRejectedValue(
      new Error("AI provider is disabled"),
    );
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={vi.fn()} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Extract AI memories from ADR-001" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "AI provider is disabled",
    );
  });

  it("extracts generalized AI memories and refreshes the registry", async () => {
    apiMock.extractMemories.mockResolvedValue([]);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={onChanged} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Extract AI memories from ADR-001" }),
    );

    await waitFor(() =>
      expect(apiMock.extractMemories).toHaveBeenCalledWith(source.id),
    );
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("retries a recent orphan failure and refreshes diagnostics", async () => {
    const orphan = job({
      id: "orphan-job-1234",
      source_id: null,
      source_version_id: null,
      state: "failed",
      stage: "indexing",
      retryable: true,
      error_code: "transient_database_error",
    });
    apiMock.retryJob.mockResolvedValue({
      ...orphan,
      state: "succeeded",
      stage: "ready",
    });
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<SourcesView sources={[]} jobs={[orphan]} onChanged={onChanged} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Retry ingestion job orphan-j" }),
    );

    expect(apiMock.retryJob).toHaveBeenCalledWith("orphan-job-1234");
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(
      screen.getByRole("button", { name: "Retry ingestion job orphan-j" }),
    ).toBeEnabled();
  });

  it("shows dead-letter orphan diagnostics without a retry action", () => {
    const orphan = job({
      id: "dead-job-1234",
      source_id: null,
      source_version_id: null,
      state: "dead_letter",
      stage: "failed",
      retryable: false,
      attempts: 3,
      error_code: "retry_exhausted",
    });
    render(<SourcesView sources={[]} jobs={[orphan]} onChanged={vi.fn()} />);

    expect(screen.getByText("dead_letter · failed")).toBeInTheDocument();
    expect(screen.getByText("Attempt 3/3")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Retry ingestion job/ }),
    ).not.toBeInTheDocument();
  });

  it("catches retry failures without an unhandled rejection", async () => {
    const orphan = job({
      id: "retry-job-1234",
      source_id: null,
      source_version_id: null,
      state: "failed",
      stage: "indexing",
      retryable: true,
    });
    apiMock.retryJob.mockRejectedValue(
      new Error("Retry is no longer available"),
    );
    render(<SourcesView sources={[]} jobs={[orphan]} onChanged={vi.fn()} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Retry ingestion job retry-jo" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Retry is no longer available",
    );
  });

  it("cancels deletion without mutating the source", async () => {
    apiMock.deletionImpact.mockResolvedValue(deletionImpact);
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete ADR-001" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Delete ADR-001?",
    });
    await waitFor(() =>
      expect(
        within(dialog).getByRole("button", { name: "Delete permanently" }),
      ).toBeEnabled(),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(apiMock.deleteSource).not.toHaveBeenCalled();
  });

  it("shows the current version and every exact deletion count", async () => {
    apiMock.deletionImpact.mockResolvedValue(deletionImpact);
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete ADR-001" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Delete ADR-001?",
    });
    expect(await within(dialog).findByText("version-1")).toBeInTheDocument();
    for (const [label, count] of [
      ["Versions", 2],
      ["Chunks", 4],
      ["Embeddings", 6],
      ["Memories", 18],
      ["Decisions", 8],
      ["Evidence", 10],
      ["Jobs detached", 12],
      ["Audit events", 14],
      ["FTS rows", 16],
    ] as const) {
      expect(
        within(dialog).getByText(label).nextElementSibling,
      ).toHaveTextContent(String(count));
    }
  });

  it("confirms deletion through the correct endpoint and refreshes", async () => {
    apiMock.deletionImpact.mockResolvedValue(deletionImpact);
    apiMock.deleteSource.mockResolvedValue(undefined);
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={onChanged} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete ADR-001" }));
    const confirm = await screen.findByRole("button", {
      name: "Delete permanently",
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(apiMock.deletionImpact).toHaveBeenCalledWith(source.id);
    expect(apiMock.deleteSource).toHaveBeenCalledWith(source.id);
    expect(apiMock.deletionImpact.mock.invocationCallOrder[0]).toBeLessThan(
      apiMock.deleteSource.mock.invocationCallOrder[0],
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows preview errors and keeps confirmation disabled", async () => {
    apiMock.deletionImpact.mockRejectedValue(
      new Error("Deletion impact is unavailable"),
    );
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete ADR-001" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Delete ADR-001?",
    });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Deletion impact is unavailable",
    );
    expect(
      within(dialog).getByRole("button", { name: "Delete permanently" }),
    ).toBeDisabled();
    expect(apiMock.deleteSource).not.toHaveBeenCalled();
  });

  it("disables confirmation while deletion is pending", async () => {
    apiMock.deletionImpact.mockResolvedValue(deletionImpact);
    let resolveDelete: (() => void) | undefined;
    apiMock.deleteSource.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveDelete = resolve;
      }),
    );
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <SourcesView sources={[source]} jobs={[job()]} onChanged={onChanged} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete ADR-001" }));
    const confirm = await screen.findByRole("button", {
      name: "Delete permanently",
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    expect(
      await screen.findByRole("button", { name: "Deleting…" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await act(async () => resolveDelete?.());
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });

  it("closes an evidence drawer that belongs to the deleted source", async () => {
    apiMock.overview.mockResolvedValue({
      sources: 1,
      chunks: 2,
      decisions: 1,
      memories: 1,
      evidence: 1,
    });
    apiMock.sources.mockResolvedValue([source]);
    apiMock.jobs.mockResolvedValue([job()]);
    apiMock.memories.mockResolvedValue([
      {
        id: "decision-1",
        source_id: source.id,
        source_version_id: "version-1",
        source_title: source.title,
        kind: "decision",
        title: "Queue decision",
        statement: "Use SQLite",
        rationale: null,
        status: "active",
        confidence: 1,
        extraction_method: "deterministic",
        model_run_id: null,
        valid_from: null,
        valid_to: null,
        created_at: "2026-07-12T10:00:00Z",
        updated_at: "2026-07-12T10:00:00Z",
        evidence: [
          {
            id: "evidence-1",
            source_id: source.id,
            source_version_id: "version-1",
            quote: "Decision: Use SQLite",
            start_offset: 0,
            end_offset: 20,
            start_line: 1,
            end_line: 1,
          },
        ],
      },
    ]);
    apiMock.sourceVersion.mockResolvedValue({
      content: "Decision: Use SQLite",
    });
    apiMock.deletionImpact.mockResolvedValue(deletionImpact);
    apiMock.deleteSource.mockResolvedValue(undefined);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /^Memories/ }));
    fireEvent.click(
      await screen.findByRole("button", { name: "View proof · L1–1" }),
    );
    expect(
      screen.getByRole("button", { name: "Close evidence" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Sources/ }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete ADR-001" }),
    );
    const confirm = await screen.findByRole("button", {
      name: "Delete permanently",
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Close evidence" }),
      ).not.toBeInTheDocument(),
    );
    expect(apiMock.deleteSource).toHaveBeenCalledWith(source.id);
  });
});
