import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("V1 investigation, V2 failure, and V3 replay use static evidence", async ({
  page,
  baseURL,
}) => {
  const unexpected: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() !== "GET" ||
      !request.url().startsWith(`${baseURL}/`) ||
      new URL(request.url()).pathname.startsWith("/api/")
    ) {
      unexpected.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "Inside an AI incident investigation." }),
  ).toBeVisible();
  await expect(page.getByLabel("Recorded case")).toHaveValue("worker-failure");
  await expect(
    page.getByRole("heading", { name: "worker stopped", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Recorded case").selectOption("healthy");
  await expect(
    page.getByRole("heading", { name: "healthy", exact: true }),
  ).toBeVisible();
  await page.getByText("Inspect V1 execution trace").click();
  const v1 = page.locator("#investigation");
  await v1.getByText("read_logs", { exact: false }).first().click();
  await expect(v1.locator("pre:visible").first()).toContainText("evidence_id");

  const evaluation = page.locator("#comparison");
  await expect(evaluation.getByText("19/24", { exact: false })).toBeVisible();
  await expect(evaluation.getByText("23/24", { exact: false })).toBeVisible();
  await expect(
    evaluation.getByText("dependency_config", { exact: true }),
  ).toBeVisible();
  await expect(
    evaluation.getByText("db_latency", { exact: true }),
  ).toBeVisible();
  await page.getByText("Inspect V2 failure trace").click();
  await expect(evaluation.getByText("timeout", { exact: true })).toBeVisible();

  const matrix = evaluation.getByRole("table", {
    name: "Correct, grounded diagnoses per prompt",
  });
  await expect(matrix.locator("tbody tr")).toHaveCount(8);
  const invoice = matrix.getByRole("row").filter({ hasText: "invoice window" });
  await expect(invoice.getByRole("cell")).toHaveText(["0/3", "2/3"]);
  const orphan = matrix.getByRole("row").filter({ hasText: "orphan alert" });
  await expect(orphan.getByRole("cell")).toHaveText(["1/3", "3/3"]);
  const trial = evaluation.getByLabel("Failed trial");
  await expect(trial.locator("option")).toHaveCount(6);
  await trial.selectOption("orphan-alert/baseline/2");
  await expect(
    evaluation.getByText("worker_stopped", { exact: true }),
  ).toBeVisible();
  await expect(
    evaluation.getByText("dependency_config", { exact: true }),
  ).toBeVisible();
  await evaluation.getByText("Inspect V2 failure trace").click();
  await expect(
    evaluation.locator("summary").filter({ hasText: "read_deployments" }),
  ).toBeVisible();

  const replay = page.locator("#replay-state");
  for (const [stage, state, order] of [
    ["Request pending", "Disabled", "queued"],
    ["Wrong confirmation", "Disabled", "queued"],
    ["Approval applied", "Enabled", "queued"],
    ["Order completed", "Enabled", "completed"],
  ]) {
    await page.getByRole("button", { name: stage }).click();
    await expect(replay.getByRole("heading", { name: stage })).toBeVisible();
    await expect(replay.getByText(state, { exact: true })).toBeVisible();
    await expect(replay.getByText(order, { exact: true })).toBeVisible();
  }
  await expect(replay.locator("dd")).toHaveText([
    "Enabled",
    "completed",
    "1",
    "1",
  ]);
  await page.getByText("Inspect MCP and database checks").click();
  await expect(page.getByText("already_applied, applied")).toBeVisible();

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});

test("public viewer supports keyboard navigation and accessibility", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to evidence" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#evidence-main")).toBeFocused();
  await page.getByRole("button", { name: "Order completed" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#replay-state")).toContainText("Order completed");
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(result.violations).toEqual([]);
});

test("the export includes the complete downloadable evidence", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const links = await page
    .locator("a[download]")
    .evaluateAll((elements) =>
      elements.map((element) => element.getAttribute("href")!),
    );
  expect(links).toHaveLength(5);
  const responses = await Promise.all(links.map((link) => request.get(link)));
  expect(responses.every((response) => response.ok())).toBe(true);
  const [v1, scorecard, v2, approval, v3] = await Promise.all(
    responses.map((response) => response.text()),
  );
  expect(JSON.parse(v1)).toHaveLength(4);
  expect(JSON.parse(scorecard).arms.recovery.all.strict_pass).toBe(23);
  expect(v2.trim().split("\n")).toHaveLength(48);
  expect(JSON.parse(approval).states.after_two_ticks.completion_events).toBe(1);
  expect(v3.trim().split("\n")).toHaveLength(6);
});
