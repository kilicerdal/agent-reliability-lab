import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("real captures expose independent verdicts, citations and tool outputs", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") writes.push(r.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Evidence before confidence." }),
  ).toBeVisible();
  await expect(page.locator(".run-list button")).toHaveCount(4);
  for (const name of [
    "Database slowdown",
    "Worker unavailable",
    "Dependency failure",
    "Healthy control",
  ]) {
    await page.locator(".run-list button").filter({ hasText: name }).click();
    await expect(page.locator(".case-head h2")).toHaveText(name);
    await expect(
      page.getByText("Verified outcome", { exact: true }),
    ).toBeVisible();
    await expect(page.locator(".checks li")).toHaveCount(5);
    const entry = page
      .locator(".timeline details")
      .filter({ hasText: "read_logs" })
      .first();
    await entry.locator("summary").click();
    await expect(entry.locator("pre")).toContainText("evidence_id");
  }
  expect(writes).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("keyboard and accessibility check the recorded viewer", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator(".run-list button")).toHaveCount(4);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to investigation" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#workspace")).toBeFocused();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
});
test("service errors are explicit and retryable", async ({ page }) => {
  await page.route("**/api/lab/runs", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.goto("/");
  await expect(page.locator("aside [role=alert]")).toContainText("unavailable");
  await expect(
    page.getByRole("button", { name: "Refresh captures" }),
  ).toBeEnabled();
});
