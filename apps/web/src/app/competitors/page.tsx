"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { getCompetitors, addCompetitor, removeCompetitor, Competitor, generateBlueprint, BlueprintResult } from "@/lib/api";
import { BlueprintDisplay } from "@/components/blueprint-display";

export default function CompetitorsPage() {
    const [competitors, setCompetitors] = useState<Competitor[]>([]);
    const [channelUrl, setChannelUrl] = useState("");
    const [loading, setLoading] = useState(true);
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Blueprint state
    const [blueprint, setBlueprint] = useState<BlueprintResult | null>(null);
    const [generating, setGenerating] = useState(false);

    useEffect(() => {
        fetchCompetitors();
    }, []);

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

    async function handleAddCompetitor(e: React.FormEvent) {
        e.preventDefault();
        if (!channelUrl.trim()) return;

        setAdding(true);
        setError(null);

        try {
            const newCompetitor = await addCompetitor(channelUrl);
            setCompetitors((prev) => [...prev, newCompetitor]);
            setChannelUrl("");
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

    return (
        <div className="min-h-screen p-8">
            {/* Header */}
            <header className="max-w-7xl mx-auto mb-8">
                <div className="flex justify-between items-center">
                    <Link href="/" className="text-2xl font-bold text-white">
                        <span className="gradient-text">SPC</span>
                    </Link>
                    <nav className="flex gap-6">
                        <Link href="/dashboard" className="text-gray-400 hover:text-white transition-colors">Dashboard</Link>
                        <Link href="/competitors" className="text-white font-medium">Competitors</Link>
                        <Link href="/audit/new" className="text-gray-400 hover:text-white transition-colors">New Audit</Link>
                    </nav>
                </div>
            </header>

            <main className="max-w-4xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-white">Competitor Channels</h1>
                    {competitors.length > 0 && (
                        <button
                            onClick={handleGenerateBlueprint}
                            disabled={generating}
                            className="px-6 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors flex items-center gap-2 border border-white/10"
                        >
                            {generating ? (
                                <>
                                    <div className="animate-spin w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full"></div>
                                    Analyzing...
                                </>
                            ) : (
                                <><span>✨</span> Generate Strategy Blueprint</>
                            )}
                        </button>
                    )}
                </div>

                {/* Blueprint Section */}
                {(blueprint || generating) && (
                    <div className="mb-12">
                        <div className="flex justify-between items-center mb-6">
                            <h2 className="text-2xl font-bold text-white">Strategy Blueprint</h2>
                            {blueprint && !generating && (
                                <button
                                    onClick={() => setBlueprint(null)}
                                    className="text-gray-400 hover:text-white text-sm"
                                >
                                    Dismiss
                                </button>
                            )}
                        </div>
                        <BlueprintDisplay blueprint={blueprint!} loading={generating} />
                        {!generating && <hr className="mt-12 border-white/5" />}
                    </div>
                )}

                {/* Error Message */}
                {error && (
                    <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                        {error}
                    </div>
                )}

                {/* Add Competitor Form */}
                <div className="glass-card p-6 mb-8">
                    <h2 className="text-lg font-semibold text-white mb-4">Add a Competitor Channel</h2>
                    <form onSubmit={handleAddCompetitor} className="flex gap-4">
                        <input
                            type="text"
                            value={channelUrl}
                            onChange={(e) => setChannelUrl(e.target.value)}
                            placeholder="Paste YouTube channel URL or @handle..."
                            className="flex-1 px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            disabled={adding}
                        />
                        <button
                            type="submit"
                            disabled={adding || !channelUrl.trim()}
                            className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {adding ? "Adding..." : "Add"}
                        </button>
                    </form>
                    <p className="text-gray-500 text-sm mt-3">
                        Supports: youtube.com/channel/..., youtube.com/@handle, youtube.com/c/...
                    </p>
                </div>

                {/* Loading State */}
                {loading && (
                    <div className="glass-card p-12 text-center">
                        <div className="animate-spin w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                        <p className="text-gray-400">Loading competitors...</p>
                    </div>
                )}

                {/* Competitors List */}
                {!loading && competitors.length > 0 && (
                    <div className="space-y-4">
                        {competitors.map((comp) => (
                            <div key={comp.id} className="glass-card p-4 flex items-center gap-4 border border-white/5">
                                {comp.thumbnail_url && (
                                    <img
                                        src={comp.thumbnail_url}
                                        alt={comp.title}
                                        className="w-16 h-16 rounded-full"
                                    />
                                )}
                                <div className="flex-1 min-w-0">
                                    <h3 className="text-white font-semibold truncate">{comp.title}</h3>
                                    <p className="text-gray-400 text-sm">
                                        {parseInt(String(comp.subscriber_count || "0"))?.toLocaleString() || "?"} subscribers
                                    </p>
                                    <p className="text-gray-500 text-xs">
                                        Added {new Date(comp.created_at).toLocaleDateString()}
                                    </p>
                                </div>
                                <button
                                    onClick={() => handleRemoveCompetitor(comp.id)}
                                    className="px-4 py-2 text-red-500/70 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors text-sm font-medium"
                                >
                                    Remove
                                </button>
                            </div>
                        ))}
                    </div>
                )}

                {/* Empty State */}
                {!loading && competitors.length === 0 && !error && (
                    <div className="glass-card p-12 text-center">
                        <div className="text-5xl mb-4">👥</div>
                        <h3 className="text-lg font-semibold text-white mb-2">No competitors added yet</h3>
                        <p className="text-gray-400">Add competitor channels to compare your performance and learn from top creators.</p>
                    </div>
                )}

                {/* Tips */}
                <div className="mt-8 p-6 bg-purple-500/10 border border-purple-500/20 rounded-xl">
                    <h3 className="text-white font-semibold mb-2">💡 Tips for choosing competitors</h3>
                    <ul className="text-gray-300 text-sm space-y-1">
                        <li>• Choose channels in your niche with similar content style</li>
                        <li>• Include a mix of channels slightly ahead of you and aspirational targets</li>
                        <li>• Add 3-10 competitors for best results</li>
                    </ul>
                </div>
            </main>
        </div>
    );
}
