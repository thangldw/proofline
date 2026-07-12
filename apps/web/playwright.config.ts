import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const apiPort = 8765;
const webPort = 4173;
const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const virtualenvPython = resolve(repositoryRoot, ".venv/bin/python");
const python = existsSync(virtualenvPython) ? JSON.stringify(virtualenvPython) : "python";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: "line",
  outputDir: resolve(tmpdir(), "proofline-playwright-results"),
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${python} e2e/start_api.py`,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        PROOFLINE_E2E_API_PORT: String(apiPort),
        PROOFLINE_AI_PROVIDER: "disabled",
        PROOFLINE_EMBEDDING_PROVIDER: "disabled",
        PROOFLINE_ALLOW_REMOTE_AI: "false",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        PROOFLINE_API_PROXY: `http://127.0.0.1:${apiPort}`,
      },
    },
  ],
});
