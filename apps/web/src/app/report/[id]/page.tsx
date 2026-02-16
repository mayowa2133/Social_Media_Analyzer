"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getConsolidatedReport, ConsolidatedReport } from "@/lib/api";
import { ReportScorecard } from "@/components/ReportScorecard";
import { BlueprintDisplay } from "@/components/blueprint-display";

export default function ReportPage({ params }: { params: { id: string } }) {
    const [report, setReport] = useState<ConsolidatedReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const id = params.id === "latest" ? undefined : params.id;
        getConsolidatedReport(id)
            .then(setReport)
            .catch(err => setError(err.message))
            .finally(() => setLoading(false));
    }, [params.id]);

    if (loading) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#e8e8e8]">
                <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#555] border-t-transparent"></div>
            </div>
        );
    }

    if (error || !report) {
        return (
            <div className="flex min-h-screen flex-col items-center justify-center bg-[#e8e8e8] p-8">
                <h1 className="mb-4 text-2xl font-bold text-[#1f1f1f]">Failed to load report</h1>
                <p className="mb-8 text-[#666]">{error || "No report found."}</p>
                <Link href="/dashboard" className="rounded-xl border border-[#d7d7d7] bg-white px-6 py-3 text-[#242424]">Back to Dashboard</Link>
            </div>
        );
    }

    const prediction = report.performance_prediction;
    const hasCorePrediction = !!(
        prediction &&
        prediction.competitor_metrics &&
        prediction.platform_metrics &&
        prediction.combined_metrics
    );

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <header className="no-print flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                    <Link href="/" className="text-lg font-bold text-[#1f1f1f]">SPC Studio</Link>
                    <nav className="flex gap-5 text-sm text-[#666]">
                        <Link href="/dashboard" className="hover:text-[#1c1c1c]">Dashboard</Link>
                        <Link href="/competitors" className="hover:text-[#1c1c1c]">Competitors</Link>
                        <Link href="/audit/new" className="hover:text-[#1c1c1c]">Audit Workspace</Link>
                    </nav>
                </header>

                <main className="mx-auto max-w-5xl bg-[#f2f2f2] px-4 py-6 md:px-8">
                    <div className="mb-12">
                        <ReportScorecard
                            score={report.overall_score}
                            auditId={report.audit_id}
                            createdAt={report.created_at}
                        />
                    </div>

                    {hasCorePrediction && prediction && (
                        <section className="mb-16">
                            <h2 className="mb-6 text-2xl font-bold text-[#1f1f1f]">Performance Likelihood Scores</h2>
                            <div className="mb-4 grid gap-4 md:grid-cols-3">
                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                    <p className="mb-2 text-xs uppercase tracking-wide text-[#7a7a7a]">Competitor Metrics</p>
                                    <p className="text-3xl font-bold text-[#514aa2]">
                                        {Math.round(prediction.competitor_metrics.score)}
                                        <span className="text-sm text-[#8a8a8a]">/100</span>
                                    </p>
                                    <p className="mt-2 text-xs text-[#666]">{prediction.competitor_metrics.summary}</p>
                                </div>
                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                    <p className="mb-2 text-xs uppercase tracking-wide text-[#7a7a7a]">Platform Metrics</p>
                                    <p className="text-3xl font-bold text-[#2f5f7a]">
                                        {Math.round(prediction.platform_metrics.score)}
                                        <span className="text-sm text-[#8a8a8a]">/100</span>
                                    </p>
                                    <p className="mt-2 text-xs text-[#666]">{prediction.platform_metrics.summary}</p>
                                </div>
                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                    <p className="mb-2 text-xs uppercase tracking-wide text-[#7a7a7a]">Combined Score</p>
                                    <p className="text-3xl font-bold text-[#2f6b39]">
                                        {Math.round(prediction.combined_metrics.score)}
                                        <span className="text-sm text-[#8a8a8a]">/100</span>
                                    </p>
                                    <p className="mt-2 text-xs text-[#666]">{prediction.combined_metrics.summary}</p>
                                </div>
                            </div>
                            <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <p className="text-xs text-[#696969]">
                                    Format: {prediction.format_type.replace("_", "-")} · Duration: {prediction.duration_seconds}s · Competitor benchmark samples: {prediction.competitor_metrics.benchmark?.sample_size ?? 0}
                                </p>
                            </div>

                            {prediction.platform_metrics.detectors && (
                                <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="mb-3 text-sm font-semibold text-[#222]">Creator Engineering Signals</h3>
                                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-[11px] uppercase tracking-wide text-[#777]">Time to Value</p>
                                            <p className="mt-1 text-lg font-semibold text-[#202020]">{prediction.platform_metrics.detectors.time_to_value.seconds}s</p>
                                            <p className="text-[11px] text-[#666]">{prediction.platform_metrics.detectors.time_to_value.assessment}</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-[11px] uppercase tracking-wide text-[#777]">Open Loops</p>
                                            <p className="mt-1 text-lg font-semibold text-[#202020]">{prediction.platform_metrics.detectors.open_loops.count}</p>
                                            <p className="text-[11px] text-[#666]">Score {Math.round(prediction.platform_metrics.detectors.open_loops.score)}</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-[11px] uppercase tracking-wide text-[#777]">Dead Zones</p>
                                            <p className="mt-1 text-lg font-semibold text-[#202020]">{prediction.platform_metrics.detectors.dead_zones.count}</p>
                                            <p className="text-[11px] text-[#666]">{Math.round(prediction.platform_metrics.detectors.dead_zones.total_seconds)}s total</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-[11px] uppercase tracking-wide text-[#777]">Interrupts / Min</p>
                                            <p className="mt-1 text-lg font-semibold text-[#202020]">{prediction.platform_metrics.detectors.pattern_interrupts.interrupts_per_minute}</p>
                                            <p className="text-[11px] text-[#666]">{prediction.platform_metrics.detectors.pattern_interrupts.assessment}</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-[11px] uppercase tracking-wide text-[#777]">CTA Style</p>
                                            <p className="mt-1 text-sm font-semibold text-[#202020]">
                                                {prediction.platform_metrics.detectors.cta_style.style.replace("_", " ")}
                                            </p>
                                            <p className="text-[11px] text-[#666]">Score {Math.round(prediction.platform_metrics.detectors.cta_style.score)}</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {prediction.platform_metrics.detector_rankings && prediction.platform_metrics.detector_rankings.length > 0 && (
                                <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <div className="mb-3 flex items-center justify-between">
                                        <h3 className="text-sm font-semibold text-[#222]">Ranked Detector Priorities</h3>
                                        <p className="text-[11px] text-[#6f6f6f]">
                                            Weighted detector score: {Math.round(prediction.platform_metrics.signals.detector_weighted_score)}
                                        </p>
                                    </div>
                                    <div className="space-y-2">
                                        {prediction.platform_metrics.detector_rankings.slice(0, 5).map((item) => (
                                            <div key={item.detector_key} className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                                <div className="flex flex-wrap items-center justify-between gap-2">
                                                    <p className="text-xs font-semibold text-[#202020]">
                                                        #{item.rank} {item.label}
                                                    </p>
                                                    <span className="rounded-full border border-[#dddddd] bg-white px-2 py-0.5 text-[10px] uppercase tracking-wide text-[#666]">
                                                        {item.priority}
                                                    </span>
                                                </div>
                                                <p className="mt-1 text-[11px] text-[#666]">
                                                    Score {Math.round(item.score)}/{Math.round(item.target_score)} · Gap {item.gap.toFixed(1)} · Weight {item.weight}
                                                </p>
                                                {!!item.evidence?.length && (
                                                    <p className="mt-1 text-[11px] text-[#666]">{item.evidence[0]}</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {prediction.next_actions && prediction.next_actions.length > 0 && (
                                <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="mb-3 text-sm font-semibold text-[#222]">Before You Post: Top Edits</h3>
                                    <div className="space-y-3">
                                        {prediction.next_actions.slice(0, 3).map((action, idx) => (
                                            <div key={`${action.detector_key}-${idx}`} className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                                <div className="flex flex-wrap items-center justify-between gap-2">
                                                    <p className="text-xs font-semibold text-[#202020]">{action.title}</p>
                                                    <span className="text-[11px] text-[#666]">+{Math.round(action.expected_lift_points)} pts</span>
                                                </div>
                                                <p className="mt-1 text-[11px] text-[#666]">{action.why}</p>
                                                {!!action.execution_steps?.length && (
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

                            {prediction.platform_metrics.metric_coverage && (
                                <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="mb-2 text-sm font-semibold text-[#222]">Metric Coverage</h3>
                                    <p className="text-xs text-[#666]">
                                        Shares: {prediction.platform_metrics.metric_coverage.shares} · Saves: {prediction.platform_metrics.metric_coverage.saves} · Retention Curve: {prediction.platform_metrics.metric_coverage.retention_curve}
                                    </p>
                                    {!!prediction.platform_metrics.true_metric_notes?.length && (
                                        <ul className="mt-2 space-y-1 text-xs text-[#666]">
                                            {prediction.platform_metrics.true_metric_notes.map((note, idx) => (
                                                <li key={idx}>• {note}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}

                            {prediction.repurpose_plan && (
                                <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="mb-3 text-sm font-semibold text-[#222]">Repurpose Plan</h3>
                                    <p className="mb-3 text-xs text-[#666]">{prediction.repurpose_plan.core_thesis}</p>
                                    <div className="grid gap-3 md:grid-cols-3">
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-xs font-semibold text-[#202020]">YouTube Shorts</p>
                                            <p className="mt-1 text-[11px] text-[#666]">Target: {prediction.repurpose_plan.youtube_shorts.target_duration_s}s · Hook by {prediction.repurpose_plan.youtube_shorts.hook_deadline_s}s</p>
                                            <p className="mt-1 text-[11px] text-[#666]">{prediction.repurpose_plan.youtube_shorts.editing_style}</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-xs font-semibold text-[#202020]">Instagram Reels</p>
                                            <p className="mt-1 text-[11px] text-[#666]">Target: {prediction.repurpose_plan.instagram_reels.target_duration_s}s · Hook by {prediction.repurpose_plan.instagram_reels.hook_deadline_s}s</p>
                                            <p className="mt-1 text-[11px] text-[#666]">{prediction.repurpose_plan.instagram_reels.editing_style}</p>
                                        </div>
                                        <div className="rounded-xl border border-[#e4e4e4] bg-[#fafafa] p-3">
                                            <p className="text-xs font-semibold text-[#202020]">TikTok</p>
                                            <p className="mt-1 text-[11px] text-[#666]">Target: {prediction.repurpose_plan.tiktok.target_duration_s}s · Hook by {prediction.repurpose_plan.tiktok.hook_deadline_s}s</p>
                                            <p className="mt-1 text-[11px] text-[#666]">{prediction.repurpose_plan.tiktok.editing_style}</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </section>
                    )}

                    <section className="mb-16">
                        <h2 className="mb-6 text-2xl font-bold text-[#1f1f1f]">Executive Recommendations</h2>
                        <div className="grid gap-4">
                            {(report.recommendations || []).map((rec, i) => (
                                <div key={i} className="flex items-start gap-4 rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#e9e8fb] text-xs font-bold text-[#4e4a9e]">
                                        {i + 1}
                                    </span>
                                    <p className="text-[#3f3f3f]">{rec}</p>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="mb-16">
                        <header className="mb-8 flex items-end justify-between">
                            <div>
                                <h2 className="text-2xl font-bold text-[#1f1f1f]">Strategy Blueprint</h2>
                                <p className="text-sm text-[#6d6d6d]">Competitive advantage & content pillars</p>
                            </div>
                        </header>
                        <BlueprintDisplay blueprint={report.blueprint} />
                    </section>

                    {report.blueprint?.velocity_actions && report.blueprint.velocity_actions.length > 0 && (
                        <section className="mb-16">
                            <h2 className="mb-6 text-2xl font-bold text-[#1f1f1f]">Do This Next (Velocity Actions)</h2>
                            <div className="grid gap-4">
                                {report.blueprint.velocity_actions.slice(0, 3).map((action, idx) => (
                                    <div key={idx} className="rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                        <p className="text-sm font-semibold text-[#202020]">{action.title}</p>
                                        <p className="mt-1 text-xs text-[#666]">{action.why}</p>
                                        <p className="mt-1 text-[11px] text-[#717171]">
                                            Target: {action.target_metric} · Expected effect: {action.expected_effect}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {report.video_analysis && (
                        <section className="mb-16">
                            <h2 className="mb-6 text-2xl font-bold text-[#1f1f1f]">Qualitative Video Audit</h2>
                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-6">
                                <h3 className="mb-2 text-lg font-semibold text-[#4e4a9e]">{report.video_analysis.summary}</h3>
                                <div className="mt-6 grid gap-4 md:grid-cols-2">
                                    {report.video_analysis.sections?.map((sec: any, i: number) => (
                                        <div key={i} className="rounded-lg border border-[#e2e2e2] bg-[#fafafa] p-4">
                                            <div className="mb-2 flex justify-between">
                                                <span className="font-medium text-[#272727]">{sec.name}</span>
                                                <span className="font-bold text-[#4e4a9e]">{sec.score}/10</span>
                                            </div>
                                            <ul className="space-y-1 text-xs text-[#666]">
                                                {sec.feedback?.map((f: string, j: number) => (
                                                    <li key={j}>• {f}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </section>
                    )}
                </main>
            </div>
        </div>
    );
}
