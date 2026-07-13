import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ModelRunsView } from "./App";
import type { ModelRun } from "./types";

const apiMock = vi.hoisted(() => ({
  modelRuns: vi.fn(),
  modelRun: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

function run(overrides: Partial<ModelRun> = {}): ModelRun {
  return {
    id: "run-child-1234",
    provider_id: "safe-provider",
    model_id: "safe-model",
    operation: "generate",
    template_version: "memory-v1",
    input_hashes: ["PRIVATE INPUT HASH MUST NOT RENDER"],
    parent_run_id: "run-parent-1234",
    attempt_number: 2,
    repair_reason: "structured_output_invalid",
    status: "failed",
    validation_status: "invalid",
    latency_ms: 127,
    prompt_tokens: 41,
    completion_tokens: 9,
    error_code: "provider_request_failed",
    created_at: "2026-07-12T10:00:00Z",
    finished_at: "2026-07-12T10:00:01Z",
    ...overrides,
  };
}

describe("safe model-run diagnostics", () => {
  beforeEach(() => {
    apiMock.modelRuns.mockReset();
    apiMock.modelRun.mockReset();
  });

  afterEach(() => cleanup());

  it("shows accessible loading and empty states", async () => {
    let resolveRuns: (value: ModelRun[]) => void = () => undefined;
    apiMock.modelRuns.mockReturnValue(
      new Promise<ModelRun[]>((resolve) => {
        resolveRuns = resolve;
      }),
    );

    render(<ModelRunsView />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading safe model-run metadata",
    );
    resolveRuns([]);
    expect(
      await screen.findByText("No model runs match these filters."),
    ).toHaveAttribute("role", "status");
  });

  it("applies status, operation, provider, and parent filters", async () => {
    apiMock.modelRuns.mockResolvedValue([]);
    render(<ModelRunsView />);
    await screen.findByText("No model runs match these filters.");

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "failed" },
    });
    fireEvent.change(screen.getByLabelText("Operation"), {
      target: { value: "generate" },
    });
    fireEvent.change(screen.getByLabelText("Provider"), {
      target: { value: "local-provider" },
    });
    fireEvent.change(screen.getByLabelText("Parent run"), {
      target: { value: "parent-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() =>
      expect(apiMock.modelRuns).toHaveBeenLastCalledWith({
        status: "failed",
        operation: "generate",
        providerId: "local-provider",
        parentRunId: "parent-1",
        limit: 100,
      }),
    );
  });

  it("opens safe detail and repair lineage without rendering private payload fields", async () => {
    const child = {
      ...run(),
      prompt: "PRIVATE PROMPT MUST NOT RENDER",
      output: "PRIVATE MODEL OUTPUT MUST NOT RENDER",
      credentials: "PRIVATE CREDENTIAL MUST NOT RENDER",
      source_text: "PRIVATE SOURCE TEXT MUST NOT RENDER",
    } as ModelRun;
    const parent = run({
      id: "run-parent-1234",
      parent_run_id: null,
      attempt_number: 1,
      repair_reason: null,
      error_code: "structured_output_invalid",
    });
    apiMock.modelRuns.mockImplementation(
      ({ parentRunId }: { parentRunId?: string } = {}) =>
        Promise.resolve(parentRunId === child.id ? [] : [child]),
    );
    apiMock.modelRun.mockImplementation((id: string) =>
      Promise.resolve(id === parent.id ? parent : child),
    );

    render(<ModelRunsView />);
    fireEvent.click(
      await screen.findByRole("button", { name: `Open model run ${child.id}` }),
    );

    const detail = await screen.findByRole("heading", {
      name: "generate · safe-provider",
    });
    const panel = detail.closest("aside");
    expect(panel).not.toBeNull();
    expect(
      within(panel!).getByText("provider_request_failed"),
    ).toBeInTheDocument();
    expect(
      within(panel!).getByText("structured_output_invalid"),
    ).toBeInTheDocument();
    expect(
      within(panel!).getByRole("button", { name: /Parent.*run-parent-1234/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE INPUT HASH MUST NOT RENDER"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE PROMPT MUST NOT RENDER"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE MODEL OUTPUT MUST NOT RENDER"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE CREDENTIAL MUST NOT RENDER"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("PRIVATE SOURCE TEXT MUST NOT RENDER"),
    ).not.toBeInTheDocument();
  });

  it("shows a safe list error", async () => {
    apiMock.modelRuns.mockRejectedValue(
      new Error("Diagnostics service unavailable"),
    );
    render(<ModelRunsView />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Diagnostics service unavailable",
    );
  });
});
