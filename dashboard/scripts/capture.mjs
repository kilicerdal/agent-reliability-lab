import { chromium } from "playwright";
const browser = await chromium.launch();
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
      deviceScaleFactor: 1,
      isMobile: width < 500,
      hasTouch: width < 500,
    });
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:3310/");
    await page
      .locator(".run-list button")
      .filter({ hasText: "Worker unavailable" })
      .click();
    await page.locator(".verdict").waitFor();
    await page.evaluate(() => window.scrollTo(0, 0));
    if (width === 1440)
      await page.screenshot({ path: "../docs/assets/overview.png" });
    await page.screenshot({
      path: `../docs/assets/dashboard-${width}.png`,
      fullPage: true,
    });
    await context.close();
  }
} finally {
  await browser.close();
}
