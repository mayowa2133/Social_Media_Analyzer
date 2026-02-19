"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    ConsolidatedReport,
    getConsolidatedReport,
    getOutcomesSummary,
    ingestOutcomeMetrics,
    recalibrateOutcomes,
} from "@/lib/api";
import { ReportScorecard } from "@/components/ReportScorecard";
import { BlueprintDisplay } from "@/components/blueprint-display";

function postedAtFromWindow(windowKey: "now" | "7d" | "30d"): string {
    const now = new Date();
    if (windowKey === "7d") {
        now.setDate(now.getDate() - 7);
    } else if (windowKey === "30d") {
        now.setDate(now.getDate() - 30);
    }
    return now.toISOString().slice(0, 16);
}

export default function ReportPage({ params }: { params: { id: string } }) {
    const [report, setReport] = useState<ConsolidatedReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [postingOutcome, setPostingOutcome] = useState(false);
    const [outcomeNotice, setOutcomeNotice] = useState<string | null>(null);
    const [outcomeError, setOutcomeError] = useState<string | null>(null);
    const [allowPlatformMismatch, setAllowPlatformMismatch] = useState(false);
    const [publishMarkedAt, setPublishMarkedAt] = useState<string | null>(null);
    const [outcomeWindow, setOutcomeWindow] = useState<"now" | "7d" | "30d">("now");
    const [outcomeSummary, setOutcomeSummary] = useState<{
        confidence?: string;
        trend?: string;
        drift_windows?: {
            d7?: { mean_delta: number; mean_abs_error: number; count: number; bias: string };
            d30?: { mean_delta: number; mean_abs_error: number; count: number; bias: string };
        };
        next_actions?: string[];
    } | null>(null);
    const [recalibrating, setRecalibrating] = useState(false);
    const [outcomeForm, setOutcomeForm] = useState({
        platform: "youtube",
        views: "",
        likes: "",
        comments: "",
        shares: "",
        saves: "",
        avg_view_duration_s: "",
        posted_at: new Date().toISOString().slice(0, 16),
    });

    useEffect(() => {
        const id = params.id === "latest" ? undefined : params.id;
        getConsolidatedReport(id)
            .then(setReport)
            .catch(err => setError(err.message))
            .finally(() => setLoading(false));
    }, [params.id]);

    useEffect(() => {
        if (!report?.report_platform) {
            return;
        }
        setOutcomeForm((prev) => ({
            ...prev,
            platform: report.report_platform,
        }));
        setAllowPlatformMismatch(false);
        setOutcomeWindow("now");
        setPublishMarkedAt(null);
    }, [report?.report_platform]);

    useEffect(() => {
        if (!report?.report_platform) {
            return;
        }
        (async () => {
            try {
                const summary = await getOutcomesSummary({ platform: report.report_platform });
                setOutcomeSummary(summary);
            } catch {
                setOutcomeSummary(null);
            }
        })();
    }, [report?.report_platform]);

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
    const reportPlatform = report.report_platform || "youtube";
    const hasPlatformMismatch = outcomeForm.platform !== reportPlatform;
    const hasCorePrediction = !!(
        prediction &&
        prediction.competitor_metrics &&
        prediction.platform_metrics &&
        prediction.combined_metrics
    );

    async function handlePostOutcome(e: React.FormEvent) {
        e.preventDefault();
        if (!report) {
            return;
        }
        setPostingOutcome(true);
        setOutcomeError(null);
        setOutcomeNotice(null);
        if (hasPlatformMismatch && !allowPlatformMismatch) {
            setOutcomeError(`Outcome platform (${outcomeForm.platform}) does not match report platform (${reportPlatform}). Confirm mismatch to continue.`);
            setPostingOutcome(false);
            return;
        }
        try {
            const postedAt = outcomeForm.posted_at
                ? new Date(outcomeForm.posted_at).toISOString()
                : new Date().toISOString();
            const response = await ingestOutcomeMetrics({
                platform: outcomeForm.platform as "youtube" | "instagram" | "tiktok",
                actual_metrics: {
                    views: Number(outcomeForm.views || 0),
                    likes: Number(outcomeForm.likes || 0),
                    comments: Number(outcomeForm.comments || 0),
                    shares: Number(outcomeForm.shares || 0),
                    saves: Number(outcomeForm.saves || 0),
                    avg_view_duration_s: Number(outcomeForm.avg_view_duration_s || 0),
                },
                posted_at: postedAt,
                predicted_score: report.performance_prediction?.combined_metrics?.score,
                draft_snapshot_id: report.best_edited_variant?.id || undefined,
                report_id: report.audit_id,
            });
            const summary = await getOutcomesSummary({ platform: outcomeForm.platform as "youtube" | "instagram" | "tiktok" });
            setOutcomeSummary(summary);
            setOutcomeNotice(
                `Saved. Calibration delta ${response.calibration_delta ?? "n/a"} • Confidence ${summary.confidence || "low"}`
            );
            const id = params.id === "latest" ? undefined : params.id;
            const refreshedReport = await getConsolidatedReport(id);
            setReport(refreshedReport);
        } catch (err: any) {
            setOutcomeError(err.message || "Could not save outcome");
        } finally {
            setPostingOutcome(false);
        }
    }

    async function handleRecalibrate() {
        setRecalibrating(true);
        setOutcomeError(null);
        try {
            const result = await recalibrateOutcomes();
            setOutcomeNotice(`Recalibrated ${result.refreshed} user/platform snapshots.`);
            const summary = await getOutcomesSummary({ platform: reportPlatform as "youtube" | "instagram" | "tiktok" });
            setOutcomeSummary(summary);
        } catch (err: any) {
            setOutcomeError(err.message || "Recalibration failed");
        } finally {
            setRecalibrating(false);
        }
    }

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <header className="no-print flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                    <Link href="/" className="text-lg font-bold text-[#1f1f1f]">SPC Studio</Link>
                    <nav className="flex gap-5 text-sm text-[#666]">
                        <Link href="/dashboard" className="hover:text-[#1c1c1c]">Dashboard</Link>
                        <Link href="/competitors" className="hover:text-[#1c1c1c]">Competitors</Link>
                        <Link href="/research" className="hover:text-[#1c1c1c]">Research</Link>
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
                        <p className="mt-2 text-center text-xs text-[#666]">
                            Report platform: <span className="font-semibold text-[#2b2b2b]">{reportPlatform}</span>
                        </p>
                    </div>

                    {report.calibration_confidence && (
                        <section className="mb-8 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <h2 className="text-lg font-bold text-[#1f1f1f]">Prediction Confidence</h2>
                                    <p className="text-xs text-[#666]">
                                        {report.calibration_confidence.platform} • Samples {report.calibration_confidence.sample_size} • MAE {report.calibration_confidence.mean_abs_error}
                                    </p>
                                </div>
                                <span className="rounded-full border border-[#d9d9d9] bg-[#fafafa] px-3 py-1 text-xs uppercase tracking-wide text-[#555]">
                                    {report.calibration_confidence.confidence}
                                </span>
                            </div>
                            {!!report.calibration_confidence.recommendations?.length && (
                                <ul className="mt-3 space-y-1 text-xs text-[#666]">
                                    {report.calibration_confidence.recommendations.slice(0, 2).map((item, idx) => (
                                        <li key={idx}>• {item}</li>
                                    ))}
                                </ul>
                            )}
                            {outcomeSummary?.drift_windows && (
                                <div className="mt-3 rounded-xl border border-[#e5e5e5] bg-[#fafafa] p-3 text-[11px] text-[#666]">
                                    <p>
                                        Drift 7d: {outcomeSummary.drift_windows.d7?.mean_delta ?? 0} (bias {outcomeSummary.drift_windows.d7?.bias || "neutral"})
                                    </p>
                                    <p>
                                        Drift 30d: {outcomeSummary.drift_windows.d30?.mean_delta ?? 0} (bias {outcomeSummary.drift_windows.d30?.bias || "neutral"})
                                    </p>
                                </div>
                            )}
                        </section>
                    )}

                    {(report.prediction_vs_actual || report.quick_actions?.length) && (
                        <section className="mb-10 grid gap-4 md:grid-cols-2">
                            {report.prediction_vs_actual && (
                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="text-sm font-semibold text-[#222]">Predicted vs Actual</h3>
                                    <p className="mt-2 text-xs text-[#666]">
                                        Predicted: {Math.round(report.prediction_vs_actual.predicted_score || 0)} • Actual: {Math.round(report.prediction_vs_actual.actual_score || 0)}
                                    </p>
                                    {typeof report.prediction_vs_actual.calibration_delta === "number" && (
                                        <p className="mt-1 text-xs text-[#666]">
                                            Delta: {report.prediction_vs_actual.calibration_delta > 0 ? "+" : ""}
                                            {report.prediction_vs_actual.calibration_delta}
                                        </p>
                                    )}
                                    {report.prediction_vs_actual.posted_at && (
                                        <p className="mt-1 text-[11px] text-[#777]">Posted at {new Date(report.prediction_vs_actual.posted_at).toLocaleString()}</p>
                                    )}
                                </div>
                            )}
                            {report.quick_actions?.length ? (
                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                    <h3 className="text-sm font-semibold text-[#222]">Next Step</h3>
                                    {report.quick_actions.map((action) => (
                                        <Link
                                            key={action.type}
                                            href={action.href}
                                            className="mt-3 block rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef]"
                                        >
                                            {action.label}
                                        </Link>
                                    ))}
                                </div>
                            ) : null}
                        </section>
                    )}

                    <section className="mb-10 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                            <h2 className="text-lg font-bold text-[#1f1f1f]">Post Result (Outcomes Learning)</h2>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setPublishMarkedAt(new Date().toISOString());
                                        setOutcomeForm((prev) => ({ ...prev, posted_at: postedAtFromWindow("now") }));
                                        setOutcomeWindow("now");
                                    }}
                                    className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1 text-xs text-[#555] hover:bg-[#efefef]"
                                >
                                    Mark as Published
                                </button>
                                <button
                                    type="button"
                                    onClick={() => void handleRecalibrate()}
                                    disabled={recalibrating}
                                    className="rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-1 text-xs text-[#555] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {recalibrating ? "Recalibrating..." : "Run Recalibration"}
                                </button>
                            </div>
                        </div>
                        <div className="mb-3 rounded-xl border border-[#e5e5e5] bg-[#fafafa] p-3">
                            <p className="text-xs text-[#666]">
                                Publish window:
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setOutcomeWindow("now");
                                        setOutcomeForm((prev) => ({ ...prev, posted_at: postedAtFromWindow("now") }));
                                    }}
                                    className={`rounded-lg border px-3 py-1 text-xs ${outcomeWindow === "now" ? "border-[#bbbbbb] bg-white text-[#222]" : "border-[#dddddd] bg-[#f4f4f4] text-[#666]"}`}
                                >
                                    Now
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setOutcomeWindow("7d");
                                        setOutcomeForm((prev) => ({ ...prev, posted_at: postedAtFromWindow("7d") }));
                                    }}
                                    className={`rounded-lg border px-3 py-1 text-xs ${outcomeWindow === "7d" ? "border-[#bbbbbb] bg-white text-[#222]" : "border-[#dddddd] bg-[#f4f4f4] text-[#666]"}`}
                                >
                                    7d Snapshot
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setOutcomeWindow("30d");
                                        setOutcomeForm((prev) => ({ ...prev, posted_at: postedAtFromWindow("30d") }));
                                    }}
                                    className={`rounded-lg border px-3 py-1 text-xs ${outcomeWindow === "30d" ? "border-[#bbbbbb] bg-white text-[#222]" : "border-[#dddddd] bg-[#f4f4f4] text-[#666]"}`}
                                >
                                    30d Snapshot
                                </button>
                            </div>
                            {publishMarkedAt && (
                                <p className="mt-2 text-[11px] text-[#666]">Marked published at {new Date(publishMarkedAt).toLocaleString()}</p>
                            )}
                        </div>
                        <form onSubmit={handlePostOutcome} className="grid gap-2 md:grid-cols-4">
                            <select
                                value={outcomeForm.platform}
                                onChange={(e) => {
                                    const platform = e.target.value;
                                    setOutcomeForm((prev) => ({ ...prev, platform }));
                                    if (platform === reportPlatform) {
                                        setAllowPlatformMismatch(false);
                                    }
                                }}
                                className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                            >
                                <option value="youtube">YouTube</option>
                                <option value="instagram">Instagram</option>
                                <option value="tiktok">TikTok</option>
                            </select>
                            <input value={outcomeForm.views} onChange={(e) => setOutcomeForm((p) => ({ ...p, views: e.target.value }))} placeholder="views" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input value={outcomeForm.likes} onChange={(e) => setOutcomeForm((p) => ({ ...p, likes: e.target.value }))} placeholder="likes" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input value={outcomeForm.comments} onChange={(e) => setOutcomeForm((p) => ({ ...p, comments: e.target.value }))} placeholder="comments" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input value={outcomeForm.shares} onChange={(e) => setOutcomeForm((p) => ({ ...p, shares: e.target.value }))} placeholder="shares" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input value={outcomeForm.saves} onChange={(e) => setOutcomeForm((p) => ({ ...p, saves: e.target.value }))} placeholder="saves" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input value={outcomeForm.avg_view_duration_s} onChange={(e) => setOutcomeForm((p) => ({ ...p, avg_view_duration_s: e.target.value }))} placeholder="avg view duration s" className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <input type="datetime-local" value={outcomeForm.posted_at} onChange={(e) => setOutcomeForm((p) => ({ ...p, posted_at: e.target.value }))} className="rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]" />
                            <button
                                type="submit"
                                disabled={postingOutcome || (hasPlatformMismatch && !allowPlatformMismatch)}
                                className="rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-xs text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                            >
                                {postingOutcome ? "Saving..." : "Save Post Result"}
                            </button>
                        </form>
                        {hasPlatformMismatch && (
                            <div className="mt-2 rounded-xl border border-[#ecd9bc] bg-[#fff8ed] px-3 py-2 text-[11px] text-[#735534]">
                                Platform mismatch detected (report: {reportPlatform}, selected: {outcomeForm.platform}).
                                <button
                                    type="button"
                                    onClick={() => setAllowPlatformMismatch(true)}
                                    className="ml-2 rounded-md border border-[#d9c7ab] bg-white px-2 py-0.5 text-[11px] text-[#6f5131] hover:bg-[#f5ede1]"
                                >
                                    Allow mismatch
                                </button>
                            </div>
                        )}
                        {outcomeNotice && <p className="mt-2 text-xs text-[#2f6b39]">{outcomeNotice}</p>}
                        {outcomeError && <p className="mt-2 text-xs text-[#7f3a3a]">{outcomeError}</p>}
                    </section>

                    {(report.outcome_drift?.next_actions?.length || outcomeSummary?.next_actions?.length) && (
                        <section className="mb-10 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h2 className="text-lg font-bold text-[#1f1f1f]">Calibration Drift: Do This Next</h2>
                            <ul className="mt-3 space-y-1 text-xs text-[#555]">
                                {(report.outcome_drift?.next_actions || outcomeSummary?.next_actions || []).slice(0, 4).map((action, idx) => (
                                    <li key={idx}>• {action}</li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {report.best_edited_variant && (
                        <section className="mb-10 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <h2 className="text-lg font-bold text-[#1f1f1f]">Best Edited Variant</h2>
                                    <p className="text-xs text-[#666]">
                                        {report.best_edited_variant.platform} • Snapshot {report.best_edited_variant.id}
                                    </p>
                                </div>
                                <span className="rounded-full border border-[#d9d9d9] bg-[#fafafa] px-3 py-1 text-xs text-[#555]">
                                    {typeof report.best_edited_variant.delta_score === "number"
                                        ? `${report.best_edited_variant.delta_score > 0 ? "+" : ""}${report.best_edited_variant.delta_score} pts`
                                        : "No delta"}
                                </span>
                            </div>
                            <p className="mt-3 rounded-xl border border-[#e1e1e1] bg-[#fafafa] p-3 text-xs text-[#444]">
                                {report.best_edited_variant.script_preview}
                            </p>
                            {report.best_edited_variant.top_detector_improvements && report.best_edited_variant.top_detector_improvements.length > 0 && (
                                <ul className="mt-3 space-y-1 text-xs text-[#666]">
                                    {report.best_edited_variant.top_detector_improvements.map((item, idx) => (
                                        <li key={`${item.detector_key}-${idx}`}>
                                            • {item.label || item.detector_key}: {Math.round(item.score || 0)}/{Math.round(item.target_score || 0)}
                                        </li>
                                    ))}
                                </ul>
                            )}
                            {report.prediction_vs_actual?.draft_snapshot_id === report.best_edited_variant.id && (
                                <div className="mt-3 rounded-xl border border-[#e3e3e3] bg-[#fafafa] p-3 text-[11px] text-[#555]">
                                    <p>
                                        Outcome linked to this draft: predicted {Math.round(report.prediction_vs_actual.predicted_score || 0)} vs actual {Math.round(report.prediction_vs_actual.actual_score || 0)}
                                    </p>
                                    <p>
                                        Delta {report.prediction_vs_actual.calibration_delta || 0}
                                    </p>
                                </div>
                            )}
                            <Link
                                href={`/research?mode=optimizer&source_item_id=${encodeURIComponent(report.best_edited_variant.source_item_id || "")}&topic=${encodeURIComponent(report.best_edited_variant.script_preview.slice(0, 100))}&source_context=${encodeURIComponent("report_refinement")}`}
                                className="mt-3 inline-flex rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-xs text-[#2f2f2f] hover:bg-[#efefef]"
                            >
                                Generate Improved A/B/C From This Draft
                            </Link>
                        </section>
                    )}

                    {hasCorePrediction && prediction && (
                        <section className="mb-16">
                            <h2 className="mb-6 text-2xl font-bold text-[#1f1f1f]">Performance Likelihood Scores</h2>
                            <div className={`mb-4 grid gap-4 ${prediction.historical_metrics ? "md:grid-cols-4" : "md:grid-cols-3"}`}>
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
                                    <p className="mt-1 text-[11px] uppercase tracking-wide text-[#6f6f6f]">
                                        Confidence: {prediction.combined_metrics.confidence}
                                    </p>
                                </div>
                                {prediction.historical_metrics && (
                                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-5">
                                        <p className="mb-2 text-xs uppercase tracking-wide text-[#7a7a7a]">Historical Calibration</p>
                                        <p className="text-3xl font-bold text-[#7a5a2f]">
                                            {Math.round(prediction.historical_metrics.score)}
                                            <span className="text-sm text-[#8a8a8a]">/100</span>
                                        </p>
                                        <p className="mt-2 text-xs text-[#666]">{prediction.historical_metrics.summary}</p>
                                        <p className="mt-1 text-[11px] text-[#6f6f6f]">
                                            Samples: {prediction.historical_metrics.format_sample_size} format-matched
                                        </p>
                                    </div>
                                )}
                            </div>

                            {prediction.combined_metrics.insufficient_data && (
                                <div className="mb-4 rounded-2xl border border-[#ecd9bc] bg-[#fff8ed] p-4">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#8a6438]">
                                        Insufficient data for highest-confidence prediction
                                    </p>
                                    {!!prediction.combined_metrics.insufficient_data_reasons?.length && (
                                        <ul className="mt-2 space-y-1 text-xs text-[#735534]">
                                            {prediction.combined_metrics.insufficient_data_reasons.map((reason, idx) => (
                                                <li key={idx}>• {reason}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}
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
