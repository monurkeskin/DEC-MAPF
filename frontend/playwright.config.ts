import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const ownedData = mkdtempSync(join(tmpdir(), "decmapf-browser-"));
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 45000,
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
  use: {
    baseURL: "http://127.0.0.1:8765",
    browserName: "chromium",
    channel: process.env.CI ? undefined : "chrome",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "../.venv/bin/python -m uvicorn mapf.gui.app:app --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/",
    timeout: 30000,
    reuseExistingServer: false,
    env: { MAPF_WORKSPACE_DIR: ownedData },
  },
});
