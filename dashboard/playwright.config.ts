import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 30000,
  reporter: [["list"], ["json", { outputFile: "artifacts/browser.json" }]],
  use: {
    baseURL: "http://127.0.0.1:3310",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], browserName: "chromium" },
    },
  ],
});
