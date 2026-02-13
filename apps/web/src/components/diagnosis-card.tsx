"use client";

import { AlertTriangle, CheckCircle, TrendingUp, HelpCircle, BarChart3, AlertCircle } from "lucide-react";

interface Evidence {
    type: string;
    message: string;
    value?: number;
    benchmark?: number;
}

interface ActionItem {
    title: string;
    description: string;
    priority: number;
}

interface DiagnosisResult {
    primary_issue: "PACKAGING" | "RETENTION" | "TOPIC_FIT" | "CONSISTENCY" | "UNDEFINED";
    summary: string;
    evidence: Evidence[];
    recommendations: ActionItem[];
}

interface DiagnosisCardProps {
    diagnosis: DiagnosisResult;
    loading?: boolean;
}

const ISSUE_CONFIG = {
    PACKAGING: {
        label: "Packaging Issue",
        color: "text-yellow-400",
        bg: "bg-yellow-400/10",
        border: "border-yellow-400/20",
        icon: AlertCircle,
        description: "Your videos aren't getting clicked."
    },
    RETENTION: {
        label: "Retention Issue",
        color: "text-red-400",
        bg: "bg-red-400/10",
        border: "border-red-400/20",
        icon: TrendingUp,
        description: "Viewers are dropping off early."
    },
    TOPIC_FIT: {
        label: "Topic Mismatch",
        color: "text-blue-400",
        bg: "bg-blue-400/10",
        border: "border-blue-400/20",
        icon: HelpCircle,
        description: "Content isn't resonating with audience."
    },
    CONSISTENCY: {
        label: "Inconsistent Schedule",
        color: "text-orange-400",
        bg: "bg-orange-400/10",
        border: "border-orange-400/20",
        icon: BarChart3,
        description: "Irregular uploads hurt momentum."
    },
    UNDEFINED: {
        label: "Needs More Data",
        color: "text-gray-400",
        bg: "bg-gray-400/10",
        border: "border-gray-400/20",
        icon: HelpCircle,
        description: "Upload more videos to get a diagnosis."
    }
};

export function DiagnosisCard({ diagnosis, loading }: DiagnosisCardProps) {
    if (loading) {
        return (
            <div className="glass-card p-6 w-full animate-pulse h-64">
                <div className="h-6 w-1/3 bg-white/10 rounded mb-4"></div>
                <div className="h-4 w-full bg-white/10 rounded mb-2"></div>
                <div className="h-4 w-2/3 bg-white/10 rounded"></div>
            </div>
        );
    }

    const config = ISSUE_CONFIG[diagnosis.primary_issue] || ISSUE_CONFIG.UNDEFINED;
    const Icon = config.icon;

    return (
        <div className={`glass-card p-0 overflow-hidden border ${config.border}`}>
            {/* Header */}
            <div className={`p-6 ${config.bg} border-b ${config.border}`}>
                <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg bg-black/20 ${config.color}`}>
                            <Icon size={24} />
                        </div>
                        <div>
                            <h3 className={`font-bold text-lg ${config.color}`}>
                                {config.label}
                            </h3>
                            <p className="text-white/60 text-sm">{config.description}</p>
                        </div>
                    </div>
                    <span className="text-xs font-mono px-2 py-1 rounded bg-black/20 text-white/50">
                        AI DIAGNOSIS
                    </span>
                </div>
                <p className="text-white mt-4 font-medium leading-relaxed">
                    {diagnosis.summary}
                </p>
            </div>

            <div className="p-6 grid md:grid-cols-2 gap-8">
                {/* Evidence Section */}
                <div>
                    <h4 className="text-gray-400 text-xs font-bold uppercase tracking-wider mb-4">
                        Key Evidence
                    </h4>
                    <ul className="space-y-3">
                        {diagnosis.evidence.map((item, i) => (
                            <li key={i} className="flex gap-3 text-sm text-gray-300">
                                <AlertTriangle size={16} className="text-white/40 shrink-0 mt-0.5" />
                                <span>
                                    {item.message}
                                    {item.value && item.benchmark && (
                                        <span className="block text-xs text-white/40 mt-1">
                                            (Value: {item.value.toFixed(1)} vs Target: {item.benchmark.toFixed(1)})
                                        </span>
                                    )}
                                </span>
                            </li>
                        ))}
                        {diagnosis.evidence.length === 0 && (
                            <li className="text-gray-500 italic text-sm">No specific anomalies detected.</li>
                        )}
                    </ul>
                </div>

                {/* Recommendations Section */}
                <div>
                    <h4 className="text-gray-400 text-xs font-bold uppercase tracking-wider mb-4">
                        Recommended Actions
                    </h4>
                    <div className="space-y-3">
                        {diagnosis.recommendations.map((action, i) => (
                            <div key={i} className="bg-white/5 rounded-lg p-3 hover:bg-white/10 transition-colors">
                                <div className="flex items-center gap-2 mb-1">
                                    <CheckCircle size={14} className="text-green-400" />
                                    <span className="font-semibold text-white text-sm">{action.title}</span>
                                </div>
                                <p className="text-gray-400 text-xs pl-6 leading-relaxed">
                                    {action.description}
                                </p>
                            </div>
                        ))}
                        {diagnosis.recommendations.length === 0 && (
                            <p className="text-gray-500 italic text-sm">No actions available yet.</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
