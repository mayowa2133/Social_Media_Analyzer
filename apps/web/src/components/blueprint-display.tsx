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

            {blueprint.framework_playbook && (
                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-6">
                    <h3 className="mb-2 flex items-center gap-2 text-xl font-bold text-[#232323]">
                        <span>🧩</span> Framework Playbook
                    </h3>
                    <p className="mb-4 text-sm text-[#666]">{blueprint.framework_playbook.summary}</p>
                    <div className="mb-4 grid gap-2 md:grid-cols-4">
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Authority Hook</p>
                            <p className="text-sm font-semibold text-[#202020]">{Math.round(blueprint.framework_playbook.stage_adoption.authority_hook * 100)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Fast Proof</p>
                            <p className="text-sm font-semibold text-[#202020]">{Math.round(blueprint.framework_playbook.stage_adoption.fast_proof * 100)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Framework Steps</p>
                            <p className="text-sm font-semibold text-[#202020]">{Math.round(blueprint.framework_playbook.stage_adoption.framework_steps * 100)}%</p>
                        </div>
                        <div className="rounded-lg border border-[#e1e1e1] bg-[#fafafa] p-3 text-center">
                            <p className="text-[11px] text-[#777]">Open Loops</p>
                            <p className="text-sm font-semibold text-[#202020]">{Math.round(blueprint.framework_playbook.stage_adoption.open_loop * 100)}%</p>
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
