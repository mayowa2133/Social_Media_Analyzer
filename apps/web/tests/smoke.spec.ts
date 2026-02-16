import { expect, Page, test } from "@playwright/test";

const MOCK_AUDIT_ID = "audit-smoke-123";
const MOCK_UPLOAD_AUDIT_ID = "audit-upload-456";

function buildMockReport(auditId: string) {
    return {
        audit_id: auditId,
        created_at: "2026-02-12T12:05:00Z",
        overall_score: 82,
        diagnosis: {
            primary_issue: "PACKAGING",
            summary: "Mock diagnosis summary",
            evidence: [],
            recommendations: [],
            metrics: {},
        },
        performance_prediction: {
            format_type: "short_form",
            duration_seconds: 42,
            competitor_metrics: {
                score: 78,
                confidence: "high",
                summary: "Competitor score summary",
                benchmark: {
                    sample_size: 24,
                    competitor_count: 3,
                    avg_views: 145000,
                    avg_like_rate: 0.062,
                    avg_comment_rate: 0.01,
                    avg_engagement_rate: 0.08,
                    difficulty_score: 71,
                    used_format_filter: true,
                },
                signals: ["Target format benchmark: short-form (<= 60s)"],
            },
            platform_metrics: {
                score: 84,
                summary: "Platform score summary",
                signals: {
                    overall_multimodal_score: 80,
                    base_multimodal_score: 78,
                    explicit_detector_score: 74,
                    detector_weighted_score: 76,
                    detector_weight_breakdown: {
                        time_to_value: 0.32,
                        open_loops: 0.16,
                        dead_zones: 0.22,
                        pattern_interrupts: 0.2,
                        cta_style: 0.1,
                    },
                    hook_strength: 79,
                    pacing_strength: 75,
                    timestamp_positive_signals: 2,
                    timestamp_negative_signals: 1,
                },
                detectors: {
                    time_to_value: { seconds: 4.1, target_seconds: 5, score: 82, assessment: "moderate" },
                    open_loops: { count: 1, score: 72, examples: ["coming up"] },
                    dead_zones: { count: 2, total_seconds: 8, score: 65, zones: [{ start: 10, end: 14, duration: 4 }] },
                    pattern_interrupts: { interrupts_per_minute: 2.4, score: 66, assessment: "low" },
                    cta_style: { style: "none", score: 20, window: "last_25_percent" },
                },
                detector_rankings: [
                    {
                        detector_key: "cta_style",
                        label: "CTA Style",
                        score: 20,
                        target_score: 76,
                        gap: 56,
                        weight: 0.1,
                        priority: "high",
                        rank: 1,
                        estimated_lift_points: 4.8,
                        evidence: ["Detected CTA style: none."],
                        edits: ["Pick one CTA objective only."],
                    },
                ],
                metric_coverage: {
                    likes: "available",
                    comments: "available",
                    shares: "proxy",
                    saves: "proxy",
                    retention_curve: "proxy",
                },
                true_metric_notes: [],
            },
            combined_metrics: {
                score: 82,
                confidence: "high",
                likelihood_band: "high",
                summary: "Combined score summary",
                weights: {
                    competitor_metrics: 0.55,
                    platform_metrics: 0.45,
                },
            },
            next_actions: [
                {
                    title: "Improve CTA Style",
                    detector_key: "cta_style",
                    priority: "high",
                    why: "Detected CTA style: none.",
                    expected_lift_points: 5.1,
                    execution_steps: ["Add one concrete comment CTA in final 3 seconds."],
                    evidence: ["Detected CTA style: none."],
                },
            ],
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
            winner_pattern_signals: {
                summary: "Velocity summary",
                sample_size: 12,
                top_topics_by_velocity: [{ topic: "hooks", count: 4, avg_views_per_day: 1200 }],
                hook_velocity_correlation: 0.41,
                top_videos_by_velocity: [{ channel: "Mock Competitor Channel", title: "Video", views: 120000, views_per_day: 1400, hook_pattern: "Question Hook" }],
            },
            framework_playbook: {
                summary: "Framework summary",
                stage_adoption: { authority_hook: 0.8, fast_proof: 0.7, framework_steps: 0.6, open_loop: 0.4 },
                cta_distribution: { comment_prompt: 8 },
                dominant_sequence: ["authority_hook", "fast_proof", "framework_steps", "cta"],
                execution_notes: ["Lead with authority."],
            },
            repurpose_plan: {
                summary: "Repurpose summary",
                core_angle: "Core angle",
                youtube_shorts: { duration_target_s: 45, hook_template: "Question Hook", edit_directives: ["Start with bold claim."] },
                instagram_reels: { duration_target_s: 35, hook_template: "Question Hook", edit_directives: ["Use clean pacing."] },
                tiktok: { duration_target_s: 28, hook_template: "Question Hook", edit_directives: ["Fast first second."] },
            },
            transcript_quality: {
                sample_size: 12,
                by_source: { youtube_transcript_api: 8, description_fallback: 4 },
                transcript_coverage_ratio: 0.67,
                fallback_ratio: 0.33,
                notes: ["Coverage note"],
            },
            velocity_actions: [
                {
                    title: "Double down on hooks topic",
                    why: "Hooks is the highest velocity topic.",
                    evidence: ["top topic hooks"],
                    execution_steps: ["Publish 2-3 hooks videos this week."],
                    target_metric: "views_per_day",
                    expected_effect: "Higher discovery velocity.",
                },
            ],
        },
        recommendations: [
            "Lead with a clearer value proposition in the first 5 seconds.",
            "Increase pattern interrupts every 20 seconds.",
        ],
    };
}

