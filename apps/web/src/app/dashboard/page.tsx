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
    setCurrentUserId,
    syncYouTubeSession,
} from "@/lib/api";
import { DiagnosisCard } from "@/components/diagnosis-card";

export default function DashboardPage() {
    const { data: session, status } = useSession();
    const [competitors, setCompetitors] = useState<Competitor[]>([]);
    const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
    const [profile, setProfile] = useState<CurrentUserResponse | null>(null);
    const [auditCount, setAuditCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchData() {
            setLoading(true);
            setError(null);

            try {
                let resolvedUserId = getCurrentUserId() || undefined;
                let resolvedProfile: CurrentUserResponse | null = null;

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
                    setCurrentUserId(synced.user_id);
                }

                if (!resolvedProfile && resolvedUserId) {
                    resolvedProfile = await getCurrentUserProfile({ userId: resolvedUserId });
                } else if (!resolvedProfile && session?.user?.email) {
                    resolvedProfile = await getCurrentUserProfile({ email: session.user.email });
                    resolvedUserId = resolvedProfile.user_id;
                    setCurrentUserId(resolvedProfile.user_id);
                }

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

    const isConnected = !!profile?.youtube_connected;

    return (
        <div className="min-h-screen p-8">
            <header className="max-w-7xl mx-auto mb-8">
                <div className="flex justify-between items-center">
                    <Link href="/" className="text-2xl font-bold text-white">
                        <span className="gradient-text">SPC</span>
                    </Link>
                    <nav className="flex items-center gap-6">
                        <Link href="/dashboard" className="text-white font-medium">Dashboard</Link>
                        <Link href="/competitors" className="text-gray-400 hover:text-white transition-colors">Competitors</Link>
                        <Link href="/audit/new" className="text-gray-400 hover:text-white transition-colors">New Audit</Link>
                        {session && (
                            <button
                                onClick={() => signOut({ callbackUrl: "/" })}
                                className="text-gray-400 hover:text-white transition-colors"
                            >
                                Logout
                            </button>
                        )}
                    </nav>
                </div>
            </header>

            <main className="max-w-7xl mx-auto">
                <h1 className="text-3xl font-bold text-white mb-8">Dashboard</h1>

                {status === "loading" || syncing ? (
                    <div className="flex items-center gap-2 text-gray-400 mb-6">
                        <div className="animate-spin w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full"></div>
                        {syncing ? "Syncing YouTube connection..." : "Loading session..."}
                    </div>
                ) : isConnected ? (
                    <div className="flex items-center gap-2 text-green-400 mb-6">
                        <span className="w-2 h-2 bg-green-400 rounded-full"></span>
                        Connected to YouTube{profile?.channel_title ? `: ${profile.channel_title}` : ""}
                    </div>
                ) : (
                    <div className="mb-6">
                        <Link
                            href="/connect"
                            className="inline-flex items-center gap-2 text-yellow-400 hover:text-yellow-300"
                        >
                            <span className="w-2 h-2 bg-yellow-400 rounded-full"></span>
                            Connect YouTube to get started →
                        </Link>
                    </div>
                )}

                {diagnosis && (
                    <div className="mb-8">
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xl font-bold text-white">Channel Diagnosis</h2>
                            <Link href="/report/latest" className="text-sm text-purple-400 hover:text-purple-300 font-bold flex items-center gap-1 group">
                                View Full Report <span className="group-hover:translate-x-1 transition-transform">→</span>
                            </Link>
                        </div>
                        <DiagnosisCard diagnosis={diagnosis} loading={loading} />
                    </div>
                )}

                <div className="grid md:grid-cols-4 gap-6 mb-8">
                    <div className="glass-card p-6">
                        <p className="text-gray-400 text-sm mb-1">Connected Channels</p>
                        <p className="text-3xl font-bold text-white">{isConnected ? 1 : 0}</p>
                    </div>
                    <div className="glass-card p-6">
                        <p className="text-gray-400 text-sm mb-1">Competitors Tracked</p>
                        <p className="text-3xl font-bold text-white">{competitors.length}</p>
                    </div>
                    <div className="glass-card p-6">
                        <p className="text-gray-400 text-sm mb-1">Audits Completed</p>
                        <p className="text-3xl font-bold text-white">{auditCount}</p>
                    </div>
                    <div className="glass-card p-6">
                        <p className="text-gray-400 text-sm mb-1">API Status</p>
                        <p className={`text-lg font-medium ${error ? "text-red-400" : "text-green-400"}`}>
                            {loading ? "..." : error ? "Offline" : "Online"}
                        </p>
                    </div>
                </div>

                <div className="grid md:grid-cols-3 gap-4 mb-8">
                    <Link href="/competitors" className="glass-card p-4 hover:bg-white/10 transition-colors">
                        <h3 className="text-white font-medium mb-1">Add Competitors</h3>
                        <p className="text-gray-400 text-sm">Track competitor channels for benchmarking</p>
                    </Link>
                    <Link href="/audit/new" className="glass-card p-4 hover:bg-white/10 transition-colors">
                        <h3 className="text-white font-medium mb-1">Run Audit</h3>
                        <p className="text-gray-400 text-sm">Analyze your content and get recommendations</p>
                    </Link>
                    <Link href="/connect" className="glass-card p-4 hover:bg-white/10 transition-colors">
                        <h3 className="text-white font-medium mb-1">Connect Platforms</h3>
                        <p className="text-gray-400 text-sm">Link more social media accounts</p>
                    </Link>
                </div>

                {competitors.length > 0 && (
                    <div className="mb-8">
                        <h2 className="text-xl font-semibold text-white mb-4">Tracked Competitors</h2>
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {competitors.map((comp) => (
                                <div key={comp.id} className="glass-card p-4 flex items-center gap-4">
                                    {comp.thumbnail_url && (
                                        <img
                                            src={comp.thumbnail_url}
                                            alt={comp.title}
                                            className="w-12 h-12 rounded-full"
                                        />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-white font-medium truncate">{comp.title}</h3>
                                        <p className="text-gray-400 text-sm">
                                            {Number(comp.subscriber_count || 0).toLocaleString()} subscribers
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {!isConnected && competitors.length === 0 && (
                    <div className="glass-card p-12 text-center">
                        <div className="text-6xl mb-4">📊</div>
                        <h2 className="text-xl font-semibold text-white mb-2">Get Started</h2>
                        <p className="text-gray-400 mb-6">Connect your YouTube channel or add competitors to begin analysis.</p>
                        <div className="flex gap-4 justify-center">
                            <Link
                                href="/connect"
                                className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
                            >
                                Connect YouTube
                            </Link>
                            <Link
                                href="/competitors"
                                className="px-6 py-3 bg-white/10 text-white font-medium rounded-lg hover:bg-white/20 transition-colors"
                            >
                                Add Competitors
                            </Link>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
