"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
    createMediaDownloadJob,
    FlowStateResponse,
    getMediaDownloadJobStatus,
    getResearchItem,
    getAuditStatus,
    getCurrentUserId,
    MediaDownloadJobStatus,
    RetentionPoint,
    runMultimodalAudit,
    syncYouTubeSession,
    uploadAuditVideo,
} from "@/lib/api";
import { StudioAppShell } from "@/components/app-shell";
import { FlowStepper } from "@/components/flow-stepper";
import { WorkflowAssistant } from "@/components/workflow-assistant";

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

function inferPlatformFromUrl(url: string): "youtube" | "instagram" | "tiktok" | null {
    const normalized = url.trim().toLowerCase();
    if (!normalized) {
        return null;
    }
    if (normalized.includes("instagram.com")) {
        return "instagram";
    }
    if (normalized.includes("tiktok.com")) {
        return "tiktok";
    }
    if (normalized.includes("youtube.com") || normalized.includes("youtu.be")) {
        return "youtube";
    }
    return null;
}

export default function NewAuditPage() {
    const router = useRouter();
    const { data: session } = useSession();
    const [sourceMode, setSourceMode] = useState<"url" | "upload">("url");
    const [selectedPlatform, setSelectedPlatform] = useState<"youtube" | "instagram" | "tiktok">("youtube");
    const [videoUrl, setVideoUrl] = useState("");
    const [videoFile, setVideoFile] = useState<File | null>(null);
    const [retentionJson, setRetentionJson] = useState("");
    const [platformMetricsJson, setPlatformMetricsJson] = useState("");
    const [showAdvancedRetentionJson, setShowAdvancedRetentionJson] = useState(false);
    const [showAdvancedPlatformMetricsJson, setShowAdvancedPlatformMetricsJson] = useState(false);
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
    const [researchItemId, setResearchItemId] = useState("");
    const [researchSourceSummary, setResearchSourceSummary] = useState<string | null>(null);
    const [loadingResearchSource, setLoadingResearchSource] = useState(false);
    const [downloadingMedia, setDownloadingMedia] = useState(false);
    const [mediaJob, setMediaJob] = useState<{
        jobId: string;
        sourceUrl: string;
        status: string;
        progress: number;
        uploadId?: string | null;
        errorMessage?: string | null;
    } | null>(null);
    const [resolvedUploadId, setResolvedUploadId] = useState<string | null>(null);
    const [appliedFlowPlatformDefault, setAppliedFlowPlatformDefault] = useState(false);
    const [entryContext, setEntryContext] = useState<string | null>(null);
    const sourceReady = sourceMode === "url" ? videoUrl.trim().length > 0 : Boolean(videoFile || resolvedUploadId);
    const canRunAudit = sourceReady && !running;
    const runAuditDisabledReason = sourceReady
        ? null
        : sourceMode === "url"
            ? "Add a source URL to run audit."
            : "Upload a file or finish URL download to run audit.";

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

    async function loadResearchSource(itemId: string) {
        const normalized = itemId.trim();
        if (!normalized) {
            return;
        }
        setLoadingResearchSource(true);
        setError(null);
        try {
            const item = await getResearchItem(normalized);
            setResearchItemId(normalized);
            setResearchSourceSummary(
                item.title ||
                    item.caption ||
                    item.url ||
                    `Imported ${item.platform} item`
            );
            setSelectedPlatform(item.platform);
            if (item.url) {
                setSourceMode("url");
                setVideoUrl(item.url);
                setMediaJob(null);
                setResolvedUploadId(null);
            }
        } catch (err: any) {
            setError(err.message || "Could not load research item");
        } finally {
            setLoadingResearchSource(false);
        }
    }

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        const params = new URLSearchParams(window.location.search);
        const sourceItemId = params.get("source_item_id");
        const platformParam = params.get("platform");
        const sourceModeParam = params.get("source_mode");
        const sourceContext = params.get("source_context");
        if (platformParam === "youtube" || platformParam === "instagram" || platformParam === "tiktok") {
            setSelectedPlatform(platformParam);
        }
        if (sourceModeParam === "url" || sourceModeParam === "upload") {
            setSourceMode(sourceModeParam);
        }
        if (sourceContext) {
            setEntryContext(sourceContext);
        }
        if (sourceItemId) {
            setResearchItemId(sourceItemId);
            void loadResearchSource(sourceItemId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (sourceMode !== "url") {
            return;
        }
        const inferred = inferPlatformFromUrl(videoUrl);
        if (inferred && selectedPlatform === "youtube" && inferred !== "youtube") {
            setSelectedPlatform(inferred);
        }
    }, [sourceMode, videoUrl, selectedPlatform]);

    useEffect(() => {
        if (sourceMode !== "url") {
            return;
        }
        const normalized = videoUrl.trim();
        if (!normalized) {
            if (mediaJob || resolvedUploadId) {
                setMediaJob(null);
                setResolvedUploadId(null);
            }
            return;
        }
        if (mediaJob && mediaJob.sourceUrl !== normalized) {
            setMediaJob(null);
            setResolvedUploadId(null);
        }
    }, [mediaJob, resolvedUploadId, sourceMode, videoUrl]);

    const applyFlowPlatformDefault = useCallback((state: FlowStateResponse) => {
        if (appliedFlowPlatformDefault) {
            return;
        }
        const preferred = state.preferred_platform;
        if (!preferred || preferred === "youtube") {
            setAppliedFlowPlatformDefault(true);
            return;
        }
        if (researchItemId.trim() || videoUrl.trim() || resolvedUploadId || sourceMode === "upload") {
            setAppliedFlowPlatformDefault(true);
            return;
        }
        setSelectedPlatform((prev) => (prev === "youtube" ? preferred : prev));
        setAppliedFlowPlatformDefault(true);
    }, [appliedFlowPlatformDefault, researchItemId, resolvedUploadId, sourceMode, videoUrl]);

    async function pollMediaDownloadJob(
        jobId: string,
        userId: string,
        sourceUrl: string
    ): Promise<MediaDownloadJobStatus> {
        let pollDelayMs = 1800;
        const maxAttempts = 120;
        let latest: MediaDownloadJobStatus | null = null;
        for (let i = 0; i < maxAttempts; i++) {
            await sleep(pollDelayMs);
            const status = await getMediaDownloadJobStatus(jobId, userId);
            latest = status;
            setMediaJob({
                jobId,
                sourceUrl,
                status: status.status,
                progress: status.progress || 0,
                uploadId: status.upload_id || null,
                errorMessage: status.error_message || null,
            });
            setProgressMessage(`Media download: ${status.status} (${status.progress}%)`);

            if (status.status === "completed") {
                if (!status.upload_id) {
                    throw new Error("Media download completed without an upload source id.");
                }
                return status;
            }
            if (status.status === "failed") {
                throw new Error(status.error_message || "Media download failed.");
            }
            pollDelayMs = Math.min(Math.round(pollDelayMs * 1.12), 4500);
        }

        throw new Error(
            latest?.error_message
                || "Media download is still processing. You can continue with direct URL or local upload mode."
        );
    }

    async function handleDownloadUrlToUpload() {
        const normalized = videoUrl.trim();
        if (!normalized) {
            setError("Enter a URL before starting media download.");
            return;
        }
        setError(null);
        setProgressMessage("Creating media download job...");
        setDownloadingMedia(true);
        try {
            const userId = await resolveUserId();
            if (!userId) {
                throw new Error("Connect a platform before downloading media so your session can be authenticated.");
            }
            const inferred = inferPlatformFromUrl(normalized);
            const platform = inferred || selectedPlatform;
            const job = await createMediaDownloadJob({
                platform,
                source_url: normalized,
                user_id: userId,
            });
            setMediaJob({
                jobId: job.job_id,
                sourceUrl: normalized,
                status: job.status,
                progress: job.progress || 0,
                uploadId: job.upload_id || null,
                errorMessage: job.error_message || null,
            });
            setProgressMessage("Media download job queued...");

            const completed = await pollMediaDownloadJob(job.job_id, userId, normalized);
            setResolvedUploadId(completed.upload_id || null);
            setSourceMode("upload");
            setVideoFile(null);
            setProgressMessage("Media download completed. Using downloaded upload source for audit.");
        } catch (err: any) {
            const message = err?.message || "Failed to download URL media.";
            if (String(message).toLowerCase().includes("disabled")) {
                setError(`${message} You can still run URL mode directly or switch to local file upload.`);
            } else {
                setError(message);
            }
        } finally {
            setDownloadingMedia(false);
        }
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
            setError("Enter a video URL to run the audit.");
            return;
        }
        if (sourceMode === "upload" && !videoFile && !resolvedUploadId) {
            setError("Select a video file or use a completed downloaded upload source.");
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
            if (!userId) {
                throw new Error("Connect a platform before running audits so your session can be authenticated.");
            }
            let run;
            if (sourceMode === "upload") {
                let uploadId = resolvedUploadId;
                if (videoFile) {
                    setProgressMessage("Uploading video...");
                    const upload = await uploadAuditVideo(videoFile as File, userId);
                    uploadId = upload.upload_id;
                    setResolvedUploadId(upload.upload_id);
                } else {
                    setProgressMessage("Using downloaded upload source...");
                }
                if (!uploadId) {
                    throw new Error("Upload source is missing. Re-upload or re-run URL download.");
                }
                run = await runMultimodalAudit({
                    source_mode: "upload",
                    platform: selectedPlatform,
                    upload_id: uploadId,
                    retention_points: retentionPoints,
                    platform_metrics: platformMetrics,
                    user_id: userId,
                });
            } else {
                const inferred = inferPlatformFromUrl(videoUrl.trim());
                run = await runMultimodalAudit({
                    source_mode: "url",
                    platform: inferred || selectedPlatform,
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
        <StudioAppShell
            rightSlot={
                <span className="rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666]">
                    Audit Workspace
                </span>
            }
        >
            <form onSubmit={handleRunAudit}>
                <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
                        <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                            <h2 className="mb-1 text-sm font-semibold text-[#222]">Source Setup</h2>
                            <p className="mb-4 text-xs text-[#777]">Start with a URL or upload your clip.</p>
                            <div className="mb-4 space-y-1">
                                <label className="text-xs font-medium text-[#4f4f4f]">Platform</label>
                                <select
                                    value={selectedPlatform}
                                    onChange={(e) => setSelectedPlatform(e.target.value as "youtube" | "instagram" | "tiktok")}
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-sm text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={running}
                                >
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <p className="text-[11px] text-[#7b7b7b]">
                                    Required for upload mode; URL mode can auto-infer from link domain.
                                </p>
                            </div>

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
                                        placeholder="https://www.youtube.com/watch?v=... / instagram.com/reel/... / tiktok.com/..."
                                        className="w-full rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                        disabled={running}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => void handleDownloadUrlToUpload()}
                                        disabled={running || downloadingMedia || !videoUrl.trim()}
                                        className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-xs font-medium text-[#333] hover:bg-[#efefef] disabled:opacity-50"
                                    >
                                        {downloadingMedia ? "Downloading..." : "Download URL to Upload Mode"}
                                    </button>
                                    {(() => {
                                        const inferred = inferPlatformFromUrl(videoUrl);
                                        if (!inferred || inferred === selectedPlatform) {
                                            return null;
                                        }
                                        return (
                                            <p className="text-[11px] text-[#8a6438]">
                                                URL suggests {inferred}. Current platform is {selectedPlatform}; you can keep or switch.
                                            </p>
                                        );
                                    })()}
                                    {mediaJob && mediaJob.sourceUrl === videoUrl.trim() && (
                                        <div className="rounded-xl border border-[#e1e1e1] bg-[#fafafa] px-3 py-2 text-[11px] text-[#666]">
                                            <p>Media job: {mediaJob.jobId.slice(0, 8)}... • {mediaJob.status} ({mediaJob.progress}%)</p>
                                            {mediaJob.uploadId && (
                                                <p className="mt-1 text-[#2f5a2f]">Ready upload id: {mediaJob.uploadId}</p>
                                            )}
                                            {mediaJob.errorMessage && (
                                                <p className="mt-1 text-[#7f3a3a]">{mediaJob.errorMessage}</p>
                                            )}
                                        </div>
                                    )}
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
                                    {resolvedUploadId && !videoFile && (
                                        <div className="rounded-xl border border-[#d9e6d9] bg-[#eef8ee] px-3 py-2 text-[11px] text-[#2f5a2f]">
                                            Using downloaded source upload id: {resolvedUploadId}
                                        </div>
                                    )}
                                </div>
                            )}

                            <div className="mt-5 space-y-2 rounded-2xl border border-[#dfdfdf] bg-white p-3">
                                <p className="text-xs font-semibold uppercase tracking-wide text-[#666]">Use Research Item</p>
                                <div className="flex items-center gap-2">
                                    <input
                                        value={researchItemId}
                                        onChange={(e) => setResearchItemId(e.target.value)}
                                        placeholder="Research item id"
                                        className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                        disabled={running || loadingResearchSource}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => void loadResearchSource(researchItemId)}
                                        disabled={running || loadingResearchSource || !researchItemId.trim()}
                                        className="rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-xs text-[#444] hover:bg-[#efefef] disabled:opacity-50"
                                    >
                                        {loadingResearchSource ? "Loading..." : "Load"}
                                    </button>
                                </div>
                                {researchSourceSummary && (
                                    <p className="text-[11px] text-[#6d6d6d]">{researchSourceSummary}</p>
                                )}
                            </div>

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
                            <div className="mx-auto flex max-w-4xl flex-col gap-5">
                                <FlowStepper />
                                <WorkflowAssistant context="audit" onFlowState={applyFlowPlatformDefault} />
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
                                        {entryContext && (
                                            <p className="mt-2 text-[11px] text-[#6b6b6b]">
                                                Launched from {entryContext.replaceAll("_", " ")}.
                                            </p>
                                        )}
                                    </div>

                                    <div className="mx-auto mt-8 max-w-2xl rounded-2xl border border-[#e0e0e0] bg-[#fafafa] p-4">
                                        <p className="text-xs uppercase tracking-wide text-[#777]">Current Input</p>
                                        <p className="mt-2 break-all text-sm text-[#252525]">
                                            {sourceMode === "url"
                                                ? (videoUrl.trim() || "No URL added yet")
                                                : (videoFile?.name || (resolvedUploadId ? `Downloaded source (${resolvedUploadId})` : "No file selected yet"))}
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
                                        <button
                                            type="button"
                                            onClick={() => setShowAdvancedRetentionJson((prev) => !prev)}
                                            className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1 text-[11px] text-[#555] hover:bg-[#efefef]"
                                            disabled={running}
                                        >
                                            {showAdvancedRetentionJson ? "Hide Advanced JSON" : "Show Advanced JSON"}
                                        </button>
                                        {showAdvancedRetentionJson && (
                                            <>
                                                <label className="mb-1 mt-2 block text-[11px] font-medium uppercase tracking-wide text-[#777]">
                                                    Advanced JSON Override (Optional)
                                                </label>
                                                <textarea
                                                    value={retentionJson}
                                                    onChange={(e) => setRetentionJson(e.target.value)}
                                                    placeholder='[{"time": 0, "retention": 100}, {"time": 5, "retention": 78}]'
                                                    className="min-h-[90px] w-full rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 font-mono text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                                    disabled={running}
                                                />
                                            </>
                                        )}
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
                                        <button
                                            type="button"
                                            onClick={() => setShowAdvancedPlatformMetricsJson((prev) => !prev)}
                                            className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1 text-[11px] text-[#555] hover:bg-[#efefef]"
                                            disabled={running}
                                        >
                                            {showAdvancedPlatformMetricsJson ? "Hide Advanced JSON" : "Show Advanced JSON"}
                                        </button>
                                        {showAdvancedPlatformMetricsJson && (
                                            <>
                                                <label className="mb-1 mt-2 block text-[11px] font-medium uppercase tracking-wide text-[#777]">
                                                    Advanced JSON Override (Optional)
                                                </label>
                                                <textarea
                                                    value={platformMetricsJson}
                                                    onChange={(e) => setPlatformMetricsJson(e.target.value)}
                                                    placeholder='{"views": 120000, "likes": 4600, "comments": 320, "shares": 210, "saves": 580, "avg_view_duration_s": 27.5, "ctr": 0.068}'
                                                    className="min-h-[90px] w-full rounded-xl border border-[#d9d9d9] bg-[#fbfbfb] px-3 py-2 font-mono text-xs text-[#242424] placeholder:text-[#9f9f9f] focus:border-[#bdbdbd] focus:outline-none"
                                                    disabled={running}
                                                />
                                            </>
                                        )}
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
                                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Run Readiness</h3>
                                <div className="space-y-1 text-xs text-[#5f5f5f]">
                                    <p>{sourceReady ? "✓" : "•"} Source ready ({sourceMode === "url" ? "URL mode" : "Upload mode"})</p>
                                    <p>✓ Platform selected ({selectedPlatform})</p>
                                    <p>• Metrics optional (add when available for stronger confidence)</p>
                                </div>
                                {runAuditDisabledReason && (
                                    <p className="mt-2 text-[11px] text-[#8a5b2f]">{runAuditDisabledReason}</p>
                                )}
                            </div>

                            <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Run Audit</h3>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Uses competitor history + your video signals to produce three score sets.
                                </p>
                                <button
                                    type="submit"
                                    disabled={!canRunAudit}
                                    className="w-full rounded-xl bg-[#1f1f1f] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#111] disabled:cursor-not-allowed disabled:bg-[#9e9e9e]"
                                >
                                    {running ? "Running Audit..." : canRunAudit ? "Run Audit" : "Add Source to Run"}
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
            </form>
        </StudioAppShell>
    );
}
