import Link from "next/link";

export default function Home() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center p-8">
            {/* Hero Section */}
            <div className="text-center max-w-4xl mx-auto">
                <div className="mb-6">
                    <span className="px-4 py-2 rounded-full bg-purple-500/20 text-purple-300 text-sm font-medium border border-purple-500/30">
                        🚀 AI-Powered Social Analytics
                    </span>
                </div>

                <h1 className="text-5xl md:text-7xl font-bold text-white mb-6 leading-tight">
                    Your Personal
                    <span className="gradient-text block">Performance Coach</span>
                </h1>

                <p className="text-xl text-gray-300 mb-10 max-w-2xl mx-auto leading-relaxed">
                    Understand <strong className="text-white">why</strong> your content isn&apos;t performing, learn what top creators do differently, and get a personalized action plan to grow faster.
                </p>

                {/* CTA Buttons */}
                <div className="flex flex-col sm:flex-row gap-4 justify-center mb-16">
                    <Link
                        href="/connect"
                        className="px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-xl hover:opacity-90 transition-opacity shadow-lg shadow-purple-500/25"
                    >
                        Connect YouTube Channel
                    </Link>
                    <Link
                        href="/dashboard"
                        className="px-8 py-4 bg-white/10 text-white font-semibold rounded-xl border border-white/20 hover:bg-white/20 transition-colors"
                    >
                        View Demo
                    </Link>
                </div>

                {/* Feature Cards */}
                <div className="grid md:grid-cols-3 gap-6 mt-16">
                    <div className="glass-card p-6 hover-lift">
                        <div className="text-4xl mb-4">🎯</div>
                        <h3 className="text-lg font-semibold text-white mb-2">Diagnose Issues</h3>
                        <p className="text-gray-400 text-sm">
                            Understand if your problem is packaging, retention, topic fit, or consistency.
                        </p>
                    </div>

                    <div className="glass-card p-6 hover-lift">
                        <div className="text-4xl mb-4">🔍</div>
                        <h3 className="text-lg font-semibold text-white mb-2">Competitor Analysis</h3>
                        <p className="text-gray-400 text-sm">
                            See what top performers in your niche do differently and why it works.
                        </p>
                    </div>

                    <div className="glass-card p-6 hover-lift">
                        <div className="text-4xl mb-4">📋</div>
                        <h3 className="text-lg font-semibold text-white mb-2">Action Plan</h3>
                        <p className="text-gray-400 text-sm">
                            Get your next 10 video ideas with hooks, titles, and thumbnail suggestions.
                        </p>
                    </div>
                </div>
            </div>

            {/* Footer */}
            <footer className="absolute bottom-8 text-gray-500 text-sm">
                Built with Next.js, FastAPI, and AI
            </footer>
        </main>
    );
}
