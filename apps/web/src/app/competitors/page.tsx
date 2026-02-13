"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
    addCompetitor,
    BlueprintResult,
    CompetitorSuggestionSortBy,
    CompetitorSuggestionSortDirection,
    Competitor,
    generateBlueprint,
    getCompetitors,
    recommendCompetitors,
    RecommendedCompetitor,
    removeCompetitor,
} from "@/lib/api";
import { BlueprintDisplay } from "@/components/blueprint-display";

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

export default function CompetitorsPage() {
    const [competitors, setCompetitors] = useState<Competitor[]>([]);
    const [channelUrl, setChannelUrl] = useState("");
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
    const [suggestionSortKey, setSuggestionSortKey] = useState<CompetitorSuggestionSortBy>("subscriber_count");
    const [sortDirection, setSortDirection] = useState<CompetitorSuggestionSortDirection>("desc");
    const [suggestionPage, setSuggestionPage] = useState(1);
    const [suggestionLimit, setSuggestionLimit] = useState(SUGGESTION_PAGE_SIZE);
    const [suggestionTotalCount, setSuggestionTotalCount] = useState(0);
    const [suggestionHasMore, setSuggestionHasMore] = useState(false);

    useEffect(() => {
        fetchCompetitors();
    }, []);

    useEffect(() => {
        if (!hasRequestedSuggestions || !suggestionNiche.trim()) {
            return;
        }
        setSuggestionPage(1);
        void fetchSuggestedCompetitors(suggestionNiche, 1);
    }, [suggestionSortKey, sortDirection]);

    async function fetchCompetitors() {
        try {
            const comps = await getCompetitors();
            setCompetitors(comps);
            setError(null);
        } catch (err) {
            setError("Could not connect to API. Make sure the backend is running.");
        } finally {
            setLoading(false);
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
            const newCompetitor = await addCompetitor(channelUrl);
            setCompetitors((prev) => [...prev, newCompetitor]);
            setChannelUrl("");

            const autoNiche = newCompetitor.title || channelUrl;
            setSuggestionNiche(autoNiche);
            setSuggestionPage(1);
            await fetchSuggestedCompetitors(autoNiche, 1);
        } catch (err: any) {
            setError(err.message || "Failed to add competitor");
        } finally {
            setAdding(false);
        }
    }

    async function handleRemoveCompetitor(id: string) {
        try {
            await removeCompetitor(id);
            setCompetitors((prev) => prev.filter((c) => c.id !== id));
        } catch (err: any) {
            setError(err.message || "Failed to remove competitor");
        }
    }

    async function handleGenerateBlueprint() {
        setGenerating(true);
        setError(null);
        try {
            const result = await generateBlueprint();
            setBlueprint(result);
        } catch (err: any) {
            setError(err.message || "Failed to generate blueprint");
        } finally {
            setGenerating(false);
        }
    }

    async function handleFindSuggestions(e: React.FormEvent) {
        e.preventDefault();
        setSuggestionPage(1);
        await fetchSuggestedCompetitors(suggestionNiche, 1);
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
            const created = await addCompetitor(toChannelUrl(suggestion));
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

    const blueprintForDisplay: BlueprintResult = blueprint || {
        gap_analysis: [],
        content_pillars: [],
        video_ideas: [],
    };

    return (
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <header className="flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="text-lg font-bold text-[#1f1f1f]">
                            SPC Studio
                        </Link>
                        <nav className="hidden items-center gap-4 text-sm text-[#6b6b6b] md:flex">
                            <Link href="/dashboard" className="hover:text-[#151515]">Dashboard</Link>
                            <Link href="/competitors" className="font-medium text-[#1b1b1b]">Competitors</Link>
                            <Link href="/audit/new" className="hover:text-[#151515]">Audit Workspace</Link>
                        </nav>
                    </div>
                    <div className="hidden items-center gap-2 lg:flex">
                        <button
                            type="button"
                            onClick={handleGenerateBlueprint}
                            disabled={generating || competitors.length === 0}
                            className="rounded-xl border border-[#d5d5d5] bg-white px-3 py-1.5 text-xs text-[#444] transition hover:bg-[#f2f2f2] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {generating ? "Analyzing..." : "Generate Blueprint"}
                        </button>
                    </div>
                </header>

                <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_330px]">
                    <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h2 className="mb-2 text-sm font-semibold text-[#222]">Add Competitor</h2>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Track channels in your niche and benchmark their winning patterns.
                            </p>
                            <form onSubmit={handleAddCompetitor} className="space-y-3">
                                <input
                                    type="text"
                                    value={channelUrl}
                                    onChange={(e) => setChannelUrl(e.target.value)}
                                    placeholder="Paste YouTube channel URL or @handle..."
                                    className="w-full rounded-xl border border-[#d8d8d8] bg-[#fbfbfb] px-3 py-2 text-sm text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                    disabled={adding}
                                />
                                <button
                                    type="submit"
                                    disabled={adding || !channelUrl.trim()}
                                    className="w-full rounded-xl bg-[#1f1f1f] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#111] disabled:cursor-not-allowed disabled:bg-[#9e9e9e]"
                                >
                                    {adding ? "Adding..." : "Add"}
                                </button>
                            </form>
                            <p className="mt-3 text-[11px] text-[#7b7b7b]">
                                Supports: youtube.com/channel/..., youtube.com/@handle, youtube.com/c/...
                            </p>
                        </div>

                        {error && (
                            <div className="mt-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                {error}
                            </div>
                        )}

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Actions</h3>
                            <div className="space-y-2">
                                <button
                                    onClick={handleGenerateBlueprint}
                                    disabled={generating || competitors.length === 0}
                                    className="w-full rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {generating ? "Generating..." : "Generate Strategy Blueprint"}
                                </button>
                                <Link
                                    href="/audit/new"
                                    className="block rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-center text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Run New Audit
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
                        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <h1 className="text-2xl font-bold text-[#1f1f1f] md:text-3xl">Competitor Workspace</h1>
                                <p className="text-sm text-[#666]">
                                    Build your tracking list and extract strategy blueprints from winning channels.
                                </p>
                            </div>
                            <div className="rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666]">
                                {competitors.length} tracked channels
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
                                                {parseInt(String(comp.subscriber_count || "0"), 10)?.toLocaleString() || "?"} subscribers
                                            </p>
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

                        {!loading && competitors.length === 0 && !error && (
                            <div className="rounded-3xl border border-[#dcdcdc] bg-white p-10 text-center shadow-[0_12px_30px_rgba(0,0,0,0.05)]">
                                <h2 className="mb-2 text-xl font-bold text-[#1f1f1f]">No competitors added yet</h2>
                                <p className="mx-auto max-w-lg text-sm text-[#6d6d6d]">
                                    Add at least one channel to start recommendations and blueprint analysis.
                                </p>
                            </div>
                        )}
                    </section>

                    <aside className="bg-[#f8f8f8] p-4 xl:border-l xl:border-[#dfdfdf]">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h2 className="mb-2 text-sm font-semibold text-[#222]">Suggested Competitors</h2>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Enter a niche (for example, AI News) to discover channels with strong metrics.
                            </p>

                            <form onSubmit={handleFindSuggestions} className="space-y-3">
                                <input
                                    type="text"
                                    value={suggestionNiche}
                                    onChange={(e) => setSuggestionNiche(e.target.value)}
                                    placeholder="Enter niche, e.g. AI News"
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
                                                {formatMetric(suggestion.subscriber_count)} subs · {formatMetric(suggestion.video_count)} videos · {formatMetric(suggestion.avg_views_per_video)} avg views/video
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
            </div>
        </div>
    );
}
