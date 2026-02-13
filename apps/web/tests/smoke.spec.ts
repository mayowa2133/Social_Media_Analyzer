import { expect, Page, test } from "@playwright/test";

const MOCK_AUDIT_ID = "audit-smoke-123";

async function installApiMocks(page: Page) {
    let competitorCount = 0;
    let pollCount = 0;

    await page.route("http://localhost:8000/**", async (route) => {
        const request = route.request();
        const method = request.method();
        const url = new URL(request.url());
        const path = url.pathname;

        const json = async (status: number, body: unknown) => {
            await route.fulfill({
                status,
                contentType: "application/json",
                body: JSON.stringify(body),
            });
        };

        if (method === "GET" && path === "/competitors/") {
            const competitors = competitorCount > 0
                ? [{
                    id: "comp-1",
                    channel_id: "UC_COMP_1",
                    title: "Mock Competitor Channel",
                    custom_url: "@mockcompetitor",
                    subscriber_count: 12345,
                    video_count: 100,
                    thumbnail_url: "https://example.com/thumb.jpg",
                    created_at: "2026-02-12T12:00:00Z",
                }]
                : [];
            await json(200, competitors);
            return;
        }

        if (method === "POST" && path === "/competitors/") {
            competitorCount = 1;
            await json(200, {
                id: "comp-1",
                channel_id: "UC_COMP_1",
                title: "Mock Competitor Channel",
                custom_url: "@mockcompetitor",
                subscriber_count: 12345,
                video_count: 100,
                thumbnail_url: "https://example.com/thumb.jpg",
                created_at: "2026-02-12T12:00:00Z",
            });
            return;
        }

        if (method === "POST" && path === "/audit/run_multimodal") {
            await json(200, {
                audit_id: MOCK_AUDIT_ID,
                status: "running",
            });
            return;
        }

        if (method === "GET" && path === `/audit/${MOCK_AUDIT_ID}`) {
            pollCount += 1;
            const completed = pollCount >= 1;
            await json(200, {
                audit_id: MOCK_AUDIT_ID,
                status: completed ? "completed" : "processing",
                progress: completed ? "100" : "50",
            });
            return;
        }

        if (method === "GET" && path === `/report/${MOCK_AUDIT_ID}`) {
            await json(200, {
                audit_id: MOCK_AUDIT_ID,
                created_at: "2026-02-12T12:05:00Z",
                overall_score: 82,
                diagnosis: {
                    primary_issue: "PACKAGING",
                    summary: "Mock diagnosis summary",
                    evidence: [],
                    recommendations: [],
                    metrics: {},
                },
                video_analysis: {
                    summary: "Strong hook, pacing can improve.",
                    sections: [
                        {
                            name: "Hook",
                            score: 8,
                            feedback: ["Open with a stronger problem statement."],
                        },
                    ],
                },
                blueprint: {
                    gap_analysis: ["Gap 1"],
                    content_pillars: ["Pillar 1"],
                    video_ideas: [{ title: "Idea 1", concept: "Concept 1" }],
                },
                recommendations: [
                    "Lead with a clearer value proposition in the first 5 seconds.",
                    "Increase pattern interrupts every 20 seconds.",
                ],
            });
            return;
        }

        await json(404, {
            detail: `No mock defined for ${method} ${path}`,
        });
    });
}

test("connect -> competitors -> audit -> report smoke flow", async ({ page }) => {
    await installApiMocks(page);

    await page.goto("/connect");
    await expect(page.getByRole("heading", { name: "Connect Your Channels" })).toBeVisible();

    await page.goto("/competitors");
    await page.getByPlaceholder("Paste YouTube channel URL or @handle...").fill("https://www.youtube.com/@mockcompetitor");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByText("Mock Competitor Channel")).toBeVisible();

    await page.goto("/audit/new");
    await page.getByPlaceholder("https://www.youtube.com/watch?v=...").fill("https://www.youtube.com/watch?v=abc123");
    await page.getByRole("button", { name: "Run Audit" }).click();

    await expect(page).toHaveURL(new RegExp(`/report/${MOCK_AUDIT_ID}$`), { timeout: 20_000 });
    await expect(page.getByText(/82\/100/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Executive Recommendations" })).toBeVisible();
    await expect(page.getByText("Lead with a clearer value proposition in the first 5 seconds.")).toBeVisible();
});
