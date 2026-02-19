"use client";

import { BlueprintResult, HookFormatProfile } from "@/lib/api";

interface BlueprintDisplayProps {
    blueprint: BlueprintResult;
    loading?: boolean;
}

export function BlueprintDisplay({ blueprint, loading }: BlueprintDisplayProps) {
    if (loading) {
        return (
            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-8 animate-pulse">
                <div className="mb-6 h-6 w-1/3 rounded bg-[#ececec]"></div>
                <div className="space-y-4">
                    <div className="h-4 w-full rounded bg-[#f0f0f0]"></div>
                    <div className="h-4 w-5/6 rounded bg-[#f0f0f0]"></div>
                    <div className="h-4 w-4/6 rounded bg-[#f0f0f0]"></div>
                </div>
            </div>
        );
    }

    const stagePercent = (value: number | undefined) => {
        const normalized = Number(value);
        if (!Number.isFinite(normalized)) {
            return 0;
        }
        return Math.round(normalized * 100);
    };
    const datasetSummary = blueprint.dataset_summary;

    const renderFormatHookProfile = (profile: HookFormatProfile) => (
        <div key={profile.format} className="rounded-xl border border-[#dddddd] bg-[#fafafa] p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-[#232323]">{profile.label}</p>
                <span className="text-xs text-[#707070]">{profile.video_count} videos</span>
            </div>
            <p className="mb-3 text-xs text-[#6a6a6a]">{profile.summary}</p>

            {profile.common_patterns.length > 0 ? (
                <div className="mb-3 space-y-2">
                    {profile.common_patterns.slice(0, 3).map((pattern, idx) => (
                        <div key={idx} className="rounded-md border border-[#e2e2e2] bg-white p-2">
                            <div className="mb-1 flex items-center justify-between gap-2">
                                <p className="text-xs text-[#202020]">{pattern.pattern}</p>
                                <span className="text-[10px] text-[#787878]">{pattern.frequency} uses</span>
                            </div>
                            <p className="text-[10px] text-[#4e4a9e]">{pattern.template}</p>
                        </div>
                    ))}
                </div>
            ) : (
                <p className="mb-3 text-[11px] text-[#8a8a8a]">No reliable hook pattern extracted yet for this format.</p>
            )}

            {profile.recommended_hooks.length > 0 && (
                <ul className="space-y-1 text-[11px] text-[#454545]">
                    {profile.recommended_hooks.slice(0, 2).map((hook, idx) => (
                        <li key={idx}>• {hook}</li>
                    ))}
                </ul>
            )}
        </div>
    );

    return (
        <div className="space-y-8">
            {datasetSummary && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                    <h3 className="text-sm font-semibold text-[#222]">Dataset Quality</h3>
                    <p className="mt-1 text-xs text-[#666]">
                        {datasetSummary.platform} · tier {datasetSummary.data_quality_tier} · competitor items {datasetSummary.mapped_competitor_items} · user items {datasetSummary.mapped_user_items}
                        {typeof datasetSummary.research_items_scanned === "number" ? ` · scanned ${datasetSummary.research_items_scanned}` : ""}
                    </p>
                </div>
            )}

            <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                <h3 className="mb-4 flex items-center gap-2 text-xl font-bold text-[#222]">
                    <span>🧠</span> Gap Analysis
                </h3>
                <ul className="space-y-3">
                    {blueprint.gap_analysis.map((gap, i) => (
                        <li key={i} className="flex items-start gap-3 text-[#3e3e3e]">
                            <span className="mt-1 text-[#5b55b6]">•</span>
                            {gap}
                        </li>
                    ))}
                </ul>
            </div>

            <div className="grid gap-5 md:grid-cols-3">
                {blueprint.content_pillars.map((pillar, i) => (
                    <div key={i} className="rounded-2xl border border-[#dcdcdc] bg-white p-6 text-center">
                        <div className="mb-3 text-3xl">📍</div>
                        <h4 className="font-bold text-[#232323]">{pillar}</h4>
                    </div>
                ))}
            </div>

            {blueprint.hook_intelligence && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>🎣</span> Competitor Hook Intelligence
                    </h3>
                    <p className="mb-6 text-sm text-[#666]">{blueprint.hook_intelligence.summary}</p>
                    {blueprint.hook_intelligence.format_definition && (
                        <p className="mb-6 text-[11px] text-[#7f7f7f]">
                            Format split: {blueprint.hook_intelligence.format_definition}
                        </p>
                    )}

                    {blueprint.hook_intelligence.common_patterns.length > 0 && (
                        <div className="mb-6">
                            <h4 className="mb-3 text-sm font-semibold text-[#2d2d2d]">Common Hook Patterns</h4>
                            <div className="space-y-3">
                                {blueprint.hook_intelligence.common_patterns.map((pattern, i) => (
                                    <div key={i} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-4">
                                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                                            <p className="font-medium text-[#222]">{pattern.pattern}</p>
                                            <span className="text-xs text-[#707070]">
                                                {pattern.frequency} uses · {pattern.competitor_count} competitors
                                            </span>
                                        </div>
                                        <p className="mb-2 text-xs text-[#444]">
                                            Template: <span className="text-[#4e4a9e]">{pattern.template}</span>
                                        </p>
                                        {pattern.examples.length > 0 && (
                                            <ul className="space-y-1 text-xs text-[#666]">
                                                {pattern.examples.map((example, idx) => (
                                                    <li key={idx}>• {example}</li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {blueprint.hook_intelligence.recommended_hooks.length > 0 && (
                        <div className="mb-6">
                            <h4 className="mb-3 text-sm font-semibold text-[#2d2d2d]">Ready-to-Use Hook Templates</h4>
                            <div className="grid gap-3 md:grid-cols-2">
                                {blueprint.hook_intelligence.recommended_hooks.map((hook, i) => (
                                    <div key={i} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                                        <p className="text-xs text-[#4e4a9e]">{hook}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {blueprint.hook_intelligence.format_breakdown && (
                        <div className="mb-6">
                            <h4 className="mb-3 text-sm font-semibold text-[#2d2d2d]">Format-Aware Hook Rankings</h4>
                            <div className="grid gap-3 md:grid-cols-2">
                                {renderFormatHookProfile(blueprint.hook_intelligence.format_breakdown.short_form)}
                                {renderFormatHookProfile(blueprint.hook_intelligence.format_breakdown.long_form)}
                            </div>
                        </div>
                    )}

                    {blueprint.hook_intelligence.competitor_examples.length > 0 && (
                        <div>
                            <h4 className="mb-3 text-sm font-semibold text-[#2d2d2d]">Specific Hooks Competitors Use</h4>
                            <div className="space-y-3">
                                {blueprint.hook_intelligence.competitor_examples.map((entry, i) => (
                                    <div key={i} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-4">
                                        <p className="mb-2 text-sm font-medium text-[#202020]">{entry.competitor}</p>
                                        <ul className="space-y-1 text-xs text-[#676767]">
                                            {entry.hooks.map((hook, idx) => (
                                                <li key={idx}>• {hook}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {blueprint.series_intelligence && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>🎬</span> Competitor Series Radar
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">
                        {blueprint.series_intelligence.summary}
                    </p>
                    <p className="mb-4 text-xs text-[#707070]">
                        Sample size: {blueprint.series_intelligence.sample_size} videos · Detected series: {blueprint.series_intelligence.total_detected_series}
                    </p>
                    {blueprint.series_intelligence.series.length > 0 ? (
                        <div className="space-y-3">
                            {blueprint.series_intelligence.series.slice(0, 6).map((series, idx) => (
                                <div key={idx} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-4">
                                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                                        <p className="text-sm font-semibold text-[#202020]">{series.series_key}</p>
                                        <span className="text-[11px] text-[#717171]">
                                            {series.video_count} videos · {series.competitor_count} competitors
                                        </span>
                                    </div>
                                    <p className="text-[11px] text-[#666]">
                                        Avg views: {series.avg_views.toLocaleString()} · Avg views/day: {series.avg_views_per_day.toLocaleString()}
                                    </p>
                                    {series.top_titles.length > 0 && (
                                        <ul className="mt-2 space-y-1 text-[11px] text-[#555]">
                                            {series.top_titles.slice(0, 3).map((title, titleIdx) => (
                                                <li key={titleIdx}>• {title}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-xs text-[#7a7a7a]">
                            No recurring series was detected yet. Add more competitors or expand tracked channels.
                        </p>
                    )}
                </div>
            )}

            {blueprint.winner_pattern_signals && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>📈</span> Winner Pattern Signals
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">{blueprint.winner_pattern_signals.summary}</p>
                    <p className="mb-4 text-xs text-[#707070]">
                        Sample size: {blueprint.winner_pattern_signals.sample_size} videos · Hook/velocity correlation: {blueprint.winner_pattern_signals.hook_velocity_correlation}
                    </p>

                    {blueprint.winner_pattern_signals.top_topics_by_velocity.length > 0 && (
                        <div className="mb-4">
                            <h4 className="mb-2 text-sm font-semibold text-[#2d2d2d]">Top Topics by Views/Day</h4>
                            <div className="grid gap-2 md:grid-cols-2">
                                {blueprint.winner_pattern_signals.top_topics_by_velocity.slice(0, 6).map((topic, idx) => (
                                    <div key={idx} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                                        <p className="text-xs font-semibold text-[#202020]">{topic.topic}</p>
                                        <p className="text-[11px] text-[#666]">{topic.count} videos · {topic.avg_views_per_day.toLocaleString()} views/day</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {blueprint.winner_pattern_signals.top_videos_by_velocity.length > 0 && (
                        <div>
                            <h4 className="mb-2 text-sm font-semibold text-[#2d2d2d]">Top Velocity Videos</h4>
                            <div className="space-y-2">
                                {blueprint.winner_pattern_signals.top_videos_by_velocity.slice(0, 5).map((video, idx) => (
                                    <div key={idx} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                                        <p className="text-xs font-semibold text-[#202020]">{video.title}</p>
                                        <p className="text-[11px] text-[#666]">
                                            {video.channel} · {video.views.toLocaleString()} views · {video.views_per_day.toLocaleString()} views/day · {video.hook_pattern}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {blueprint.transcript_quality && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>📝</span> Transcript Quality
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">
                        Coverage: {Math.round(blueprint.transcript_quality.transcript_coverage_ratio * 100)}% ·
                        Fallback ratio: {Math.round(blueprint.transcript_quality.fallback_ratio * 100)}% ·
                        Sample size: {blueprint.transcript_quality.sample_size}
                    </p>

                    {Object.keys(blueprint.transcript_quality.by_source).length > 0 && (
                        <div className="mb-3 flex flex-wrap gap-2">
                            {Object.entries(blueprint.transcript_quality.by_source).map(([source, count]) => (
                                <span key={source} className="rounded-full border border-[#dfdfdf] bg-[#f6f6f6] px-2 py-1 text-[11px] text-[#555]">
                                    {source.replaceAll("_", " ")}: {count}
                                </span>
                            ))}
                        </div>
                    )}

                    {blueprint.transcript_quality.notes.length > 0 && (
                        <ul className="space-y-1 text-xs text-[#666]">
                            {blueprint.transcript_quality.notes.map((note, idx) => (
                                <li key={idx}>• {note}</li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {blueprint.velocity_actions && blueprint.velocity_actions.length > 0 && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>⚡</span> Do This Next
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">
                        Prioritized actions based on competitor velocity patterns and framework gaps.
                    </p>
                    <div className="space-y-3">
                        {blueprint.velocity_actions.map((action, idx) => (
                            <div key={idx} className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-4">
                                <p className="text-sm font-semibold text-[#202020]">{action.title}</p>
                                <p className="mt-1 text-xs text-[#666]">{action.why}</p>
                                <p className="mt-1 text-[11px] text-[#717171]">
                                    Target metric: {action.target_metric} · Expected effect: {action.expected_effect}
                                </p>
                                {action.execution_steps.length > 0 && (
                                    <ul className="mt-2 space-y-1 text-[11px] text-[#555]">
                                        {action.execution_steps.map((step, stepIdx) => (
                                            <li key={stepIdx}>• {step}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {blueprint.framework_playbook && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>🧩</span> Framework Playbook
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">{blueprint.framework_playbook.summary}</p>
                    <div className="mb-4 grid gap-2 md:grid-cols-4">
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Authority Hook</p>
                            <p className="text-sm font-semibold text-[#202020]">{stagePercent(blueprint.framework_playbook.stage_adoption.authority_hook)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Fast Proof</p>
                            <p className="text-sm font-semibold text-[#202020]">{stagePercent(blueprint.framework_playbook.stage_adoption.fast_proof)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Framework Steps</p>
                            <p className="text-sm font-semibold text-[#202020]">{stagePercent(blueprint.framework_playbook.stage_adoption.framework_steps)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Open Loops</p>
                            <p className="text-sm font-semibold text-[#202020]">{stagePercent(blueprint.framework_playbook.stage_adoption.open_loop)}%</p>
                        </div>
                    </div>

                    {Object.keys(blueprint.framework_playbook.cta_distribution).length > 0 && (
                        <div className="mb-3">
                            <h4 className="mb-2 text-sm font-semibold text-[#2d2d2d]">CTA Distribution</h4>
                            <div className="flex flex-wrap gap-2">
                                {Object.entries(blueprint.framework_playbook.cta_distribution).map(([style, count]) => (
                                    <span key={style} className="rounded-full border border-[#dfdfdf] bg-[#f6f6f6] px-2 py-1 text-[11px] text-[#555]">
                                        {style.replace("_", " ")}: {count}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {blueprint.framework_playbook.execution_notes.length > 0 && (
                        <ul className="space-y-1 text-xs text-[#666]">
                            {blueprint.framework_playbook.execution_notes.map((note, idx) => (
                                <li key={idx}>• {note}</li>
                            ))}
                        </ul>
                    )}
                </div>
            )}

            {blueprint.repurpose_plan && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>🔁</span> Cross-Platform Repurpose Plan
                    </h3>
                    <p className="mb-2 text-sm text-[#666]">{blueprint.repurpose_plan.summary}</p>
                    <p className="mb-4 text-xs text-[#707070]">{blueprint.repurpose_plan.core_angle}</p>
                    <div className="grid gap-3 md:grid-cols-3">
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                            <p className="text-xs font-semibold text-[#202020]">YouTube Shorts ({blueprint.repurpose_plan.youtube_shorts.duration_target_s}s)</p>
                            <p className="mt-1 text-[11px] text-[#666]">Hook: {blueprint.repurpose_plan.youtube_shorts.hook_template}</p>
                            <ul className="mt-1 space-y-1 text-[11px] text-[#666]">
                                {blueprint.repurpose_plan.youtube_shorts.edit_directives.map((item, idx) => (
                                    <li key={idx}>• {item}</li>
                                ))}
                            </ul>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                            <p className="text-xs font-semibold text-[#202020]">Instagram Reels ({blueprint.repurpose_plan.instagram_reels.duration_target_s}s)</p>
                            <p className="mt-1 text-[11px] text-[#666]">Hook: {blueprint.repurpose_plan.instagram_reels.hook_template}</p>
                            <ul className="mt-1 space-y-1 text-[11px] text-[#666]">
                                {blueprint.repurpose_plan.instagram_reels.edit_directives.map((item, idx) => (
                                    <li key={idx}>• {item}</li>
                                ))}
                            </ul>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3">
                            <p className="text-xs font-semibold text-[#202020]">TikTok ({blueprint.repurpose_plan.tiktok.duration_target_s}s)</p>
                            <p className="mt-1 text-[11px] text-[#666]">Hook: {blueprint.repurpose_plan.tiktok.hook_template}</p>
                            <ul className="mt-1 space-y-1 text-[11px] text-[#666]">
                                {blueprint.repurpose_plan.tiktok.edit_directives.map((item, idx) => (
                                    <li key={idx}>• {item}</li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            )}

            <div>
                <h3 className="mb-6 flex items-center gap-2 text-xl font-bold text-[#222]">
                    <span>💡</span> Video Blueprint Ideas
                </h3>
                <div className="grid gap-5 md:grid-cols-3">
                    {blueprint.video_ideas.map((idea, i) => (
                        <div key={i} className="rounded-2xl border border-[#dcdcdc] bg-white p-6 transition-colors hover:bg-[#f8f8f8]">
                            <h4 className="mb-3 font-bold text-[#4e4a9e]">{idea.title}</h4>
                            <p className="text-sm leading-relaxed text-[#606060]">{idea.concept}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
