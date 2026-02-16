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
    uploadAuditVideo,
} from "@/lib/api";

function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

interface RetentionRowInput {
    time: string;
    retention: string;
}

interface GuidedPlatformMetricsInput {
    views: string;
    likes: string;
    comments: string;
    shares: string;
    saves: string;
    avg_view_duration_s: string;
    ctr: string;
}

export default function NewAuditPage() {
    const router = useRouter();
    const { data: session } = useSession();
    const [sourceMode, setSourceMode] = useState<"url" | "upload">("url");
    const [videoUrl, setVideoUrl] = useState("");
    const [videoFile, setVideoFile] = useState<File | null>(null);
    const [retentionJson, setRetentionJson] = useState("");
    const [platformMetricsJson, setPlatformMetricsJson] = useState("");
    const [retentionRows, setRetentionRows] = useState<RetentionRowInput[]>([{ time: "", retention: "" }]);
    const [guidedMetrics, setGuidedMetrics] = useState<GuidedPlatformMetricsInput>({
        views: "",
        likes: "",
        comments: "",
        shares: "",
        saves: "",
        avg_view_duration_s: "",
        ctr: "",
    });
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

    function updateRetentionRow(index: number, key: keyof RetentionRowInput, value: string) {
        setRetentionRows((prev) =>
            prev.map((row, rowIdx) => (rowIdx === index ? { ...row, [key]: value } : row))
        );
    }

    function addRetentionRow() {
        setRetentionRows((prev) => [...prev, { time: "", retention: "" }]);
    }

    function removeRetentionRow(index: number) {
        setRetentionRows((prev) => {
            if (prev.length <= 1) {
                return [{ time: "", retention: "" }];
            }
            return prev.filter((_, rowIdx) => rowIdx !== index);
        });
    }

    function updateGuidedMetric(field: keyof GuidedPlatformMetricsInput, value: string) {
        setGuidedMetrics((prev) => ({ ...prev, [field]: value }));
    }

    async function handleRunAudit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setProgressMessage(null);

        if (sourceMode === "url" && !videoUrl.trim()) {
            setError("Enter a YouTube video URL to run the audit.");
            return;
        }
        if (sourceMode === "upload" && !videoFile) {
            setError("Select a video file to upload.");
            return;
        }

        let retentionPoints: RetentionPoint[] | undefined;
        let platformMetrics:
            | {
                  views?: number;
                  likes?: number;
                  comments?: number;
                  shares?: number;
                  saves?: number;
                  watch_time_hours?: number;
                  avg_view_duration_s?: number;
                  ctr?: number;
              }
            | undefined;
        const parsedRetentionRows: RetentionPoint[] = [];
        for (const row of retentionRows) {
            const timeRaw = row.time.trim();
            const retentionRaw = row.retention.trim();
            if (!timeRaw && !retentionRaw) {
                continue;
            }
            const time = Number(timeRaw);
            const retention = Number(retentionRaw);
            if (!Number.isFinite(time) || !Number.isFinite(retention)) {
                setError("Retention row values must be numeric.");
                return;
            }
            parsedRetentionRows.push({ time, retention });
        }
        if (parsedRetentionRows.length > 0) {
            retentionPoints = parsedRetentionRows;
        }

        const guidedPlatformMetrics: Record<string, number> = {};
        const numericFields: Array<keyof GuidedPlatformMetricsInput> = [
            "views",
            "likes",
            "comments",
            "shares",
            "saves",
            "avg_view_duration_s",
            "ctr",
        ];
        for (const field of numericFields) {
            const raw = guidedMetrics[field].trim();
            if (!raw) {
                continue;
            }
            const numericValue = Number(raw);
            if (!Number.isFinite(numericValue)) {
                setError(`Platform metric '${field}' must be numeric.`);
                return;
            }
            guidedPlatformMetrics[field] = numericValue;
        }
        if (Object.keys(guidedPlatformMetrics).length > 0) {
            platformMetrics = guidedPlatformMetrics;
        }

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
        if (platformMetricsJson.trim()) {
            try {
                const parsed = JSON.parse(platformMetricsJson);
                if (Array.isArray(parsed) || typeof parsed !== "object" || parsed === null) {
                    throw new Error("Platform metrics JSON must be an object.");
                }
                platformMetrics = {
                    ...(platformMetrics || {}),
                    ...parsed,
                };
            } catch (err: any) {
                setError(err.message || "Invalid platform metrics JSON.");
                return;
            }
        }

        setRunning(true);
        try {
            const userId = await resolveUserId();
            let run;
            if (sourceMode === "upload") {
                setProgressMessage("Uploading video...");
                const upload = await uploadAuditVideo(videoFile as File, userId);
                run = await runMultimodalAudit({
                    source_mode: "upload",
                    upload_id: upload.upload_id,
                    retention_points: retentionPoints,
                    platform_metrics: platformMetrics,
                    user_id: userId,
                });
            } else {
                run = await runMultimodalAudit({
                    source_mode: "url",
                    video_url: videoUrl.trim(),
                    retention_points: retentionPoints,
                    platform_metrics: platformMetrics,
                    user_id: userId,
                });
            }

            setProgressMessage("Audit started. Processing video...");
            const maxAttempts = sourceMode === "upload" ? 180 : 120;
            let pollDelayMs = sourceMode === "upload" ? 2500 : 2000;
            for (let i = 0; i < maxAttempts; i++) {
                await sleep(pollDelayMs);
                const status = await getAuditStatus(run.audit_id, userId);
                setProgressMessage(`Status: ${status.status} (${status.progress}%)`);

                if (status.status === "completed") {
                    router.push(`/report/${run.audit_id}`);
                    return;
                }
                if (status.status === "failed") {
                    throw new Error(status.error || "Audit failed.");
                }
                pollDelayMs = Math.min(Math.round(pollDelayMs * 1.08), 5000);
            }

            throw new Error("Audit is still processing. Check the dashboard in a few minutes.");
        } catch (err: any) {
            setError(err.message || "Failed to run audit.");
        } finally {
            setRunning(false);
        }
    }

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <form onSubmit={handleRunAudit} className="mx-auto w-full max-w-[1500px]">
                <div className="overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                    <header className="flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                        <div className="flex items-center gap-4">
                            <Link href="/" className="text-lg font-bold text-[#1f1f1f]">
                                SPC Studio
                            </Link>
                            <nav className="hidden items-center gap-4 text-sm text-[#6b6b6b] md:flex">
                                <Link href="/dashboard" className="hover:text-[#151515]">Dashboard</Link>
                                <Link href="/competitors" className="hover:text-[#151515]">Competitors</Link>
                                <Link href="/audit/new" className="font-medium text-[#1b1b1b]">Audit Workspace</Link>
                            </nav>
                        </div>

                        <div className="hidden items-center gap-2 lg:flex">
                            <button type="button" className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-1.5 text-xs text-[#444]">⟲</button>
                            <button type="button" className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-1.5 text-xs text-[#444]">⟲</button>
                            <button type="button" className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-1.5 text-xs text-[#444]">100%</button>
                        </div>

                        <div className="flex items-center gap-3">
                            <span className="hidden rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666] md:inline-flex">Single Creator</span>
                            <button type="button" className="rounded-xl border border-[#d5d5d5] bg-white px-4 py-2 text-sm text-[#222]">
                                Share
                            </button>
                        </div>
                    </header>

                    <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
                        <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                            <h2 className="mb-1 text-sm font-semibold text-[#222]">Source Setup</h2>
                            <p className="mb-4 text-xs text-[#777]">Start with a URL or upload your clip.</p>

                            <div className="mb-4 grid grid-cols-2 gap-2 rounded-xl border border-[#dfdfdf] bg-[#efefef] p-1">
                                <button
                                    type="button"
                                    onClick={() => setSourceMode("url")}
                                    disabled={running}
                                    className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                                        sourceMode === "url" ? "bg-white text-[#141414] shadow-sm" : "text-[#666] hover:text-[#1d1d1d]"
                                    }`}
                                >
                                    URL
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setSourceMode("upload")}
                                    disabled={running}
                                    className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                                        sourceMode === "upload" ? "bg-white text-[#141414] shadow-sm" : "text-[#666] hover:text-[#1d1d1d]"
                                    }`}
                                >
                                    Upload
                                </button>
                            </div>

                            {sourceMode === "url" ? (
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-[#4f4f4f]">Video URL</label>
                                    <input
                                        value={videoUrl}
                                        onChange={(e) => setVideoUrl(e.target.value)}
                                        placeholder="https://www.youtube.com/watch?v=..."
                                        className="w-full rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                        disabled={running}
                                    />
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-[#4f4f4f]">Upload Video</label>
                                    <input
                                        type="file"
                                        accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska,.mp4,.mov,.m4v,.webm,.avi,.mkv"
                                        onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
                                        className="w-full rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-sm text-[#222] file:mr-2 file:rounded-md file:border-0 file:bg-[#ececec] file:px-3 file:py-1 file:text-[#303030]"
                                        disabled={running}
                                    />
                                    <p className="text-[11px] text-[#7b7b7b]">Max 300MB • mp4, mov, m4v, webm, avi, mkv</p>
                                </div>
                            )}

                            <div className="mt-6 rounded-2xl border border-[#dfdfdf] bg-white p-3">
                                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#666]">Checklist</h3>
                                <ul className="space-y-1 text-xs text-[#575757]">
                                    <li>• Clear opening 3 seconds</li>
                                    <li>• Single message per clip</li>
                                    <li>• Strong visual movement</li>
                                    <li>• End with a specific outcome</li>
                                </ul>
                            </div>
                        </aside>

                        <section className="border-b border-[#dfdfdf] bg-[#f2f2f2] px-4 py-4 md:px-6 xl:border-b-0">
                            <div className="mb-4 flex items-center justify-center gap-2">
                                <button type="button" className="rounded-lg border border-[#dbdbdb] bg-white px-3 py-1.5 text-xs text-[#545454]">⟵</button>
                                <button type="button" className="rounded-lg border border-[#dbdbdb] bg-white px-3 py-1.5 text-xs text-[#545454]">⟶</button>
                                <button type="button" className="rounded-lg border border-[#dbdbdb] bg-white px-3 py-1.5 text-xs text-[#545454]">Preview</button>
                            </div>

                            <div className="mx-auto flex max-w-4xl flex-col gap-5">
                                <div className="relative min-h-[360px] rounded-[28px] border border-[#dcdcdc] bg-white p-8 shadow-[0_14px_40px_rgba(0,0,0,0.06)] md:min-h-[500px]">
                                    <div className="absolute right-6 top-6 rounded-full border border-[#d9d9d9] bg-[#f7f7f7] px-3 py-1 text-[11px] text-[#666]">
                                        {sourceMode === "url" ? "URL Mode" : "Upload Mode"}
                                    </div>

                                    <div className="mx-auto mt-8 max-w-xl text-center">
                                        <div className="mb-4 text-5xl">🎬</div>
                                        <h1 className="mb-2 text-2xl font-bold text-[#1f1f1f]">Performance Audit Workspace</h1>
                                        <p className="text-sm leading-relaxed text-[#666]">
                                            Upload a short/reel/tiktok/long-form video or paste a URL. We score likelihood using competitor benchmarks, platform quality signals, and a combined model.
                                        </p>
                                    </div>

                                    <div className="mx-auto mt-8 max-w-2xl rounded-2xl border border-[#e0e0e0] bg-[#fafafa] p-4">
                                        <p className="text-xs uppercase tracking-wide text-[#777]">Current Input</p>
                                        <p className="mt-2 break-all text-sm text-[#252525]">
                                            {sourceMode === "url"
                                                ? (videoUrl.trim() || "No URL added yet")
                                                : (videoFile?.name || "No file selected yet")}
                                        </p>
                                    </div>

                                    {progressMessage && (
                                        <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#cbdacb] bg-[#edf7ed] px-4 py-3 text-sm text-[#2f5a2f]">
                                            {progressMessage}
                                        </div>
                                    )}
                                    {error && (
                                        <div className="mx-auto mt-4 max-w-2xl rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-4 py-3 text-sm text-[#7f3a3a]">
                                            {error}
                                        </div>
                                    )}
                                </div>

                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
                                    <div className="mb-2 flex items-center justify-between">
                                        <label className="text-xs font-semibold uppercase tracking-wide text-[#626262]">
                                            Retention Points (Optional)
                                        </label>
                                        <span className="text-[11px] text-[#888]">Guided rows + advanced JSON fallback</span>
                                    </div>

                                    <div className="space-y-2">
                                        {retentionRows.map((row, idx) => (
                                            <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                                                <input
                                                    value={row.time}
                                                    onChange={(e) => updateRetentionRow(idx, "time", e.target.value)}
                                                    placeholder="time (s)"
                                                    className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                                    disabled={running}
                                                />
                                                <input
                                                    value={row.retention}
                                                    onChange={(e) => updateRetentionRow(idx, "retention", e.target.value)}
                                                    placeholder="retention (%)"
                                                    className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                                    disabled={running}
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => removeRetentionRow(idx)}
                                                    className="rounded-xl border border-[#d9d9d9] bg-[#f3f3f3] px-3 py-2 text-xs text-[#555]"
                                                    disabled={running}
                                                >
                                                    Remove
                                                </button>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="mt-3 flex justify-between">
                                        <button
                                            type="button"
                                            onClick={addRetentionRow}
                                            className="rounded-xl border border-[#d9d9d9] bg-[#f7f7f7] px-3 py-1.5 text-xs text-[#444]"
                                            disabled={running}
                                        >
                                            Add retention row
                                        </button>
                                        <span className="text-[11px] text-[#888]">time + retention</span>
                                    </div>

                                    <div className="mt-3">
                                        <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[#777]">
                                            Advanced JSON Override (Optional)
                                        </label>
                                        <textarea
                                            value={retentionJson}
                                            onChange={(e) => setRetentionJson(e.target.value)}
                                            placeholder='[{"time": 0, "retention": 100}, {"time": 5, "retention": 78}]'
                                            className="min-h-[90px] w-full rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 font-mono text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
                                    <div className="mb-2 flex items-center justify-between">
                                        <label className="text-xs font-semibold uppercase tracking-wide text-[#626262]">
                                            Platform Metrics (Optional)
                                        </label>
                                        <span className="text-[11px] text-[#888]">Guided fields + advanced JSON fallback</span>
                                    </div>
                                    <div className="grid gap-2 md:grid-cols-2">
                                        <input
                                            value={guidedMetrics.views}
                                            onChange={(e) => updateGuidedMetric("views", e.target.value)}
                                            placeholder="views"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.likes}
                                            onChange={(e) => updateGuidedMetric("likes", e.target.value)}
                                            placeholder="likes"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.comments}
                                            onChange={(e) => updateGuidedMetric("comments", e.target.value)}
                                            placeholder="comments"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.shares}
                                            onChange={(e) => updateGuidedMetric("shares", e.target.value)}
                                            placeholder="shares"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.saves}
                                            onChange={(e) => updateGuidedMetric("saves", e.target.value)}
                                            placeholder="saves"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.avg_view_duration_s}
                                            onChange={(e) => updateGuidedMetric("avg_view_duration_s", e.target.value)}
                                            placeholder="avg_view_duration_s"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                        <input
                                            value={guidedMetrics.ctr}
                                            onChange={(e) => updateGuidedMetric("ctr", e.target.value)}
                                            placeholder="ctr (e.g. 0.067)"
                                            className="rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none md:col-span-2"
                                            disabled={running}
                                        />
                                    </div>

                                    <div className="mt-3">
                                        <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[#777]">
                                            Advanced JSON Override (Optional)
                                        </label>
                                        <textarea
                                            value={platformMetricsJson}
                                            onChange={(e) => setPlatformMetricsJson(e.target.value)}
                                            placeholder='{"views": 120000, "likes": 4600, "comments": 320, "shares": 210, "saves": 580, "avg_view_duration_s": 27.5, "ctr": 0.068}'
                                            className="min-h-[90px] w-full rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 font-mono text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                            disabled={running}
                                        />
                                    </div>
                                </div>
                            </div>
                        </section>

                        <aside className="bg-[#f8f8f8] p-4 xl:border-l xl:border-[#dfdfdf]">
                            <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <div className="mb-3 flex items-center justify-between">
                                    <h2 className="text-sm font-semibold text-[#222]">Scoring Stack</h2>
                                    <span className="rounded-full border border-[#dcdcdc] bg-[#f5f5f5] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[#666]">MVP</span>
                                </div>

                                <div className="space-y-2">
                                    <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-3">
                                        <p className="text-xs text-[#757575]">Competitor Metrics</p>
                                        <p className="mt-1 text-lg font-semibold text-[#232323]">Benchmark Match</p>
                                    </div>
                                    <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-3">
                                        <p className="text-xs text-[#757575]">Platform Metrics</p>
                                        <p className="mt-1 text-lg font-semibold text-[#232323]">Hook + Pacing Quality</p>
                                    </div>
                                    <div className="rounded-xl border border-[#ececec] bg-[#fafafa] p-3">
                                        <p className="text-xs text-[#757575]">Combined Metrics</p>
                                        <p className="mt-1 text-lg font-semibold text-[#232323]">Final Likelihood</p>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Run Audit</h3>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Uses competitor history + your video signals to produce three score sets.
                                </p>
                                <button
                                    type="submit"
                                    disabled={running}
                                    className="w-full rounded-xl bg-[#1f1f1f] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#111] disabled:cursor-not-allowed disabled:bg-[#9e9e9e]"
                                >
                                    {running ? "Running Audit..." : "Run Audit"}
                                </button>
                            </div>

                            <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Model Notes</h3>
                                <ul className="space-y-1 text-xs text-[#666]">
                                    <li>• Format-aware: shorts vs long videos</li>
                                    <li>• Pulls tracked competitor baselines</li>
                                    <li>• Falls back safely if data is missing</li>
                                </ul>
                            </div>
                        </aside>
                    </div>
                </div>
            </form>
        </div>
    );
}
