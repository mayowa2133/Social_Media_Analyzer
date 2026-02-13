"use client";

import { BlueprintResult } from "@/lib/api";

interface BlueprintDisplayProps {
    blueprint: BlueprintResult;
    loading?: boolean;
}

export function BlueprintDisplay({ blueprint, loading }: BlueprintDisplayProps) {
    if (loading) {
        return (
            <div className="glass-card p-8 animate-pulse">
                <div className="h-6 w-1/3 bg-white/10 rounded mb-6"></div>
                <div className="space-y-4">
                    <div className="h-4 w-full bg-white/5 rounded"></div>
                    <div className="h-4 w-5/6 bg-white/5 rounded"></div>
                    <div className="h-4 w-4/6 bg-white/5 rounded"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Gap Analysis */}
            <div className="glass-card p-6 border-l-4 border-purple-500">
                <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>🧠</span> Gap Analysis
                </h3>
                <ul className="space-y-3">
                    {blueprint.gap_analysis.map((gap, i) => (
                        <li key={i} className="text-gray-300 flex items-start gap-3">
                            <span className="text-purple-400 mt-1">•</span>
                            {gap}
                        </li>
                    ))}
                </ul>
            </div>

            {/* Content Pillars */}
            <div className="grid md:grid-cols-3 gap-6">
                {blueprint.content_pillars.map((pillar, i) => (
                    <div key={i} className="glass-card p-6 text-center">
                        <div className="text-3xl mb-3">📍</div>
                        <h4 className="text-white font-bold mb-2">{pillar}</h4>
                    </div>
                ))}
            </div>

            {/* Video Ideas */}
            <div>
                <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                    <span>💡</span> Video Blueprint Ideas
                </h3>
                <div className="grid md:grid-cols-3 gap-6">
                    {blueprint.video_ideas.map((idea, i) => (
                        <div key={i} className="glass-card p-6 hover:bg-white/5 transition-colors border border-white/5">
                            <h4 className="text-purple-400 font-bold mb-3">{idea.title}</h4>
                            <p className="text-gray-400 text-sm leading-relaxed">
                                {idea.concept}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