async function installApiMocks(page: Page) {
    let competitorCount = 0;
    const pollCountByAudit: Record<string, number> = {};

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

        if (method === "POST" && path === "/audit/upload") {
            await json(200, {
                upload_id: "upload-smoke-1",
                file_name: "sample.mp4",
                mime_type: "video/mp4",
                file_size_bytes: 2048,
                status: "uploaded",
            });
            return;
        }

        if (method === "POST" && path === "/audit/run_multimodal") {
            let sourceMode = "url";
            try {
                const payload = request.postDataJSON() as { source_mode?: string };
                sourceMode = payload?.source_mode || "url";
            } catch {
                sourceMode = "url";
            }
            await json(200, {
                audit_id: sourceMode === "upload" ? MOCK_UPLOAD_AUDIT_ID : MOCK_AUDIT_ID,
                status: "running",
            });
            return;
        }

        if (method === "GET" && (path === `/audit/${MOCK_AUDIT_ID}` || path === `/audit/${MOCK_UPLOAD_AUDIT_ID}`)) {
            const auditId = path.split("/").pop() || MOCK_AUDIT_ID;
            pollCountByAudit[auditId] = (pollCountByAudit[auditId] || 0) + 1;
            const completed = pollCountByAudit[auditId] >= 1;
            await json(200, {
                audit_id: auditId,
                status: completed ? "completed" : "processing",
                progress: completed ? "100" : "50",
            });
            return;
        }

        if (method === "GET" && (path === `/report/${MOCK_AUDIT_ID}` || path === `/report/${MOCK_UPLOAD_AUDIT_ID}`)) {
            const auditId = path.split("/").pop() || MOCK_AUDIT_ID;
            await json(200, buildMockReport(auditId));
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
    await expect(page.getByText(/82\/100/).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Executive Recommendations" })).toBeVisible();
    await expect(page.getByText("Lead with a clearer value proposition in the first 5 seconds.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Competitor Hook Intelligence" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Format-Aware Hook Rankings" })).toBeVisible();
    await expect(page.getByText("Short-form (<= 60s)")).toBeVisible();
    await expect(page.getByText("Long-form (> 60s)")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ready-to-Use Hook Templates" })).toBeVisible();
    await expect(page.getByText("Why [specific pain point] is holding back your [desired outcome]").first()).toBeVisible();
});

test("upload -> score -> recommendations render smoke flow", async ({ page }) => {
    await installApiMocks(page);

    await page.goto("/audit/new");
    await page.getByRole("button", { name: "Upload" }).click();
    await page.setInputFiles('input[type="file"]', {
        name: "sample.mp4",
        mimeType: "video/mp4",
        buffer: Buffer.from("synthetic-video-content"),
    });
    await page.getByRole("button", { name: "Run Audit" }).click();

    await expect(page).toHaveURL(new RegExp(`/report/${MOCK_UPLOAD_AUDIT_ID}$`), { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Performance Likelihood Scores" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Before You Post: Top Edits" })).toBeVisible();
    await expect(page.getByText("Improve CTA Style")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Do This Next (Velocity Actions)" })).toBeVisible();
});
