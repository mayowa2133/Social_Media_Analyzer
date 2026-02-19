import { expect, Page, test } from "@playwright/test";

const MOCK_AUDIT_ID = "audit-smoke-123";
const MOCK_UPLOAD_AUDIT_ID = "audit-upload-456";
const MOCK_IG_AUDIT_ID = "audit-ig-789";

function buildMockReport(
    auditId: string,
    reportPlatform: "youtube" | "instagram" | "tiktok" = "youtube"
) {
    return {
        audit_id: auditId,
        report_platform: reportPlatform,
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
            platform: reportPlatform,
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
                    historical_metrics: 0.0,
                },
                insufficient_data: true,
                insufficient_data_reasons: [
                    "Historical posted-video sample is below 5 format-matched videos.",
                ],
            },
            historical_metrics: {
                sample_size: 3,
                format_sample_size: 2,
                score: 68,
                confidence: "low",
                insufficient_data: true,
                summary: "Historical baseline has limited samples; confidence is reduced.",
                signals: ["Historical sample size: 3 videos"],
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
            series_intelligence: {
                summary: "Recurring competitor series extracted from repeated title anchors and ranked by velocity.",
                sample_size: 12,
                total_detected_series: 2,
                series: [
                    {
                        series_key: "Ai News Breakdown",
                        series_key_slug: "ai_news_breakdown",
                        video_count: 4,
                        competitor_count: 2,
                        avg_views: 185000,
                        avg_views_per_day: 2400.3,
                        top_titles: ["AI News Breakdown Part 1", "AI News Breakdown Part 2"],
                        channels: ["Mock Competitor Channel"],
                        recommended_angle: "Run this as a repeatable arc with strong proof early.",
                    },
                ],
            },
        },
        best_edited_variant: {
            id: "snapshot-report-1",
            platform: reportPlatform,
            variant_id: "variant-1",
            source_item_id: "research-1",
            script_preview: "I tested this format and lifted retention. Comment your niche for the template.",
            baseline_score: 79,
            rescored_score: 83,
            delta_score: 4,
            created_at: "2026-02-12T12:04:00Z",
            top_detector_improvements: [
                {
                    detector_key: "cta_style",
                    label: "CTA Style",
                    score: 82,
                    target_score: 76,
                    gap: -6,
                },
            ],
        },
        recommendations: [
            "Lead with a clearer value proposition in the first 5 seconds.",
            "Increase pattern interrupts every 20 seconds.",
        ],
        calibration_confidence: {
            platform: reportPlatform,
            sample_size: 6,
            mean_abs_error: 11.2,
            hit_rate: 0.58,
            trend: "flat",
            confidence: "medium",
            insufficient_data: false,
            recommendations: ["Keep ingesting outcomes for tighter confidence."],
        },
        prediction_vs_actual: null,
        outcome_drift: {
            drift_windows: {
                d7: { days: 7, count: 2, mean_delta: -1.2, mean_abs_error: 6.4, bias: "neutral" },
                d30: { days: 30, count: 4, mean_delta: -0.8, mean_abs_error: 8.1, bias: "neutral" },
            },
            next_actions: [
                "Calibration is healthy. Scale the current format and topic mix.",
            ],
            recent_outcomes: [],
        },
    };
}

