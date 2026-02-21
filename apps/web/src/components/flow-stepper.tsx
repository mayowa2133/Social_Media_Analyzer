"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { FlowStateResponse, getFlowState } from "@/lib/api";

interface StepDef {
    key: string;
    label: string;
    href: string;
}

const FLOW_STEPS: StepDef[] = [
    { key: "connected_platform", label: "Connect", href: "/connect" },
    { key: "competitors_added", label: "Competitors", href: "/competitors" },
    { key: "research_collected", label: "Research", href: "/research" },
    { key: "script_generated", label: "Script", href: "/research?mode=optimizer" },
    { key: "audit_completed", label: "Audit", href: "/audit/new" },
    { key: "outcome_recorded", label: "Outcomes", href: "/report/latest" },
];

function normalizePath(path: string): string {
    if (path.startsWith("/report/")) {
        return "/report/latest";
    }
    if (path.startsWith("/audit/")) {
        return "/audit/new";
    }
    return path;
}

function actionLabel(action: FlowStateResponse["next_best_action"]): string {
    switch (action) {
        case "connect_platform":
            return "Connect a platform";
        case "add_competitors":
            return "Add competitors";
        case "import_research":
            return "Import research";
        case "generate_script":
            return "Generate script variants";
        case "run_audit":
            return "Run an audit";
        case "post_outcome":
            return "Post result";
        case "optimize_loop":
            return "Optimize next iteration";
        default:
            return "Continue";
    }
}

export function FlowStepper() {
    const pathname = usePathname();
    const normalizedPath = normalizePath(pathname || "");
    const [state, setState] = useState<FlowStateResponse | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const result = await getFlowState();
                if (!cancelled) {
                    setState(result);
                }
            } catch {
                if (!cancelled) {
                    setState(null);
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    const steps = useMemo(() => {
        if (!state) {
            return FLOW_STEPS.map((step) => ({ ...step, done: false }));
        }
        return FLOW_STEPS.map((step) => ({
            ...step,
            done: Boolean(state.stage_completion?.[step.key]),
        }));
    }, [state]);

    if (loading || !state) {
        return null;
    }

    const onTargetPage = normalizePath(state.next_best_href) === normalizedPath;

    return (
        <div className="mb-4 rounded-2xl border border-[#dcdcdc] bg-white p-3 shadow-[0_8px_24px_rgba(0,0,0,0.04)]">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#666]">Guided Workflow</p>
                    <p className="text-xs text-[#6f6f6f]">
                        Completion {state.completion_percent}% • Next: {actionLabel(state.next_best_action)}
                    </p>
                </div>
                {onTargetPage ? (
                    <span className="rounded-lg border border-[#d9d9d9] bg-[#f7f7f7] px-3 py-1.5 text-xs text-[#555]">
                        You are on the current next step
                    </span>
                ) : (
                    <Link
                        href={state.next_best_href}
                        className="rounded-lg border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-1.5 text-xs font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                    >
                        Continue →
                    </Link>
                )}
            </div>

            <div className="mb-3 h-2 overflow-hidden rounded-full bg-[#ededed]">
                <div
                    className="h-full rounded-full bg-[#4f4b9e] transition-all"
                    style={{ width: `${Math.max(0, Math.min(100, state.completion_percent))}%` }}
                />
            </div>

            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
                {steps.map((step) => {
                    const current = normalizePath(step.href) === normalizedPath;
                    return (
                        <Link
                            key={step.key}
                            href={step.href}
                            className={`rounded-lg border px-2 py-1.5 text-center text-[11px] transition-colors ${
                                step.done
                                    ? "border-[#cfe6cf] bg-[#edf7ed] text-[#2e5a33]"
                                    : current
                                        ? "border-[#d8d4f4] bg-[#f2f1fb] text-[#3f3881]"
                                        : "border-[#e1e1e1] bg-[#fafafa] text-[#666]"
                            }`}
                        >
                            {step.done ? "✓ " : ""}{step.label}
                        </Link>
                    );
                })}
            </div>
        </div>
    );
}
