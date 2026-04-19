import { defineConfig } from "@playwright/test";

const frontendPort = 38178;
const backendPort = 38108;
const backendUrl = `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: [
        "cd ../backend",
        "rm -f e2e.sqlite3",
        "DATABASE_URL='sqlite+aiosqlite:///./e2e.sqlite3' PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 38108",
      ].join(" && "),
      url: `${backendUrl}/api/health`,
      timeout: 90_000,
      reuseExistingServer: true,
    },
    {
      command: `VITE_API_BASE=${backendUrl} npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: `http://127.0.0.1:${frontendPort}`,
      timeout: 90_000,
      reuseExistingServer: true,
    },
  ],
});
