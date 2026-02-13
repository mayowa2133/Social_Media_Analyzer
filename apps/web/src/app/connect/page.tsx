"use client";

import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ConnectPage() {
    const { data: session, status } = useSession();
    const router = useRouter();

    // Redirect if already connected
    useEffect(() => {
        if (session?.accessToken) {
            router.push("/dashboard");
        }
    }, [session, router]);

    const handleConnectYouTube = () => {
        signIn("google", { callbackUrl: "/dashboard" });
    };

    return (
        <div className="min-h-screen p-8">
            {/* Header */}
            <header className="max-w-4xl mx-auto mb-8">
                <Link href="/" className="text-2xl font-bold text-white">
                    <span className="gradient-text">SPC</span>
                </Link>
            </header>

            <main className="max-w-2xl mx-auto">
                <div className="text-center mb-12">
                    <h1 className="text-3xl font-bold text-white mb-4">Connect Your Channels</h1>
                    <p className="text-gray-400">Link your social media accounts to start analyzing your performance.</p>
                </div>

                {/* Loading State */}
                {status === "loading" && (
                    <div className="text-center py-12">
                        <div className="animate-spin w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                        <p className="text-gray-400">Loading...</p>
                    </div>
                )}

                {/* Platform Cards */}
                {status !== "loading" && (
                    <div className="space-y-4">
                        {/* YouTube */}
                        <div className="glass-card p-6 flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-red-600 rounded-xl flex items-center justify-center">
                                    <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-white font-semibold">YouTube</h3>
                                    <p className="text-gray-400 text-sm">Connect via Google OAuth</p>
                                </div>
                            </div>
                            <button
                                onClick={handleConnectYouTube}
                                className="px-6 py-2 bg-red-600 text-white font-medium rounded-lg hover:bg-red-700 transition-colors"
                            >
                                Connect
                            </button>
                        </div>

                        {/* TikTok */}
                        <div className="glass-card p-6 flex items-center justify-between opacity-60">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-black rounded-xl flex items-center justify-center border border-white/20">
                                    <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                                        <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-white font-semibold">TikTok</h3>
                                    <p className="text-gray-400 text-sm">Coming soon (manual upload available)</p>
                                </div>
                            </div>
                            <span className="px-4 py-2 bg-gray-700 text-gray-400 text-sm rounded-lg">Coming Soon</span>
                        </div>

                        {/* Instagram */}
                        <div className="glass-card p-6 flex items-center justify-between opacity-60">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-gradient-to-br from-purple-600 via-pink-500 to-orange-400 rounded-xl flex items-center justify-center">
                                    <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                                        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
                                    </svg>
                                </div>
                                <div>
                                    <h3 className="text-white font-semibold">Instagram</h3>
                                    <p className="text-gray-400 text-sm">Coming soon (manual upload available)</p>
                                </div>
                            </div>
                            <span className="px-4 py-2 bg-gray-700 text-gray-400 text-sm rounded-lg">Coming Soon</span>
                        </div>
                    </div>
                )}

                {/* Manual Upload Option */}
                <div className="mt-8 text-center">
                    <p className="text-gray-400 text-sm mb-4">
                        Don&apos;t want to connect? You can also manually upload your analytics exports.
                    </p>
                    <Link href="/audit/new" className="text-purple-400 hover:text-purple-300 font-medium">
                        Upload manually →
                    </Link>
                </div>
            </main>
        </div>
    );
}
