"use client";

import Link from "next/link";
import { useSession, signOut } from "next-auth/react";
import { useEffect, useState } from "react";
import {
    Competitor,
    CurrentUserResponse,
    DiagnosisResult,
    getAudits,
    getChannelDiagnosis,
    getCompetitors,
    getCurrentUserId,
    getCurrentUserProfile,
    getOutcomesSummary,
    logoutBackendSession,
    syncYouTubeSession,
} from "@/lib/api";
import { StudioAppShell } from "@/components/app-shell";
import { DiagnosisCard } from "@/components/diagnosis-card";
import { FlowStepper } from "@/components/flow-stepper";

export default function DashboardPage() {
    const { data: session, status } = useSession();
    const [competitors, setCompetitors] = useState<Competitor[]>([]);
    const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
    const [profile, setProfile] = useState<CurrentUserResponse | null>(null);
    const [auditCount, setAuditCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [platformConfidence, setPlatformConfidence] = useState<Record<string, string>>({});

    useEffect(() => {
        async function fetchData() {
            setLoading(true);
            setError(null);

            try {
                let resolvedUserId = getCurrentUserId() || undefined;

                if (session?.accessToken && session.user?.email) {
                    setSyncing(true);
                    const synced = await syncYouTubeSession({
                        access_token: session.accessToken,
                        refresh_token: session.refreshToken,
                        expires_at: session.expiresAt,
                        email: session.user.email,
                        name: session.user.name || undefined,
                        picture: session.user.image || undefined,
                    });
                    resolvedUserId = synced.user_id;
                }

                const resolvedProfile: CurrentUserResponse | null = resolvedUserId
                    ? await getCurrentUserProfile()
                    : null;

                setProfile(resolvedProfile || null);

                const [comps, audits] = await Promise.all([
                    getCompetitors(resolvedUserId),
                    getAudits(resolvedUserId),
                ]);

                setCompetitors(comps);
                setAuditCount(audits.filter((a) => a.status === "completed").length);

                if (resolvedProfile?.channel_id) {
                    const channelDiagnosis = await getChannelDiagnosis(resolvedProfile.channel_id);
                    setDiagnosis(channelDiagnosis);
                } else {
                    setDiagnosis(null);
                }

                const connectedPlatforms = resolvedProfile?.connected_platforms;
                const confidence: Record<string, string> = {};
                if (connectedPlatforms) {
                    const platformKeys = (["youtube", "instagram", "tiktok"] as const).filter((key) => connectedPlatforms[key]);
                    await Promise.all(
                        platformKeys.map(async (platform) => {
                            try {
                                const summary = await getOutcomesSummary({ platform, userId: resolvedUserId });
                                confidence[platform] = String(summary?.confidence || "low");
                            } catch {
                                confidence[platform] = "n/a";
                            }
                        })
                    );
                }
                setPlatformConfidence(confidence);
            } catch (err) {
                console.error("Error fetching dashboard data:", err);
                setError("Could not connect to API");
            } finally {
                setLoading(false);
                setSyncing(false);
            }
        }

        if (status !== "loading") {
            fetchData();
        }
    }, [status, session?.accessToken, session?.user?.email, session?.refreshToken, session?.expiresAt]);

    const connectedPlatforms = profile?.connected_platforms || { youtube: false, instagram: false, tiktok: false };
    const connectedCount = Object.values(connectedPlatforms).filter(Boolean).length;
    const isConnected = connectedCount > 0;

    const statusLabel = status === "loading" || syncing
        ? (syncing ? "Syncing channel connection..." : "Loading session...")
        : isConnected
            ? `Connected platforms: ${Object.entries(connectedPlatforms)
                .filter(([, value]) => value)
                .map(([name]) => name)
                .join(", ")}`
            : "No platform connected yet";

    const statusTone = status === "loading" || syncing
        ? "bg-[#f0f0f0] border-[#dddddd] text-[#6b6b6b]"
        : isConnected
            ? "bg-[#edf7ed] border-[#cfe6cf] text-[#2e5a33]"
            : "bg-[#fff5e8] border-[#ecdcc0] text-[#7a6032]";

    return (
        <StudioAppShell
            rightSlot={
                session ? (
                    <button
                        onClick={async () => {
                            await logoutBackendSession();
                            await signOut({ callbackUrl: "/" });
                        }}
                        className="rounded-xl border border-[#d6d6d6] bg-white px-3 py-1.5 text-sm text-[#575757] hover:text-[#1f1f1f]"
                    >
                        Logout
                    </button>
                ) : null
            }
        >
            <main className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)]">
                    <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                        <h1 className="text-xl font-bold text-[#202020]">Creator Dashboard</h1>
                        <p className="mt-1 text-sm text-[#6f6f6f]">
                            Track cross-platform health, competitor position, and audit momentum.
                        </p>

                        <div className={`mt-4 rounded-2xl border px-3 py-2 text-sm ${statusTone}`}>
                            {statusLabel}
                        </div>

                        {!isConnected && (
                            <Link
                                href="/connect"
                                className="mt-3 inline-flex text-sm font-medium text-[#5d4ea2] hover:text-[#3d2f84]"
                            >
                                Connect Platforms →
                            </Link>
                        )}

                        <div className="mt-5 space-y-3">
                            <div className="rounded-2xl border border-[#dddddd] bg-white p-4">
                                <p className="text-xs uppercase tracking-wide text-[#777]">Connected Platforms</p>
                                <p className="mt-1 text-3xl font-bold text-[#1f1f1f]">{connectedCount}</p>
                                <p className="mt-1 text-[11px] text-[#777]">
                                    YouTube {connectedPlatforms.youtube ? "Yes" : "No"} · Instagram {connectedPlatforms.instagram ? "Yes" : "No"} · TikTok {connectedPlatforms.tiktok ? "Yes" : "No"}
                                </p>
                            </div>
                            <div className="rounded-2xl border border-[#dddddd] bg-white p-4">
                                <p className="text-xs uppercase tracking-wide text-[#777]">Competitors Tracked</p>
                                <p className="mt-1 text-3xl font-bold text-[#1f1f1f]">{competitors.length}</p>
                            </div>
                            <div className="rounded-2xl border border-[#dddddd] bg-white p-4">
                                <p className="text-xs uppercase tracking-wide text-[#777]">Outcome Confidence</p>
                                <p className="mt-1 text-sm text-[#1f1f1f]">
                                    YT {platformConfidence.youtube || "n/a"} · IG {platformConfidence.instagram || "n/a"} · TT {platformConfidence.tiktok || "n/a"}
                                </p>
                            </div>
                            <div className="rounded-2xl border border-[#dddddd] bg-white p-4">
                                <p className="text-xs uppercase tracking-wide text-[#777]">Audits Completed</p>
                                <p className="mt-1 text-3xl font-bold text-[#1f1f1f]">{auditCount}</p>
                            </div>
                            <div className="rounded-2xl border border-[#dddddd] bg-white p-4">
                                <p className="text-xs uppercase tracking-wide text-[#777]">API Status</p>
                                <p className={`mt-1 text-lg font-semibold ${error ? "text-[#8a3a3a]" : "text-[#2f5d35]"}`}>
                                    {loading ? "..." : error ? "Offline" : "Online"}
                                </p>
                            </div>
                        </div>

                        <div className="mt-5 space-y-2">
                            <Link href="/competitors" className="block rounded-xl border border-[#ddd] bg-white px-3 py-2 text-sm text-[#2b2b2b] hover:bg-[#f4f4f4]">
                                Add Competitors
                            </Link>
                            <Link href="/audit/new" className="block rounded-xl border border-[#ddd] bg-white px-3 py-2 text-sm text-[#2b2b2b] hover:bg-[#f4f4f4]">
                                Run New Audit
                            </Link>
                            <Link href="/research" className="block rounded-xl border border-[#ddd] bg-white px-3 py-2 text-sm text-[#2b2b2b] hover:bg-[#f4f4f4]">
                                Open Research Studio
                            </Link>
                            <Link href="/report/latest" className="block rounded-xl border border-[#ddd] bg-white px-3 py-2 text-sm text-[#2b2b2b] hover:bg-[#f4f4f4]">
                                View Latest Report
                            </Link>
                        </div>
                    </aside>

                    <section className="bg-[#f2f2f2] p-4 md:p-6">
                        <FlowStepper />
                        {diagnosis && (
                            <div className="mb-6">
                                <div className="mb-3 flex items-center justify-between">
                                    <h2 className="text-xl font-bold text-[#1f1f1f]">Channel Diagnosis</h2>
                                    <Link href="/report/latest" className="text-sm font-semibold text-[#4f4b9e] hover:text-[#383277]">
                                        View Full Report →
                                    </Link>
                                </div>
                                <DiagnosisCard diagnosis={diagnosis} loading={loading} />
                            </div>
                        )}

                        {competitors.length > 0 && (
                            <div className="mb-6">
                                <h2 className="mb-3 text-xl font-semibold text-[#1f1f1f]">Tracked Competitors</h2>
                                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                                    {competitors.map((comp) => (
                                        <div key={comp.id} className="flex items-center gap-3 rounded-2xl border border-[#dbdbdb] bg-white p-3">
                                            {comp.thumbnail_url && (
                                                <img src={comp.thumbnail_url} alt={comp.title} className="h-11 w-11 rounded-full border border-[#e2e2e2]" />
                                            )}
                                            <div className="min-w-0">
                                                <h3 className="truncate text-sm font-semibold text-[#232323]">{comp.title}</h3>
                                                <p className="text-xs text-[#727272]">
                                                    {Number(comp.subscriber_count || 0).toLocaleString()} audience · {comp.platform}
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {!isConnected && competitors.length === 0 && (
                            <div className="rounded-3xl border border-[#dadada] bg-white p-10 text-center shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <div className="mb-4 text-5xl">📊</div>
                                <h2 className="mb-2 text-2xl font-bold text-[#1f1f1f]">Get Started</h2>
                                <p className="mx-auto mb-5 max-w-lg text-sm text-[#6d6d6d]">
                                    Connect at least one platform and add competitors to unlock scoring benchmarks and strategy analysis.
                                </p>
                                <div className="flex flex-wrap justify-center gap-3">
                                    <Link href="/connect" className="rounded-xl bg-[#1d1d1d] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#101010]">
                                        Connect Platforms
                                    </Link>
                                    <Link href="/competitors" className="rounded-xl border border-[#d9d9d9] bg-white px-5 py-2.5 text-sm font-semibold text-[#333] hover:bg-[#f7f7f7]">
                                        Add Competitors
                                    </Link>
                                </div>
                            </div>
                        )}
                    </section>
            </main>
        </StudioAppShell>
    );
}
