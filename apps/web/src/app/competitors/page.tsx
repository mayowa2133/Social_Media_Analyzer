"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
    addCompetitor,
    addManualCompetitor,
    buildSeriesCalendar,
    CompetitorAnalysisPlatform,
    BlueprintResult,
    CompetitorSuggestionSortBy,
    CompetitorSuggestionSortDirection,
    Competitor,
    discoverCompetitors,
    DiscoverCompetitorCandidate,
    getNextSeriesEpisode,
    generateSeriesPlan,
    generateViralScript,
    generateBlueprint,
    getCompetitorSeriesInsights,
    getCompetitors,
    importCompetitorsFromResearch,
    NextSeriesEpisodeResult,
    recommendCompetitors,
    RecommendedCompetitor,
    removeCompetitor,
    SeriesCalendarResult,
    SeriesIntelligence,
    SeriesPlanResult,
    ViralScriptResult,
} from "@/lib/api";
import { StudioAppShell } from "@/components/app-shell";
import { BlueprintDisplay } from "@/components/blueprint-display";
import { FlowStepper } from "@/components/flow-stepper";

function formatMetric(value: number): string {
    return value.toLocaleString();
}

function toChannelUrl(suggestion: RecommendedCompetitor): string {
    if (suggestion.custom_url) {
        const handle = suggestion.custom_url.startsWith("@")
            ? suggestion.custom_url
            : `@${suggestion.custom_url}`;
        return `https://www.youtube.com/${handle}`;
    }
    return `https://www.youtube.com/channel/${suggestion.channel_id}`;
}

const SUGGESTION_PAGE_SIZE = 8;
const PLATFORM_LABELS: Record<CompetitorAnalysisPlatform, string> = {
    youtube: "YouTube",
    instagram: "Instagram",
    tiktok: "TikTok",
};

