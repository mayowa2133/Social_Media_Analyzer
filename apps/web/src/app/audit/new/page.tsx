"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";
import {
    getAuditStatus,
    getCurrentUserId,
    RetentionPoint,
    runMultimodalAudit,
    syncYouTubeSession,
} from "@/lib/api";

function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function NewAuditPage() {
    const router = useRouter();
    const { data: session } = useSession();
    const [videoUrl, setVideoUrl] = useState("");
    const [retentionJson, setRetentionJson] = useState("");
    const [running, setRunning] = useState(false);
    const [progressMessage, setProgressMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function resolveUserId(): Promise<string | undefined> {
        const stored = getCurrentUserId();
        if (stored) {
            return stored;
        }

        if (session?.accessToken && session.user?.email) {
            const synced = await syncYouTubeSession({
                access_token: session.accessToken,
                refresh_token: session.refreshToken,
                expires_at: session.expiresAt,
                email: session.user.email,
                name: session.user.name || undefined,
                picture: session.user.image || undefined,
            });
            return synced.user_id;
        }

        return undefined;
    }

    async function handleRunAudit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setProgressMessage(null);

        if (!videoUrl.trim()) {
            setError("Enter a YouTube video URL to run the audit.");
            return;
        }

        let retentionPoints: RetentionPoint[] | undefined;
        if (retentionJson.trim()) {
            try {
                const parsed = JSON.parse(retentionJson);
                if (!Array.isArray(parsed)) {
                    throw new Error("Retention JSON must be an array.");
                }
                retentionPoints = parsed;
            } catch (err: any) {
                setError(err.message || "Invalid retention JSON.");
                return;
            }
        }

        setRunning(true);
        try {
            const userId = await resolveUserId();
            const run = await runMultimodalAudit({
                source_mode: "url",
                video_url: videoUrl.trim(),
                retention_points: retentionPoints,
                user_id: userId,
            });

            setProgressMessage("Audit started. Processing video...");

            for (let i = 0; i < 90; i++) {
                await sleep(2000);
                const status = await getAuditStatus(run.audit_id);
                setProgressMessage(`Status: ${status.status} (${status.progress}%)`);

                if (status.status === "completed") {
                    router.push(`/report/${run.audit_id}`);
                    return;
                }
                if (status.status === "failed") {
                    throw new Error(status.error || "Audit failed.");
                }
            }

            throw new Error("Audit timed out. Try again.");
        } catch (err: any) {
            setError(err.message || "Failed to run audit.");
        } finally {
            setRunning(false);
        }
    }

    return (
        <div className="min-h-screen p-8">
            <header className="max-w-7xl mx-auto mb-8">
                <div className="flex justify-between items-center">
                    <Link href="/" className="text-2xl font-bold text-white">
                        <span className="gradient-text">SPC</span>
                    </Link>
                    <nav className="flex gap-6">
                        <Link href="/dashboard" className="text-gray-400 hover:text-white transition-colors">Dashboard</Link>
                        <Link href="/competitors" className="text-gray-400 hover:text-white transition-colors">Competitors</Link>
                        <Link href="/audit/new" className="text-white font-medium">New Audit</Link>
                    </nav>
                </div>
            </header>

            <main className="max-w-3xl mx-auto">
                <h1 className="text-3xl font-bold text-white mb-2">New Audit</h1>
                <p className="text-gray-400 mb-8">Run a multimodal audit on a single video URL and get a consolidated report.</p>

                <form className="space-y-6" onSubmit={handleRunAudit}>
                    <div className="glass-card p-6">
                        <h2 className="text-lg font-semibold text-white mb-4">1. Video URL</h2>
                        <input
                            value={videoUrl}
                            onChange={(e) => setVideoUrl(e.target.value)}
                            placeholder="https://www.youtube.com/watch?v=..."
                            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            disabled={running}
                        />
                    </div>

                    <div className="glass-card p-6">
                        <h2 className="text-lg font-semibold text-white mb-4">2. Retention Data (Optional)</h2>
                        <p className="text-gray-400 text-sm mb-4">
                            Paste retention points if available. Example format:
                            {" "}
                            <code className="text-gray-300">[{`{"time":0,"retention":100}`}, {`{"time":5,"retention":78}`}]</code>
                        </p>
                        <textarea
                            value={retentionJson}
                            onChange={(e) => setRetentionJson(e.target.value)}
                            placeholder='[{"time": 0, "retention": 100}, {"time": 5, "retention": 78}]'
                            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[120px] font-mono text-sm"
                            disabled={running}
                        />
                    </div>

                    {error && (
                        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                            {error}
                        </div>
                    )}

                    {progressMessage && (
                        <div className="p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg text-purple-300">
                            {progressMessage}
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={running}
                        className="w-full py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {running ? "Running Audit..." : "Run Audit"}
                    </button>
                </form>
            </main>
        </div>
    );
}
