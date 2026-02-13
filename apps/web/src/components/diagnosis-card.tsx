"use client";

import { AlertTriangle, CheckCircle, TrendingUp, HelpCircle, BarChart3, AlertCircle } from "lucide-react";

interface Evidence {
    type: string;
    message: string;
    value?: number;
    benchmark?: number;
}

interface ActionItem {
    title: string;
    description: string;
    priority: number;
}

interface DiagnosisResult {
    primary_issue: "PACKAGING" | "RETENTION" | "TOPIC_FIT" | "CONSISTENCY" | "UNDEFINED";
    summary: string;
    evidence: Evidence[];
    recommendations: ActionItem[];
    metrics?: Record<string, any>;
}

interface DiagnosisCardProps {
    diagnosis: DiagnosisResult;
    loading?: boolean;
}

const ISSUE_CONFIG = {
    PACKAGING: {
        label: "Packaging Issue",
        tone: "text-[#7a6032] bg-[#fff4e6] border-[#ecd9b9]",
        iconTone: "text-[#7a6032] bg-[#f5e7ce]",
        icon: AlertCircle,
        description: "Your videos are not getting enough initial clicks."
    },
    RETENTION: {
        label: "Retention Issue",
        tone: "text-[#7f3a3a] bg-[#fff0f0] border-[#e5c4c4]",
        iconTone: "text-[#7f3a3a] bg-[#f4dede]",
        icon: TrendingUp,
        description: "Viewers are dropping off before the key payoff."
    },
    TOPIC_FIT: {
        label: "Topic Mismatch",
        tone: "text-[#34526d] bg-[#eef5fc] border-[#cad8e8]",
        iconTone: "text-[#34526d] bg-[#dce8f4]",
        icon: HelpCircle,
        description: "Recent topics are not fully aligned with audience demand."
    },
    CONSISTENCY: {
        label: "Inconsistent Schedule",
        tone: "text-[#6b4f2f] bg-[#fbf3e8] border-[#e3d4bf]",
        iconTone: "text-[#6b4f2f] bg-[#eee1cf]",
        icon: BarChart3,
        description: "Upload cadence is limiting algorithm momentum."
    },
    UNDEFINED: {
        label: "Needs More Data",
        tone: "text-[#555] bg-[#f4f4f4] border-[#dddddd]",
        iconTone: "text-[#555] bg-[#e8e8e8]",
        icon: HelpCircle,
        description: "Upload more data to generate a reliable diagnosis."
    }
};

