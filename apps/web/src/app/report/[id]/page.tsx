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
            <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a]">
                <div className="animate-spin w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (error || !report) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center p-8 bg-[#0a0a0a] text-white">
                <h1 className="text-2xl font-bold mb-4">Failed to load report</h1>
                <p className="text-gray-400 mb-8">{error || "No report found."}</p>
                <Link href="/dashboard" className="px-6 py-3 bg-white/5 border border-white/10 rounded-lg">Back to Dashboard</Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0a0a0a] pb-24">
            {/* Header */}
            <header className="fixed top-0 left-0 right-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/5 no-print">
                <div className="max-w-7xl mx-auto px-8 h-16 flex items-center justify-between">
                    <Link href="/" className="text-xl font-bold gradient-text">SPC</Link>
                    <nav className="flex gap-6">
                        <Link href="/dashboard" className="text-sm text-gray-400 hover:text-white">Dashboard</Link>
                        <Link href="/competitors" className="text-sm text-gray-400 hover:text-white">Competitors</Link>
                    </nav>
                </div>
            </header>

            <main className="max-w-4xl mx-auto px-8 pt-32">
                {/* Scorecard Hero */}
                <div className="mb-12">
                    <ReportScorecard
                        score={report.overall_score}
                        auditId={report.audit_id}
                        createdAt={report.created_at}
                    />
                </div>

                {/* Recommendations Summary */}
                <section className="mb-16">
                    <h2 className="text-2xl font-bold text-white mb-6">Executive Recommendations</h2>
                    <div className="grid gap-4">
                        {(report.recommendations || []).map((rec, i) => (
                            <div key={i} className="glass-card p-5 border-l-2 border-purple-500 flex items-start gap-4">
                                <span className="bg-purple-500/20 text-purple-400 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">
                                    {i + 1}
                                </span>
                                <p className="text-gray-300">{rec}</p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Strategy Blueprint */}
                <section className="mb-16">
                    <header className="flex justify-between items-end mb-8">
                        <div>
                            <h2 className="text-2xl font-bold text-white">Strategy Blueprint</h2>
                            <p className="text-gray-400 text-sm">Competitive advantage & content pillars</p>
                        </div>
                    </header>
                    <BlueprintDisplay blueprint={report.blueprint} />
                </section>

                {/* Video Analysis Result (Mini) */}
                {report.video_analysis && (
                    <section className="mb-16">
                        <h2 className="text-2xl font-bold text-white mb-6">Qualitative Video Audit</h2>
                        <div className="glass-card p-6">
                            <h3 className="text-lg font-semibold text-purple-400 mb-2">{report.video_analysis.summary}</h3>
                            <div className="grid md:grid-cols-2 gap-4 mt-6">
                                {report.video_analysis.sections?.map((sec: any, i: number) => (
                                    <div key={i} className="p-4 bg-white/5 rounded-lg border border-white/5">
                                        <div className="flex justify-between mb-2">
                                            <span className="text-white font-medium">{sec.name}</span>
                                            <span className="text-purple-400 font-bold">{sec.score}/10</span>
                                        </div>
                                        <ul className="text-xs text-gray-400 space-y-1">
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
    );
}