export default function CompetitorsPage() {
    const [competitors, setCompetitors] = useState<Competitor[]>([]);
    const [channelUrl, setChannelUrl] = useState("");
    const [competitorPlatform, setCompetitorPlatform] = useState<"youtube" | "instagram" | "tiktok">("youtube");
    const [analysisPlatform, setAnalysisPlatform] = useState<CompetitorAnalysisPlatform>("youtube");
    const [loading, setLoading] = useState(true);
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [blueprint, setBlueprint] = useState<BlueprintResult | null>(null);
    const [generating, setGenerating] = useState(false);

    const [suggestionNiche, setSuggestionNiche] = useState("");
    const [suggestedCompetitors, setSuggestedCompetitors] = useState<RecommendedCompetitor[]>([]);
    const [suggesting, setSuggesting] = useState(false);
    const [suggestionError, setSuggestionError] = useState<string | null>(null);
    const [hasRequestedSuggestions, setHasRequestedSuggestions] = useState(false);
    const [suggestionPlatform, setSuggestionPlatform] = useState<"youtube" | "instagram" | "tiktok">("youtube");
    const [suggestionSortKey, setSuggestionSortKey] = useState<CompetitorSuggestionSortBy>("subscriber_count");
    const [sortDirection, setSortDirection] = useState<CompetitorSuggestionSortDirection>("desc");
    const [suggestionPage, setSuggestionPage] = useState(1);
    const [suggestionLimit, setSuggestionLimit] = useState(SUGGESTION_PAGE_SIZE);
    const [suggestionTotalCount, setSuggestionTotalCount] = useState(0);
    const [suggestionHasMore, setSuggestionHasMore] = useState(false);
    const [importingFromResearch, setImportingFromResearch] = useState(false);
    const [importNiche, setImportNiche] = useState("");
    const [importStatus, setImportStatus] = useState<string | null>(null);
    const [discoverQuery, setDiscoverQuery] = useState("");
    const [discovering, setDiscovering] = useState(false);
    const [discoverError, setDiscoverError] = useState<string | null>(null);
    const [discoveredCandidates, setDiscoveredCandidates] = useState<DiscoverCompetitorCandidate[]>([]);
    const [selectedDiscoverIds, setSelectedDiscoverIds] = useState<string[]>([]);
    const [importingDiscovered, setImportingDiscovered] = useState(false);
    const [discoverSourceFilter, setDiscoverSourceFilter] = useState<string>("all");
    const [discoverConfidenceFilter, setDiscoverConfidenceFilter] = useState<"all" | "low" | "medium" | "high">("all");
    const [showAdvancedImportTools, setShowAdvancedImportTools] = useState(false);
    const [showAdvancedDiscoveryTools, setShowAdvancedDiscoveryTools] = useState(false);

    const [seriesInsights, setSeriesInsights] = useState<SeriesIntelligence | null>(null);
    const [loadingSeries, setLoadingSeries] = useState(false);
    const [seriesError, setSeriesError] = useState<string | null>(null);

    const [seriesMode, setSeriesMode] = useState<"scratch" | "competitor_template">("scratch");
    const [seriesNiche, setSeriesNiche] = useState("AI News");
    const [seriesAudience, setSeriesAudience] = useState("Founders and creators building with AI");
    const [seriesObjective, setSeriesObjective] = useState("increase shares and average view duration");
    const [seriesPlatform, setSeriesPlatform] = useState<"youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long">("youtube_shorts");
    const [seriesEpisodes, setSeriesEpisodes] = useState(5);
    const [seriesTemplateKey, setSeriesTemplateKey] = useState("");
    const [seriesPlan, setSeriesPlan] = useState<SeriesPlanResult | null>(null);
    const [planningSeries, setPlanningSeries] = useState(false);
    const [seriesPlanError, setSeriesPlanError] = useState<string | null>(null);
    const [calendarStartDate, setCalendarStartDate] = useState(() => new Date().toISOString().slice(0, 10));
    const [calendarCadenceDays, setCalendarCadenceDays] = useState(2);
    const [seriesCalendar, setSeriesCalendar] = useState<SeriesCalendarResult | null>(null);
    const [buildingCalendar, setBuildingCalendar] = useState(false);
    const [completedEpisodes, setCompletedEpisodes] = useState(0);
    const [nextEpisode, setNextEpisode] = useState<NextSeriesEpisodeResult | null>(null);
    const [generatingNextEpisode, setGeneratingNextEpisode] = useState(false);
    const [seriesExecutionError, setSeriesExecutionError] = useState<string | null>(null);

    const [scriptPlatform, setScriptPlatform] = useState<"youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long">("youtube_shorts");
    const [scriptTopic, setScriptTopic] = useState("AI News hook formulas");
    const [scriptAudience, setScriptAudience] = useState("Creators who want more reach");
    const [scriptObjective, setScriptObjective] = useState("higher retention and shares");
    const [scriptTone, setScriptTone] = useState<"bold" | "expert" | "conversational">("bold");
    const [scriptTemplateKey, setScriptTemplateKey] = useState("");
    const [scriptDuration, setScriptDuration] = useState<number | "">(45);
    const [scriptResult, setScriptResult] = useState<ViralScriptResult | null>(null);
    const [generatingScript, setGeneratingScript] = useState(false);
    const [scriptError, setScriptError] = useState<string | null>(null);

    useEffect(() => {
        fetchCompetitors();
    }, []);

    useEffect(() => {
        if (loading) {
            return;
        }
        if (competitors.some((item) => item.platform === analysisPlatform)) {
            void fetchSeriesInsights(analysisPlatform);
        } else {
            setSeriesInsights(null);
            setSeriesTemplateKey("");
            setScriptTemplateKey("");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [analysisPlatform]);

    useEffect(() => {
        if (!hasRequestedSuggestions || !suggestionNiche.trim()) {
            return;
        }
        setSuggestionPage(1);
        void fetchSuggestedCompetitors(suggestionNiche, 1);
    }, [suggestionSortKey, sortDirection, suggestionPlatform]);

    useEffect(() => {
        const candidates = seriesInsights?.series || blueprint?.series_intelligence?.series || [];
        if (candidates.length === 0) {
            setSeriesTemplateKey("");
            setScriptTemplateKey("");
            return;
        }
        const firstSeries = candidates[0];
        const firstKey = firstSeries.series_key_slug || firstSeries.series_key;
        if (!seriesTemplateKey) {
            setSeriesTemplateKey(firstKey);
        }
        if (!scriptTemplateKey) {
            setScriptTemplateKey(firstKey);
        }
    }, [seriesInsights, blueprint, seriesTemplateKey, scriptTemplateKey]);

    const filteredDiscoveredCandidates = useMemo(() => {
        return discoveredCandidates.filter((candidate) => {
            if (discoverSourceFilter !== "all") {
                const labels = candidate.source_labels || [];
                if (candidate.source !== discoverSourceFilter && !labels.includes(discoverSourceFilter)) {
                    return false;
                }
            }
            if (discoverConfidenceFilter !== "all") {
                if ((candidate.confidence_tier || "low") !== discoverConfidenceFilter) {
                    return false;
                }
            }
            return true;
        });
    }, [discoveredCandidates, discoverSourceFilter, discoverConfidenceFilter]);

    const selectedImportableCount = useMemo(() => {
        return discoveredCandidates.filter(
            (item) => selectedDiscoverIds.includes(item.external_id) && !item.already_tracked
        ).length;
    }, [discoveredCandidates, selectedDiscoverIds]);

    function hasPlatformCompetitor(platform: CompetitorAnalysisPlatform, rows: Competitor[]) {
        return rows.some((item) => item.platform === platform);
    }

    async function fetchCompetitors() {
        try {
            const comps = await getCompetitors();
            setCompetitors(comps);
            setError(null);
            if (hasPlatformCompetitor(analysisPlatform, comps)) {
                await fetchSeriesInsights(analysisPlatform);
            } else {
                setSeriesInsights(null);
                setSeriesTemplateKey("");
                setScriptTemplateKey("");
            }
        } catch (err) {
            setError("Could not connect to API. Make sure the backend is running.");
        } finally {
            setLoading(false);
        }
    }

    async function fetchSeriesInsights(platform: CompetitorAnalysisPlatform = analysisPlatform) {
        setLoadingSeries(true);
        setSeriesError(null);
        try {
            const response = await getCompetitorSeriesInsights(undefined, platform);
            setSeriesInsights(response);
        } catch (err: any) {
            setSeriesError(err.message || "Failed to load competitor series insights");
        } finally {
            setLoadingSeries(false);
        }
    }

    async function fetchSuggestedCompetitors(niche: string, page = 1) {
        const trimmed = niche.trim();
        if (!trimmed) {
            setSuggestionError("Enter a niche to find suggested competitors.");
            setSuggestedCompetitors([]);
            setHasRequestedSuggestions(false);
            setSuggestionPage(1);
            setSuggestionLimit(SUGGESTION_PAGE_SIZE);
            setSuggestionTotalCount(0);
            setSuggestionHasMore(false);
            return;
        }

        setSuggesting(true);
        setSuggestionError(null);
        setHasRequestedSuggestions(true);
        try {
            const response = await recommendCompetitors(trimmed, {
                platform: suggestionPlatform,
                limit: SUGGESTION_PAGE_SIZE,
                page,
                sortBy: suggestionSortKey,
                sortDirection,
            });
            setSuggestedCompetitors(response.recommendations);
            setSuggestionPage(response.page);
            setSuggestionLimit(response.limit);
            setSuggestionTotalCount(response.total_count);
            setSuggestionHasMore(response.has_more);
        } catch (err: any) {
            setSuggestionError(err.message || "Failed to fetch suggestions");
            setSuggestedCompetitors([]);
            setSuggestionTotalCount(0);
            setSuggestionHasMore(false);
        } finally {
            setSuggesting(false);
        }
    }

    async function handleAddCompetitor(e: React.FormEvent) {
        e.preventDefault();
        if (!channelUrl.trim()) return;

        setAdding(true);
        setError(null);

        try {
            const newCompetitor = competitorPlatform === "youtube"
                ? await addCompetitor(channelUrl)
                : await addManualCompetitor({
                    platform: competitorPlatform,
                    handle: channelUrl,
                });
            setCompetitors((prev) => [...prev, newCompetitor]);
            setChannelUrl("");

            const autoNiche = newCompetitor.title || channelUrl;
            setSuggestionNiche(autoNiche);
            setSuggestionPlatform(competitorPlatform);
            setSuggestionPage(1);
            await fetchSuggestedCompetitors(autoNiche, 1);
            if (newCompetitor.platform === analysisPlatform) {
                await fetchSeriesInsights(analysisPlatform);
            }
        } catch (err: any) {
            setError(err.message || "Failed to add competitor");
        } finally {
            setAdding(false);
        }
    }

    async function handleRemoveCompetitor(id: string) {
        try {
            await removeCompetitor(id);
            const nextCompetitors = competitors.filter((c) => c.id !== id);
            setCompetitors(nextCompetitors);
            if (hasPlatformCompetitor(analysisPlatform, nextCompetitors)) {
                await fetchSeriesInsights(analysisPlatform);
            } else {
                setSeriesInsights(null);
                setSeriesTemplateKey("");
                setScriptTemplateKey("");
            }
        } catch (err: any) {
            setError(err.message || "Failed to remove competitor");
        }
    }

    async function handleGenerateBlueprint() {
        setGenerating(true);
        setError(null);
        try {
            const result = await generateBlueprint(undefined, analysisPlatform);
            setBlueprint(result);
            if (result.series_intelligence) {
                setSeriesInsights(result.series_intelligence);
            }
        } catch (err: any) {
            setError(err.message || "Failed to generate blueprint");
        } finally {
            setGenerating(false);
        }
    }

    async function handleImportCompetitorsFromResearch() {
        if (analysisPlatform === "youtube") {
            setImportStatus("Use YouTube search recommendations or add channel URLs directly for YouTube.");
            return;
        }
        setImportingFromResearch(true);
        setImportStatus(null);
        try {
            const response = await importCompetitorsFromResearch({
                platform: analysisPlatform,
                niche: importNiche.trim() || undefined,
                minItemsPerCreator: 2,
                topN: 25,
            });
            setImportStatus(
                `Imported ${response.imported_count} competitors (${response.skipped_existing} already tracked, ${response.skipped_low_volume} low volume).`
            );
            await fetchCompetitors();
        } catch (err: any) {
            setImportStatus(err.message || "Failed to import competitors from research.");
        } finally {
            setImportingFromResearch(false);
        }
    }

    async function handleFindSuggestions(e: React.FormEvent) {
        e.preventDefault();
        setSuggestionPage(1);
        await fetchSuggestedCompetitors(suggestionNiche, 1);
    }

    async function handleDiscoverCompetitorCandidates(e: React.FormEvent) {
        e.preventDefault();
        if (analysisPlatform === "youtube") {
            setDiscoverError("Use niche suggestions for YouTube, or switch platform for hybrid discover.");
            return;
        }
        setDiscovering(true);
        setDiscoverError(null);
        try {
            const result = await discoverCompetitors({
                platform: analysisPlatform,
                query: discoverQuery.trim(),
                page: 1,
                limit: 20,
            });
            setDiscoveredCandidates(result.candidates);
            setSelectedDiscoverIds([]);
            setDiscoverSourceFilter("all");
            setDiscoverConfidenceFilter("all");
        } catch (err: any) {
            setDiscoverError(err.message || "Failed to discover competitors.");
            setDiscoveredCandidates([]);
        } finally {
            setDiscovering(false);
        }
    }

    function toggleDiscoveredSelection(externalId: string) {
        setSelectedDiscoverIds((prev) =>
            prev.includes(externalId)
                ? prev.filter((value) => value !== externalId)
                : [...prev, externalId]
        );
    }

    async function handleImportSelectedDiscovered() {
        if (analysisPlatform === "youtube") {
            return;
        }
        const selected = discoveredCandidates.filter((item) => selectedDiscoverIds.includes(item.external_id) && !item.already_tracked);
        if (selected.length === 0) {
            setDiscoverError("Select at least one untracked competitor.");
            return;
        }
        setImportingDiscovered(true);
        setDiscoverError(null);
        try {
            for (const candidate of selected) {
                await addManualCompetitor({
                    platform: analysisPlatform,
                    handle: candidate.handle || candidate.external_id,
                    display_name: candidate.display_name,
                    external_id: candidate.external_id,
                    subscriber_count: candidate.subscriber_count,
                    thumbnail_url: candidate.thumbnail_url,
                });
            }
            await fetchCompetitors();
            setDiscoveredCandidates((prev) =>
                prev.map((item) =>
                    selectedDiscoverIds.includes(item.external_id)
                        ? { ...item, already_tracked: true }
                        : item
                )
            );
            setSelectedDiscoverIds([]);
        } catch (err: any) {
            setDiscoverError(err.message || "Failed to import discovered competitors.");
        } finally {
            setImportingDiscovered(false);
        }
    }

    async function handleSuggestionPageChange(nextPage: number) {
        if (suggesting || nextPage < 1 || nextPage === suggestionPage) {
            return;
        }
        await fetchSuggestedCompetitors(suggestionNiche, nextPage);
    }

    async function handleAddSuggestedCompetitor(suggestion: RecommendedCompetitor) {
        setSuggestionError(null);
        try {
            const created = suggestionPlatform === "youtube"
                ? await addCompetitor(toChannelUrl(suggestion))
                : await addManualCompetitor({
                    platform: suggestionPlatform,
                    handle: suggestion.custom_url || suggestion.channel_id,
                    display_name: suggestion.title,
                    external_id: suggestion.channel_id,
                    subscriber_count: suggestion.subscriber_count,
                    thumbnail_url: suggestion.thumbnail_url,
                });
            setCompetitors((prev) => {
                const exists = prev.some((c) => c.channel_id === created.channel_id);
                return exists ? prev : [...prev, created];
            });
            setSuggestedCompetitors((prev) =>
                prev.map((item) =>
                    item.channel_id === suggestion.channel_id
                        ? { ...item, already_tracked: true }
                        : item
                )
            );
        } catch (err: any) {
            const message = err?.message || "Failed to add suggested competitor";
            if (String(message).toLowerCase().includes("already added")) {
                setSuggestedCompetitors((prev) =>
                    prev.map((item) =>
                        item.channel_id === suggestion.channel_id
                            ? { ...item, already_tracked: true }
                            : item
                    )
                );
                return;
            }
            setSuggestionError(message);
        }
    }

    async function handleGenerateSeriesPlan(e: React.FormEvent) {
        e.preventDefault();
        setSeriesPlanError(null);
        setSeriesExecutionError(null);
        setPlanningSeries(true);
        try {
            const selectedTemplate =
                seriesMode === "competitor_template"
                    ? (seriesTemplateKey || seriesInsights?.series?.[0]?.series_key_slug || "")
                    : undefined;
            const response = await generateSeriesPlan({
                mode: seriesMode,
                niche: seriesNiche.trim() || "creator growth",
                audience: seriesAudience.trim() || "creators in your niche",
                objective: seriesObjective.trim() || "increase views and retention",
                platform: seriesPlatform,
                episodes: seriesEpisodes,
                templateSeriesKey: selectedTemplate,
            });
            setSeriesPlan(response);
            if (response.source_template?.series_key && !seriesTemplateKey) {
                setSeriesTemplateKey(response.source_template.series_key);
            }
            setSeriesCalendar(null);
            setNextEpisode(null);
        } catch (err: any) {
            setSeriesPlanError(err.message || "Failed to generate series plan");
            setSeriesPlan(null);
        } finally {
            setPlanningSeries(false);
        }
    }

    async function handleBuildSeriesCalendar() {
        if (!seriesPlan) {
            setSeriesExecutionError("Generate a series plan first.");
            return;
        }
        setSeriesExecutionError(null);
        setBuildingCalendar(true);
        try {
            const response = await buildSeriesCalendar({
                seriesTitle: seriesPlan.series_title,
                platform: seriesPlan.platform,
                startDate: calendarStartDate,
                cadenceDays: calendarCadenceDays,
                episodes: seriesPlan.episodes,
            });
            setSeriesCalendar(response);
        } catch (err: any) {
            setSeriesExecutionError(err.message || "Failed to build series calendar");
            setSeriesCalendar(null);
        } finally {
            setBuildingCalendar(false);
        }
    }

    async function handleGenerateNextEpisode() {
        const seriesTitle = seriesPlan?.series_title || seriesRows[0]?.series_key;
        if (!seriesTitle) {
            setSeriesExecutionError("Need a series plan or detected series first.");
            return;
        }
        setSeriesExecutionError(null);
        setGeneratingNextEpisode(true);
        try {
            const response = await getNextSeriesEpisode({
                seriesTitle,
                platform: seriesPlan?.platform || seriesPlatform,
                completedEpisodes,
                objective: seriesObjective,
                audience: seriesAudience,
            });
            setNextEpisode(response);
        } catch (err: any) {
            setSeriesExecutionError(err.message || "Failed to generate next episode");
            setNextEpisode(null);
        } finally {
            setGeneratingNextEpisode(false);
        }
    }

    async function handleGenerateScript(e: React.FormEvent) {
        e.preventDefault();
        if (!scriptTopic.trim()) {
            setScriptError("Enter a topic first.");
            return;
        }
        setScriptError(null);
        setGeneratingScript(true);
        try {
            const response = await generateViralScript({
                platform: scriptPlatform,
                topic: scriptTopic.trim(),
                audience: scriptAudience.trim() || "creators",
                objective: scriptObjective.trim() || "higher retention and shares",
                tone: scriptTone,
                templateSeriesKey: scriptTemplateKey || undefined,
                desiredDurationS: scriptDuration === "" ? undefined : Number(scriptDuration),
            });
            setScriptResult(response);
        } catch (err: any) {
            setScriptError(err.message || "Failed to generate script");
            setScriptResult(null);
        } finally {
            setGeneratingScript(false);
        }
    }

    const blueprintForDisplay: BlueprintResult = blueprint || {
        gap_analysis: [],
        content_pillars: [],
        video_ideas: [],
    };
    const seriesRows = seriesInsights?.series || blueprint?.series_intelligence?.series || [];
    const analysisPlatformLabel = PLATFORM_LABELS[analysisPlatform];
    const analysisCreatorNoun = analysisPlatform === "youtube" ? "channels" : "creators";
    const analysisPlatformCompetitorCount = competitors.filter((item) => item.platform === analysisPlatform).length;
    const hasAnyCompetitors = competitors.length > 0;
    const hasAnalysisPlatformCompetitors = analysisPlatformCompetitorCount > 0;
    const fallbackAnalysisPlatform = (["youtube", "instagram", "tiktok"] as CompetitorAnalysisPlatform[]).find((platform) =>
        competitors.some((item) => item.platform === platform)
    );

    return (
        <StudioAppShell
            rightSlot={
                <div className="hidden items-center gap-2 lg:flex">
                    <select
                        value={analysisPlatform}
                        onChange={(e) => setAnalysisPlatform(e.target.value as CompetitorAnalysisPlatform)}
                        className="rounded-xl border border-[#d5d5d5] bg-white px-3 py-1.5 text-xs text-[#444] focus:border-[#bbbbbb] focus:outline-none"
                    >
                        <option value="youtube">YouTube Analysis</option>
                        <option value="instagram">Instagram Analysis</option>
                        <option value="tiktok">TikTok Analysis</option>
                    </select>
                    <button
                        type="button"
                        onClick={handleGenerateBlueprint}
                        disabled={generating || !hasAnalysisPlatformCompetitors}
                        className="rounded-xl border border-[#d5d5d5] bg-white px-3 py-1.5 text-xs text-[#444] transition hover:bg-[#f2f2f2] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {generating ? "Analyzing..." : `Generate ${analysisPlatform} Blueprint`}
                    </button>
                </div>
            }
        >
            <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_330px]">
                        <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                            <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                    <h2 className="text-sm font-semibold text-[#222]">Add Competitor</h2>
                                    <span className="rounded-full border border-[#d9d9d9] bg-[#f7f7f7] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#666]">
                                        Primary Workflow
                                    </span>
                                </div>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Start here: track creators in your niche and benchmark their winning patterns.
                            </p>
                            <form onSubmit={handleAddCompetitor} className="space-y-3">
                                <select
                                    value={competitorPlatform}
                                    onChange={(e) => setCompetitorPlatform(e.target.value as "youtube" | "instagram" | "tiktok")}
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={adding}
                                >
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <input
                                    type="text"
                                    value={channelUrl}
                                    onChange={(e) => setChannelUrl(e.target.value)}
                                    placeholder={
                                        competitorPlatform === "youtube"
                                            ? "Paste YouTube channel URL or @handle..."
                                            : "Enter creator handle, e.g. @creator"
                                    }
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={adding}
                                />
                                <button
                                    type="submit"
                                    disabled={adding || !channelUrl.trim()}
                                    className="w-full rounded-xl bg-[#1f1f1f] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#111] disabled:cursor-not-allowed disabled:bg-[#9e9e9e]"
                                >
                                    {adding ? "Adding..." : competitorPlatform === "youtube" ? "Add YouTube Competitor" : "Add Manual Competitor"}
                                </button>
                            </form>
                            <p className="mt-3 text-[11px] text-[#7b7b7b]">
                                {competitorPlatform === "youtube"
                                    ? "Supports: youtube.com/channel/..., youtube.com/@handle, youtube.com/c/..."
                                    : "Use public handle for manual tracking (metadata-based parity mode)."}
                            </p>
                        </div>

                        {analysisPlatform !== "youtube" && (
                            <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                    <h3 className="text-sm font-semibold text-[#222]">Advanced Import Tools</h3>
                                    <span className="rounded-full border border-[#d9d9d9] bg-[#f7f7f7] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#666]">
                                        Tertiary Tools
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => setShowAdvancedImportTools((prev) => !prev)}
                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555] hover:bg-[#efefef]"
                                    >
                                        {showAdvancedImportTools ? "Hide" : "Show"}
                                    </button>
                                </div>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Import competitors from research metadata when you need a broader benchmark set.
                                </p>
                                {showAdvancedImportTools && (
                                    <>
                                        <input
                                            type="text"
                                            value={importNiche}
                                            onChange={(e) => setImportNiche(e.target.value)}
                                            placeholder="Optional niche filter (e.g. AI News)"
                                            className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => void handleImportCompetitorsFromResearch()}
                                            disabled={importingFromResearch}
                                            className="mt-3 w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            {importingFromResearch ? "Importing..." : "Import From Research"}
                                        </button>
                                        {importStatus && (
                                            <p className="mt-2 text-[11px] text-[#6d6d6d]">{importStatus}</p>
                                        )}
                                    </>
                                )}
                            </div>
                        )}

                        {analysisPlatform !== "youtube" && (
                            <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                                <div className="mb-2 flex items-center justify-between gap-2">
                                    <h3 className="text-sm font-semibold text-[#222]">Advanced Discovery Tools</h3>
                                    <span className="rounded-full border border-[#d9d9d9] bg-[#f7f7f7] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#666]">
                                        Tertiary Tools
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => setShowAdvancedDiscoveryTools((prev) => !prev)}
                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555] hover:bg-[#efefef]"
                                    >
                                        {showAdvancedDiscoveryTools ? "Hide" : "Show"}
                                    </button>
                                </div>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Hybrid-safe discover from your research corpus with deterministic quality ranking.
                                </p>
                                {showAdvancedDiscoveryTools && (
                                    <>
                                        <form onSubmit={handleDiscoverCompetitorCandidates} className="space-y-2">
                                            <input
                                                type="text"
                                                value={discoverQuery}
                                                onChange={(e) => setDiscoverQuery(e.target.value)}
                                                placeholder={`Find ${analysisPlatform} creators by niche (optional)`}
                                                className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                disabled={discovering || importingDiscovered}
                                            />
                                            <button
                                                type="submit"
                                                disabled={discovering || importingDiscovered}
                                                className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                            >
                                                {discovering ? "Discovering..." : "Discover Candidates"}
                                            </button>
                                        </form>
                                        {discoverError && (
                                            <p className="mt-2 text-[11px] text-[#7f3a3a]">{discoverError}</p>
                                        )}
                                        {discoveredCandidates.length > 0 && (
                                            <div className="mt-3 space-y-2">
                                                <div className="grid grid-cols-2 gap-2">
                                                    <select
                                                        value={discoverSourceFilter}
                                                        onChange={(e) => setDiscoverSourceFilter(e.target.value)}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-xs text-[#444] focus:border-[#bcbcbc] focus:outline-none"
                                                    >
                                                        <option value="all">All Sources</option>
                                                        <option value="official_api">Official API</option>
                                                        <option value="research_corpus">Research Corpus</option>
                                                        <option value="community_graph">Community Graph</option>
                                                        <option value="manual_url_seed">Manual URL Seed</option>
                                                    </select>
                                                    <select
                                                        value={discoverConfidenceFilter}
                                                        onChange={(e) => setDiscoverConfidenceFilter(e.target.value as "all" | "low" | "medium" | "high")}
                                                        className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-xs text-[#444] focus:border-[#bcbcbc] focus:outline-none"
                                                    >
                                                        <option value="all">All Confidence</option>
                                                        <option value="high">High Confidence</option>
                                                        <option value="medium">Medium Confidence</option>
                                                        <option value="low">Low Confidence</option>
                                                    </select>
                                                </div>
                                                <div className="max-h-56 space-y-2 overflow-auto rounded-xl border border-[#e1e1e1] bg-[#fafafa] p-2">
                                                    {filteredDiscoveredCandidates.map((candidate) => (
                                                        <label key={candidate.external_id} className="flex items-start gap-2 rounded-lg border border-[#e8e8e8] bg-white p-2">
                                                            <input
                                                                type="checkbox"
                                                                checked={selectedDiscoverIds.includes(candidate.external_id)}
                                                                onChange={() => toggleDiscoveredSelection(candidate.external_id)}
                                                                disabled={candidate.already_tracked || importingDiscovered}
                                                            />
                                                            <div className="min-w-0">
                                                                <p className="truncate text-xs font-semibold text-[#222]">
                                                                    {candidate.display_name}
                                                                    {candidate.already_tracked ? " (tracked)" : ""}
                                                                </p>
                                                                <p className="text-[11px] text-[#666]">
                                                                    {candidate.handle} · score {candidate.quality_score.toFixed(1)} · {candidate.confidence_tier || "low"} confidence
                                                                </p>
                                                                <p className="text-[11px] text-[#777]">
                                                                    src {candidate.source} · {candidate.source_count || 1} source{(candidate.source_count || 1) > 1 ? "s" : ""}
                                                                </p>
                                                                {candidate.evidence && candidate.evidence.length > 0 && (
                                                                    <p className="mt-1 line-clamp-2 text-[10px] text-[#7a7a7a]">
                                                                        {candidate.evidence.slice(0, 2).join(" ")}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        </label>
                                                    ))}
                                                    {filteredDiscoveredCandidates.length === 0 && (
                                                        <p className="rounded-lg border border-dashed border-[#ddd] bg-white px-2 py-2 text-[11px] text-[#777]">
                                                            No candidates match your source/confidence filters.
                                                        </p>
                                                    )}
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => void handleImportSelectedDiscovered()}
                                                    disabled={importingDiscovered || selectedImportableCount === 0}
                                                    className="w-full rounded-xl bg-[#1f1f1f] px-3 py-2 text-sm font-semibold text-white hover:bg-[#111] disabled:opacity-50"
                                                >
                                                    {importingDiscovered ? "Importing..." : `Import Selected (${selectedImportableCount})`}
                                                </button>
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        )}

                        {error && (
                            <div className="mt-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                {error}
                            </div>
                        )}

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Actions</h3>
                            <select
                                value={analysisPlatform}
                                onChange={(e) => setAnalysisPlatform(e.target.value as CompetitorAnalysisPlatform)}
                                className="mb-3 w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                            >
                                <option value="youtube">YouTube Analysis</option>
                                <option value="instagram">Instagram Analysis</option>
                                <option value="tiktok">TikTok Analysis</option>
                            </select>
                            <div className="space-y-2">
                                <button
                                    onClick={handleGenerateBlueprint}
                                    disabled={generating || !hasAnalysisPlatformCompetitors}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {generating ? "Generating..." : `Generate ${analysisPlatform} Strategy Blueprint`}
                                </button>
                                <Link
                                    href="/audit/new"
                                    className="block rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-center text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Run New Audit
                                </Link>
                                <Link
                                    href="/research?mode=optimizer"
                                    className="block rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-center text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Open Research Studio
                                </Link>
                                <Link
                                    href="/report/latest"
                                    className="block rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-center text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Open Latest Report
                                </Link>
                            </div>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Tips</h3>
                            <ul className="space-y-1 text-xs text-[#666]">
                                <li>Choose channels with a similar audience size</li>
                                <li>Mix direct peers with aspirational creators</li>
                                <li>Track 3-10 channels for stable patterns</li>
                            </ul>
                        </div>
                    </aside>

                    <section className="border-b border-[#dfdfdf] bg-[#f2f2f2] px-4 py-4 md:px-6 xl:border-b-0">
                        <FlowStepper />
                        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <h1 className="text-2xl font-bold text-[#1f1f1f] md:text-3xl">Competitor Workspace</h1>
                                <p className="text-sm text-[#666]">
                                    Build your tracking list and extract strategy blueprints from winning channels.
                                </p>
                                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                                    <span className="rounded-full border border-[#d9d9d9] bg-white px-2 py-1 text-[#555]">
                                        Primary: add tracked competitors
                                    </span>
                                    <span className="rounded-full border border-[#d9d9d9] bg-white px-2 py-1 text-[#555]">
                                        Secondary: suggested competitors
                                    </span>
                                    <span className="rounded-full border border-[#d9d9d9] bg-white px-2 py-1 text-[#555]">
                                        Tertiary: advanced import and discovery
                                    </span>
                                </div>
                            </div>
                            <div className="rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666]">
                                {analysisPlatformCompetitorCount} tracked {analysisPlatformLabel} {analysisCreatorNoun}
                            </div>
                        </div>

                        {(blueprint || generating) && (
                            <div className="mb-6 rounded-3xl border border-[#dcdcdc] bg-white p-5 shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <div className="mb-4 flex items-center justify-between gap-3">
                                    <h2 className="text-xl font-bold text-[#1f1f1f]">Strategy Blueprint</h2>
                                    {blueprint && !generating && (
                                        <button
                                            onClick={() => setBlueprint(null)}
                                            className="rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-1 text-xs text-[#555] hover:bg-[#efefef]"
                                        >
                                            Dismiss
                                        </button>
                                    )}
                                </div>
                                <BlueprintDisplay blueprint={blueprintForDisplay} loading={generating} />
                            </div>
                        )}

                        <div className="mb-6 grid gap-4 2xl:grid-cols-2">
                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-5 shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                                    <h2 className="text-lg font-bold text-[#1f1f1f]">
                                        {analysisPlatform === "youtube"
                                            ? "YouTube Series Radar"
                                            : analysisPlatform === "instagram"
                                                ? "Instagram Series Radar"
                                                : "TikTok Series Radar"}
                                    </h2>
                                    <button
                                        type="button"
                                        onClick={() => void fetchSeriesInsights(analysisPlatform)}
                                        disabled={loadingSeries || !hasAnalysisPlatformCompetitors}
                                        className="rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-1.5 text-xs text-[#444] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                        {loadingSeries ? "Refreshing..." : "Refresh"}
                                    </button>
                                </div>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Detects recurring content series across tracked {analysisPlatform} competitors so you can model repeatable audience loops.
                                </p>
                                {seriesError && (
                                    <div className="mb-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                        {seriesError}
                                    </div>
                                )}
                                {loadingSeries && (
                                    <p className="text-xs text-[#777]">Scanning competitor libraries for recurring series...</p>
                                )}
                                {!loadingSeries && seriesRows.length > 0 && (
                                    <div className="space-y-3">
                                        {seriesRows.slice(0, 6).map((series) => (
                                            <div key={series.series_key_slug || series.series_key} className="rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                                <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                                                    <p className="text-sm font-semibold text-[#232323]">{series.series_key}</p>
                                                    <span className="text-[11px] text-[#6f6f6f]">
                                                        {series.video_count} videos · {series.competitor_count} channels
                                                    </span>
                                                </div>
                                                <p className="text-[11px] text-[#666]">
                                                    Avg views: {formatMetric(series.avg_views)} · Avg views/day: {formatMetric(Math.round(series.avg_views_per_day))}
                                                </p>
                                                {series.top_titles.length > 0 && (
                                                    <p className="mt-1 line-clamp-2 text-[11px] text-[#7a7a7a]">
                                                        Top episodes: {series.top_titles.slice(0, 2).join(" | ")}
                                                    </p>
                                                )}
                                                <Link
                                                    href={`/research?mode=optimizer&topic=${encodeURIComponent(series.recommended_angle || series.series_key)}&source_context=${encodeURIComponent(series.series_key)}`}
                                                    className="mt-2 inline-flex rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#555] hover:bg-[#efefef]"
                                                >
                                                    Send to Script Studio
                                                </Link>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {!loadingSeries && seriesRows.length === 0 && (
                                    <p className="text-xs text-[#7a7a7a]">
                                        No recurring series detected yet. Add more competitors or run blueprint after expanding your list.
                                    </p>
                                )}
                            </div>

                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-5 shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <h2 className="mb-2 text-lg font-bold text-[#1f1f1f]">Series Planner</h2>
                                <p className="mb-3 text-xs text-[#6d6d6d]">
                                    Build a repeatable series from scratch or remix a detected competitor series template.
                                </p>
                                <form onSubmit={handleGenerateSeriesPlan} className="space-y-3">
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Mode</label>
                                            <select
                                                value={seriesMode}
                                                onChange={(e) => setSeriesMode(e.target.value as "scratch" | "competitor_template")}
                                                className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                            >
                                                <option value="scratch">From Scratch</option>
                                                <option value="competitor_template">Competitor Template</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Platform</label>
                                            <select
                                                value={seriesPlatform}
                                                onChange={(e) => setSeriesPlatform(e.target.value as "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long")}
                                                className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                            >
                                                <option value="youtube_shorts">YouTube Shorts</option>
                                                <option value="instagram_reels">Instagram Reels</option>
                                                <option value="tiktok">TikTok</option>
                                                <option value="youtube_long">YouTube Long</option>
                                            </select>
                                        </div>
                                    </div>

                                    <input
                                        type="text"
                                        value={seriesNiche}
                                        onChange={(e) => setSeriesNiche(e.target.value)}
                                        placeholder="Series niche, e.g. AI News"
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        type="text"
                                        value={seriesAudience}
                                        onChange={(e) => setSeriesAudience(e.target.value)}
                                        placeholder="Audience"
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                    <input
                                        type="text"
                                        value={seriesObjective}
                                        onChange={(e) => setSeriesObjective(e.target.value)}
                                        placeholder="Objective"
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    />

                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Episodes</label>
                                            <input
                                                type="number"
                                                min={3}
                                                max={12}
                                                value={seriesEpisodes}
                                                onChange={(e) => setSeriesEpisodes(Math.min(12, Math.max(3, Number(e.target.value) || 3)))}
                                                className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Template</label>
                                            <select
                                                value={seriesTemplateKey}
                                                onChange={(e) => setSeriesTemplateKey(e.target.value)}
                                                disabled={seriesRows.length === 0}
                                                className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                                            >
                                                <option value="">Auto-select best match</option>
                                                {seriesRows.map((series) => (
                                                    <option key={series.series_key_slug || series.series_key} value={series.series_key_slug || series.series_key}>
                                                        {series.series_key}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>

                                    <button
                                        type="submit"
                                        disabled={planningSeries}
                                        className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                        {planningSeries ? "Building..." : "Generate Series Plan"}
                                    </button>
                                </form>
                                {seriesPlanError && (
                                    <div className="mt-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                        {seriesPlanError}
                                    </div>
                                )}
                                {seriesPlan && (
                                    <div className="mt-4 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                        <p className="text-sm font-semibold text-[#222]">{seriesPlan.series_title}</p>
                                        <p className="mt-1 text-[11px] text-[#666]">{seriesPlan.series_thesis}</p>
                                        <p className="mt-1 text-[11px] text-[#777]">
                                            {seriesPlan.platform.replace("_", " ")} · {seriesPlan.episodes_count} episodes · {seriesPlan.publishing_cadence}
                                        </p>
                                        <div className="mt-2 space-y-2">
                                            {seriesPlan.episodes.slice(0, 4).map((episode) => (
                                                <div key={episode.episode_number} className="rounded-lg border border-[#e3e3e3] bg-white p-2">
                                                    <p className="text-xs font-semibold text-[#202020]">{episode.working_title}</p>
                                                    <p className="text-[11px] text-[#666]">{episode.content_goal}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                <div className="mt-4 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-3">
                                    <p className="text-xs font-semibold text-[#222]">Series Execution</p>
                                    <p className="mt-1 text-[11px] text-[#666]">
                                        Turn series plans into publish dates and generate the next episode brief.
                                    </p>
                                    <div className="mt-2 grid grid-cols-2 gap-2">
                                        <input
                                            type="date"
                                            value={calendarStartDate}
                                            onChange={(e) => setCalendarStartDate(e.target.value)}
                                            className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                        />
                                        <input
                                            type="number"
                                            min={1}
                                            max={14}
                                            value={calendarCadenceDays}
                                            onChange={(e) => setCalendarCadenceDays(Math.min(14, Math.max(1, Number(e.target.value) || 1)))}
                                            className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                        />
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => void handleBuildSeriesCalendar()}
                                        disabled={buildingCalendar || !seriesPlan}
                                        className="mt-2 w-full rounded-lg border border-[#d9d9d9] bg-white px-2 py-1.5 text-[11px] text-[#444] disabled:opacity-50"
                                    >
                                        {buildingCalendar ? "Building calendar..." : "Build Calendar"}
                                    </button>
                                    <div className="mt-2 grid grid-cols-[1fr_auto] gap-2">
                                        <input
                                            type="number"
                                            min={0}
                                            max={200}
                                            value={completedEpisodes}
                                            onChange={(e) => setCompletedEpisodes(Math.max(0, Number(e.target.value) || 0))}
                                            placeholder="Completed episodes"
                                            className="rounded-lg border border-[#d8d8d8] bg-white px-2 py-1 text-[11px] text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => void handleGenerateNextEpisode()}
                                            disabled={generatingNextEpisode}
                                            className="rounded-lg border border-[#d9d9d9] bg-white px-2 py-1 text-[11px] text-[#444] disabled:opacity-50"
                                        >
                                            {generatingNextEpisode ? "Generating..." : "Next Episode"}
                                        </button>
                                    </div>
                                    {seriesExecutionError && (
                                        <p className="mt-2 text-[11px] text-[#7f3a3a]">{seriesExecutionError}</p>
                                    )}
                                    {seriesCalendar?.episodes?.length ? (
                                        <div className="mt-2 space-y-1">
                                            {seriesCalendar.episodes.slice(0, 4).map((episode) => (
                                                <div key={episode.episode_number} className="rounded-lg border border-[#e3e3e3] bg-white p-2">
                                                    <p className="text-[11px] font-semibold text-[#202020]">
                                                        Ep {episode.episode_number}: {episode.working_title}
                                                    </p>
                                                    <p className="text-[10px] text-[#777]">Publish {episode.publish_date}</p>
                                                </div>
                                            ))}
                                        </div>
                                    ) : null}
                                    {nextEpisode && (
                                        <div className="mt-2 rounded-lg border border-[#e3e3e3] bg-white p-2">
                                            <p className="text-[11px] font-semibold text-[#202020]">{nextEpisode.working_title}</p>
                                            <p className="mt-1 text-[11px] text-[#666]">{nextEpisode.hook_line}</p>
                                            <p className="mt-1 text-[10px] text-[#777]">{nextEpisode.cta}</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="mb-6 rounded-3xl border border-[#dcdcdc] bg-white p-5 shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                            <h2 className="mb-2 text-lg font-bold text-[#1f1f1f]">Viral Script Studio</h2>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Generate platform-aware short/reel/tiktok scripts with hook, section timing, and edit priorities.
                            </p>
                            <form onSubmit={handleGenerateScript} className="grid gap-3 md:grid-cols-2">
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Topic</label>
                                    <input
                                        type="text"
                                        value={scriptTopic}
                                        onChange={(e) => setScriptTopic(e.target.value)}
                                        placeholder="e.g. AI News hook formulas"
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Platform</label>
                                    <select
                                        value={scriptPlatform}
                                        onChange={(e) => setScriptPlatform(e.target.value as "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long")}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="youtube_shorts">YouTube Shorts</option>
                                        <option value="instagram_reels">Instagram Reels</option>
                                        <option value="tiktok">TikTok</option>
                                        <option value="youtube_long">YouTube Long</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Audience</label>
                                    <input
                                        type="text"
                                        value={scriptAudience}
                                        onChange={(e) => setScriptAudience(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Objective</label>
                                    <input
                                        type="text"
                                        value={scriptObjective}
                                        onChange={(e) => setScriptObjective(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Tone</label>
                                    <select
                                        value={scriptTone}
                                        onChange={(e) => setScriptTone(e.target.value as "bold" | "expert" | "conversational")}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="bold">Bold</option>
                                        <option value="expert">Expert</option>
                                        <option value="conversational">Conversational</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Duration (seconds)</label>
                                    <input
                                        type="number"
                                        min={15}
                                        max={900}
                                        value={scriptDuration}
                                        onChange={(e) => setScriptDuration(e.target.value === "" ? "" : Number(e.target.value))}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Use Competitor Series Template (optional)</label>
                                    <select
                                        value={scriptTemplateKey}
                                        onChange={(e) => setScriptTemplateKey(e.target.value)}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="">No template</option>
                                        {seriesRows.map((series) => (
                                            <option key={series.series_key_slug || series.series_key} value={series.series_key_slug || series.series_key}>
                                                {series.series_key}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <button
                                    type="submit"
                                    disabled={generatingScript}
                                    className="md:col-span-2 rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {generatingScript ? "Generating..." : "Generate Viral Script"}
                                </button>
                            </form>
                            {scriptError && (
                                <div className="mt-3 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                    {scriptError}
                                </div>
                            )}
                            {scriptResult && (
                                <div className="mt-4 rounded-xl border border-[#dfdfdf] bg-[#fafafa] p-4">
                                    <div className="mb-2 flex flex-wrap items-center gap-2">
                                        <span className="rounded-full border border-[#dcdcdc] bg-white px-2 py-1 text-[11px] text-[#555]">
                                            Hook: {Math.round(scriptResult.score_breakdown.hook_strength)}
                                        </span>
                                        <span className="rounded-full border border-[#dcdcdc] bg-white px-2 py-1 text-[11px] text-[#555]">
                                            Retention: {Math.round(scriptResult.score_breakdown.retention_design)}
                                        </span>
                                        <span className="rounded-full border border-[#dcdcdc] bg-white px-2 py-1 text-[11px] text-[#555]">
                                            Shareability: {Math.round(scriptResult.score_breakdown.shareability)}
                                        </span>
                                        <span className="rounded-full border border-[#dcdcdc] bg-white px-2 py-1 text-[11px] text-[#555]">
                                            Overall: {Math.round(scriptResult.score_breakdown.overall)}
                                        </span>
                                    </div>
                                    <p className="text-sm font-semibold text-[#202020]">{scriptResult.hook_line}</p>
                                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                                        <div className="space-y-2">
                                            <p className="text-xs font-semibold uppercase tracking-wide text-[#777]">Script Sections</p>
                                            {scriptResult.script_sections.map((section, idx) => (
                                                <div key={idx} className="rounded-lg border border-[#e3e3e3] bg-white p-2">
                                                    <p className="text-xs font-semibold text-[#202020]">{section.section} ({section.time_window})</p>
                                                    <p className="text-[11px] text-[#666]">{section.text}</p>
                                                </div>
                                            ))}
                                        </div>
                                        <div className="space-y-2">
                                            <p className="text-xs font-semibold uppercase tracking-wide text-[#777]">Caption Options</p>
                                            <ul className="space-y-1 text-[11px] text-[#555]">
                                                {scriptResult.caption_options.slice(0, 3).map((caption, idx) => (
                                                    <li key={idx}>• {caption}</li>
                                                ))}
                                            </ul>
                                            <p className="pt-2 text-xs font-semibold uppercase tracking-wide text-[#777]">Improvement Notes</p>
                                            <ul className="space-y-1 text-[11px] text-[#555]">
                                                {scriptResult.improvement_notes.slice(0, 3).map((note, idx) => (
                                                    <li key={idx}>• {note}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {loading && (
                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-12 text-center shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#777] border-t-transparent"></div>
                                <p className="text-sm text-[#717171]">Loading competitors...</p>
                            </div>
                        )}

                        {!loading && competitors.length > 0 && (
                            <div className="space-y-3">
                                {competitors.map((comp) => (
                                    <div key={comp.id} className="flex items-center gap-4 rounded-2xl border border-[#dcdcdc] bg-white p-4 shadow-[0_6px_18px_rgba(0,0,0,0.04)]">
                                        {comp.thumbnail_url && (
                                            <img
                                                src={comp.thumbnail_url}
                                                alt={comp.title}
                                                className="h-14 w-14 rounded-full border border-[#e2e2e2]"
                                            />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <h3 className="truncate text-sm font-semibold text-[#232323]">{comp.title}</h3>
                                            <p className="text-xs text-[#727272]">
                                                {parseInt(String(comp.subscriber_count || "0"), 10)?.toLocaleString() || "?"} {comp.platform === "youtube" ? "subscribers" : "audience proxy"}
                                            </p>
                                            <p className="text-xs uppercase tracking-wide text-[#8a8a8a]">{comp.platform}</p>
                                            <p className="text-xs text-[#8a8a8a]">
                                                Added {new Date(comp.created_at).toLocaleDateString()}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => handleRemoveCompetitor(comp.id)}
                                            className="rounded-xl border border-[#ebd2d2] bg-[#fff6f6] px-3 py-1.5 text-xs font-medium text-[#9a4242] hover:bg-[#ffefef]"
                                        >
                                            Remove
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {!loading && hasAnyCompetitors && !hasAnalysisPlatformCompetitors && !error && (
                            <div className="rounded-3xl border border-[#e4dbbf] bg-[#fffaf0] p-6 shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <h2 className="mb-2 text-lg font-bold text-[#5a4b1f]">No {analysisPlatformLabel} competitors in your current list</h2>
                                <p className="text-sm text-[#6a5b30]">
                                    You already track competitors on other platforms. Add at least one {analysisPlatformLabel} creator or switch your analysis platform.
                                </p>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    {fallbackAnalysisPlatform && fallbackAnalysisPlatform !== analysisPlatform && (
                                        <button
                                            type="button"
                                            onClick={() => setAnalysisPlatform(fallbackAnalysisPlatform)}
                                            className="rounded-lg border border-[#d8c898] bg-white px-3 py-1.5 text-xs font-medium text-[#6a5b30] hover:bg-[#fffdf6]"
                                        >
                                            Switch to {PLATFORM_LABELS[fallbackAnalysisPlatform]} Analysis
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => setCompetitorPlatform(analysisPlatform)}
                                        className="rounded-lg border border-[#d8c898] bg-white px-3 py-1.5 text-xs font-medium text-[#6a5b30] hover:bg-[#fffdf6]"
                                    >
                                        Add a {analysisPlatformLabel} Competitor
                                    </button>
                                </div>
                            </div>
                        )}

                        {!loading && !hasAnyCompetitors && !error && (
                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-10 text-center shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <h2 className="mb-2 text-xl font-bold text-[#1f1f1f]">No competitors added yet</h2>
                                <p className="mx-auto max-w-lg text-sm text-[#6d6d6d]">
                                    {analysisPlatform === "youtube"
                                        ? "Add at least one YouTube channel URL or @handle to start recommendations and blueprint analysis."
                                        : `Add at least one ${analysisPlatformLabel} creator handle to start parity-safe recommendations and blueprint analysis.`}
                                </p>
                            </div>
                        )}
                    </section>

                    <aside className="bg-[#f8f8f8] p-4 xl:border-l xl:border-[#dfdfdf]">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <div className="mb-2 flex items-center justify-between gap-2">
                                <h2 className="text-sm font-semibold text-[#222]">Suggested Competitors</h2>
                                <span className="rounded-full border border-[#d9d9d9] bg-[#f7f7f7] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#666]">
                                    Secondary Workflow
                                </span>
                            </div>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Enter a niche (for example, AI News) to discover high-performing competitors.
                            </p>

                            <form onSubmit={handleFindSuggestions} className="space-y-3">
                                <select
                                    value={suggestionPlatform}
                                    onChange={(e) => {
                                        setSuggestionPlatform(e.target.value as "youtube" | "instagram" | "tiktok");
                                        setSuggestedCompetitors([]);
                                        setHasRequestedSuggestions(false);
                                        setSuggestionPage(1);
                                    }}
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={suggesting}
                                >
                                    <option value="youtube">YouTube</option>
                                    <option value="instagram">Instagram</option>
                                    <option value="tiktok">TikTok</option>
                                </select>
                                <input
                                    type="text"
                                    value={suggestionNiche}
                                    onChange={(e) => setSuggestionNiche(e.target.value)}
                                    placeholder={`Enter ${suggestionPlatform} niche, e.g. AI News`}
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={suggesting}
                                />
                                <button
                                    type="submit"
                                    disabled={suggesting || !suggestionNiche.trim()}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {suggesting ? "Finding..." : "Find Suggestions"}
                                </button>
                            </form>

                            <div className="mt-4 grid grid-cols-2 gap-2">
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Rank by</label>
                                    <select
                                        value={suggestionSortKey}
                                        onChange={(e) => {
                                            setSuggestionPage(1);
                                            setSuggestionSortKey(e.target.value as CompetitorSuggestionSortBy);
                                        }}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="subscriber_count">Subscribers</option>
                                        <option value="avg_views_per_video">Avg Views/Video</option>
                                        <option value="view_count">Total Views</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-[#777]">Order</label>
                                    <select
                                        value={sortDirection}
                                        onChange={(e) => {
                                            setSuggestionPage(1);
                                            setSortDirection(e.target.value as CompetitorSuggestionSortDirection);
                                        }}
                                        className="w-full rounded-lg border border-[#d8d8d8] bg-[#fbfbfb] px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                    >
                                        <option value="desc">High to Low</option>
                                        <option value="asc">Low to High</option>
                                    </select>
                                </div>
                            </div>

                            {suggestionError && (
                                <div className="mt-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                    {suggestionError}
                                </div>
                            )}

                            {suggesting && (
                                <div className="py-6 text-center">
                                    <div className="mx-auto mb-2 h-6 w-6 animate-spin rounded-full border-2 border-[#777] border-t-transparent"></div>
                                    <p className="text-xs text-[#717171]">Finding high-performing channels...</p>
                                </div>
                            )}

                            {!suggesting && suggestedCompetitors.length > 0 && (
                                <div className="mt-4 space-y-3">
                                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#777]">
                                        <p>
                                            Showing {Math.min((suggestionPage - 1) * suggestionLimit + 1, suggestionTotalCount)}-
                                            {Math.min(suggestionPage * suggestionLimit, suggestionTotalCount)} of {formatMetric(suggestionTotalCount)}
                                        </p>
                                        <span>Page {suggestionPage}</span>
                                    </div>

                                    {suggestedCompetitors.map((suggestion) => (
                                        <div key={suggestion.channel_id} className="rounded-xl border border-[#dcdcdc] bg-[#fafafa] p-3">
                                            <div className="mb-2 flex items-center gap-3">
                                                {suggestion.thumbnail_url && (
                                                    <img
                                                        src={suggestion.thumbnail_url}
                                                        alt={suggestion.title}
                                                        className="h-10 w-10 rounded-full border border-[#e2e2e2]"
                                                    />
                                                )}
                                                <div className="min-w-0 flex-1">
                                                    <h3 className="truncate text-xs font-semibold text-[#222]">{suggestion.title}</h3>
                                                    <p className="truncate text-[11px] text-[#767676]">
                                                        {suggestion.custom_url || suggestion.channel_id}
                                                    </p>
                                                </div>
                                            </div>

                                            <p className="mb-3 text-[11px] text-[#666]">
                                                {formatMetric(suggestion.subscriber_count)} {suggestionPlatform === "youtube" ? "subs" : "engagement proxy"} · {formatMetric(suggestion.video_count)} posts · {formatMetric(suggestion.avg_views_per_video)} avg views/post
                                            </p>

                                            <button
                                                onClick={() => handleAddSuggestedCompetitor(suggestion)}
                                                disabled={suggestion.already_tracked}
                                                className="w-full rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                            >
                                                {suggestion.already_tracked ? "Added" : "Add"}
                                            </button>
                                        </div>
                                    ))}

                                    <div className="flex items-center gap-2">
                                        <button
                                            type="button"
                                            onClick={() => handleSuggestionPageChange(suggestionPage - 1)}
                                            disabled={suggestionPage <= 1 || suggesting}
                                            className="flex-1 rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#444] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            Previous
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleSuggestionPageChange(suggestionPage + 1)}
                                            disabled={!suggestionHasMore || suggesting}
                                            className="flex-1 rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#444] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            Next
                                        </button>
                                    </div>
                                </div>
                            )}

                            {!suggesting && hasRequestedSuggestions && suggestedCompetitors.length === 0 && !suggestionError && (
                                <p className="mt-4 text-xs text-[#777]">No suggestions found. Try a broader niche keyword.</p>
                            )}
                        </div>
                    </aside>
            </div>
        </StudioAppShell>
    );
}
