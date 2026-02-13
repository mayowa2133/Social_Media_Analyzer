"use client";

interface ReportScorecardProps {
    score: number;
    auditId: string;
    createdAt?: string | null;
}

export function ReportScorecard({ score, auditId, createdAt }: ReportScorecardProps) {
    const getScoreColor = (s: number) => {
        if (s >= 80) return "text-[#2f6b39]";
        if (s >= 50) return "text-[#8a6a26]";
        return "text-[#8f3e3e]";
    };

    const formattedDate = createdAt ? new Date(createdAt).toLocaleDateString() : "N/A";

    return (
        <div className="relative overflow-hidden rounded-3xl border border-[#dcdcdc] bg-white p-8 text-center shadow-[0_14px_40px_rgba(0,0,0,0.05)]">
            <div className="absolute right-0 top-0 h-28 w-28 -translate-y-8 translate-x-8 rounded-full bg-[#efefef]"></div>

            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#7a7a7a]">Audit Scorecard</div>
            <div className={`mb-4 text-7xl font-black ${getScoreColor(score)}`}>
                {score}<span className="text-3xl font-light text-[#969696]">/100</span>
            </div>

            <div className="mx-auto mb-6 h-2 w-48 overflow-hidden rounded-full bg-[#ececec]">
                <div
                    className="h-full bg-gradient-to-r from-[#4e4a9e] to-[#7270ca] transition-all duration-1000"
                    style={{ width: `${score}%` }}
                ></div>
            </div>

            <div className="flex flex-wrap justify-center gap-2 text-xs text-[#666]">
                <span>AUDIT ID: <span className="text-[#2e2e2e]">{auditId.substring(0, 8)}</span></span>
                <span className="text-[#aaa]">•</span>
                <span>DATE: <span className="text-[#2e2e2e]">{formattedDate}</span></span>
            </div>

            <button
                onClick={() => window.print()}
                className="no-print mt-7 rounded-xl border border-[#d6d6d6] bg-[#f7f7f7] px-4 py-2 text-xs text-[#404040] transition-colors hover:bg-[#ececec]"
            >
                🖨️ Export PDF Report
            </button>
        </div>
    );
}