export function DiagnosisCard({ diagnosis, loading }: DiagnosisCardProps) {
    if (loading) {
        return (
            <div className="h-64 w-full animate-pulse rounded-3xl border border-[#dcdcdc] bg-white p-6">
                <div className="mb-4 h-6 w-1/3 rounded bg-[#ececec]"></div>
                <div className="mb-2 h-4 w-full rounded bg-[#f0f0f0]"></div>
                <div className="h-4 w-2/3 rounded bg-[#f0f0f0]"></div>
            </div>
        );
    }

    const config = ISSUE_CONFIG[diagnosis.primary_issue] || ISSUE_CONFIG.UNDEFINED;
    const Icon = config.icon;
    const winner = diagnosis.metrics?.winner_analysis;
    const formats = diagnosis.metrics?.format_breakdown;
    const signals = diagnosis.metrics?.social_signal_summary;
    const scorecards = diagnosis.metrics?.video_scorecards || [];

    const lift = (winnerValue?: number, baselineValue?: number) => {
        if (!winnerValue || !baselineValue || baselineValue <= 0) {
            return "n/a";
        }
        return `${(((winnerValue - baselineValue) / baselineValue) * 100).toFixed(0)}%`;
    };

    const pct = (value?: number) => {
        if (typeof value !== "number") {
            return "0%";
        }
        return `${(value * 100).toFixed(0)}%`;
    };

    const fixed = (value?: number, digits = 2) => {
        if (typeof value !== "number") {
            return "0";
        }
        return value.toFixed(digits);
    };

    return (
        <div className="overflow-hidden rounded-3xl border border-[#dcdcdc] bg-white shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
            <div className={`border-b px-6 py-5 ${config.tone}`}>
                <div className="mb-2 flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <div className={`rounded-lg p-2 ${config.iconTone}`}>
                            <Icon size={22} />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold">{config.label}</h3>
                            <p className="text-sm opacity-80">{config.description}</p>
                        </div>
                    </div>
                    <span className="rounded-full border border-current px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide opacity-70">
                        AI Diagnosis
                    </span>
                </div>
                <p className="text-sm font-medium leading-relaxed text-[#242424]">{diagnosis.summary}</p>
            </div>

            <div className="grid gap-8 p-6 md:grid-cols-2">
                <div>
                    <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">Key Evidence</h4>
                    <ul className="space-y-3">
                        {diagnosis.evidence.map((item, i) => (
                            <li key={i} className="flex gap-3 text-sm text-[#4f4f4f]">
                                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[#8a8a8a]" />
                                <span>
                                    {item.message}
                                    {item.value && item.benchmark && (
                                        <span className="mt-1 block text-xs text-[#8a8a8a]">
                                            (Value: {item.value.toFixed(1)} vs Target: {item.benchmark.toFixed(1)})
                                        </span>
                                    )}
                                </span>
                            </li>
                        ))}
                        {diagnosis.evidence.length === 0 && (
                            <li className="text-sm italic text-[#8a8a8a]">No specific anomalies detected.</li>
                        )}
                    </ul>
                </div>

                <div>
                    <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">Recommended Actions</h4>
                    <div className="space-y-3">
                        {diagnosis.recommendations.map((action, i) => (
                            <div key={i} className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                <div className="mb-1 flex items-center gap-2">
                                    <CheckCircle size={14} className="text-[#3e7a46]" />
                                    <span className="text-sm font-semibold text-[#272727]">{action.title}</span>
                                </div>
                                <p className="pl-6 text-xs leading-relaxed text-[#666]">{action.description}</p>
                            </div>
                        ))}
                        {diagnosis.recommendations.length === 0 && (
                            <p className="text-sm italic text-[#8a8a8a]">No actions available yet.</p>
                        )}
                    </div>
                </div>
            </div>

            {(winner || formats) && (
                <div className="grid gap-8 border-t border-[#e2e2e2] p-6 md:grid-cols-2">
                    {winner && (
                        <div>
                            <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">Why Winners Win</h4>
                            <div className="mb-4 grid grid-cols-3 gap-2">
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7d7d7d]">Views Lift</p>
                                    <p className="text-sm font-semibold text-[#272727]">{lift(winner.winner_avg_views, winner.baseline_avg_views)}</p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7d7d7d]">Engagement Lift</p>
                                    <p className="text-sm font-semibold text-[#272727]">
                                        {lift(winner.winner_avg_engagement_rate, winner.baseline_avg_engagement_rate)}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7d7d7d]">Retention Proxy Lift</p>
                                    <p className="text-sm font-semibold text-[#272727]">
                                        {lift(winner.winner_avg_retention_proxy, winner.baseline_avg_retention_proxy)}
                                    </p>
                                </div>
                            </div>
                            <ul className="space-y-2 text-xs text-[#565656]">
                                <li>Hook-pattern titles in winners: {pct(winner.winner_hook_signal_rate)} vs baseline {pct(winner.baseline_hook_signal_rate)}</li>
                                <li>Story-led titles in winners: {pct(winner.winner_story_signal_rate)} vs baseline {pct(winner.baseline_story_signal_rate)}</li>
                                <li>Thought-provoking questions in winners: {pct(winner.winner_thought_prompt_rate)} vs baseline {pct(winner.baseline_thought_prompt_rate)}</li>
                            </ul>
                        </div>
                    )}

                    {formats && (
                        <div>
                            <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">YouTube Format Split</h4>
                            <div className="space-y-3">
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <div className="mb-1 flex items-center justify-between">
                                        <p className="text-sm font-semibold text-[#262626]">Short-form</p>
                                        <span className="text-xs text-[#777]">{formats.short_form?.count || 0} videos</span>
                                    </div>
                                    <p className="text-xs text-[#636363]">
                                        Avg views: {(formats.short_form?.avg_views || 0).toFixed(0)} • Engagement: {pct(formats.short_form?.avg_engagement_rate)}
                                    </p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <div className="mb-1 flex items-center justify-between">
                                        <p className="text-sm font-semibold text-[#262626]">Long-form</p>
                                        <span className="text-xs text-[#777]">{formats.long_form?.count || 0} videos</span>
                                    </div>
                                    <p className="text-xs text-[#636363]">
                                        Avg views: {(formats.long_form?.avg_views || 0).toFixed(0)} • Engagement: {pct(formats.long_form?.avg_engagement_rate)}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {(signals || scorecards.length > 0) && (
                <div className="space-y-8 border-t border-[#e2e2e2] p-6">
                    {signals && (
                        <div>
                            <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">Social Signal Breakdown</h4>
                            <div className="grid gap-3 md:grid-cols-5">
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7a7a7a]">Likes</p>
                                    <p className="text-sm font-semibold text-[#242424]">{pct(signals.likes?.avg_rate)}</p>
                                    <p className="mt-1 text-[10px] text-[#888]">Initial validation</p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7a7a7a]">Comments</p>
                                    <p className="text-sm font-semibold text-[#242424]">{pct(signals.comments?.avg_rate)}</p>
                                    <p className="mt-1 text-[10px] text-[#888]">Deep engagement</p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7a7a7a]">Shares*</p>
                                    <p className="text-sm font-semibold text-[#242424]">{pct(signals.shares?.avg_proxy)}</p>
                                    <p className="mt-1 text-[10px] text-[#888]">Amplification proxy</p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7a7a7a]">Saves*</p>
                                    <p className="text-sm font-semibold text-[#242424]">{pct(signals.saves?.avg_proxy)}</p>
                                    <p className="mt-1 text-[10px] text-[#888]">Long-term value proxy</p>
                                </div>
                                <div className="rounded-lg border border-[#e4e4e4] bg-[#fafafa] p-3">
                                    <p className="text-[10px] uppercase text-[#7a7a7a]">Posts/Week</p>
                                    <p className="text-sm font-semibold text-[#242424]">{fixed(signals.posting_cadence?.posts_per_week, 1)}</p>
                                    <p className="mt-1 text-[10px] capitalize text-[#888]">{signals.posting_cadence?.health || "unknown"} cadence</p>
                                </div>
                            </div>
                            <p className="mt-2 text-[11px] text-[#848484]">
                                * Shares and saves are estimated proxies for public YouTube channels (direct metrics unavailable from this API scope).
                            </p>
                        </div>
                    )}

                    {scorecards.length > 0 && (
                        <div>
                            <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-[#717171]">Video Performance Hypotheses</h4>
                            <div className="space-y-3">
                                {scorecards.slice(0, 6).map((video: any) => (
                                    <div key={video.video_id || video.title} className="rounded-lg border border-[#e3e3e3] bg-[#fafafa] p-4">
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div className="min-w-0">
                                                <p className="truncate text-sm font-semibold text-[#252525]">{video.title}</p>
                                                <p className="mt-1 text-xs text-[#747474]">
                                                    {video.format_type === "short_form" ? "Short-form" : video.format_type === "long_form" ? "Long-form" : "Unknown format"} · {Number(video.duration_seconds || 0)}s · {Number(video.view_count || 0).toLocaleString()} views
                                                </p>
                                            </div>
                                            <span className="rounded-full border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] uppercase tracking-wide text-[#666]">
                                                {String(video.performance_tier || "baseline").replace("_", " ")}
                                            </span>
                                        </div>
                                        <div className="mt-3 grid gap-2 text-xs md:grid-cols-4">
                                            <div className="rounded border border-[#e5e5e5] bg-white px-2 py-1.5 text-[#5f5f5f]">
                                                Engagement: <span className="text-[#242424]">{pct(video.engagement_rate)}</span>
                                            </div>
                                            <div className="rounded border border-[#e5e5e5] bg-white px-2 py-1.5 text-[#5f5f5f]">
                                                Retention*: <span className="text-[#242424]">{pct(video.retention_proxy)}</span>
                                            </div>
                                            <div className="rounded border border-[#e5e5e5] bg-white px-2 py-1.5 text-[#5f5f5f]">
                                                Shares*: <span className="text-[#242424]">{pct(video.amplification_proxy)}</span>
                                            </div>
                                            <div className="rounded border border-[#e5e5e5] bg-white px-2 py-1.5 text-[#5f5f5f]">
                                                Saves*: <span className="text-[#242424]">{pct(video.save_intent_proxy)}</span>
                                            </div>
                                        </div>
                                        <p className="mt-3 text-xs text-[#585858]">{video.hypothesis}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
