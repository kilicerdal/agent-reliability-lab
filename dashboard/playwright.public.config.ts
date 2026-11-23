import { defineConfig } from "@playwright/test";
import common from "./playwright.config";

const baseURL = "http://127.0.0.1:3314";
export default defineConfig({
  ...common,
  testMatch: "showcase.spec.ts",
  testIgnore: [],
  reporter: [
    ["list"],
    ["json", { outputFile: "artifacts/public-browser.json" }],
  ],
  use: { ...common.use, baseURL },
  webServer: {
    command: "python3 -m http.server 3314 --bind 127.0.0.1 --directory out",
    url: baseURL,
    reuseExistingServer: false,
  },
});