async function installApiMocks(page: Page) {
    const competitors: Array<any> = [];
    const connectedPlatforms = { youtube: false, instagram: false, tiktok: false };
    const pollCountByAudit: Record<string, number> = {};
    const draftSnapshots: any[] = [];
    const outcomes: Array<any> = [];

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

        if (method === "GET" && path === "/auth/me") {
            await json(200, {
                user_id: "smoke-user",
                email: "smoke@example.com",
                youtube_connected: connectedPlatforms.youtube,
                instagram_connected: connectedPlatforms.instagram,
                tiktok_connected: connectedPlatforms.tiktok,
                connected_platforms: connectedPlatforms,
                profiles: [],
                connector_capabilities: {
                    instagram_oauth_available: false,
                    tiktok_oauth_available: false,
                },
            });
            return;
        }

        if (method === "POST" && path === "/auth/sync/social") {
            const payload = request.postDataJSON() as any;
            const platform = payload.platform as "youtube" | "instagram" | "tiktok";
            if (platform && Object.prototype.hasOwnProperty.call(connectedPlatforms, platform)) {
                connectedPlatforms[platform] = true;
            }
            await json(200, {
                user_id: "smoke-user",
                email: payload.email || "smoke@example.com",
                platform: platform || "instagram",
                connected: true,
                session_token: "smoke-session-token",
                session_expires_at: 1790000000,
                profile: {
                    platform: platform || "instagram",
                    external_id: payload.external_id || payload.handle || "@smokecreator",
                    handle: payload.handle || "@smokecreator",
                    display_name: payload.display_name || "Smoke Creator",
                    subscriber_count: payload.follower_count || "0",
                    profile_picture_url: null,
                },
            });
            return;
        }

        if (method === "GET" && path === "/competitors/") {
            await json(200, competitors);
            return;
        }

        if (method === "POST" && path === "/competitors/") {
            const created = {
                id: "comp-1",
                channel_id: "UC_COMP_1",
                title: "Mock Competitor Channel",
                platform: "youtube",
                custom_url: "@mockcompetitor",
                subscriber_count: 12345,
                video_count: 100,
                thumbnail_url: "https://example.com/thumb.jpg",
                created_at: "2026-02-12T12:00:00Z",
            };
            competitors.push(created);
            await json(200, created);
            return;
        }

        if (method === "POST" && path === "/competitors/manual") {
            const payload = request.postDataJSON() as any;
            const created = {
                id: `comp-${competitors.length + 1}`,
                channel_id: payload.external_id || payload.handle || `creator-${competitors.length + 1}`,
                title: payload.display_name || payload.handle || "Manual Competitor",
                platform: payload.platform || "instagram",
                custom_url: payload.handle || "@manualcompetitor",
                subscriber_count: payload.subscriber_count || 0,
                video_count: null,
                thumbnail_url: payload.thumbnail_url || null,
                created_at: "2026-02-12T12:00:00Z",
            };
            competitors.push(created);
            await json(200, created);
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

        if (method === "POST" && path === "/competitors/series") {
            await json(200, {
                summary: "Recurring competitor series extracted from repeated title anchors and ranked by velocity.",
                sample_size: 12,
                total_detected_series: 1,
                series: [
                    {
                        series_key: "Ai News Breakdown",
                        series_key_slug: "ai_news_breakdown",
                        video_count: 4,
                        competitor_count: 2,
                        avg_views: 185000,
                        avg_views_per_day: 2400.3,
                        top_titles: ["AI News Breakdown Part 1", "AI News Breakdown Part 2"],
                        channels: ["Mock Competitor Channel"],
                        recommended_angle: "Run this as a repeatable arc with strong proof early.",
                    },
                ],
            });
            return;
        }

        if (method === "POST" && path === "/competitors/discover") {
            await json(200, {
                platform: "instagram",
                query: "ai news",
                page: 1,
                limit: 20,
                total_count: 2,
                has_more: false,
                candidates: [
                    {
                        external_id: "ig-creator-1",
                        handle: "@ainewslab",
                        display_name: "AI News Lab",
                        subscriber_count: 12000,
                        video_count: 16,
                        view_count: 820000,
                        avg_views_per_video: 51250,
                        thumbnail_url: "https://example.com/ig1.jpg",
                        source: "research_corpus",
                        quality_score: 38.4,
                        already_tracked: false,
                    },
                    {
                        external_id: "ig-creator-2",
                        handle: "@growthradar",
                        display_name: "Growth Radar",
                        subscriber_count: 9800,
                        video_count: 11,
                        view_count: 430000,
                        avg_views_per_video: 39090,
                        thumbnail_url: "https://example.com/ig2.jpg",
                        source: "research_corpus",
                        quality_score: 34.2,
                        already_tracked: false,
                    },
                ],
            });
            return;
        }

        if (method === "POST" && path === "/competitors/blueprint") {
            await json(200, {
                ...buildMockReport("blueprint-seed", "instagram").blueprint,
                dataset_summary: {
                    platform: "instagram",
                    research_items_scanned: 18,
                    mapped_competitor_items: 11,
                    mapped_user_items: 4,
                    data_quality_tier: "medium",
                },
            });
            return;
        }

        if (method === "GET" && path === "/billing/credits") {
            await json(200, {
                balance: 8,
                period_key: "2026-02",
                free_monthly_credits: 10,
                costs: {
                    research_search: 1,
                    optimizer_variants: 2,
                    audit_run: 3,
                },
                recent_entries: [],
            });
            return;
        }

        if (method === "POST" && path === "/outcomes/ingest") {
            const payload = request.postDataJSON() as any;
            const predicted = Number(payload.predicted_score || 0);
            const views = Number(payload.actual_metrics?.views || 0);
            const likes = Number(payload.actual_metrics?.likes || 0);
            const comments = Number(payload.actual_metrics?.comments || 0);
            const shares = Number(payload.actual_metrics?.shares || 0);
            const saves = Number(payload.actual_metrics?.saves || 0);
            const actualScore = Math.round(Math.min(100, Math.max(0, (views / 2000) + (likes / 100) + (comments / 30) + (shares / 20) + (saves / 15))));
            const delta = Number((actualScore - predicted).toFixed(2));
            const row = {
                outcome_id: `outcome-${outcomes.length + 1}`,
                platform: payload.platform || "youtube",
                draft_snapshot_id: payload.draft_snapshot_id || null,
                report_id: payload.report_id || null,
                content_item_id: payload.content_item_id || null,
                posted_at: payload.posted_at || "2026-02-12T12:00:00Z",
                predicted_score: predicted,
                actual_score: actualScore,
                calibration_delta: delta,
            };
            outcomes.unshift(row);
            await json(200, {
                outcome_id: row.outcome_id,
                calibration_delta: row.calibration_delta,
                actual_score: row.actual_score,
                predicted_score: row.predicted_score,
                confidence_update: {
                    platform: row.platform,
                    sample_size: outcomes.length,
                    avg_error: 9.2,
                    hit_rate: 0.62,
                    trend: "flat",
                    confidence: "medium",
                    insufficient_data: outcomes.length < 5,
                    recommendations: ["Keep ingesting outcomes for tighter confidence."],
                },
            });
            return;
        }

        if (method === "GET" && path === "/outcomes/summary") {
            const platform = (url.searchParams.get("platform") || "youtube") as "youtube" | "instagram" | "tiktok";
            const platformRows = outcomes.filter((item) => item.platform === platform);
            await json(200, {
                platform,
                sample_size: platformRows.length,
                avg_error: 9.2,
                hit_rate: 0.62,
                trend: "flat",
                confidence: platformRows.length >= 1 ? "medium" : "low",
                insufficient_data: platformRows.length < 5,
                recommendations: ["Keep ingesting outcomes for tighter confidence."],
                drift_windows: {
                    d7: {
                        days: 7,
                        count: platformRows.length,
                        mean_delta: platformRows.length ? platformRows[0].calibration_delta : 0,
                        mean_abs_error: platformRows.length ? Math.abs(platformRows[0].calibration_delta) : 0,
                        bias: "neutral",
                    },
                    d30: {
                        days: 30,
                        count: platformRows.length,
                        mean_delta: platformRows.length ? platformRows[0].calibration_delta : 0,
                        mean_abs_error: platformRows.length ? Math.abs(platformRows[0].calibration_delta) : 0,
                        bias: "neutral",
                    },
                },
                recent_outcomes: platformRows.slice(0, 12),
                next_actions: ["Calibration is healthy. Scale the current format and topic mix."],
            });
            return;
        }

        if (method === "POST" && path === "/research/search") {
            await json(200, {
                page: 1,
                limit: 12,
                total_count: 1,
                has_more: false,
                items: [
                    {
                        item_id: "research-1",
                        platform: "youtube",
                        source_type: "manual_url",
                        url: "https://www.youtube.com/watch?v=abc123",
                        external_id: "abc123",
                        creator_handle: "@mockcreator",
                        creator_display_name: "Mock Creator",
                        title: "AI News Hook Breakdown",
                        caption: "How to hook in first 3 seconds",
                        metrics: {
                            views: 120000,
                            likes: 7400,
                            comments: 320,
                            shares: 210,
                            saves: 180,
                        },
                        media_meta: {},
                        collection_id: "collection-default",
                    },
                ],
                credits: {
                    charged: 1,
                    balance_after: 8,
                },
            });
            return;
        }

        if (method === "POST" && path === "/research/import_url") {
            await json(200, {
                item_id: "research-import-1",
                platform: "instagram",
                source_type: "manual_url",
                url: "https://www.instagram.com/reel/C1234567890/",
                external_id: "ig-import-1",
                creator_handle: "@ainewslab",
                creator_display_name: "AI News Lab",
                title: "AI News Hook Breakdown",
                caption: "How to structure AI News hooks",
                metrics: { views: 84000, likes: 4200, comments: 190, shares: 120, saves: 88 },
                media_meta: {},
                collection_id: "collection-default",
            });
            return;
        }

        if (method === "POST" && path === "/research/capture") {
            await json(200, {
                item_id: "research-capture-1",
                platform: "instagram",
                source_type: "capture",
                url: "https://www.instagram.com/reel/C2222222/",
                external_id: "ig-capture-1",
                creator_handle: "@growthradar",
                creator_display_name: "Growth Radar",
                title: "AI News pacing teardown",
                caption: "Captured reel entry",
                metrics: { views: 56000, likes: 2800, comments: 150, shares: 90, saves: 70 },
                media_meta: {},
                collection_id: "collection-default",
            });
            return;
        }

        if (method === "GET" && path === "/research/collections") {
            await json(200, {
                collections: [
                    {
                        id: "collection-default",
                        name: "Default Collection",
                        platform: "mixed",
                        description: "Default collection",
                        is_system: true,
                        created_at: "2026-02-12T12:00:00Z",
                    },
                ],
            });
            return;
        }

        if (method === "GET" && path === "/optimizer/draft_snapshot") {
            await json(200, {
                items: draftSnapshots,
                count: draftSnapshots.length,
            });
            return;
        }

        if (method === "GET" && path.startsWith("/optimizer/draft_snapshot/")) {
            const snapshotId = path.split("/").pop() || "";
            const snapshot = draftSnapshots.find((item) => item.id === snapshotId);
            if (!snapshot) {
                await json(404, { detail: "Draft snapshot not found" });
                return;
            }
            await json(200, snapshot);
            return;
        }

        if (method === "POST" && path === "/optimizer/variant_generate") {
            await json(200, {
                batch_id: "batch-1",
                generated_at: "2026-02-12T12:00:00Z",
                generation: {
                    mode: "ai_first_fallback",
                    provider: "openai",
                    model: "gpt-4o",
                    used_fallback: false,
                    fallback_reason: null,
                },
                credits: {
                    charged: 2,
                    balance_after: 6,
                },
                variants: [
                    {
                        id: "variant-1",
                        style_key: "variant_a",
                        label: "Outcome + Proof",
                        rationale: "Best for direct authority and fast proof.",
                        script: "I tested this format and lifted retention.\\nComment your niche for the template.",
                        script_text: "I tested this format and lifted retention.\\nComment your niche for the template.",
                        structure: {
                            hook: "I tested this format and lifted retention.",
                            setup: "Here is how this works in 40 seconds.",
                            value: "Use a concrete proof point before the first tip.",
                            cta: "Comment your niche for the template.",
                        },
                        rank: 1,
                        expected_lift_points: 3.2,
                        score_breakdown: {
                            platform_metrics: 81,
                            competitor_metrics: 77,
                            historical_metrics: 69,
                            combined: 79,
                            detector_weighted_score: 76,
                            confidence: "medium",
                        },
                        detector_rankings: [],
                        next_actions: [],
                    },
                    {
                        id: "variant-2",
                        style_key: "variant_b",
                        label: "Curiosity Gap",
                        rationale: "Best for curiosity-driven retention and completion.",
                        script: "Most creators miss this hook signal.\\nStay to the end for the exact fix.",
                        script_text: "Most creators miss this hook signal.\\nStay to the end for the exact fix.",
                        structure: {
                            hook: "Most creators miss this hook signal.",
                            setup: "Stay to the end for the exact fix.",
                            value: "Reveal the mistake and immediately show the fix.",
                            cta: "Save this to use before your next post.",
                        },
                        rank: 2,
                        expected_lift_points: 1.4,
                        score_breakdown: {
                            platform_metrics: 76,
                            competitor_metrics: 75,
                            historical_metrics: 69,
                            combined: 76,
                            detector_weighted_score: 72,
                            confidence: "medium",
                        },
                        detector_rankings: [],
                        next_actions: [],
                    },
                    {
                        id: "variant-3",
                        style_key: "variant_c",
                        label: "Contrarian Take",
                        rationale: "Best for differentiated positioning and share triggers.",
                        script: "Stop copying viral edits blindly.\\nUse one strong payoff first.",
                        script_text: "Stop copying viral edits blindly.\\nUse one strong payoff first.",
                        structure: {
                            hook: "Stop copying viral edits blindly.",
                            setup: "Use one strong payoff first.",
                            value: "Claim -> proof -> 2 steps beats over-edited intros.",
                            cta: "Follow for part two and comment your niche.",
                        },
                        rank: 3,
                        expected_lift_points: 0,
                        score_breakdown: {
                            platform_metrics: 71,
                            competitor_metrics: 72,
                            historical_metrics: 69,
                            combined: 73,
                            detector_weighted_score: 70,
                            confidence: "low",
                        },
                        detector_rankings: [],
                        next_actions: [],
                    },
                ],
            });
            return;
        }

        if (method === "POST" && path === "/optimizer/rescore") {
            await json(200, {
                score_breakdown: {
                    platform_metrics: 84,
                    competitor_metrics: 78,
                    historical_metrics: 70,
                    combined: 81,
                    confidence: "medium",
                    weights: {
                        competitor_metrics: 0.55,
                        platform_metrics: 0.45,
                        historical_metrics: 0.0,
                    },
                    delta_from_baseline: 2,
                },
                detector_rankings: [],
                next_actions: [
                    {
                        title: "Improve CTA Style",
                        detector_key: "cta_style",
                        priority: "high",
                        why: "Detected CTA style: none.",
                        expected_lift_points: 4.8,
                        execution_steps: ["Add one concrete comment CTA in final 3 seconds."],
                        evidence: ["Detected CTA style: none."],
                    },
                ],
                line_level_edits: [
                    {
                        detector_key: "cta_style",
                        detector_label: "CTA Style",
                        priority: "high",
                        line_number: 2,
                        original_line: "Comment your niche for the template.",
                        suggested_line: "Comment \"PLAN\" and I will post the full template.",
                        reason: "Detected CTA style: none.",
                    },
                ],
                improvement_diff: {
                    combined: {
                        before: 79,
                        after: 81,
                        delta: 2,
                    },
                    detectors: [
                        {
                            detector_key: "cta_style",
                            before_score: 20,
                            after_score: 68,
                            delta: 48,
                        },
                    ],
                },
                signals: {
                    detector_weighted_score: 78,
                },
                format_type: "short_form",
                duration_seconds: 45,
            });
            return;
        }

        if (method === "POST" && path === "/optimizer/draft_snapshot") {
            const payload = request.postDataJSON() as any;
            const snapshot = {
                id: `snapshot-${draftSnapshots.length + 1}`,
                user_id: payload.user_id || "smoke-user",
                platform: payload.platform || "youtube",
                source_item_id: payload.source_item_id || null,
                variant_id: payload.variant_id || null,
                script_text: payload.script_text || "",
                baseline_score: payload.baseline_score ?? null,
                rescored_score: payload.rescored_score ?? payload.score_breakdown?.combined ?? 81,
                delta_score: payload.delta_score ?? payload.score_breakdown?.delta_from_baseline ?? null,
                detector_rankings: payload.detector_rankings || payload.rescore_output?.detector_rankings || [],
                next_actions: payload.next_actions || payload.rescore_output?.next_actions || [],
                line_level_edits: payload.line_level_edits || payload.rescore_output?.line_level_edits || [],
                created_at: "2026-02-12T12:06:00Z",
            };
            draftSnapshots.unshift(snapshot);
            await json(200, snapshot);
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
            let requestedPlatform: "youtube" | "instagram" | "tiktok" = "youtube";
            try {
                const payload = request.postDataJSON() as { source_mode?: string; platform?: "youtube" | "instagram" | "tiktok" };
                sourceMode = payload?.source_mode || "url";
                requestedPlatform = payload?.platform || "youtube";
            } catch {
                sourceMode = "url";
                requestedPlatform = "youtube";
            }
            await json(200, {
                audit_id: requestedPlatform === "instagram"
                    ? MOCK_IG_AUDIT_ID
                    : (sourceMode === "upload" ? MOCK_UPLOAD_AUDIT_ID : MOCK_AUDIT_ID),
                status: "running",
            });
            return;
        }

        if (method === "GET" && (path === `/audit/${MOCK_AUDIT_ID}` || path === `/audit/${MOCK_UPLOAD_AUDIT_ID}` || path === `/audit/${MOCK_IG_AUDIT_ID}`)) {
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

        if (method === "GET" && (path === `/report/${MOCK_AUDIT_ID}` || path === `/report/${MOCK_UPLOAD_AUDIT_ID}` || path === `/report/${MOCK_IG_AUDIT_ID}`)) {
            const auditId = path.split("/").pop() || MOCK_AUDIT_ID;
            const platform = auditId === MOCK_IG_AUDIT_ID ? "instagram" : "youtube";
            await json(200, buildMockReport(auditId, platform));
            return;
        }

        await json(404, {
            detail: `No mock defined for ${method} ${path}`,
        });
    });
}

