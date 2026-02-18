"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ConsolidatedReport, getSharedReport } from "@/lib/api";

export default function SharedReportPage({ params }: { params: { token: string } }) {
    const [report, setReport] = useState<ConsolidatedReport | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getSharedReport(params.token)
            .then(setReport)
            .catch((err) => setError(err.message || "Failed to load shared report"))
            .finally(() => setLoading(false));
    }, [params.token]);

    if (loading) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#e8e8e8]">
                <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#555] border-t-transparent"></div>
            </div>
        );
    }

    if (!report || error) {
        return (
            <div className="flex min-h-screen flex-col items-center justify-center bg-[#e8e8e8] p-8">
                <h1 className="text-2xl font-bold text-[#1f1f1f]">Shared report unavailable</h1>
                <p className="mt-2 text-sm text-[#666]">{error || "This link may have expired."}</p>
                <Link href="/" className="mt-4 rounded-xl border border-[#d7d7d7] bg-white px-4 py-2 text-sm text-[#242424]">
                    Back Home
                </Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto max-w-4xl rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] p-6 shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <h1 className="text-2xl font-bold text-[#1f1f1f]">Shared Social Performance Report</h1>
                <p className="mt-1 text-sm text-[#666]">Audit ID: {report.audit_id}</p>

                <div className="mt-6 grid gap-4 md:grid-cols-3">
                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                        <p className="text-xs uppercase tracking-wide text-[#777]">Overall</p>
                        <p className="mt-1 text-3xl font-bold text-[#2f6b39]">{Math.round(report.overall_score)}</p>
                    </div>
                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                        <p className="text-xs uppercase tracking-wide text-[#777]">Combined</p>
                        <p className="mt-1 text-3xl font-bold text-[#2f5f7a]">
                            {Math.round(report.performance_prediction?.combined_metrics?.score || 0)}
                        </p>
                    </div>
                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                        <p className="text-xs uppercase tracking-wide text-[#777]">Confidence</p>
                        <p className="mt-1 text-3xl font-bold text-[#514aa2]">
                            {(report.performance_prediction?.combined_metrics?.confidence || "n/a").toUpperCase()}
                        </p>
                    </div>
                </div>

                <section className="mt-6 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                    <h2 className="text-sm font-semibold text-[#222]">Recommendations</h2>
                    <ul className="mt-2 space-y-2 text-sm text-[#444]">
                        {(report.recommendations || []).slice(0, 6).map((rec, idx) => (
                            <li key={idx}>• {rec}</li>
                        ))}
                    </ul>
                </section>
            </div>
        </div>
    );
}
