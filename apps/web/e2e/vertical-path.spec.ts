import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const fixture = fileURLToPath(new URL("./fixtures/vertical-path.md", import.meta.url));
const hostileMarker = "window.__prooflineE2ECompromised = true";

test("local evidence-first workflow preserves provenance and renders hostile source text inert", async ({ page }) => {
  const externalRequests: string[] = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (["http:", "https:", "ws:", "wss:"].includes(url.protocol)
      && !["127.0.0.1", "localhost", "[::1]", "::1"].includes(url.hostname)) {
      externalRequests.push(url.href);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByText("Index ready")).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles(fixture);
  await expect(page.getByRole("heading", { name: "Memories", level: 1 })).toBeVisible();

  const decision = page.locator(".memory-card").filter({
    hasText: "Use SQLite for the local job queue",
  });
  await expect(decision).toBeVisible();
  await decision.getByRole("combobox").selectOption("accepted");
  await expect(decision.locator(".status")).toHaveText("accepted");

  await decision.getByRole("button", { name: /Edit decision:/ }).click();
  const correctionForm = page.getByRole("form", { name: "Edit decision memory" });
  await correctionForm.getByLabel("Statement").fill("Use SQLite for the durable local job queue");
  await correctionForm.getByLabel("Rationale").fill("Confirmed during the E2E architecture review.");
  await correctionForm.getByRole("button", { name: "Save correction" }).click();
  const correctedDecision = page.locator(".memory-card").filter({
    hasText: "Use SQLite for the durable local job queue",
  });
  await expect(correctedDecision).toContainText("Confirmed during the E2E architecture review.");
  await expect(correctedDecision.locator(".status")).toHaveText("accepted");

  await page.getByRole("button", { name: "Search", exact: true }).first().click();
  const searchForm = page.locator("form.search-box");
  await searchForm.getByLabel("Search engineering memory").fill("transactional recovery");
  await searchForm.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("heading", { name: /evidence matches/ })).toBeVisible();

  const retrievalResult = page.locator(".result-card").filter({ hasText: "transactional recovery" }).last();
  await expect(retrievalResult).toBeVisible();
  await retrievalResult.getByText("Why this result?").click();
  await expect(retrievalResult.getByText("lexical", { exact: true })).toBeVisible();
  await expect(retrievalResult.getByText(/offsets \d+:\d+/)).toBeVisible();
  await retrievalResult.getByRole("button", { name: /Lines \d+–\d+/ }).click();
  const evidenceDrawer = page.locator(".drawer");
  await expect(evidenceDrawer.getByText("EXACT EVIDENCE")).toBeVisible();
  await expect(evidenceDrawer.locator("blockquote")).toContainText("transactional recovery");
  await expect(evidenceDrawer).toContainText(/offsets \d+:\d+/);
  await evidenceDrawer.getByRole("button", { name: "Close evidence" }).click();

  await searchForm.getByLabel("Search engineering memory").fill("prooflineE2ECompromised");
  await searchForm.getByRole("button", { name: "Search" }).click();
  const hostileResult = page.locator(".result-card").filter({ hasText: hostileMarker }).last();
  await expect(hostileResult).toContainText(`<script>${hostileMarker}</script>`);
  await expect(hostileResult).toContainText(`<img src=x onerror="${hostileMarker}">`);
  await expect(hostileResult.locator("script")).toHaveCount(0);
  await expect(hostileResult.locator("img")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as Window & {
    __prooflineE2ECompromised?: boolean;
  }).__prooflineE2ECompromised)).toBeUndefined();

  await page.getByRole("button", { name: /^Sources\b/ }).click();
  const sourceRow = page.locator(".table-row").filter({ hasText: "vertical-path.md" });
  await sourceRow.getByRole("button", { name: "Delete vertical-path.md" }).click();
  const deletionDialog = page.getByRole("dialog", { name: "Delete vertical-path.md?" });
  await expect(deletionDialog.getByText("DELETION IMPACT", { exact: true })).toBeVisible();
  await expect(deletionDialog.getByText("Versions").locator("..")).toContainText("1");
  await expect(deletionDialog.getByText("Memories").locator("..")).toContainText("2");
  await expect(deletionDialog.getByText("Evidence").locator("..")).toContainText("2");
  await deletionDialog.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("vertical-path.md")).toHaveCount(0);
  await expect(page.getByText("0", { exact: true }).first()).toBeVisible();

  expect(externalRequests).toEqual([]);
});

test("decision health opens exact drift evidence without responsive overflow", async ({ page }) => {
  const uri = "file:///decision-health-e2e.md";
  const original = "# Queue\n\nDecision: Use SQLite.\nReason: local durability.";
  const changed = "# Queue\n\nDecision: Use NATS.\nReason: shared workload.";
  const created = await page.request.post("/api/v1/sources", {
    data: { title: "Decision Health E2E", uri, content: original },
  });
  expect(created.ok()).toBeTruthy();
  const source = await created.json();
  const memories = await (await page.request.get("/api/v1/memories")).json();
  const decision = memories.find(
    (item: { source_id: string; kind: string }) =>
      item.source_id === source.id && item.kind === "decision",
  );
  expect(decision).toBeTruthy();
  expect(
    (
      await page.request.patch(`/api/v1/memories/${decision.id}`, {
        data: { status: "accepted" },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await page.request.post("/api/v1/sources", {
        data: { title: "Decision Health E2E", uri, content: changed },
      })
    ).ok(),
  ).toBeTruthy();
  const reviews = await (
    await page.request.get("/api/v1/decision-reviews", { params: { state: "open" } })
  ).json();
  const review = reviews.find(
    (item: { decision_id: string }) => item.decision_id === decision.id,
  );
  expect(review).toBeTruthy();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Decision Health", level: 1 })).toBeVisible();
  await expect(page.getByText("Accepted · review required")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.getByRole("button", { name: `Open review ${review.id}` }).click();
  const drawer = page.getByRole("dialog", { name: "Decision review detail" });
  await expect(drawer.getByText("Decision: Use SQLite.")).toBeVisible();
  await expect(drawer.getByText("Decision: Use NATS.")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(drawer).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});
