"use client";

import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearStoredAuthSession } from "@/lib/api";

export default function ConnectPage() {
    const { data: session, status } = useSession();
    const router = useRouter();
    const [authError, setAuthError] = useState<string | null>(null);

    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        const value = new URLSearchParams(window.location.search).get("error");
        setAuthError(value);
    }, []);

    useEffect(() => {
        if (status === "unauthenticated") {
            clearStoredAuthSession();
        }
    }, [status]);

    const errorMessage =
        authError === "OAuthSignin" || authError === "google"
            ? "Google OAuth is not configured for this frontend. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then restart the web server."
            : authError
              ? "Could not complete Google sign-in. Please try again."
              : null;

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
        <div className="min-h-screen bg-[#e8e8e8] px-3 py-4 md:px-8 md:py-6">
            <div className="mx-auto w-full max-w-[1500px] overflow-hidden rounded-[30px] border border-[#d8d8d8] bg-[#f5f5f5] shadow-[0_35px_90px_rgba(0,0,0,0.12)]">
                <header className="flex h-16 items-center justify-between border-b border-[#dfdfdf] bg-[#fafafa] px-4 md:px-6">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="text-lg font-bold text-[#1f1f1f]">
                            SPC Studio
                        </Link>
                        <nav className="hidden items-center gap-4 text-sm text-[#6b6b6b] md:flex">
                            <Link href="/dashboard" className="hover:text-[#151515]">Dashboard</Link>
                            <Link href="/competitors" className="hover:text-[#151515]">Competitors</Link>
                            <Link href="/audit/new" className="hover:text-[#151515]">Audit Workspace</Link>
                            <Link href="/connect" className="font-medium text-[#1b1b1b]">Connect</Link>
                        </nav>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="hidden rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666] md:inline-flex">
                            YouTube-First MVP
                        </span>
                    </div>
                </header>

                <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
                    <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                        <h2 className="mb-1 text-sm font-semibold text-[#222]">Connection Checklist</h2>
                        <p className="mb-4 text-xs text-[#777]">
                            Link YouTube to unlock diagnosis, competitor benchmarks, and audits.
                        </p>

                        <div className="rounded-2xl border border-[#dfdfdf] bg-white p-3">
                            <ul className="space-y-2 text-xs text-[#575757]">
                                <li>1. Use Google account with your channel</li>
                                <li>2. Approve requested OAuth scopes</li>
                                <li>3. Return here and continue to dashboard</li>
                            </ul>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dfdfdf] bg-white p-3">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#666]">Status</h3>
                            <p className="text-sm text-[#454545]">
                                {status === "loading" ? "Loading session..." : "Ready to connect"}
                            </p>
                        </div>

                        {errorMessage && (
                            <div className="mt-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                {errorMessage}
                            </div>
                        )}
                    </aside>

                    <section className="border-b border-[#dfdfdf] bg-[#f2f2f2] px-4 py-4 md:px-6 xl:border-b-0">
                        <div className="mx-auto flex max-w-4xl flex-col gap-5">
                            <div className="rounded-[28px] border border-[#dcdcdc] bg-white p-6 shadow-[0_14px_40px_rgba(0,0,0,0.06)] md:p-8">
                                <h1 className="text-2xl font-bold text-[#1f1f1f] md:text-3xl">Connect Your Channels</h1>
                                <p className="mt-2 text-sm text-[#666]">
                                    Start by connecting YouTube through Google OAuth. TikTok and Instagram stay manual for now.
                                </p>

                                {status === "loading" ? (
                                    <div className="py-12 text-center">
                                        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#777] border-t-transparent"></div>
                                        <p className="text-sm text-[#717171]">Checking authentication state...</p>
                                    </div>
                                ) : (
                                    <div className="mt-6 space-y-4">
                                        <div className="flex items-center justify-between gap-4 rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4">
                                            <div className="flex items-center gap-4">
                                                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#d93b3b] text-white">
                                                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                                                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
                                                    </svg>
                                                </div>
                                                <div>
                                                    <h2 className="text-sm font-semibold text-[#222]">YouTube</h2>
                                                    <p className="text-xs text-[#666]">Connect via Google OAuth</p>
                                                </div>
                                            </div>
                                            <button
                                                onClick={handleConnectYouTube}
                                                className="rounded-xl bg-[#1f1f1f] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#111]"
                                            >
                                                Connect
                                            </button>
                                        </div>

                                        <div className="flex items-center justify-between gap-4 rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4 opacity-70">
                                            <div>
                                                <h2 className="text-sm font-semibold text-[#222]">TikTok</h2>
                                                <p className="text-xs text-[#666]">Coming soon (manual upload available)</p>
                                            </div>
                                            <span className="rounded-lg border border-[#dbdbdb] bg-white px-3 py-1 text-xs text-[#6f6f6f]">
                                                Coming Soon
                                            </span>
                                        </div>

                                        <div className="flex items-center justify-between gap-4 rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4 opacity-70">
                                            <div>
                                                <h2 className="text-sm font-semibold text-[#222]">Instagram</h2>
                                                <p className="text-xs text-[#666]">Coming soon (manual upload available)</p>
                                            </div>
                                            <span className="rounded-lg border border-[#dbdbdb] bg-white px-3 py-1 text-xs text-[#6f6f6f]">
                                                Coming Soon
                                            </span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </section>

                    <aside className="bg-[#f8f8f8] p-4 xl:border-l xl:border-[#dfdfdf]">
                        <div className="rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-sm font-semibold text-[#222]">What You Unlock</h3>
                            <ul className="space-y-1 text-xs text-[#666]">
                                <li>Diagnosis from channel performance data</li>
                                <li>Competitor gap and hook intelligence</li>
                                <li>Audit workspace and consolidated reports</li>
                            </ul>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dcdcdc] bg-white p-4">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">Manual Path</h3>
                            <p className="mb-3 text-xs text-[#6d6d6d]">
                                Skip OAuth and run a video audit directly using URL or file upload.
                            </p>
                            <Link
                                href="/audit/new"
                                className="inline-flex rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                            >
                                Open Audit Workspace
                            </Link>
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
