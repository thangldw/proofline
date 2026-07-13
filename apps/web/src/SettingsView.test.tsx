import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "./App";

const configuration = {
  ai_provider: "disabled",
  ai_base_url: null,
  ai_model: null,
  ai_api_key_configured: false,
  embedding_provider: "disabled",
  embedding_base_url: null,
  embedding_model: null,
  embedding_api_key_configured: false,
  allow_remote_ai: false,
};
const status = (mode: "ready" | "degraded" | "disabled") => ({
  configured: mode !== "disabled",
  provider_id: null,
  model_id: null,
  generation: false,
  structured_output: false,
  embedding: false,
  reranking: false,
  remote_egress_allowed: false,
  healthy: mode === "ready",
  error_code: null,
  mode,
});
const apiMock = vi.hoisted(() => ({
  providerConfiguration: vi.fn(),
  saveProviderConfiguration: vi.fn(),
  generationProviderStatus: vi.fn(),
  embeddingProviderStatus: vi.fn(),
  rerankingProviderStatus: vi.fn(),
}));
vi.mock("./api", () => ({ api: apiMock }));

describe("SettingsView", () => {
  beforeEach(() => {
    apiMock.providerConfiguration.mockResolvedValue(configuration);
    apiMock.generationProviderStatus.mockResolvedValue(status("disabled"));
    apiMock.embeddingProviderStatus.mockResolvedValue(status("disabled"));
    apiMock.rerankingProviderStatus.mockResolvedValue(status("disabled"));
    apiMock.saveProviderConfiguration.mockResolvedValue(configuration);
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("configures explicit provider profiles and never displays stored keys", async () => {
    render(<SettingsView />);
    await screen.findByRole("heading", { name: "Model providers" });
    fireEvent.change(screen.getByLabelText("Generation provider"), {
      target: { value: "ollama" },
    });
    fireEvent.change(screen.getByLabelText("Generation API key"), {
      target: { value: "private-key" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save and check health" }),
    );
    await waitFor(() =>
      expect(apiMock.saveProviderConfiguration).toHaveBeenCalled(),
    );
    expect(apiMock.saveProviderConfiguration.mock.calls[0][0]).toMatchObject({
      ai_provider: "ollama",
      ai_api_key: "private-key",
    });
    expect(screen.queryByText("private-key")).not.toBeInTheDocument();
  });
});
