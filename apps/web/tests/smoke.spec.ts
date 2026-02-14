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

        if (method === "POST" && path === "/competitors/recommend") {
            await json(200, {
                niche: "Mock Competitor Channel",
                page: 1,
                limit: 8,
                total_count: 1,
                has_more: false,
                recommendations: [
                    {
                        channel_id: "UC_SUGGESTED_1",
                        title: "Suggested Channel One",
                        custom_url: "@suggestedone",
                        subscriber_count: 456789,
                        video_count: 320,
                        view_count: 25400000,
                        avg_views_per_video: 79375,
                        thumbnail_url: "https://example.com/suggested1.jpg",
                        already_tracked: false,
                    },
                ],
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
                    hook_intelligence: {
                        summary: "Top competitors consistently use question hooks and how-to framing.",
                        format_definition: "short_form <= 60s, long_form > 60s",
                        common_patterns: [
                            {
                                pattern: "Question Hook",
                                frequency: 6,
                                competitor_count: 3,
                                avg_views: 182000,
                                examples: ["Why your shorts stop getting views", "What kills retention in long-form?"],
                                template: "Why [specific pain point] is holding back your [desired outcome]",
                            },
                        ],
                        recommended_hooks: [
                            "Why [specific pain point] is holding back your [desired outcome]",
                            "How to [achieve outcome] without [common frustration]",
                        ],
                        competitor_examples: [
                            {
                                competitor: "Mock Competitor Channel",
                                hooks: ["Why your shorts stop getting views"],
                            },
                        ],
                        format_breakdown: {
                            short_form: {
                                format: "short_form",
                                label: "Short-form (<= 60s)",
                                video_count: 7,
                                summary: "Short-form winner pattern: Question Hook.",
                                common_patterns: [
                                    {
                                        pattern: "Question Hook",
                                        frequency: 4,
                                        competitor_count: 3,
                                        avg_views: 221000,
                                        examples: ["Why your shorts stop getting views"],
                                        template: "Why [specific pain point] is holding back your [desired outcome]",
                                    },
                                ],
                                recommended_hooks: ["Why [specific pain point] is holding back your [desired outcome]"],
                                competitor_examples: [
                                    {
                                        competitor: "Mock Competitor Channel",
                                        hooks: ["Why your shorts stop getting views"],
                                    },
                                ],
                            },
                            long_form: {
                                format: "long_form",
                                label: "Long-form (> 60s)",
                                video_count: 5,
                                summary: "Long-form winner pattern: How-To Hook.",
                                common_patterns: [
                                    {
                                        pattern: "How-To Hook",
                                        frequency: 3,
                                        competitor_count: 2,
                                        avg_views: 140000,
                                        examples: ["How to keep retention high in 10-minute videos"],
                                        template: "How to [achieve outcome] without [common frustration]",
                                    },
                                ],
                                recommended_hooks: ["How to [achieve outcome] without [common frustration]"],
                                competitor_examples: [
                                    {
                                        competitor: "Mock Competitor Channel",
                                        hooks: ["How to keep retention high in 10-minute videos"],
                                    },
                                ],
                            },
                        },
                    },
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
    await expect(page.getByRole("heading", { name: "Competitor Hook Intelligence" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Format-Aware Hook Rankings" })).toBeVisible();
    await expect(page.getByText("Short-form (<= 60s)")).toBeVisible();
    await expect(page.getByText("Long-form (> 60s)")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ready-to-Use Hook Templates" })).toBeVisible();
    await expect(page.getByText("Why [specific pain point] is holding back your [desired outcome]").first()).toBeVisible();
});
