import { defineConfig, devices, type ReporterDescription } from "@playwright/test";

const PORT = process.env.PORT || "3100";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || `http://localhost:${PORT}`;
const BROWSER = process.env.PLAYWRIGHT_BROWSER || (process.env.CI ? "chromium" : "chrome");
const IS_CHROME = BROWSER === "chrome";
const CI_REPORTER: ReporterDescription[] = [
    ["github"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
];

export default defineConfig({
    testDir: "./tests",
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: process.env.CI ? CI_REPORTER : "list",
    use: {
        baseURL: BASE_URL,
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        video: "retain-on-failure",
    },
    webServer: {
        command: `npm run dev -- --port ${PORT}`,
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
            NEXT_PUBLIC_API_URL: "http://localhost:8000",
            NEXTAUTH_URL: BASE_URL,
            NEXTAUTH_SECRET: "playwright-smoke-secret",
        },
    },
    projects: [
        {
            name: BROWSER,
            use: {
                ...devices["Desktop Chrome"],
                ...(IS_CHROME ? { channel: "chrome" } : {}),
            },
        },
    ],
});