async function installLocalAuthState(page: Page) {
    await page.addInitScript(() => {
        localStorage.setItem("spc_user_id", "smoke-user");
        localStorage.setItem("spc_backend_session_token", "smoke-session-token");
    });
}

test("connect -> competitors -> audit -> report smoke flow", async ({ page }) => {
    await installApiMocks(page);
    await installLocalAuthState(page);

    await page.goto("/connect");
    await expect(page.getByRole("heading", { name: "Connect Your Channels" })).toBeVisible();

    await page.goto("/competitors");
    await page.getByPlaceholder("Paste YouTube channel URL or @handle...").fill("https://www.youtube.com/@mockcompetitor");
    await page.getByRole("button", { name: /Add/ }).click();
    await expect(page.getByText("Mock Competitor Channel")).toBeVisible();

    await page.goto("/audit/new");
    await page.getByPlaceholder("https://www.youtube.com/watch?v=...").fill("https://www.youtube.com/watch?v=abc123");
    await page.getByRole("button", { name: "Run Audit" }).click();

    await expect(page).toHaveURL(new RegExp(`/report/${MOCK_AUDIT_ID}$`), { timeout: 20_000 });
    await expect(page.getByText(/82\/100/).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Executive Recommendations" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Best Edited Variant" })).toBeVisible();
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
    await installLocalAuthState(page);

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

