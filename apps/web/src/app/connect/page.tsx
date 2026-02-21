"use client";

import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import {
    clearStoredAuthSession,
    connectSocialPlatformCallback,
    connectSocialPlatformStart,
    CurrentUserResponse,
    getCurrentUserProfile,
    ingestPlatformMetricsCsv,
    syncSocialConnection,
} from "@/lib/api";
import { StudioAppShell } from "@/components/app-shell";
import { FlowStepper } from "@/components/flow-stepper";

export default function ConnectPage() {
    const { data: session, status } = useSession();
    const [authError, setAuthError] = useState<string | null>(null);
    const [profile, setProfile] = useState<CurrentUserResponse | null>(null);
    const [activeConnectPlatform, setActiveConnectPlatform] = useState<"youtube" | "instagram" | "tiktok">("instagram");
    const [socialPlatform, setSocialPlatform] = useState<"instagram" | "tiktok">("instagram");
    const [socialEmail, setSocialEmail] = useState("");
    const [socialHandle, setSocialHandle] = useState("");
    const [socialDisplayName, setSocialDisplayName] = useState("");
    const [socialFollowers, setSocialFollowers] = useState("");
    const [connectingSocial, setConnectingSocial] = useState(false);
    const [connectingSocialOauth, setConnectingSocialOauth] = useState<"instagram" | "tiktok" | null>(null);
    const [socialMessage, setSocialMessage] = useState<string | null>(null);
    const [metricsPlatform, setMetricsPlatform] = useState<"youtube" | "instagram" | "tiktok">("instagram");
    const [metricsCsvFile, setMetricsCsvFile] = useState<File | null>(null);
    const [importingMetrics, setImportingMetrics] = useState(false);
    const [metricsMessage, setMetricsMessage] = useState<string | null>(null);

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

    useEffect(() => {
        (async () => {
            try {
                const user = await getCurrentUserProfile();
                setProfile(user);
            } catch {
                setProfile(null);
            }
        })();
    }, []);

    const errorMessage =
        authError === "OAuthSignin" || authError === "google"
            ? "Google OAuth is not configured for this frontend. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then restart the web server."
            : authError
              ? "Could not complete Google sign-in. Please try again."
              : null;

    useEffect(() => {
        if (activeConnectPlatform === "instagram" || activeConnectPlatform === "tiktok") {
            setSocialPlatform(activeConnectPlatform);
            setMetricsPlatform(activeConnectPlatform);
        }
        if (activeConnectPlatform === "youtube") {
            setMetricsPlatform("youtube");
        }
    }, [activeConnectPlatform]);

    const handleConnectYouTube = () => {
        signIn("google", { callbackUrl: "/dashboard" });
    };

    async function handleConnectSocial(e: React.FormEvent) {
        e.preventDefault();
        if (!socialEmail.trim() || !socialHandle.trim()) {
            setSocialMessage("Email and handle are required.");
            return;
        }
        setConnectingSocial(true);
        setSocialMessage(null);
        try {
            const response = await syncSocialConnection({
                platform: socialPlatform,
                email: socialEmail.trim(),
                handle: socialHandle.trim(),
                display_name: socialDisplayName.trim() || undefined,
                follower_count: socialFollowers.trim() || undefined,
                name: session?.user?.name || undefined,
                picture: session?.user?.image || undefined,
            });
            const refreshed = await getCurrentUserProfile();
            setProfile(refreshed);
            setSocialMessage(`Connected ${response.platform} as ${response.profile.handle || socialHandle.trim()}.`);
        } catch (err: any) {
            setSocialMessage(err.message || "Could not connect account.");
        } finally {
            setConnectingSocial(false);
        }
    }

    async function handleConnectSocialOAuth(platform: "instagram" | "tiktok") {
        const derivedEmail = socialEmail.trim() || session?.user?.email || "";
        if (!derivedEmail) {
            setSocialMessage("Email is required to complete connector setup.");
            return;
        }
        setConnectingSocialOauth(platform);
        setSocialMessage(null);
        try {
            const start = await connectSocialPlatformStart(platform);
            const response = await connectSocialPlatformCallback(platform, {
                code: "stub_code",
                state: start.state || "stub_state",
                email: derivedEmail,
                name: session?.user?.name || undefined,
                picture: session?.user?.image || undefined,
            });
            const refreshed = await getCurrentUserProfile();
            setProfile(refreshed);
            setSocialMessage(`Connected ${response.platform} via OAuth as ${response.profile.handle || "creator"}.`);
        } catch (err: any) {
            setSocialMessage(err.message || "Could not start OAuth connection.");
        } finally {
            setConnectingSocialOauth(null);
        }
    }

    async function handleImportMetricsCsv(e: React.FormEvent) {
        e.preventDefault();
        if (!metricsCsvFile) {
            setMetricsMessage("Select a CSV file first.");
            return;
        }
        setImportingMetrics(true);
        setMetricsMessage(null);
        try {
            const response = await ingestPlatformMetricsCsv(metricsCsvFile, { platform: metricsPlatform });
            const mappedCount = Object.values(response.normalized_fields || {}).filter((value) => value === "mapped").length;
            setMetricsMessage(
                `Imported ${response.successful_rows}/${response.processed_rows} rows for ${metricsPlatform} (${mappedCount}/8 mapped fields).`
            );
            if (response.failed_rows > 0) {
                setMetricsMessage(
                    `Imported ${response.successful_rows}/${response.processed_rows} rows for ${metricsPlatform} (${response.failed_rows} failed, ${mappedCount}/8 mapped fields).`
                );
            }
        } catch (err: any) {
            setMetricsMessage(err.message || "Could not import metrics CSV.");
        } finally {
            setImportingMetrics(false);
        }
    }

    const connectedPlatforms = profile?.connected_platforms || { youtube: false, instagram: false, tiktok: false };
    const connectedCount = Object.values(connectedPlatforms).filter(Boolean).length;
    const hasConnectedSession = Boolean(session?.accessToken) || connectedCount > 0;

    return (
        <StudioAppShell
            rightSlot={
                <span className="hidden rounded-full border border-[#d5d5d5] bg-white px-3 py-1 text-xs text-[#666] md:inline-flex">
                    Multi-Platform Connect
                </span>
            }
        >
            <div className="grid min-h-[calc(100vh-8.5rem)] grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
                    <aside className="border-b border-[#dfdfdf] bg-[#f8f8f8] p-4 xl:border-b-0 xl:border-r">
                        <h2 className="mb-1 text-sm font-semibold text-[#222]">Connection Checklist</h2>
                        <p className="mb-4 text-xs text-[#777]">
                            Connect at least one platform, then import owned analytics to calibrate scoring.
                        </p>

                        <div className="rounded-2xl border border-[#dfdfdf] bg-white p-3">
                            <ul className="space-y-2 text-xs text-[#575757]">
                                <li>1. Connect YouTube or add Instagram/TikTok handle</li>
                                <li>2. Import your analytics CSV for true shares/saves/retention</li>
                                <li>3. Continue to dashboard, competitors, and audits</li>
                            </ul>
                        </div>

                        <div className="mt-4 rounded-2xl border border-[#dfdfdf] bg-white p-3">
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#666]">Status</h3>
                            <p className="text-sm text-[#454545]">
                                {status === "loading" ? "Loading session..." : "Ready to connect"}
                            </p>
                            {profile?.connected_platforms && (
                                <p className="mt-2 text-xs text-[#666]">
                                    Connected: {profile.connected_platforms.youtube ? "YouTube " : ""}
                                    {profile.connected_platforms.instagram ? "Instagram " : ""}
                                    {profile.connected_platforms.tiktok ? "TikTok" : ""}
                                </p>
                            )}
                        </div>

                        {errorMessage && (
                            <div className="mt-4 rounded-xl border border-[#e3c4c4] bg-[#fff1f1] px-3 py-2 text-xs text-[#7f3a3a]">
                                {errorMessage}
                            </div>
                        )}
                    </aside>

                    <section className="border-b border-[#dfdfdf] bg-[#f2f2f2] px-4 py-4 md:px-6 xl:border-b-0">
                        <div className="mx-auto flex max-w-4xl flex-col gap-5">
                            <FlowStepper />

                            {hasConnectedSession && (
                                <div className="rounded-2xl border border-[#cfe6cf] bg-[#edf7ed] p-4">
                                    <p className="text-sm font-semibold text-[#2e5a33]">
                                        You are already authenticated.
                                    </p>
                                    <p className="mt-1 text-xs text-[#3d6744]">
                                        Continue to your dashboard or stay here to connect additional platforms.
                                    </p>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        <Link
                                            href="/dashboard"
                                            className="rounded-lg border border-[#b9d8b9] bg-white px-3 py-1.5 text-xs font-medium text-[#2f5a33] hover:bg-[#f7fff7]"
                                        >
                                            Continue to Dashboard
                                        </Link>
                                        <Link
                                            href="/competitors"
                                            className="rounded-lg border border-[#b9d8b9] bg-white px-3 py-1.5 text-xs font-medium text-[#2f5a33] hover:bg-[#f7fff7]"
                                        >
                                            Continue to Competitors
                                        </Link>
                                    </div>
                                </div>
                            )}

                            <div className="rounded-[28px] border border-[#dcdcdc] bg-white p-6 shadow-[0_14px_40px_rgba(0,0,0,0.06)] md:p-8">
                                <h1 className="text-2xl font-bold text-[#1f1f1f] md:text-3xl">Connect Your Channels</h1>
                                <p className="mt-2 text-sm text-[#666]">
                                    Four-step setup: choose platform, connect account, import analytics, continue workflow.
                                </p>

                                {status === "loading" ? (
                                    <div className="py-12 text-center">
                                        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#777] border-t-transparent"></div>
                                        <p className="text-sm text-[#717171]">Checking authentication state...</p>
                                    </div>
                                ) : (
                                    <div className="mt-6 space-y-4">
                                        <div className="rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4">
                                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#666]">Step 1</p>
                                            <h2 className="text-sm font-semibold text-[#222]">Choose Platform</h2>
                                            <div className="mt-3 grid gap-2 sm:grid-cols-3">
                                                {(["youtube", "instagram", "tiktok"] as const).map((platform) => (
                                                    <button
                                                        key={platform}
                                                        type="button"
                                                        onClick={() => setActiveConnectPlatform(platform)}
                                                        className={`rounded-xl border px-3 py-2 text-xs font-medium ${
                                                            activeConnectPlatform === platform
                                                                ? "border-[#b9b9b9] bg-white text-[#1f1f1f]"
                                                                : "border-[#d9d9d9] bg-[#f5f5f5] text-[#555] hover:bg-[#efefef]"
                                                        }`}
                                                    >
                                                        {platform === "youtube" ? "YouTube" : platform === "instagram" ? "Instagram" : "TikTok"}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4">
                                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#666]">Step 2</p>
                                            <h2 className="text-sm font-semibold text-[#222]">
                                                {activeConnectPlatform === "youtube" ? "Connect YouTube" : `Connect ${activeConnectPlatform === "instagram" ? "Instagram" : "TikTok"}`}
                                            </h2>

                                            {activeConnectPlatform === "youtube" ? (
                                                <div className="mt-3 flex items-center justify-between gap-4 rounded-xl border border-[#e3e3e3] bg-white p-4">
                                                    <div>
                                                        <p className="text-sm font-semibold text-[#222]">YouTube OAuth</p>
                                                        <p className="text-xs text-[#666]">Connect via Google sign-in.</p>
                                                    </div>
                                                    <button
                                                        onClick={handleConnectYouTube}
                                                        className="rounded-xl bg-[#1f1f1f] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#111]"
                                                    >
                                                        Connect
                                                    </button>
                                                </div>
                                            ) : (
                                                <form
                                                    onSubmit={handleConnectSocial}
                                                    className="mt-3 rounded-xl border border-[#e3e3e3] bg-white p-3"
                                                >
                                                    <div className="mb-3 rounded-xl border border-[#e7e7e7] bg-[#fafafa] p-3">
                                                        <p className="text-[11px] text-[#666]">
                                                            OAuth availability: Instagram {profile?.connector_capabilities?.instagram_oauth_available ? "enabled" : "disabled"} · TikTok {profile?.connector_capabilities?.tiktok_oauth_available ? "enabled" : "disabled"}
                                                        </p>
                                                        <button
                                                            type="button"
                                                            onClick={() => void handleConnectSocialOAuth(activeConnectPlatform as "instagram" | "tiktok")}
                                                            disabled={
                                                                connectingSocialOauth !== null ||
                                                                (activeConnectPlatform === "instagram"
                                                                    ? !profile?.connector_capabilities?.instagram_oauth_available
                                                                    : !profile?.connector_capabilities?.tiktok_oauth_available)
                                                            }
                                                            className="mt-2 rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#444] hover:bg-[#efefef] disabled:opacity-50"
                                                        >
                                                            {connectingSocialOauth === activeConnectPlatform
                                                                ? "Connecting..."
                                                                : `Connect ${activeConnectPlatform === "instagram" ? "Instagram" : "TikTok"} OAuth`}
                                                        </button>
                                                        <p className="mt-2 text-[11px] text-[#777]">
                                                            If OAuth is disabled, manual sync below remains fully supported.
                                                        </p>
                                                    </div>
                                                    <div className="grid gap-2 md:grid-cols-2">
                                                        <input
                                                            type="email"
                                                            value={socialEmail}
                                                            onChange={(e) => setSocialEmail(e.target.value)}
                                                            placeholder="Email"
                                                            className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                        />
                                                        <input
                                                            value={socialHandle}
                                                            onChange={(e) => setSocialHandle(e.target.value)}
                                                            placeholder="@handle"
                                                            className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                        />
                                                        <input
                                                            value={socialDisplayName}
                                                            onChange={(e) => setSocialDisplayName(e.target.value)}
                                                            placeholder="Display name (optional)"
                                                            className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                        />
                                                        <input
                                                            value={socialFollowers}
                                                            onChange={(e) => setSocialFollowers(e.target.value)}
                                                            placeholder="Follower count (optional)"
                                                            className="rounded-xl border border-[#d8d8d8] bg-white px-3 py-2 text-xs text-[#222] placeholder:text-[#9a9a9a] focus:border-[#b8b8b8] focus:outline-none"
                                                        />
                                                    </div>
                                                    <button
                                                        type="submit"
                                                        disabled={connectingSocial || !socialEmail.trim() || !socialHandle.trim()}
                                                        className="mt-3 rounded-xl bg-[#1f1f1f] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#111] disabled:opacity-50"
                                                    >
                                                        {connectingSocial ? "Connecting..." : "Connect Account"}
                                                    </button>
                                                    {socialMessage && (
                                                        <p className="mt-2 text-xs text-[#5a5a5a]">{socialMessage}</p>
                                                    )}
                                                </form>
                                            )}
                                        </div>

                                        <div className="rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4">
                                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#666]">Step 3</p>
                                            <h2 className="text-sm font-semibold text-[#222]">Import Owned Analytics (Optional)</h2>
                                            <p className="mt-1 text-xs text-[#666]">
                                                Upload exported CSV analytics to ingest true views/likes/comments/shares/saves/retention.
                                            </p>
                                            <form onSubmit={handleImportMetricsCsv} className="mt-3 space-y-2">
                                                <select
                                                    value={metricsPlatform}
                                                    onChange={(e) => setMetricsPlatform(e.target.value as "youtube" | "instagram" | "tiktok")}
                                                    className="w-full rounded-xl border border-[#d8d8d8] bg-white px-2 py-2 text-xs text-[#222] focus:border-[#b8b8b8] focus:outline-none"
                                                >
                                                    <option value="youtube">YouTube CSV</option>
                                                    <option value="instagram">Instagram CSV</option>
                                                    <option value="tiktok">TikTok CSV</option>
                                                </select>
                                                <input
                                                    type="file"
                                                    accept=".csv,text/csv"
                                                    onChange={(e) => setMetricsCsvFile(e.target.files?.[0] || null)}
                                                    className="w-full rounded-xl border border-[#d8d8d8] bg-white px-2 py-2 text-xs text-[#222]"
                                                />
                                                <button
                                                    type="submit"
                                                    disabled={importingMetrics || !metricsCsvFile}
                                                    className="inline-flex rounded-xl border border-[#d9d9d9] bg-[#f8f8f8] px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef] disabled:opacity-50"
                                                >
                                                    {importingMetrics ? "Importing..." : "Import CSV Metrics"}
                                                </button>
                                            </form>
                                            {metricsMessage && (
                                                <p className="mt-2 text-xs text-[#5a5a5a]">{metricsMessage}</p>
                                            )}
                                        </div>

                                        <div className="rounded-2xl border border-[#dcdcdc] bg-[#fafafa] p-4">
                                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#666]">Step 4</p>
                                            <h2 className="text-sm font-semibold text-[#222]">Continue Workflow</h2>
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                <Link
                                                    href="/dashboard"
                                                    className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#555] hover:bg-[#efefef]"
                                                >
                                                    Go to Dashboard
                                                </Link>
                                                <Link
                                                    href="/competitors"
                                                    className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#555] hover:bg-[#efefef]"
                                                >
                                                    Add Competitors
                                                </Link>
                                                <Link
                                                    href="/research"
                                                    className="rounded-lg border border-[#d9d9d9] bg-white px-3 py-1.5 text-xs text-[#555] hover:bg-[#efefef]"
                                                >
                                                    Open Research
                                                </Link>
                                            </div>
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
                            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#676767]">After Connect</h3>
                            <ul className="space-y-1 text-xs text-[#6d6d6d]">
                                <li>1. Add 3-10 competitors in your platform.</li>
                                <li>2. Generate scripts from research items.</li>
                                <li>3. Run an audit and post outcomes.</li>
                            </ul>
                            <div className="mt-3 flex flex-wrap gap-2">
                                <Link
                                    href="/competitors"
                                    className="inline-flex rounded-xl border border-[#d9d9d9] bg-white px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Open Competitors
                                </Link>
                                <Link
                                    href="/audit/new"
                                    className="inline-flex rounded-xl border border-[#d9d9d9] bg-white px-3 py-2 text-sm font-medium text-[#2f2f2f] hover:bg-[#efefef]"
                                >
                                    Open Audit Workspace
                                </Link>
                            </div>
                        </div>
                    </aside>
            </div>
        </StudioAppShell>
    );
}
