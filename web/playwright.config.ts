import { defineConfig } from "@playwright/test";
import os from "node:os";
import path from "node:path";

// Run through `calflab test --e2e`, which sets CALFLAB_PYTHON and CALFLAB_REPO.
const python = process.env.CALFLAB_PYTHON ?? "python";
const repo = process.env.CALFLAB_REPO ?? path.resolve(process.cwd(), "..");
const port = Number(process.env.CALFLAB_E2E_PORT ?? 8123);
const project = path.join(os.tmpdir(), `calflab-e2e-${Date.now()}`);

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  outputDir: path.join(os.tmpdir(), "calflab-e2e-results"),
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1600, height: 950 },
    launchOptions: { args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  webServer: {
    command: `"${python}" -m calflab.cli.main lab --no-browser --port ${port} --project "${project}"`,
    cwd: repo,
    url: `http://127.0.0.1:${port}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
  },
});
