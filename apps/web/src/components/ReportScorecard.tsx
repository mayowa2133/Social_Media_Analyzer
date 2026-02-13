"use client";

interface ReportScorecardProps {
    score: number;
    auditId: string;
    createdAt?: string | null;
}

export function ReportScorecard({ score, auditId, createdAt }: ReportScorecardProps) {
    const getScoreColor = (s: number) => {
        if (s >= 80) return "text-green-400";
        if (s >= 50) return "text-yellow-400";
        return "text-red-400";
    };

    const formattedDate = createdAt ? new Date(createdAt).toLocaleDateString() : "N/A";

    return (
        <div className="glass-card p-8 flex flex-col items-center text-center relative overflow-hidden">
            {/* Background Glow */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-purple-600/20 blur-3xl -mr-16 -mt-16 rounded-full"></div>

            <div className="text-gray-400 text-sm uppercase tracking-widest mb-2 font-medium">Audit Scorecard</div>
            <div className={`text-7xl font-black mb-4 ${getScoreColor(score)}`}>
                {score}<span className="text-3xl font-light text-white/50">/100</span>
            </div>

            <div className="h-2 w-48 bg-white/5 rounded-full mb-6 overflow-hidden">
                <div
                    className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-1000"
                    style={{ width: `${score}%` }}
                ></div>
            </div>

            <div className="flex gap-4 text-xs text-gray-500">
                <span>AUDIT ID: <span className="text-gray-300">{auditId.substring(0, 8)}</span></span>
                <span>•</span>
                <span>DATE: <span className="text-gray-300">{formattedDate}</span></span>
            </div>

            <button
                onClick={() => window.print()}
                className="mt-8 px-4 py-2 border border-white/10 hover:bg-white/5 rounded-lg text-xs text-white/50 hover:text-white transition-all no-print"
            >
                🖨️ Export PDF Report
            </button>
        </div>
    );
}
