"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { FlowStateResponse, getFlowState } from "@/lib/api";

interface WorkflowAssistantProps {
    context: "research" | "audit" | "report";
    onFlowState?: (state: FlowStateResponse) => void;
}

interface StageMeta {
    key: keyof FlowStateResponse["stage_completion"];
    label: string;
    href: string;
}

const STAGES: StageMeta[] = [
    { key: "connected_platform", label: "Connect platform", href: "/connect" },
    { key: "competitors_added", label: "Add competitors", href: "/competitors" },
    { key: "research_collected", label: "Collect research", href: "/research" },
    { key: "script_generated", label: "Generate scripts", href: "/research?mode=optimizer" },
    { key: "audit_completed", label: "Run audit", href: "/audit/new" },
    { key: "outcome_recorded", label: "Post outcomes", href: "/report/latest" },
];

const PLATFORM_LABELS: Record<NonNullable<FlowStateResponse["preferred_platform"]>, string> = {
    youtube: "YouTube",
    instagram: "Instagram",
    tiktok: "TikTok",
};

function actionLabel(action: FlowStateResponse["next_best_action"]): string {
    switch (action) {
        case "connect_platform":
            return "Connect your first platform";
        case "add_competitors":
            return "Add competitor benchmarks";
        case "import_research":
            return "Import research items";
        case "generate_script":
            return "Generate script variants";
        case "run_audit":
            return "Run a pre-publish audit";
        case "post_outcome":
            return "Record actual results";
        case "optimize_loop":
            return "Optimize your next iteration";
        default:
            return "Continue";
    }
}

function contextHint(context: WorkflowAssistantProps["context"]): string {
    switch (context) {
        case "research":
            return "Use this workspace to generate/edit variants before moving to audit.";
        case "audit":
            return "Use audit after script edits so detector recommendations are actionable.";
        case "report":
            return "Use report recommendations, then loop back into research for improved variants.";
        default:
            return "Follow the guided workflow for best results.";
    }
}

export function WorkflowAssistant({ context, onFlowState }: WorkflowAssistantProps) {
    const [state, setState] = useState<FlowStateResponse | null>(null);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const result = await getFlowState();
                if (!cancelled) {
                    setState(result);
                    onFlowState?.(result);
                }
            } catch {
                if (!cancelled) {
                    setState(null);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [onFlowState]);

    const missingSteps = useMemo(() => {
        if (!state) {
            return [];
        }
        return STAGES.filter((stage) => !state.stage_completion?.[stage.key]);
    }, [state]);

    if (!state) {
        return null;
    }

    const preferredPlatform = state.preferred_platform ? PLATFORM_LABELS[state.preferred_platform] : null;

    return (
        <div className="mb-4 rounded-2xl border border-[#d9d9d9] bg-white p-4 shadow-[0_8px_22px_rgba(0,0,0,0.04)]">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#666]">Workflow Assistant</p>
                    <p className="mt-1 text-sm text-[#3a3a3a]">{actionLabel(state.next_best_action)}</p>
                    <p className="mt-1 text-xs text-[#777]">{contextHint(context)}</p>
                </div>
                <Link
                    href={state.next_best_href}
                    className="rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-1.5 text-xs font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                >
                    Go to next step
                </Link>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                <span className="rounded-full border border-[#d8d8d8] bg-[#f7f7f7] px-2 py-1 text-[#555]">
                    Completion {state.completion_percent}%
                </span>
                {preferredPlatform && (
                    <span className="rounded-full border border-[#d8d8d8] bg-[#f7f7f7] px-2 py-1 text-[#555]">
                        Preferred platform: {preferredPlatform}
                    </span>
                )}
                {!!state.totals?.competitors && (
                    <span className="rounded-full border border-[#d8d8d8] bg-[#f7f7f7] px-2 py-1 text-[#555]">
                        Tracked competitors: {state.totals.competitors}
                    </span>
                )}
            </div>

            {missingSteps.length > 0 && (
                <div className="mt-3">
                    <p className="mb-2 text-[11px] uppercase tracking-wide text-[#7a7a7a]">Missing Prerequisites</p>
                    <div className="flex flex-wrap gap-2">
                        {missingSteps.slice(0, 4).map((step) => (
                            <Link
                                key={step.key}
                                href={step.href}
                                className="rounded-lg border border-[#e0e0e0] bg-[#fafafa] px-2 py-1 text-[11px] text-[#595959] hover:bg-[#efefef]"
                            >
                                {step.label}
                            </Link>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