test("research -> variants -> rescore smoke flow", async ({ page }) => {
    await installApiMocks(page);
    await installLocalAuthState(page);

    await page.goto("/research");
    await expect(page.getByRole("heading", { name: "Research Studio" })).toBeVisible();
    await expect(page.getByText("AI News Hook Breakdown")).toBeVisible();

    await page.getByPlaceholder("Topic").fill("AI News hooks");
    await page.getByRole("button", { name: "Generate 3 Variants" }).click();
    await expect(page.getByText("#1 Outcome + Proof")).toBeVisible();
    await expect(page.getByText("AI Generated").first()).toBeVisible();

    await page.getByText("#1 Outcome + Proof").click();
    await page.getByRole("button", { name: "Re-score Edited Draft" }).click();

    await expect(page.getByText(/Combined: 81/)).toBeVisible();
    await expect(page.getByText(/Improve CTA Style/)).toBeVisible();
    await expect(page.getByText(/Line 2 \(CTA Style\)/)).toBeVisible();

    await page.getByRole("button", { name: "Save Iteration" }).click();
    await expect(page.getByText("Iteration History")).toBeVisible();
    await expect(page.getByText(/Score 81/)).toBeVisible();
});

test("instagram parity -> connect -> discover -> blueprint -> upload audit -> report smoke flow", async ({ page }) => {
    await installApiMocks(page);
    await installLocalAuthState(page);

    await page.goto("/connect");
    await page.getByPlaceholder("Email").fill("ig-user@example.com");
    await page.getByPlaceholder("@handle").fill("@igcreator");
    await page.getByRole("button", { name: "Connect Account" }).click();
    await expect(page.getByText(/Connected instagram/i)).toBeVisible();

    await page.goto("/research");
    await page.getByPlaceholder("Paste post/reel/video URL").fill("https://www.instagram.com/reel/C1234567890/");
    await page.getByRole("button", { name: "Import URL" }).click();
    await expect(page.getByRole("heading", { name: "Research Studio" })).toBeVisible();

    await page.goto("/competitors");
    await page.locator("select").filter({ hasText: "YouTube Analysis" }).first().selectOption("instagram");
    await page.getByPlaceholder("Find instagram creators by niche (optional)").fill("ai news");
    await page.getByRole("button", { name: "Discover Candidates" }).click();
    await expect(page.getByText("AI News Lab")).toBeVisible();
    await page.locator("label", { hasText: "AI News Lab" }).locator('input[type="checkbox"]').check();
    await page.getByRole("button", { name: /Import Selected \(1\)/ }).click();
    await expect(page.getByText("AI News Lab").first()).toBeVisible();

    await page.getByRole("button", { name: /Generate instagram Strategy Blueprint/i }).click();
    await expect(page.getByText("Dataset Quality")).toBeVisible();
    await expect(page.getByText(/tier medium/i)).toBeVisible();

    await page.goto("/audit/new");
    await page.locator("select").first().selectOption("instagram");
    await page.getByRole("button", { name: "Upload" }).click();
    await page.setInputFiles('input[type="file"]', {
        name: "sample.mp4",
        mimeType: "video/mp4",
        buffer: Buffer.from("synthetic-video-content"),
    });
    await page.getByRole("button", { name: "Run Audit" }).click();

    await expect(page).toHaveURL(new RegExp(`/report/${MOCK_IG_AUDIT_ID}$`), { timeout: 20_000 });
    await expect(page.getByText(/Report platform: instagram/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Prediction Confidence" })).toBeVisible();
});

test("report -> mark published -> save outcome updates calibration notice", async ({ page }) => {
    await installApiMocks(page);
    await installLocalAuthState(page);

    await page.goto(`/report/${MOCK_AUDIT_ID}`);
    await expect(page.getByText(/Report platform: youtube/i)).toBeVisible();

    await page.getByRole("button", { name: "Mark as Published" }).click();
    await page.getByPlaceholder("views").fill("25000");
    await page.getByPlaceholder("likes").fill("1300");
    await page.getByPlaceholder("comments").fill("120");
    await page.getByPlaceholder("shares").fill("95");
    await page.getByPlaceholder("saves").fill("88");
    await page.getByRole("button", { name: "Save Post Result" }).click();

    await expect(page.getByText(/Saved\. Calibration delta/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Calibration Drift: Do This Next" })).toBeVisible();
});
