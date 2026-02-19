"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
    captureResearchItem,
    createResearchCollection,
    createDraftSnapshot,
    DraftSnapshot,
    exportResearchCollection,
    generateOptimizerVariants,
    getApiBaseUrl,
    getCreditSummary,
    getCurrentUserId,
    getOutcomesSummary,
    getResearchItem,
    ingestOutcomeMetrics,
    importResearchCsv,
    importResearchUrl,
    listDraftSnapshots,
    listResearchCollections,
    moveResearchItem,
    OptimizerRescoreResponse,
    ResearchCollection,
    ResearchItem,
    rescoreOptimizerDraft,
    ScriptVariantResult,
    searchResearchItems,
    syncYouTubeSession,
    updateResearchItemMeta,
} from "@/lib/api";
import { useSession } from "next-auth/react";

type ResearchTab = "discover" | "collections" | "compare";

function formatNumber(value: number | undefined) {
    if (!value || Number.isNaN(value)) {
        return "0";
    }
    return value.toLocaleString();
}

function platformLabel(value: string) {
    if (value === "youtube") return "YouTube";
    if (value === "instagram") return "Instagram";
    if (value === "tiktok") return "TikTok";
    return value;
}

export default function ResearchPage() {
    const { data: session } = useSession();

    const [activeTab, setActiveTab] = useState<ResearchTab>("discover");

    const [importUrlValue, setImportUrlValue] = useState("");
    const [importPlatform, setImportPlatform] = useState<"youtube" | "instagram" | "tiktok">("youtube");
    const [importingUrl, setImportingUrl] = useState(false);
    const [csvFile, setCsvFile] = useState<File | null>(null);
    const [importingCsv, setImportingCsv] = useState(false);
    const [captureUrlValue, setCaptureUrlValue] = useState("");
    const [captureTitleValue, setCaptureTitleValue] = useState("");
    const [captureViewsValue, setCaptureViewsValue] = useState("");

    const [searchPlatform, setSearchPlatform] = useState<"" | "youtube" | "instagram" | "tiktok">("");
    const [searchQuery, setSearchQuery] = useState("");
    const [searchTimeframe, setSearchTimeframe] = useState<"24h" | "7d" | "30d" | "90d" | "all">("all");
    const [searchCollectionId, setSearchCollectionId] = useState<string>("");
    const [searchTags, setSearchTags] = useState<string>("");
    const [includeArchived, setIncludeArchived] = useState(false);
    const [pinnedOnly, setPinnedOnly] = useState(false);
    const [searchSortBy, setSearchSortBy] = useState<"created_at" | "posted_at" | "views" | "likes" | "comments" | "shares" | "saves">("created_at");
    const [searchDirection, setSearchDirection] = useState<"asc" | "desc">("desc");
    const [searchPage, setSearchPage] = useState(1);
    const [searchLimit] = useState(12);

    const [searching, setSearching] = useState(false);
    const [searchError, setSearchError] = useState<string | null>(null);
    const [items, setItems] = useState<ResearchItem[]>([]);
    const [totalCount, setTotalCount] = useState(0);
    const [hasMore, setHasMore] = useState(false);
    const [lastCharge, setLastCharge] = useState<{ charged: number; balance_after: number } | null>(null);

    const [collections, setCollections] = useState<ResearchCollection[]>([]);
    const [loadingCollections, setLoadingCollections] = useState(false);
    const [newCollectionName, setNewCollectionName] = useState("");
    const [newCollectionPlatform, setNewCollectionPlatform] = useState<"mixed" | "youtube" | "instagram" | "tiktok">("mixed");
    const [creatingCollection, setCreatingCollection] = useState(false);

    const [selectedIds, setSelectedIds] = useState<string[]>([]);

    const [scriptPlatform, setScriptPlatform] = useState<"youtube" | "instagram" | "tiktok">("youtube");
    const [scriptTopic, setScriptTopic] = useState("");
    const [scriptAudience, setScriptAudience] = useState("solo creators in my niche");
    const [scriptObjective, setScriptObjective] = useState("higher retention and more shares");
    const [scriptTone, setScriptTone] = useState("bold");
    const [scriptDuration, setScriptDuration] = useState<number>(45);
    const [scriptHookStyle, setScriptHookStyle] = useState("outcome_proof");
    const [scriptCtaStyle, setScriptCtaStyle] = useState("comment_prompt");
    const [scriptPacingDensity, setScriptPacingDensity] = useState("dense");

    const [generatingVariants, setGeneratingVariants] = useState(false);
    const [variantError, setVariantError] = useState<string | null>(null);
    const [variants, setVariants] = useState<ScriptVariantResult[]>([]);
    const [generationMeta, setGenerationMeta] = useState<{
        provider: string;
        model: string;
        used_fallback: boolean;
        fallback_reason?: string | null;
    } | null>(null);
    const [selectedSourceItemId, setSelectedSourceItemId] = useState<string | undefined>(undefined);
    const [sourceContextNote, setSourceContextNote] = useState<string | undefined>(undefined);
    const [selectedVariantId, setSelectedVariantId] = useState<string | undefined>(undefined);
    const [baselineDetectorRankings, setBaselineDetectorRankings] = useState<ScriptVariantResult["detector_rankings"]>([]);

    const [draftText, setDraftText] = useState("");
    const [baselineScore, setBaselineScore] = useState<number | undefined>(undefined);
    const [rescoring, setRescoring] = useState(false);
    const [rescoreError, setRescoreError] = useState<string | null>(null);
    const [rescoreResult, setRescoreResult] = useState<OptimizerRescoreResponse | null>(null);
    const [savingIteration, setSavingIteration] = useState(false);
    const [saveIterationError, setSaveIterationError] = useState<string | null>(null);
    const [draftHistory, setDraftHistory] = useState<DraftSnapshot[]>([]);
    const [loadingDraftHistory, setLoadingDraftHistory] = useState(false);

    const [creditsBalance, setCreditsBalance] = useState<number>(0);
    const [capturingItem, setCapturingItem] = useState(false);
    const [outcomeMetricsInput, setOutcomeMetricsInput] = useState({
        views: "",
        likes: "",
        comments: "",
        shares: "",
        saves: "",
        avg_view_duration_s: "",
    });
    const [postingOutcome, setPostingOutcome] = useState(false);
    const [outcomeMessage, setOutcomeMessage] = useState<string | null>(null);

    const selectedItems = useMemo(() => {
        const selectedSet = new Set(selectedIds);
        return items.filter((item) => selectedSet.has(item.item_id));
    }, [items, selectedIds]);

    async function resolveUserId() {
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

        throw new Error("Connect YouTube first so the backend can scope research to your account.");
    }

    async function refreshCredits() {
        try {
            await resolveUserId();
            const summary = await getCreditSummary();
            setCreditsBalance(summary.balance || 0);
        } catch {
            // Ignore credit refresh failures in UI boot.
        }
    }

    async function refreshCollections() {
        setLoadingCollections(true);
        try {
            await resolveUserId();
            const rows = await listResearchCollections();
            setCollections(rows);
        } catch {
            setCollections([]);
        } finally {
            setLoadingCollections(false);
        }
    }

    async function refreshDraftHistory(platform?: "youtube" | "instagram" | "tiktok") {
        setLoadingDraftHistory(true);
        try {
            await resolveUserId();
            const response = await listDraftSnapshots({ platform: platform || scriptPlatform, limit: 20 });
            setDraftHistory(response.items || []);
        } catch {
            setDraftHistory([]);
        } finally {
            setLoadingDraftHistory(false);
        }
    }

    async function runSearch(page = 1) {
        setSearching(true);
        setSearchError(null);
        try {
            await resolveUserId();
            const response = await searchResearchItems({
                platform: searchPlatform || undefined,
                query: searchQuery,
                collection_id: searchCollectionId || undefined,
                include_archived: includeArchived,
                pinned_only: pinnedOnly,
                tags: searchTags
                    .split(",")
                    .map((tag) => tag.trim())
                    .filter(Boolean),
                sort_by: searchSortBy,
                sort_direction: searchDirection,
                timeframe: searchTimeframe,
                page,
                limit: searchLimit,
            });
            setItems(response.items || []);
            setTotalCount(response.total_count || 0);
            setHasMore(!!response.has_more);
            setSearchPage(response.page || page);
            if (response.credits) {
                setLastCharge(response.credits);
                setCreditsBalance(response.credits.balance_after);
            }
        } catch (err: any) {
            setSearchError(err.message || "Search failed");
            setItems([]);
            setTotalCount(0);
            setHasMore(false);
        } finally {
            setSearching(false);
        }
    }

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        const params = new URLSearchParams(window.location.search);
        const mode = params.get("mode");
        const topic = params.get("topic");
        const sourceItemId = params.get("source_item_id");
        const sourceContext = params.get("source_context");

        if (mode === "optimizer") {
            setActiveTab("discover");
        }
        if (topic) {
            setScriptTopic(topic);
        }
        if (sourceContext) {
            setSourceContextNote(sourceContext);
        }
        if (sourceItemId) {
            setSelectedSourceItemId(sourceItemId);
            (async () => {
                try {
                    const item = await getResearchItem(sourceItemId);
                    const seededTopic = item.title || item.caption || scriptTopic;
                    if (seededTopic) {
                        setScriptTopic(seededTopic);
                    }
                } catch {
                    // Ignore prefill failures.
                }
            })();
        }

        (async () => {
            try {
                await resolveUserId();
                await Promise.all([runSearch(1), refreshCollections(), refreshCredits(), refreshDraftHistory()]);
            } catch (err: any) {
                setSearchError(err.message || "Please connect YouTube first.");
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        void refreshDraftHistory(scriptPlatform);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scriptPlatform]);

    async function handleImportUrl(e: React.FormEvent) {
        e.preventDefault();
        if (!importUrlValue.trim()) {
            return;
        }
        setImportingUrl(true);
        setSearchError(null);
        try {
            await resolveUserId();
            const imported = await importResearchUrl({
                platform: importPlatform,
                url: importUrlValue.trim(),
            });
            setImportUrlValue("");
            setScriptTopic(imported.title || imported.caption || scriptTopic);
            setSelectedSourceItemId(imported.item_id);
            await Promise.all([runSearch(1), refreshCollections()]);
        } catch (err: any) {
            setSearchError(err.message || "URL import failed");
        } finally {
            setImportingUrl(false);
        }
    }

    async function handleImportCsv(e: React.FormEvent) {
        e.preventDefault();
        if (!csvFile) {
            return;
        }
        setImportingCsv(true);
        setSearchError(null);
        try {
            await resolveUserId();
            await importResearchCsv(csvFile, { platform: importPlatform });
            setCsvFile(null);
            await Promise.all([runSearch(1), refreshCollections()]);
        } catch (err: any) {
            setSearchError(err.message || "CSV import failed");
        } finally {
            setImportingCsv(false);
        }
    }

    async function handleCaptureForm(e: React.FormEvent) {
        e.preventDefault();
        if (!captureUrlValue.trim()) {
            return;
        }
        setCapturingItem(true);
        setSearchError(null);
        try {
            await resolveUserId();
            await captureResearchItem({
                platform: importPlatform,
                url: captureUrlValue.trim(),
                title: captureTitleValue.trim() || undefined,
                views: Number(captureViewsValue || 0),
            });
            setCaptureUrlValue("");
            setCaptureTitleValue("");
            setCaptureViewsValue("");
            await Promise.all([runSearch(1), refreshCollections()]);
        } catch (err: any) {
            setSearchError(err.message || "Capture failed");
        } finally {
            setCapturingItem(false);
        }
    }

    async function handleExport(collectionId: string, format: "csv" | "json") {
        try {
            await resolveUserId();
            const response = await exportResearchCollection({ collectionId, format });
            const link = `${getApiBaseUrl()}${response.signed_url}`;
            window.open(link, "_blank", "noopener,noreferrer");
        } catch (err: any) {
            setSearchError(err.message || "Export failed");
        }
    }

    async function handleCreateCollection(e: React.FormEvent) {
        e.preventDefault();
        if (!newCollectionName.trim()) {
            return;
        }
        setCreatingCollection(true);
        try {
            await resolveUserId();
            await createResearchCollection({
                name: newCollectionName.trim(),
                platform: newCollectionPlatform,
            });
            setNewCollectionName("");
            await refreshCollections();
        } catch (err: any) {
            setSearchError(err.message || "Could not create collection");
        } finally {
            setCreatingCollection(false);
        }
    }

    async function handleQuickCapture(item: ResearchItem) {
        setCapturingItem(true);
        try {
            await resolveUserId();
            await captureResearchItem({
                platform: item.platform,
                url: item.url || undefined,
                external_id: item.external_id || undefined,
                creator_handle: item.creator_handle || undefined,
                creator_display_name: item.creator_display_name || undefined,
                title: item.title || undefined,
                caption: item.caption || undefined,
                views: item.metrics.views,
                likes: item.metrics.likes,
                comments: item.metrics.comments,
                shares: item.metrics.shares,
                saves: item.metrics.saves,
                media_meta: item.media_meta,
                published_at: item.published_at || undefined,
            });
            await Promise.all([runSearch(1), refreshCollections()]);
        } catch (err: any) {
            setSearchError(err.message || "Capture failed");
        } finally {
            setCapturingItem(false);
        }
    }

    async function handleMoveItem(itemId: string, collectionId: string) {
        try {
            await resolveUserId();
            await moveResearchItem({ itemId, collectionId });
            await runSearch(searchPage);
        } catch (err: any) {
            setSearchError(err.message || "Move failed");
        }
    }

    async function handleUpdateItemMeta(
        itemId: string,
        update: { pinned?: boolean; archived?: boolean; tags?: string[] }
    ) {
        try {
            await resolveUserId();
            await updateResearchItemMeta({
                itemId,
                pinned: update.pinned,
                archived: update.archived,
                tags: update.tags,
            });
            await runSearch(searchPage);
        } catch (err: any) {
            setSearchError(err.message || "Item update failed");
        }
    }

    function toggleCompareItem(itemId: string) {
        setSelectedIds((prev) => {
            if (prev.includes(itemId)) {
                return prev.filter((id) => id !== itemId);
            }
            if (prev.length >= 3) {
                return [...prev.slice(1), itemId];
            }
            return [...prev, itemId];
        });
    }

    async function handleGenerateVariants(e: React.FormEvent) {
        e.preventDefault();
        if (!scriptTopic.trim()) {
            setVariantError("Enter a topic first.");
            return;
        }
        setGeneratingVariants(true);
        setVariantError(null);
        setSaveIterationError(null);
        try {
            await resolveUserId();
            const response = await generateOptimizerVariants({
                platform: scriptPlatform,
                topic: scriptTopic.trim(),
                audience: scriptAudience,
                objective: scriptObjective,
                tone: scriptTone,
                duration_s: scriptDuration,
                source_item_id: selectedSourceItemId,
                source_context: sourceContextNote,
                generation_mode: "ai_first_fallback",
                constraints: {
                    platform: scriptPlatform,
                    duration_s: scriptDuration,
                    tone: scriptTone,
                    hook_style: scriptHookStyle,
                    cta_style: scriptCtaStyle,
                    pacing_density: scriptPacingDensity,
                },
            });
            setVariants(response.variants || []);
            setGenerationMeta(response.generation || null);
            if (response.variants?.[0]) {
                setDraftText(response.variants[0].script_text || response.variants[0].script);
                setBaselineScore(response.variants[0].score_breakdown.combined);
                setSelectedVariantId(response.variants[0].id);
                setBaselineDetectorRankings(response.variants[0].detector_rankings || []);
            }
            if (response.credits) {
                setCreditsBalance(response.credits.balance_after);
                setLastCharge(response.credits);
            }
        } catch (err: any) {
            setVariantError(err.message || "Variant generation failed");
            setVariants([]);
            setGenerationMeta(null);
        } finally {
            setGeneratingVariants(false);
        }
    }

    async function handleRescoreDraft() {
        if (!draftText.trim()) {
            setRescoreError("Draft cannot be empty.");
            return;
        }
        setRescoring(true);
        setRescoreError(null);
        try {
            await resolveUserId();
            const response = await rescoreOptimizerDraft({
                platform: scriptPlatform,
                script_text: draftText,
                duration_s: scriptDuration,
                baseline_score: baselineScore,
                baseline_detector_rankings: baselineDetectorRankings,
            });
            setRescoreResult(response);
            setSaveIterationError(null);
        } catch (err: any) {
            setRescoreError(err.message || "Rescore failed");
            setRescoreResult(null);
        } finally {
            setRescoring(false);
        }
    }

    async function handleSaveIteration() {
        if (!draftText.trim()) {
            setSaveIterationError("Draft cannot be empty.");
            return;
        }
        if (!rescoreResult) {
            setSaveIterationError("Re-score the draft before saving an iteration.");
            return;
        }
        setSavingIteration(true);
        setSaveIterationError(null);
        try {
            await resolveUserId();
            await createDraftSnapshot({
                platform: scriptPlatform,
                source_item_id: selectedSourceItemId,
                variant_id: selectedVariantId,
                script_text: draftText,
                baseline_score: baselineScore,
                rescored_score: rescoreResult.score_breakdown.combined,
                delta_score: rescoreResult.score_breakdown.delta_from_baseline ?? undefined,
                detector_rankings: rescoreResult.detector_rankings,
                next_actions: rescoreResult.next_actions,
                line_level_edits: rescoreResult.line_level_edits,
                score_breakdown: rescoreResult.score_breakdown,
                rescore_output: rescoreResult,
            });
            await refreshDraftHistory(scriptPlatform);
        } catch (err: any) {
            setSaveIterationError(err.message || "Failed to save iteration");
        } finally {
            setSavingIteration(false);
        }
    }

    function restoreSnapshot(snapshot: DraftSnapshot) {
        setDraftText(snapshot.script_text);
        setBaselineScore(snapshot.baseline_score ?? undefined);
        setSelectedVariantId(snapshot.variant_id || undefined);
        setSelectedSourceItemId(snapshot.source_item_id || undefined);
        setBaselineDetectorRankings(snapshot.detector_rankings || []);
        setRescoreResult({
            score_breakdown: {
                platform_metrics: 0,
                competitor_metrics: 0,
                historical_metrics: 0,
                combined: snapshot.rescored_score,
                confidence: "medium",
                weights: {},
                delta_from_baseline: snapshot.delta_score ?? null,
            },
            detector_rankings: snapshot.detector_rankings || [],
            next_actions: snapshot.next_actions || [],
            line_level_edits: snapshot.line_level_edits || [],
            improvement_diff: {
                combined: {
                    before: snapshot.baseline_score ?? null,
                    after: snapshot.rescored_score,
                    delta: snapshot.delta_score ?? null,
                },
                detectors: [],
            },
            signals: {},
            format_type: scriptDuration <= 60 ? "short_form" : "long_form",
            duration_seconds: scriptDuration,
        });
        setSaveIterationError(null);
        setRescoreError(null);
    }

    async function handlePostOutcomeFromResearch() {
        const latestSnapshot = draftHistory[0];
        if (!latestSnapshot) {
            setOutcomeMessage("Save an iteration first.");
            return;
        }
        setPostingOutcome(true);
        setOutcomeMessage(null);
        try {
            await resolveUserId();
            const response = await ingestOutcomeMetrics({
                platform: scriptPlatform,
                draft_snapshot_id: latestSnapshot.id,
                actual_metrics: {
                    views: Number(outcomeMetricsInput.views || 0),
                    likes: Number(outcomeMetricsInput.likes || 0),
                    comments: Number(outcomeMetricsInput.comments || 0),
                    shares: Number(outcomeMetricsInput.shares || 0),
                    saves: Number(outcomeMetricsInput.saves || 0),
                    avg_view_duration_s: Number(outcomeMetricsInput.avg_view_duration_s || 0),
                },
                posted_at: new Date().toISOString(),
                predicted_score: latestSnapshot.rescored_score,
            });
            const summary = await getOutcomesSummary({ platform: scriptPlatform });
            setOutcomeMessage(
                `Outcome saved. Delta ${response.calibration_delta ?? "n/a"} • Confidence ${summary.confidence || "low"}`
            );
        } catch (err: any) {
            setOutcomeMessage(err.message || "Failed to save outcome");
        } finally {
            setPostingOutcome(false);
        }
    }

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <header className="flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="text-lg font-bold text-[#1f1f1f]">SPC Studio</Link>
                        <nav className="hidden items-center gap-4 text-sm text-[#6b6b6b] md:flex">
                            <Link href="/dashboard" className="hover:text-[#151515]">Dashboard</Link>
                            <Link href="/competitors" className="hover:text-[#151515]">Competitors</Link>
                            <Link href="/research" className="font-medium text-[#1b1b1b]">Research</Link>
                            <Link href="/audit/new" className="hover:text-[#151515]">Audit Workspace</Link>
                        </nav>
                    </div>
                    <div className="rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666]">
                        Credits: {creditsBalance}
                    </div>
                </header>

                <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[300px_minmax(0,1fr)_360px]">
                    <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h2 className="mb-2 text-sm font-semibold text-[#222]">Import Research</h2>
                            <form onSubmit={handleImportUrl} className="space-y-2">
                                <select
                                    value={importPlatform}
                                    onChange={(e) => setImportPlatform(e.target.value as "youtube" | "instagram" | "tiktok")}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                >
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <input
                                    value={importUrlValue}
                                    onChange={(e) => setImportUrlValue(e.target.value)}
                                    placeholder="Paste post/reel/video URL"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <button
                                    type="submit"
                                    disabled={importingUrl || !importUrlValue.trim()}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {importingUrl ? "Importing..." : "Import URL"}
                                </button>
                            </form>
                            <form onSubmit={handleImportCsv} className="mt-3 space-y-2">
                                <input
                                    type="file"
                                    accept=".csv,text/csv"
                                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222]"
                                />
                                <button
                                    type="submit"
                                    disabled={importingCsv || !csvFile}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {importingCsv ? "Importing..." : "Import CSV"}
                                </button>
                            </form>
                            <form onSubmit={handleCaptureForm} className="mt-3 space-y-2">
                                <input
                                    value={captureUrlValue}
                                    onChange={(e) => setCaptureUrlValue(e.target.value)}
                                    placeholder="Browser-captured URL"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <input
                                    value={captureTitleValue}
                                    onChange={(e) => setCaptureTitleValue(e.target.value)}
                                    placeholder="Optional title"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <input
                                    value={captureViewsValue}
                                    onChange={(e) => setCaptureViewsValue(e.target.value)}
                                    placeholder="Optional views"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <button
                                    type="submit"
                                    disabled={capturingItem || !captureUrlValue.trim()}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {capturingItem ? "Capturing..." : "Capture Item"}
                                </button>
                            </form>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-sm font-semibold text-[#222]">Search Filters</h3>
                            <div className="space-y-2">
                                <input
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Query by caption/title/creator"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <select
                                    value={searchPlatform}
                                    onChange={(e) => setSearchPlatform(e.target.value as "" | "youtube" | "instagram" | "tiktok")}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                >
                                    <option value="">All Platforms</option>
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <select
                                    value={searchCollectionId}
                                    onChange={(e) => setSearchCollectionId(e.target.value)}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                >
                                    <option value="">All Collections</option>
                                    {collections.map((collection) => (
                                        <option key={collection.id} value={collection.id}>
                                            {collection.name}
                                        </option>
                                    ))}
                                </select>
                                <input
                                    value={searchTags}
                                    onChange={(e) => setSearchTags(e.target.value)}
                                    placeholder="Tags (comma separated)"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <div className="grid grid-cols-2 gap-2">
                                    <select
                                        value={searchTimeframe}
                                        onChange={(e) => setSearchTimeframe(e.target.value as "24h" | "7d" | "30d" | "90d" | "all")}
                                        className="rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="all">All Time</option>
                                        <option value="90d">90d</option>
                                        <option value="30d">30d</option>
                                        <option value="7d">7d</option>
                                        <option value="24h">24h</option>
                                    </select>
                                    <select
                                        value={searchSortBy}
                                        onChange={(e) => setSearchSortBy(e.target.value as any)}
                                        className="rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="created_at">Newest</option>
                                        <option value="views">Views</option>
                                        <option value="likes">Likes</option>
                                        <option value="comments">Comments</option>
                                        <option value="shares">Shares</option>
                                        <option value="saves">Saves</option>
                                    </select>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setSearchDirection("desc");
                                            void runSearch(1);
                                        }}
                                        className={`rounded-lg border px-2 py-2 text-xs ${searchDirection === "desc" ? "border-[#b9b9b9] bg-white text-[#222]" : "border-[#dedede] bg-[#f6f6f6] text-[#555]"}`}
                                    >
                                        High to Low
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setSearchDirection("asc");
                                            void runSearch(1);
                                        }}
                                        className={`rounded-lg border px-2 py-2 text-xs ${searchDirection === "asc" ? "border-[#b9b9b9] bg-white text-[#222]" : "border-[#dedede] bg-[#f6f6f6] text-[#555]"}`}
                                    >
                                        Low to High
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setPinnedOnly((prev) => !prev)}
                                        className={`rounded-lg border px-2 py-2 text-xs ${pinnedOnly ? "border-[#b9b9b9] bg-white text-[#222]" : "border-[#dedede] bg-[#f6f6f6] text-[#555]"}`}
                                    >
                                        {pinnedOnly ? "Pinned only" : "All pinned states"}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setIncludeArchived((prev) => !prev)}
                                        className={`rounded-lg border px-2 py-2 text-xs ${includeArchived ? "border-[#b9b9b9] bg-white text-[#222]" : "border-[#dedede] bg-[#f6f6f6] text-[#555]"}`}
                                    >
                                        {includeArchived ? "Including archived" : "Hide archived"}
                                    </button>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => void runSearch(1)}
                                    disabled={searching}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {searching ? "Searching..." : "Run Search"}
                                </button>
                            </div>
                        </div>

                        {lastCharge && (
                            <div className="mt-4 rounded-xl border border-[#dcdcdc] bg-white px-3 py-2 text-xs text-[#666]">
                                Search charged {lastCharge.charged} credit(s) • Balance {lastCharge.balance_after}
                            </div>
                        )}
                    </aside>

                    <section className="border-b border-[#dfdfdf] bg-[#f2f2f2] px-4 py-4 md:px-6 xl:border-b-0">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                            <h1 className="text-2xl font-bold text-[#1f1f1f] md:text-3xl">Research Studio</h1>
                            <div className="grid grid-cols-3 gap-2 rounded-xl border border-[#d9d9d9] bg-[#efefef] p-1">
                                <button
                                    type="button"
                                    onClick={() => setActiveTab("discover")}
                                    className={`rounded-lg px-3 py-1.5 text-xs ${activeTab === "discover" ? "bg-white text-[#1d1d1d]" : "text-[#666]"}`}
                                >
                                    Discover
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setActiveTab("collections")}
                                    className={`rounded-lg px-3 py-1.5 text-xs ${activeTab === "collections" ? "bg-white text-[#1d1d1d]" : "text-[#666]"}`}
                                >
                                    Collections
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setActiveTab("compare")}
                                    className={`rounded-lg px-3 py-1.5 text-xs ${activeTab === "compare" ? "bg-white text-[#1d1d1d]" : "text-[#666]"}`}
                                >
                                    Compare
                                </button>
                            </div>
                        </div>

                        {searchError && (
                            <div className="mb-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                {searchError}
                            </div>
                        )}

                        {activeTab === "discover" && (
                            <div className="space-y-3">
                                <p className="text-xs text-[#6d6d6d]">{formatNumber(totalCount)} items found.</p>
                                {items.map((item) => {
                                    const selected = selectedIds.includes(item.item_id);
                                    return (
                                        <div key={item.item_id} className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                            <div className="mb-2 flex items-start justify-between gap-2">
                                                <div>
                                                    <p className="text-[11px] uppercase tracking-wide text-[#7a7a7a]">{platformLabel(item.platform)} • {item.source_type}</p>
                                                    <p className="text-sm font-semibold text-[#232323]">{item.title || item.caption || item.url || "Untitled item"}</p>
                                                    <p className="text-xs text-[#7a7a7a]">{item.creator_handle || item.creator_display_name || "Unknown creator"}</p>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => toggleCompareItem(item.item_id)}
                                                        className={`rounded-lg border px-2 py-1 text-[11px] ${selected ? "border-[#b8b8b8] bg-[#efefef] text-[#222]" : "border-[#d9d9d9] bg-white text-[#555]"}`}
                                                    >
                                                        {selected ? "Selected" : "Compare"}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            const topic = item.title || item.caption || "Content angle";
                                                            setScriptTopic(topic.slice(0, 180));
                                                            setSelectedSourceItemId(item.item_id);
                                                            setSourceContextNote(item.creator_handle || item.creator_display_name || undefined);
                                                            setVariants([]);
                                                            setGenerationMeta(null);
                                                            setRescoreResult(null);
                                                            if (item.platform === "instagram" || item.platform === "tiktok" || item.platform === "youtube") {
                                                                setScriptPlatform(item.platform);
                                                            }
                                                        }}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                    >
                                                        Use in Script Studio
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => void handleQuickCapture(item)}
                                                        disabled={capturingItem}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                    >
                                                        Capture
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="grid gap-2 text-xs text-[#666] sm:grid-cols-5">
                                                <p>Views: {formatNumber(item.metrics.views)}</p>
                                                <p>Likes: {formatNumber(item.metrics.likes)}</p>
                                                <p>Comments: {formatNumber(item.metrics.comments)}</p>
                                                <p>Shares: {formatNumber(item.metrics.shares)}</p>
                                                <p>Saves: {formatNumber(item.metrics.saves)}</p>
                                            </div>
                                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                                <select
                                                    value={item.collection_id || ""}
                                                    onChange={(e) => {
                                                        if (!e.target.value) return;
                                                        void handleMoveItem(item.item_id, e.target.value);
                                                    }}
                                                    className="rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                                >
                                                    <option value="">Move to collection...</option>
                                                    {collections.map((collection) => (
                                                        <option key={collection.id} value={collection.id}>
                                                            {collection.name}
                                                        </option>
                                                    ))}
                                                </select>
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => void handleUpdateItemMeta(item.item_id, { pinned: !item.pinned })}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                    >
                                                        {item.pinned ? "Unpin" : "Pin"}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => void handleUpdateItemMeta(item.item_id, { archived: !item.archived })}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                    >
                                                        {item.archived ? "Unarchive" : "Archive"}
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="mt-2">
                                                <input
                                                    defaultValue={(item.tags || []).join(", ")}
                                                    onBlur={(e) => {
                                                        const tags = e.target.value
                                                            .split(",")
                                                            .map((tag) => tag.trim())
                                                            .filter(Boolean);
                                                        void handleUpdateItemMeta(item.item_id, { tags });
                                                    }}
                                                    placeholder="tags, separated, by commas"
                                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-1 text-[11px] text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                />
                                            </div>
                                        </div>
                                    );
                                })}

                                {items.length === 0 && !searching && (
                                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-8 text-center text-sm text-[#666]">
                                        No research items yet. Import URLs or CSV to start.
                                    </div>
                                )}

                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => void runSearch(Math.max(1, searchPage - 1))}
                                        disabled={searchPage <= 1 || searching}
                                        className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#555] disabled:opacity-50"
                                    >
                                        Previous
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => void runSearch(searchPage + 1)}
                                        disabled={!hasMore || searching}
                                        className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#555] disabled:opacity-50"
                                    >
                                        Next
                                    </button>
                                </div>
                            </div>
                        )}

                        {activeTab === "collections" && (
                            <div className="space-y-3">
                                {loadingCollections && <p className="text-xs text-[#777]">Loading collections...</p>}
                                {!loadingCollections && collections.length === 0 && (
                                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-8 text-center text-sm text-[#666]">
                                        Collections will appear after your first import.
                                    </div>
                                )}
                                {collections.map((collection) => (
                                    <div key={collection.id} className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                        <div className="flex items-center justify-between gap-2">
                                            <div>
                                                <p className="text-sm font-semibold text-[#232323]">{collection.name}</p>
                                                <p className="text-xs text-[#777]">{collection.platform || "mixed"} • {collection.is_system ? "system" : "custom"}</p>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => void handleExport(collection.id, "csv")}
                                                    className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                >
                                                    Export CSV
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => void handleExport(collection.id, "json")}
                                                    className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555]"
                                                >
                                                    Export JSON
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {activeTab === "compare" && (
                            <div className="space-y-3">
                                <p className="text-xs text-[#6d6d6d]">Select up to 3 items from Discover to compare side-by-side.</p>
                                {selectedItems.length === 0 && (
                                    <div className="rounded-2xl border border-[#dcdcdc] bg-white p-8 text-center text-sm text-[#666]">
                                        No items selected.
                                    </div>
                                )}
                                {selectedItems.length > 0 && (
                                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                                        {selectedItems.map((item) => (
                                            <div key={item.item_id} className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                                <p className="text-[11px] uppercase tracking-wide text-[#7a7a7a]">{platformLabel(item.platform)}</p>
                                                <p className="text-sm font-semibold text-[#232323]">{item.title || item.caption || "Untitled"}</p>
                                                <div className="mt-2 space-y-1 text-xs text-[#666]">
                                                    <p>Views: {formatNumber(item.metrics.views)}</p>
                                                    <p>Likes: {formatNumber(item.metrics.likes)}</p>
                                                    <p>Comments: {formatNumber(item.metrics.comments)}</p>
                                                    <p>Shares: {formatNumber(item.metrics.shares)}</p>
                                                    <p>Saves: {formatNumber(item.metrics.saves)}</p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </section>

                    <aside className="bg-[#f8f8f8] p-4 xl:border-l xl:border-[#dfdfdf]">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h2 className="mb-2 text-sm font-semibold text-[#222]">Script Optimizer</h2>
                            <p className="mb-3 text-xs text-[#6d6d6d]">Research to Generate 3 variants to Edit and Re-score</p>
                            {(selectedSourceItemId || sourceContextNote) && (
                                <p className="mb-3 text-[11px] text-[#6d6d6d]">
                                    Source context: {sourceContextNote || selectedSourceItemId}
                                </p>
                            )}

                            <form onSubmit={handleGenerateVariants} className="space-y-2">
                                <input
                                    value={scriptTopic}
                                    onChange={(e) => setScriptTopic(e.target.value)}
                                    placeholder="Topic"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <div className="grid grid-cols-2 gap-2">
                                    <select
                                        value={scriptPlatform}
                                        onChange={(e) => setScriptPlatform(e.target.value as "youtube" | "instagram" | "tiktok")}
                                        className="rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="youtube">YouTube</option>
                                        <option value="instagram">Instagram</option>
                                        <option value="tiktok">TikTok</option>
                                    </select>
                                    <input
                                        type="number"
                                        min={15}
                                        max={900}
                                        value={scriptDuration}
                                        onChange={(e) => setScriptDuration(Number(e.target.value) || 45)}
                                        className="rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <input
                                    value={scriptAudience}
                                    onChange={(e) => setScriptAudience(e.target.value)}
                                    placeholder="Audience"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <input
                                    value={scriptObjective}
                                    onChange={(e) => setScriptObjective(e.target.value)}
                                    placeholder="Objective"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <select
                                    value={scriptTone}
                                    onChange={(e) => setScriptTone(e.target.value)}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                >
                                    <option value="bold">Bold</option>
                                    <option value="expert">Expert</option>
                                    <option value="conversational">Conversational</option>
                                </select>
                                <div className="grid grid-cols-1 gap-2">
                                    <select
                                        value={scriptHookStyle}
                                        onChange={(e) => setScriptHookStyle(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="outcome_proof">Hook: Outcome + Proof</option>
                                        <option value="curiosity_gap">Hook: Curiosity Gap</option>
                                        <option value="contrarian_take">Hook: Contrarian</option>
                                    </select>
                                    <select
                                        value={scriptCtaStyle}
                                        onChange={(e) => setScriptCtaStyle(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="comment_prompt">CTA: Comment Prompt</option>
                                        <option value="save_share">CTA: Save/Share</option>
                                        <option value="follow_subscribe">CTA: Follow/Subscribe</option>
                                    </select>
                                    <select
                                        value={scriptPacingDensity}
                                        onChange={(e) => setScriptPacingDensity(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="dense">Pacing: Dense</option>
                                        <option value="balanced">Pacing: Balanced</option>
                                        <option value="slow_clear">Pacing: Slow + Clear</option>
                                    </select>
                                </div>
                                <button
                                    type="submit"
                                    disabled={generatingVariants}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {generatingVariants ? "Generating..." : "Generate 3 Variants"}
                                </button>
                            </form>

                            {variantError && (
                                <div className="mt-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                    {variantError}
                                </div>
                            )}

                            {generationMeta && (
                                <div className={`mt-3 rounded-xl border px-3 py-2 text-[11px] ${
                                    generationMeta.used_fallback
                                        ? "border-[#e7d8bb] bg-[#fff8ed] text-[#7b5e35]"
                                        : "border-[#d5e6d8] bg-[#f2fbf3] text-[#2f6b39]"
                                }`}>
                                    {generationMeta.used_fallback ? "Fallback Script" : "AI Generated"} • {generationMeta.provider} • {generationMeta.model}
                                    {generationMeta.fallback_reason ? ` • ${generationMeta.fallback_reason}` : ""}
                                </div>
                            )}

                            {variants.length > 0 && (
                                <div className="mt-3 space-y-2">
                                    {variants.map((variant) => (
                                        <button
                                            key={variant.id}
                                            type="button"
                                            onClick={() => {
                                                setDraftText(variant.script_text || variant.script);
                                                setBaselineScore(variant.score_breakdown.combined);
                                                setSelectedVariantId(variant.id);
                                                setBaselineDetectorRankings(variant.detector_rankings || []);
                                                setRescoreResult(null);
                                            }}
                                            className="w-full rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3 text-left hover:bg-[#f2f2f2]"
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <p className="text-xs font-semibold text-[#222]">#{variant.rank} {variant.label}</p>
                                                <span className={`rounded-full border px-2 py-0.5 text-[10px] ${
                                                    generationMeta?.used_fallback
                                                        ? "border-[#e7d8bb] bg-[#fff8ed] text-[#7b5e35]"
                                                        : "border-[#d5e6d8] bg-[#f2fbf3] text-[#2f6b39]"
                                                }`}>
                                                    {generationMeta?.used_fallback ? "Fallback" : "AI Generated"}
                                                </span>
                                            </div>
                                            <p className="text-[11px] text-[#666]">Score {Math.round(variant.score_breakdown.combined)} • Lift +{variant.expected_lift_points}</p>
                                        </button>
                                    ))}
                                </div>
                            )}

                            <div className="mt-3">
                                <textarea
                                    value={draftText}
                                    onChange={(e) => setDraftText(e.target.value)}
                                    placeholder="Edit your draft here, then re-score"
                                    className="h-40 w-full rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <button
                                    type="button"
                                    onClick={() => void handleRescoreDraft()}
                                    disabled={rescoring || !draftText.trim()}
                                    className="mt-2 w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {rescoring ? "Rescoring..." : "Re-score Edited Draft"}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => void handleSaveIteration()}
                                    disabled={savingIteration || !rescoreResult}
                                    className="mt-2 w-full rounded-xl border border-[#d9d9d9] bg-white px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#f4f4f4] disabled:opacity-50"
                                >
                                    {savingIteration ? "Saving..." : "Save Iteration"}
                                </button>
                            </div>

                            {rescoreError && (
                                <div className="mt-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                    {rescoreError}
                                </div>
                            )}

                            {saveIterationError && (
                                <div className="mt-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                    {saveIterationError}
                                </div>
                            )}

                            {rescoreResult && (
                                <div className="mt-3 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                    <p className="text-xs font-semibold text-[#222]">
                                        Combined: {Math.round(rescoreResult.score_breakdown.combined)} ({rescoreResult.score_breakdown.confidence})
                                    </p>
                                    {typeof rescoreResult.score_breakdown.delta_from_baseline === "number" && (
                                        <p className="text-[11px] text-[#666]">
                                            Delta vs baseline: {rescoreResult.score_breakdown.delta_from_baseline > 0 ? "+" : ""}
                                            {rescoreResult.score_breakdown.delta_from_baseline}
                                        </p>
                                    )}
                                    {rescoreResult.next_actions?.length > 0 && (
                                        <ul className="mt-2 space-y-1 text-[11px] text-[#555]">
                                            {rescoreResult.next_actions.slice(0, 3).map((action: any, idx: number) => (
                                                <li key={`${action.detector_key}-${idx}`}>• {action.title}: {action.why}</li>
                                            ))}
                                        </ul>
                                    )}
                                    {rescoreResult.line_level_edits?.length > 0 && (
                                        <ul className="mt-2 space-y-1 text-[11px] text-[#555]">
                                            {rescoreResult.line_level_edits.slice(0, 2).map((edit, idx) => (
                                                <li key={`${edit.detector_key}-${idx}`}>
                                                    • Line {edit.line_number} ({edit.detector_label}): {edit.suggested_line}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}

                            <div className="mt-4 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                    <p className="text-xs font-semibold text-[#222]">Iteration History</p>
                                    <button
                                        type="button"
                                        onClick={() => void refreshDraftHistory(scriptPlatform)}
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#555]"
                                    >
                                        Refresh
                                    </button>
                                </div>
                                {loadingDraftHistory && <p className="text-[11px] text-[#666]">Loading history...</p>}
                                {!loadingDraftHistory && draftHistory.length === 0 && (
                                    <p className="text-[11px] text-[#666]">No saved iterations yet.</p>
                                )}
                                {!loadingDraftHistory && draftHistory.length > 0 && (
                                    <div className="space-y-2">
                                        {draftHistory.slice(0, 6).map((snapshot) => (
                                            <div key={snapshot.id} className="rounded-lg border border-[#e1e1e1] bg-white p-2">
                                                <p className="text-[11px] text-[#555]">
                                                    Score {Math.round(snapshot.rescored_score)}{" "}
                                                    {typeof snapshot.delta_score === "number"
                                                        ? `(${snapshot.delta_score > 0 ? "+" : ""}${snapshot.delta_score})`
                                                        : ""}
                                                </p>
                                                <p className="text-[10px] text-[#777]">
                                                    {snapshot.created_at ? new Date(snapshot.created_at).toLocaleString() : "Saved draft"}
                                                </p>
                                                <button
                                                    type="button"
                                                    onClick={() => restoreSnapshot(snapshot)}
                                                    className="mt-1 rounded-md border border-[#d8d8d8] bg-[#f9f9f9] px-2 py-1 text-[10px] text-[#444]"
                                                >
                                                    Restore
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <div className="mt-4 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                <p className="text-xs font-semibold text-[#222]">Post Result From Latest Iteration</p>
                                <p className="mt-1 text-[11px] text-[#666]">
                                    Submit actual outcomes to improve confidence and calibration for future scores.
                                </p>
                                <div className="mt-2 grid grid-cols-2 gap-2">
                                    <input
                                        value={outcomeMetricsInput.views}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, views: e.target.value }))}
                                        placeholder="views"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        value={outcomeMetricsInput.likes}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, likes: e.target.value }))}
                                        placeholder="likes"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        value={outcomeMetricsInput.comments}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, comments: e.target.value }))}
                                        placeholder="comments"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        value={outcomeMetricsInput.shares}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, shares: e.target.value }))}
                                        placeholder="shares"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        value={outcomeMetricsInput.saves}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, saves: e.target.value }))}
                                        placeholder="saves"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        value={outcomeMetricsInput.avg_view_duration_s}
                                        onChange={(e) => setOutcomeMetricsInput((prev) => ({ ...prev, avg_view_duration_s: e.target.value }))}
                                        placeholder="avg view duration s"
                                        className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <button
                                    type="button"
                                    onClick={() => void handlePostOutcomeFromResearch()}
                                    disabled={postingOutcome || draftHistory.length === 0}
                                    className="mt-2 w-full rounded-lg border border-[#d9d9d9] bg-white px-2 py-1.5 text-[11px] text-[#444] disabled:opacity-50"
                                >
                                    {postingOutcome ? "Saving..." : "Save Outcome"}
                                </button>
                                {outcomeMessage && (
                                    <p className="mt-2 text-[11px] text-[#555]">{outcomeMessage}</p>
                                )}
                            </div>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-sm font-semibold text-[#222]">Collections</h3>
                            <form onSubmit={handleCreateCollection} className="space-y-2">
                                <input
                                    value={newCollectionName}
                                    onChange={(e) => setNewCollectionName(e.target.value)}
                                    placeholder="New collection name"
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                />
                                <select
                                    value={newCollectionPlatform}
                                    onChange={(e) => setNewCollectionPlatform(e.target.value as "mixed" | "youtube" | "instagram" | "tiktok")}
                                    className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                >
                                    <option value="mixed">Mixed</option>
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <button
                                    type="submit"
                                    disabled={creatingCollection || !newCollectionName.trim()}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                >
                                    {creatingCollection ? "Creating..." : "Create Collection"}
                                </button>
                            </form>
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
