/**
 * API client for communication with the FastAPI backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const USER_ID_STORAGE_KEY = "spc_user_id";
const BACKEND_SESSION_TOKEN_STORAGE_KEY = "spc_backend_session_token";

interface ApiOptions {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: any;
    accessToken?: string;
}

function safeEncode(value: string): string {
    return encodeURIComponent(value);
}

function resolveUserId(userId?: string): string {
    const resolved = userId || getCurrentUserId();
    if (!resolved) {
        throw new Error("No authenticated user found. Connect at least one platform to continue.");
    }
    return resolved;
}

export function setCurrentUserId(userId: string) {
    if (typeof window !== "undefined") {
        localStorage.setItem(USER_ID_STORAGE_KEY, userId);
    }
}

export function getCurrentUserId(): string | null {
    if (typeof window === "undefined") {
        return null;
    }
    return localStorage.getItem(USER_ID_STORAGE_KEY);
}

export function setBackendSessionToken(token: string) {
    if (typeof window !== "undefined") {
        localStorage.setItem(BACKEND_SESSION_TOKEN_STORAGE_KEY, token);
    }
}

export function getBackendSessionToken(): string | null {
    if (typeof window === "undefined") {
        return null;
    }
    return localStorage.getItem(BACKEND_SESSION_TOKEN_STORAGE_KEY);
}

export function clearStoredAuthSession() {
    if (typeof window !== "undefined") {
        localStorage.removeItem(USER_ID_STORAGE_KEY);
        localStorage.removeItem(BACKEND_SESSION_TOKEN_STORAGE_KEY);
    }
}

async function fetchApi<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
    const { method = "GET", body, accessToken } = options;

    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };

    const bearerToken = accessToken || getBackendSessionToken();
    if (bearerToken) {
        headers.Authorization = `Bearer ${bearerToken}`;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });

    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `API error: ${response.status}`);
    }

    return response.json();
}

async function fetchFormApi<T>(
    endpoint: string,
    formData: FormData,
    options: { accessToken?: string } = {}
): Promise<T> {
    const headers: Record<string, string> = {};
    const bearerToken = options.accessToken || getBackendSessionToken();
    if (bearerToken) {
        headers.Authorization = `Bearer ${bearerToken}`;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers,
        body: formData,
        cache: "no-store",
    });

    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `API error: ${response.status}`);
    }

    return response.json();
}

// ==================== Auth APIs ====================

export interface SyncYouTubeSessionRequest {
    access_token: string;
    refresh_token?: string;
    expires_at?: number;
    scope?: string;
    user_id?: string;
    email: string;
    name?: string;
    picture?: string;
}

export interface SyncYouTubeSessionResponse {
    user_id: string;
    email: string;
    youtube_connected: boolean;
    session_token: string;
    session_expires_at: number;
    channel_id?: string;
    channel_title?: string;
    channel_handle?: string;
    subscriber_count?: string;
    thumbnail_url?: string;
}

export interface SyncSocialConnectionRequest {
    platform: "instagram" | "tiktok";
    handle: string;
    external_id?: string;
    display_name?: string;
    follower_count?: string;
    profile_picture_url?: string;
    access_token?: string;
    refresh_token?: string;
    expires_at?: number;
    scope?: string;
    user_id?: string;
    email: string;
    name?: string;
    picture?: string;
}

export interface SyncSocialConnectionResponse {
    user_id: string;
    email: string;
    platform: "instagram" | "tiktok";
    connected: boolean;
    session_token: string;
    session_expires_at: number;
    profile: {
        platform: string;
        external_id?: string;
        handle?: string;
        display_name?: string;
        subscriber_count?: string;
        profile_picture_url?: string;
    };
}

export interface CurrentUserResponse {
    user_id: string;
    email: string;
    name?: string;
    picture?: string;
    youtube_connected: boolean;
    channel_id?: string;
    channel_title?: string;
    channel_handle?: string;
    subscriber_count?: string;
    thumbnail_url?: string;
    instagram_connected?: boolean;
    tiktok_connected?: boolean;
    connected_platforms?: {
        youtube: boolean;
        instagram: boolean;
        tiktok: boolean;
    };
    profiles?: Array<{
        platform: "youtube" | "instagram" | "tiktok";
        external_id?: string;
        handle?: string;
        display_name?: string;
        subscriber_count?: string;
        profile_picture_url?: string;
    }>;
    connector_capabilities?: {
        instagram_oauth_available: boolean;
        tiktok_oauth_available: boolean;
    };
}

export interface ConnectPlatformStartResponse {
    platform: "instagram" | "tiktok";
    oauth_available: boolean;
    connect_url?: string | null;
    state?: string | null;
    provider?: string | null;
    setup_message: string;
    manual_fallback_supported: boolean;
}

export interface ConnectPlatformCallbackRequest {
    code: string;
    state: string;
    email?: string;
    name?: string;
    picture?: string;
    user_id?: string;
    redirect_uri?: string;
}

export interface FlowStateResponse {
    connected_platforms: Record<string, boolean>;
    has_competitors_by_platform: Record<string, boolean>;
    has_research_items_by_platform: Record<string, boolean>;
    has_script_variants: boolean;
    has_completed_audit: boolean;
    has_report: boolean;
    has_outcomes: boolean;
    next_best_action:
        | "connect_platform"
        | "add_competitors"
        | "import_research"
        | "generate_script"
        | "run_audit"
        | "post_outcome"
        | "optimize_loop";
    next_best_href: string;
    completion_percent: number;
    stage_completion: Record<string, boolean>;
    totals: Record<string, number>;
    preferred_platform?: "youtube" | "instagram" | "tiktok" | null;
}

export async function syncYouTubeSession(payload: SyncYouTubeSessionRequest): Promise<SyncYouTubeSessionResponse> {
    const result = await fetchApi<SyncYouTubeSessionResponse>("/auth/sync/youtube", {
        method: "POST",
        body: payload,
    });
    setCurrentUserId(result.user_id);
    setBackendSessionToken(result.session_token);
    return result;
}

export async function getCurrentUserProfile(): Promise<CurrentUserResponse> {
    return fetchApi<CurrentUserResponse>("/auth/me");
}

export async function syncSocialConnection(payload: SyncSocialConnectionRequest): Promise<SyncSocialConnectionResponse> {
    const result = await fetchApi<SyncSocialConnectionResponse>("/auth/sync/social", {
        method: "POST",
        body: payload,
    });
    setCurrentUserId(result.user_id);
    setBackendSessionToken(result.session_token);
    return result;
}

export async function connectSocialPlatformStart(
    platform: "instagram" | "tiktok"
): Promise<ConnectPlatformStartResponse> {
    return fetchApi<ConnectPlatformStartResponse>(`/auth/connect/${platform}/start`, {
        method: "POST",
    });
}

export async function connectSocialPlatformCallback(
    platform: "instagram" | "tiktok",
    payload: ConnectPlatformCallbackRequest
): Promise<SyncSocialConnectionResponse> {
    const result = await fetchApi<SyncSocialConnectionResponse>(`/auth/connect/${platform}/callback`, {
        method: "POST",
        body: payload,
    });
    setCurrentUserId(result.user_id);
    setBackendSessionToken(result.session_token);
    return result;
}

export async function getFlowState(): Promise<FlowStateResponse> {
    return fetchApi<FlowStateResponse>("/ux/flow_state");
}

export async function logoutBackendSession(): Promise<void> {
    try {
        await fetchApi<{ message: string }>("/auth/logout", { method: "POST" });
    } finally {
        clearStoredAuthSession();
    }
}

// ==================== Channel APIs ====================

export interface ChannelInfo {
    channel_id: string;
    title: string;
    description?: string;
    custom_url?: string;
    subscriber_count?: number;
    video_count?: number;
    view_count?: number;
    thumbnail_url?: string;
}

export interface VideoInfo {
    video_id: string;
    title: string;
    description?: string;
    published_at: string;
    duration_seconds: number;
    thumbnail_url?: string;
    view_count: number;
    like_count: number;
    comment_count: number;
}

export interface Competitor {
    id: string;
    channel_id: string;
    title: string;
    platform: "youtube" | "instagram" | "tiktok";
    custom_url?: string;
    subscriber_count?: number | string;
    video_count?: number;
    thumbnail_url?: string;
    created_at: string;
}

export type CompetitorAnalysisPlatform = "youtube" | "instagram" | "tiktok";

export async function resolveChannel(url: string): Promise<{ channel_id?: string; title?: string; error?: string }> {
    return fetchApi("/youtube/resolve", {
        method: "POST",
        body: { url },
    });
}

export async function getChannelInfo(channelId: string): Promise<ChannelInfo> {
    return fetchApi(`/youtube/channel/${channelId}`);
}

export async function getChannelVideos(channelId: string, limit = 20): Promise<VideoInfo[]> {
    return fetchApi(`/youtube/channel/${channelId}/videos?limit=${limit}`);
}

export async function addCompetitor(channelUrl: string, userId?: string): Promise<Competitor> {
    return fetchApi("/competitors/", {
        method: "POST",
        body: { channel_url: channelUrl, user_id: resolveUserId(userId) },
    });
}

export async function getCompetitors(userId?: string): Promise<Competitor[]> {
    const qUserId = resolveUserId(userId);
    return fetchApi(`/competitors/?user_id=${safeEncode(qUserId)}`);
}

export async function removeCompetitor(competitorId: string, userId?: string): Promise<void> {
    const qUserId = resolveUserId(userId);
    return fetchApi(`/competitors/${competitorId}?user_id=${safeEncode(qUserId)}`, {
        method: "DELETE",
    });
}

export async function getCompetitorVideos(competitorId: string, limit = 10, userId?: string): Promise<VideoInfo[]> {
    const qUserId = resolveUserId(userId);
    return fetchApi(`/competitors/${competitorId}/videos?limit=${limit}&user_id=${safeEncode(qUserId)}`);
}

export interface HookPattern {
    pattern: string;
    frequency: number;
    competitor_count: number;
    avg_views: number;
    examples: string[];
    template: string;
}

export interface HookCompetitorExample {
    competitor: string;
    hooks: string[];
}

export interface HookFormatProfile {
    format: "short_form" | "long_form" | "unknown";
    label: string;
    video_count: number;
    summary: string;
    common_patterns: HookPattern[];
    recommended_hooks: string[];
    competitor_examples: HookCompetitorExample[];
}

export interface HookIntelligence {
    summary: string;
    format_definition?: string;
    common_patterns: HookPattern[];
    recommended_hooks: string[];
    competitor_examples: HookCompetitorExample[];
    format_breakdown?: {
        short_form: HookFormatProfile;
        long_form: HookFormatProfile;
    };
}

export interface WinnerPatternTopic {
    topic: string;
    count: number;
    avg_views_per_day: number;
}

export interface WinnerPatternVideo {
    channel: string;
    title: string;
    views: number;
    views_per_day: number;
    hook_pattern: string;
}

export interface WinnerPatternSignals {
    summary: string;
    sample_size: number;
    top_topics_by_velocity: WinnerPatternTopic[];
    hook_velocity_correlation: number;
    top_videos_by_velocity: WinnerPatternVideo[];
}

export interface FrameworkPlaybook {
    summary: string;
    stage_adoption: {
        authority_hook: number;
        fast_proof: number;
        framework_steps: number;
        open_loop: number;
    };
    cta_distribution: Record<string, number>;
    dominant_sequence: string[];
    execution_notes: string[];
}

export interface RepurposePlatformPlan {
    duration_target_s: number;
    hook_template: string;
    edit_directives: string[];
}

export interface BlueprintRepurposePlan {
    summary: string;
    core_angle: string;
    youtube_shorts: RepurposePlatformPlan;
    instagram_reels: RepurposePlatformPlan;
    tiktok: RepurposePlatformPlan;
}

export interface BlueprintTranscriptQuality {
    sample_size: number;
    by_source: Record<string, number>;
    transcript_coverage_ratio: number;
    fallback_ratio: number;
    notes: string[];
}

export interface BlueprintVelocityAction {
    title: string;
    why: string;
    evidence: string[];
    execution_steps: string[];
    target_metric: string;
    expected_effect: string;
}

export interface CompetitorSeries {
    series_key: string;
    series_key_slug: string;
    video_count: number;
    competitor_count: number;
    avg_views: number;
    avg_views_per_day: number;
    top_titles: string[];
    channels: string[];
    recommended_angle: string;
}

export interface SeriesIntelligence {
    summary: string;
    sample_size: number;
    total_detected_series: number;
    series: CompetitorSeries[];
}

export interface BlueprintResult {
    gap_analysis: string[];
    content_pillars: string[];
    video_ideas: { title: string; concept: string }[];
    hook_intelligence?: HookIntelligence;
    winner_pattern_signals?: WinnerPatternSignals;
    framework_playbook?: FrameworkPlaybook;
    repurpose_plan?: BlueprintRepurposePlan;
    transcript_quality?: BlueprintTranscriptQuality;
    velocity_actions?: BlueprintVelocityAction[];
    series_intelligence?: SeriesIntelligence;
    dataset_summary?: {
        platform: "youtube" | "instagram" | "tiktok";
        research_items_scanned?: number;
        mapped_competitor_items: number;
        mapped_user_items: number;
        data_quality_tier: "high" | "medium" | "low";
    };
}

export interface RecommendedCompetitor {
    channel_id: string;
    title: string;
    custom_url?: string;
    subscriber_count: number;
    video_count: number;
    view_count: number;
    avg_views_per_video: number;
    thumbnail_url?: string;
    already_tracked: boolean;
}

export interface RecommendCompetitorsResponse {
    niche: string;
    page: number;
    limit: number;
    total_count: number;
    has_more: boolean;
    recommendations: RecommendedCompetitor[];
}

export interface DiscoverCompetitorCandidate {
    external_id: string;
    handle: string;
    display_name: string;
    subscriber_count: number;
    video_count: number;
    view_count: number;
    avg_views_per_video: number;
    thumbnail_url?: string;
    source: string;
    quality_score: number;
    already_tracked: boolean;
    source_count?: number;
    source_labels?: string[];
    confidence_tier?: "low" | "medium" | "high";
    evidence?: string[];
}

export interface DiscoverCompetitorsResponse {
    platform: "youtube" | "instagram" | "tiktok";
    query: string;
    page: number;
    limit: number;
    total_count: number;
    has_more: boolean;
    candidates: DiscoverCompetitorCandidate[];
}

export type CompetitorSuggestionSortBy =
    | "subscriber_count"
    | "avg_views_per_video"
    | "view_count";
export type CompetitorSuggestionSortDirection = "desc" | "asc";

export interface SeriesCalendarEpisode {
    episode_number: number;
    working_title: string;
    publish_date: string;
    status: "planned" | "drafted" | "published";
    checklist: string[];
}

export interface SeriesCalendarResult {
    series_title: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    cadence_days: number;
    episodes: SeriesCalendarEpisode[];
}

export interface NextSeriesEpisodeResult {
    series_title: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    episode_number: number;
    working_title: string;
    hook_line: string;
    outline: string[];
    cta: string;
}

export async function generateBlueprint(
    userId?: string,
    platform: CompetitorAnalysisPlatform = "youtube"
): Promise<BlueprintResult> {
    return fetchApi("/competitors/blueprint", {
        method: "POST",
        body: { user_id: resolveUserId(userId), platform },
    });
}

export interface SeriesPlanRequest {
    userId?: string;
    mode: "scratch" | "competitor_template";
    niche: string;
    audience: string;
    objective: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    episodes: number;
    templateSeriesKey?: string;
}

export interface SeriesPlanEpisode {
    episode_number: number;
    working_title: string;
    hook_template: string;
    content_goal: string;
    proof_idea: string;
    duration_target_s: number;
    cta: string;
}

export interface SeriesPlanResult {
    mode: "scratch" | "competitor_template";
    series_title: string;
    series_thesis: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    episodes_count: number;
    publishing_cadence: string;
    success_metrics: string[];
    why_this_will_work: string[];
    episodes: SeriesPlanEpisode[];
    source_template?: {
        series_key: string;
        video_count: number;
        competitor_count: number;
        channels: string[];
        top_titles: string[];
    };
}

export interface ViralScriptRequest {
    userId?: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    topic: string;
    audience: string;
    objective: string;
    tone: "bold" | "expert" | "conversational";
    templateSeriesKey?: string;
    desiredDurationS?: number;
}

export interface ViralScriptSection {
    section: string;
    time_window: string;
    text: string;
}

export interface ViralScriptResult {
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    topic: string;
    audience: string;
    objective: string;
    tone: "bold" | "expert" | "conversational";
    duration_target_s: number;
    hook_deadline_s: number;
    hook_template: string;
    hook_line: string;
    script_sections: ViralScriptSection[];
    on_screen_text: string[];
    shot_list: string[];
    caption_options: string[];
    hashtags: string[];
    cta_line: string;
    score_breakdown: {
        hook_strength: number;
        retention_design: number;
        shareability: number;
        overall: number;
    };
    improvement_notes: string[];
    competitor_template?: {
        series_key: string;
        channels: string[];
        top_titles: string[];
    };
}

export async function getCompetitorSeriesInsights(
    userId?: string,
    platform: CompetitorAnalysisPlatform = "youtube"
): Promise<SeriesIntelligence> {
    return fetchApi<SeriesIntelligence>("/competitors/series", {
        method: "POST",
        body: { user_id: resolveUserId(userId), platform },
    });
}

export interface ImportCompetitorsFromResearchResponse {
    platform: "instagram" | "tiktok";
    scanned_items: number;
    candidate_creators: number;
    imported_count: number;
    skipped_existing: number;
    skipped_low_volume: number;
    competitors: Competitor[];
}

export async function importCompetitorsFromResearch(payload: {
    platform: "instagram" | "tiktok";
    niche?: string;
    minItemsPerCreator?: number;
    topN?: number;
    userId?: string;
}): Promise<ImportCompetitorsFromResearchResponse> {
    return fetchApi<ImportCompetitorsFromResearchResponse>("/competitors/import_from_research", {
        method: "POST",
        body: {
            user_id: resolveUserId(payload.userId),
            platform: payload.platform,
            niche: payload.niche,
            min_items_per_creator: payload.minItemsPerCreator,
            top_n: payload.topN,
        },
    });
}

export async function generateSeriesPlan(payload: SeriesPlanRequest): Promise<SeriesPlanResult> {
    return fetchApi<SeriesPlanResult>("/competitors/series/plan", {
        method: "POST",
        body: {
            user_id: resolveUserId(payload.userId),
            mode: payload.mode,
            niche: payload.niche,
            audience: payload.audience,
            objective: payload.objective,
            platform: payload.platform,
            episodes: payload.episodes,
            template_series_key: payload.templateSeriesKey,
        },
    });
}

export async function generateViralScript(payload: ViralScriptRequest): Promise<ViralScriptResult> {
    return fetchApi<ViralScriptResult>("/competitors/script/generate", {
        method: "POST",
        body: {
            user_id: resolveUserId(payload.userId),
            platform: payload.platform,
            topic: payload.topic,
            audience: payload.audience,
            objective: payload.objective,
            tone: payload.tone,
            template_series_key: payload.templateSeriesKey,
            desired_duration_s: payload.desiredDurationS,
        },
    });
}

export async function recommendCompetitors(
    niche: string,
    options: {
        userId?: string;
        platform?: "youtube" | "instagram" | "tiktok";
        limit?: number;
        page?: number;
        sortBy?: CompetitorSuggestionSortBy;
        sortDirection?: CompetitorSuggestionSortDirection;
    } = {}
): Promise<RecommendCompetitorsResponse> {
    return fetchApi<RecommendCompetitorsResponse>(
        "/competitors/recommend",
        {
            method: "POST",
            body: {
                niche,
                platform: options.platform || "youtube",
                user_id: resolveUserId(options.userId),
                limit: options.limit ?? 8,
                page: options.page ?? 1,
                sort_by: options.sortBy ?? "subscriber_count",
                sort_direction: options.sortDirection ?? "desc",
            },
        }
    );
}

export async function discoverCompetitors(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    query?: string;
    page?: number;
    limit?: number;
    userId?: string;
}): Promise<DiscoverCompetitorsResponse> {
    return fetchApi<DiscoverCompetitorsResponse>("/competitors/discover", {
        method: "POST",
        body: {
            platform: payload.platform,
            query: payload.query || "",
            page: payload.page ?? 1,
            limit: payload.limit ?? 12,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function addManualCompetitor(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    handle: string;
    display_name?: string;
    external_id?: string;
    subscriber_count?: number;
    thumbnail_url?: string;
    userId?: string;
}): Promise<Competitor> {
    return fetchApi<Competitor>("/competitors/manual", {
        method: "POST",
        body: {
            platform: payload.platform,
            handle: payload.handle,
            display_name: payload.display_name,
            external_id: payload.external_id,
            subscriber_count: payload.subscriber_count,
            thumbnail_url: payload.thumbnail_url,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function buildSeriesCalendar(payload: {
    seriesTitle: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    startDate: string;
    cadenceDays: number;
    episodes: Array<Record<string, any>>;
    userId?: string;
}): Promise<SeriesCalendarResult> {
    return fetchApi<SeriesCalendarResult>("/competitors/series/calendar", {
        method: "POST",
        body: {
            user_id: resolveUserId(payload.userId),
            series_title: payload.seriesTitle,
            platform: payload.platform,
            start_date: payload.startDate,
            cadence_days: payload.cadenceDays,
            episodes: payload.episodes,
        },
    });
}

export async function getNextSeriesEpisode(payload: {
    seriesTitle: string;
    platform: "youtube_shorts" | "instagram_reels" | "tiktok" | "youtube_long";
    completedEpisodes: number;
    objective: string;
    audience: string;
    userId?: string;
}): Promise<NextSeriesEpisodeResult> {
    return fetchApi<NextSeriesEpisodeResult>("/competitors/series/next_episode", {
        method: "POST",
        body: {
            user_id: resolveUserId(payload.userId),
            series_title: payload.seriesTitle,
            platform: payload.platform,
            completed_episodes: payload.completedEpisodes,
            objective: payload.objective,
            audience: payload.audience,
        },
    });
}

export interface DiagnosisResult {
    primary_issue: "PACKAGING" | "RETENTION" | "TOPIC_FIT" | "CONSISTENCY" | "UNDEFINED";
    summary: string;
    evidence: any[];
    recommendations: any[];
    metrics: Record<string, any>;
}

export async function getChannelDiagnosis(channelId: string): Promise<DiagnosisResult> {
    return fetchApi<DiagnosisResult>(`/analysis/diagnose/channel/${channelId}`);
}

export interface PlatformMetricsIngestRecord {
    platform: "youtube" | "instagram" | "tiktok";
    video_external_id: string;
    video_url?: string;
    title?: string;
    published_at?: string;
    duration_seconds?: number;
    views?: number;
    likes?: number;
    comments?: number;
    shares?: number;
    saves?: number;
    watch_time_hours?: number;
    avg_view_duration_s?: number;
    ctr?: number;
    retention_points?: Array<{ time: number; retention: number }>;
    user_id?: string;
}

export interface PlatformMetricsIngestResponse {
    ingested: boolean;
    video_id: string;
    metrics_id: string;
    metric_coverage: Record<string, string>;
}

export interface PlatformMetricsCsvIngestResponse {
    ingested: boolean;
    processed_rows: number;
    successful_rows: number;
    failed_rows: number;
    failures: Array<Record<string, any>>;
    normalized_fields: {
        views: string;
        likes: string;
        comments: string;
        shares: string;
        saves: string;
        retention_points: string;
        avg_view_duration_s: string;
        ctr: string;
    };
}

export async function ingestPlatformMetrics(payload: PlatformMetricsIngestRecord): Promise<PlatformMetricsIngestResponse> {
    return fetchApi<PlatformMetricsIngestResponse>("/analysis/ingest/platform_metrics", {
        method: "POST",
        body: {
            ...payload,
            user_id: resolveUserId(payload.user_id),
        },
    });
}

export async function ingestPlatformMetricsCsv(
    file: File,
    options: {
        platform: "youtube" | "instagram" | "tiktok";
        userId?: string;
    }
): Promise<PlatformMetricsCsvIngestResponse> {
    const userId = resolveUserId(options.userId);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("platform", options.platform);
    formData.append("user_id", userId);
    return fetchFormApi<PlatformMetricsCsvIngestResponse>("/analysis/ingest/platform_metrics_csv", formData);
}

// ==================== Audit APIs ====================

export interface RetentionPoint {
    time: number;
    retention: number;
}

export interface RunAuditRequest {
    source_mode: "url" | "upload";
    platform?: "youtube" | "instagram" | "tiktok";
    video_url?: string;
    upload_id?: string;
    retention_points?: RetentionPoint[];
    platform_metrics?: {
        views?: number;
        likes?: number;
        comments?: number;
        shares?: number;
        saves?: number;
        watch_time_hours?: number;
        avg_view_duration_s?: number;
        ctr?: number;
    };
    user_id?: string;
}

export interface UploadAuditVideoResponse {
    upload_id: string;
    file_name: string;
    mime_type?: string;
    file_size_bytes: number;
    status: string;
}

export interface CreateMediaDownloadRequest {
    platform: "youtube" | "instagram" | "tiktok";
    source_url: string;
    user_id?: string;
}

export interface MediaDownloadJobStatus {
    job_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    source_url: string;
    status: string;
    progress: number;
    attempts: number;
    max_attempts: number;
    queue_job_id?: string | null;
    media_asset_id?: string | null;
    upload_id?: string | null;
    error_code?: string | null;
    error_message?: string | null;
    created_at?: string | null;
    completed_at?: string | null;
}

export interface RunAuditResponse {
    audit_id: string;
    status: string;
}

export interface AuditStatus {
    audit_id: string;
    status: string;
    progress: string;
    created_at?: string;
    output?: Record<string, any>;
    error?: string;
}

export interface AuditSummary {
    audit_id: string;
    status: string;
    progress: string;
    created_at?: string;
    completed_at?: string;
}

export async function runMultimodalAudit(payload: RunAuditRequest): Promise<RunAuditResponse> {
    return fetchApi<RunAuditResponse>("/audit/run_multimodal", {
        method: "POST",
        body: {
            ...payload,
            user_id: resolveUserId(payload.user_id),
        },
    });
}

export async function uploadAuditVideo(file: File, userId?: string): Promise<UploadAuditVideoResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", resolveUserId(userId));
    return fetchFormApi<UploadAuditVideoResponse>("/audit/upload", formData);
}

export async function createMediaDownloadJob(payload: CreateMediaDownloadRequest): Promise<MediaDownloadJobStatus> {
    return fetchApi<MediaDownloadJobStatus>("/media/download", {
        method: "POST",
        body: {
            platform: payload.platform,
            source_url: payload.source_url,
            user_id: resolveUserId(payload.user_id),
        },
    });
}

export async function getMediaDownloadJobStatus(jobId: string, userId?: string): Promise<MediaDownloadJobStatus> {
    const qUserId = resolveUserId(userId);
    return fetchApi<MediaDownloadJobStatus>(`/media/download/${safeEncode(jobId)}?user_id=${safeEncode(qUserId)}`);
}

export async function getAuditStatus(auditId: string, userId?: string): Promise<AuditStatus> {
    const qUserId = resolveUserId(userId);
    return fetchApi<AuditStatus>(`/audit/${auditId}?user_id=${safeEncode(qUserId)}`);
}

export async function getAudits(userId?: string, limit = 20): Promise<AuditSummary[]> {
    const qUserId = resolveUserId(userId);
    return fetchApi<AuditSummary[]>(
        `/audit/?user_id=${safeEncode(qUserId)}&limit=${limit}`
    );
}

// ==================== Report APIs ====================

export interface ConsolidatedReport {
    audit_id: string;
    report_platform: "youtube" | "instagram" | "tiktok";
    created_at?: string | null;
    overall_score: number;
    diagnosis: DiagnosisResult;
    video_analysis: any;
    performance_prediction?: {
        format_type: "short_form" | "long_form" | "unknown";
        duration_seconds: number;
        competitor_metrics: {
            score: number;
            confidence: "low" | "medium" | "high";
            summary: string;
            benchmark: {
                sample_size: number;
                competitor_count: number;
                avg_views: number;
                avg_like_rate: number;
                avg_comment_rate: number;
                avg_engagement_rate: number;
                difficulty_score: number;
                used_format_filter: boolean;
            };
            signals: string[];
        };
        platform_metrics: {
            score: number;
            summary: string;
            signals: {
                overall_multimodal_score: number;
                base_multimodal_score: number;
                explicit_detector_score: number;
                detector_weighted_score: number;
                detector_weight_breakdown: Record<string, number>;
                hook_strength: number;
                pacing_strength: number;
                timestamp_positive_signals: number;
                timestamp_negative_signals: number;
            };
            detectors?: {
                time_to_value: {
                    seconds: number;
                    target_seconds: number;
                    score: number;
                    assessment: "fast" | "moderate" | "slow";
                };
                open_loops: {
                    count: number;
                    score: number;
                    examples: string[];
                };
                dead_zones: {
                    count: number;
                    total_seconds: number;
                    score: number;
                    zones: Array<{ start: number; end: number; duration: number }>;
                };
                pattern_interrupts: {
                    interrupts_per_minute: number;
                    score: number;
                    assessment: "low" | "healthy" | "high";
                };
                cta_style: {
                    style: string;
                    score: number;
                    window: string;
                };
            };
            detector_rankings?: Array<{
                detector_key: string;
                label: string;
                score: number;
                target_score: number;
                gap: number;
                weight: number;
                priority: "critical" | "high" | "medium" | "low";
                rank: number;
                estimated_lift_points: number;
                evidence: string[];
                edits: string[];
            }>;
            metric_coverage?: {
                likes: string;
                comments: string;
                shares: string;
                saves: string;
                retention_curve: string;
            };
            true_metrics?: Record<string, any> | null;
            true_metric_notes?: string[];
        };
        historical_metrics?: {
            sample_size: number;
            format_sample_size: number;
            score: number;
            confidence: "low" | "medium" | "high";
            insufficient_data: boolean;
            summary: string;
            signals: string[];
        };
        combined_metrics: {
            score: number;
            confidence: "low" | "medium" | "high";
            likelihood_band: "low" | "medium" | "high";
            summary: string;
            weights: {
                competitor_metrics: number;
                platform_metrics: number;
                historical_metrics?: number;
            };
            insufficient_data?: boolean;
            insufficient_data_reasons?: string[];
        };
        repurpose_plan?: {
            core_thesis: string;
            source_format: string;
            youtube_shorts: {
                target_duration_s: number;
                hook_deadline_s: number;
                editing_style: string;
                cta: string;
            };
            instagram_reels: {
                target_duration_s: number;
                hook_deadline_s: number;
                editing_style: string;
                cta: string;
            };
            tiktok: {
                target_duration_s: number;
                hook_deadline_s: number;
                editing_style: string;
                cta: string;
            };
        };
        next_actions?: Array<{
            title: string;
            detector_key: string;
            priority: "critical" | "high" | "medium" | "low";
            why: string;
            expected_lift_points: number;
            execution_steps: string[];
            evidence: string[];
        }>;
    };
    blueprint: BlueprintResult;
    prediction_vs_actual?: {
        outcome_id: string;
        platform: string;
        content_item_id?: string | null;
        draft_snapshot_id?: string | null;
        report_id?: string | null;
        posted_at?: string | null;
        predicted_score?: number | null;
        actual_score?: number | null;
        calibration_delta?: number | null;
        actual_metrics?: Record<string, any>;
    } | null;
    calibration_confidence?: {
        platform: string;
        sample_size: number;
        mean_abs_error: number;
        hit_rate: number;
        trend: string;
        confidence: "low" | "medium" | "high";
        insufficient_data: boolean;
        recommendations: string[];
    };
    outcome_drift?: {
        drift_windows?: {
            d7?: {
                days: number;
                count: number;
                mean_delta: number;
                mean_abs_error: number;
                bias: "underpredicting" | "overpredicting" | "neutral";
            };
            d30?: {
                days: number;
                count: number;
                mean_delta: number;
                mean_abs_error: number;
                bias: "underpredicting" | "overpredicting" | "neutral";
            };
        };
        next_actions?: string[];
        recent_outcomes?: Array<{
            outcome_id: string;
            platform: string;
            draft_snapshot_id?: string | null;
            report_id?: string | null;
            content_item_id?: string | null;
            posted_at?: string | null;
            predicted_score?: number | null;
            actual_score?: number | null;
            calibration_delta?: number | null;
        }>;
    };
    best_edited_variant?: {
        id: string;
        platform: string;
        variant_id?: string | null;
        source_item_id?: string | null;
        script_preview: string;
        baseline_score?: number | null;
        rescored_score?: number | null;
        delta_score?: number | null;
        created_at?: string | null;
        top_detector_improvements?: Array<{
            detector_key?: string;
            label?: string;
            score?: number;
            target_score?: number;
            gap?: number;
        }>;
    } | null;
    quick_actions?: Array<{
        type: string;
        label: string;
        href: string;
    }>;
    recommendations: string[];
}

export async function getConsolidatedReport(auditId?: string, userId?: string): Promise<ConsolidatedReport> {
    const qUserId = resolveUserId(userId);
    const endpoint = auditId
        ? `/report/${auditId}?user_id=${safeEncode(qUserId)}`
        : `/report/latest?user_id=${safeEncode(qUserId)}`;
    return fetchApi(endpoint);
}

export interface ShareReportLinkResponse {
    share_id: string;
    audit_id: string;
    share_token: string;
    expires_at: string;
    share_url: string;
}

export async function createReportShareLink(
    auditId: string,
    options: { userId?: string; expiresHours?: number } = {}
): Promise<ShareReportLinkResponse> {
    return fetchApi<ShareReportLinkResponse>(`/report/${auditId}/share`, {
        method: "POST",
        body: {
            user_id: resolveUserId(options.userId),
            expires_hours: options.expiresHours ?? 168,
        },
    });
}

export async function getSharedReport(shareToken: string): Promise<ConsolidatedReport> {
    return fetchApi<ConsolidatedReport>(`/report/shared/${safeEncode(shareToken)}`);
}

// ==================== Research APIs ====================

export interface ResearchItem {
    item_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    source_type: string;
    url?: string | null;
    external_id?: string | null;
    creator_handle?: string | null;
    creator_display_name?: string | null;
    title?: string | null;
    caption?: string | null;
    metrics: {
        views: number;
        likes: number;
        comments: number;
        shares: number;
        saves: number;
    };
    media_meta: Record<string, any>;
    tags?: string[];
    pinned?: boolean;
    archived?: boolean;
    published_at?: string | null;
    created_at?: string | null;
    collection_id?: string | null;
}

export interface ResearchCollection {
    id: string;
    name: string;
    platform?: string | null;
    description?: string | null;
    is_system: boolean;
    created_at?: string | null;
}

export interface ResearchSearchResponse {
    page: number;
    limit: number;
    total_count: number;
    has_more: boolean;
    items: ResearchItem[];
    credits?: {
        charged: number;
        balance_after: number;
    };
}

export async function importResearchUrl(
    payload: {
        platform?: "youtube" | "instagram" | "tiktok";
        url: string;
        userId?: string;
    }
): Promise<ResearchItem> {
    return fetchApi<ResearchItem>("/research/import_url", {
        method: "POST",
        body: {
            platform: payload.platform,
            url: payload.url,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function captureResearchItem(
    payload: Record<string, any> & { userId?: string }
): Promise<ResearchItem> {
    return fetchApi<ResearchItem>("/research/capture", {
        method: "POST",
        body: {
            ...payload,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function importResearchCsv(
    file: File,
    payload: {
        platform?: "youtube" | "instagram" | "tiktok";
        userId?: string;
    } = {}
): Promise<{
    imported_count: number;
    failed_rows: Array<{ row: number; error: string }>;
    collection_id: string;
}> {
    const formData = new FormData();
    formData.append("file", file);
    if (payload.platform) {
        formData.append("platform", payload.platform);
    }
    formData.append("user_id", resolveUserId(payload.userId));
    return fetchFormApi("/research/import_csv", formData);
}

export async function searchResearchItems(payload: {
    platform?: "youtube" | "instagram" | "tiktok";
    query?: string;
    collection_id?: string;
    include_archived?: boolean;
    pinned_only?: boolean;
    tags?: string[];
    sort_by?: "created_at" | "posted_at" | "views" | "likes" | "comments" | "shares" | "saves";
    sort_direction?: "asc" | "desc";
    timeframe?: "24h" | "7d" | "30d" | "90d" | "all";
    page?: number;
    limit?: number;
    userId?: string;
}): Promise<ResearchSearchResponse> {
    return fetchApi<ResearchSearchResponse>("/research/search", {
        method: "POST",
        body: {
            platform: payload.platform,
            query: payload.query || "",
            collection_id: payload.collection_id,
            include_archived: payload.include_archived || false,
            pinned_only: payload.pinned_only || false,
            tags: payload.tags,
            sort_by: payload.sort_by || "created_at",
            sort_direction: payload.sort_direction || "desc",
            timeframe: payload.timeframe || "all",
            page: payload.page || 1,
            limit: payload.limit || 20,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function listResearchCollections(userId?: string): Promise<ResearchCollection[]> {
    const qUserId = resolveUserId(userId);
    const response = await fetchApi<{ collections: ResearchCollection[] }>(
        `/research/collections?user_id=${safeEncode(qUserId)}`
    );
    return response.collections || [];
}

export async function createResearchCollection(payload: {
    name: string;
    platform?: "mixed" | "youtube" | "instagram" | "tiktok";
    description?: string;
    userId?: string;
}): Promise<ResearchCollection> {
    return fetchApi<ResearchCollection>("/research/collections", {
        method: "POST",
        body: {
            name: payload.name,
            platform: payload.platform || "mixed",
            description: payload.description,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function getResearchItem(itemId: string, userId?: string): Promise<ResearchItem> {
    const qUserId = resolveUserId(userId);
    return fetchApi<ResearchItem>(`/research/items/${safeEncode(itemId)}?user_id=${safeEncode(qUserId)}`);
}

export async function moveResearchItem(payload: {
    itemId: string;
    collectionId: string;
    userId?: string;
}): Promise<ResearchItem> {
    return fetchApi<ResearchItem>(`/research/items/${safeEncode(payload.itemId)}/move`, {
        method: "POST",
        body: {
            collection_id: payload.collectionId,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function updateResearchItemMeta(payload: {
    itemId: string;
    tags?: string[];
    pinned?: boolean;
    archived?: boolean;
    userId?: string;
}): Promise<ResearchItem> {
    return fetchApi<ResearchItem>(`/research/items/${safeEncode(payload.itemId)}/meta`, {
        method: "POST",
        body: {
            tags: payload.tags,
            pinned: payload.pinned,
            archived: payload.archived,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function exportResearchCollection(payload: {
    collectionId: string;
    format: "csv" | "json";
    userId?: string;
}): Promise<{
    export_id: string;
    status: string;
    signed_url: string;
    format: "csv" | "json";
    item_count: number;
}> {
    return fetchApi("/research/export", {
        method: "POST",
        body: {
            collection_id: payload.collectionId,
            format: payload.format,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedDiscoveryItem {
    item_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    source_type: string;
    url?: string | null;
    external_id?: string | null;
    creator_handle?: string | null;
    creator_display_name?: string | null;
    title?: string | null;
    caption?: string | null;
    metrics: {
        views: number;
        likes: number;
        comments: number;
        shares: number;
        saves: number;
    };
    published_at?: string | null;
    created_at?: string | null;
    engagement_rate: number;
    views_per_hour: number;
    trending_score: number;
}

export interface FeedDiscoverResponse {
    run_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    mode: "profile" | "hashtag" | "keyword" | "audio";
    query: string;
    timeframe: "24h" | "7d" | "30d" | "90d" | "all";
    ingestion_method: string;
    source_health: Record<string, string>;
    page: number;
    limit: number;
    total_count: number;
    has_more: boolean;
    items: FeedDiscoveryItem[];
}

export interface FeedSearchResponse {
    platform: "youtube" | "instagram" | "tiktok" | "all";
    mode?: "profile" | "hashtag" | "keyword" | "audio";
    query: string;
    timeframe: "24h" | "7d" | "30d" | "90d" | "all";
    page: number;
    limit: number;
    total_count: number;
    has_more: boolean;
    items: FeedDiscoveryItem[];
}

export async function discoverFeedItems(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    mode: "profile" | "hashtag" | "keyword" | "audio";
    query: string;
    timeframe?: "24h" | "7d" | "30d" | "90d" | "all";
    sort_by?: "trending_score" | "engagement_rate" | "views_per_hour" | "views" | "likes" | "comments" | "shares" | "saves" | "posted_at" | "created_at";
    sort_direction?: "asc" | "desc";
    page?: number;
    limit?: number;
    userId?: string;
}): Promise<FeedDiscoverResponse> {
    return fetchApi<FeedDiscoverResponse>("/feed/discover", {
        method: "POST",
        body: {
            platform: payload.platform,
            mode: payload.mode,
            query: payload.query,
            timeframe: payload.timeframe || "7d",
            sort_by: payload.sort_by || "trending_score",
            sort_direction: payload.sort_direction || "desc",
            page: payload.page || 1,
            limit: payload.limit || 20,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function searchFeedItems(payload: {
    platform?: "youtube" | "instagram" | "tiktok";
    mode?: "profile" | "hashtag" | "keyword" | "audio";
    query?: string;
    timeframe?: "24h" | "7d" | "30d" | "90d" | "all";
    sort_by?: "trending_score" | "engagement_rate" | "views_per_hour" | "views" | "likes" | "comments" | "shares" | "saves" | "posted_at" | "created_at";
    sort_direction?: "asc" | "desc";
    page?: number;
    limit?: number;
    userId?: string;
}): Promise<FeedSearchResponse> {
    return fetchApi<FeedSearchResponse>("/feed/search", {
        method: "POST",
        body: {
            platform: payload.platform,
            mode: payload.mode,
            query: payload.query || "",
            timeframe: payload.timeframe || "all",
            sort_by: payload.sort_by || "trending_score",
            sort_direction: payload.sort_direction || "desc",
            page: payload.page || 1,
            limit: payload.limit || 20,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function toggleFeedFavorite(payload: {
    itemId: string;
    favorite: boolean;
    userId?: string;
}): Promise<{ item_id: string; favorite: boolean }> {
    return fetchApi<{ item_id: string; favorite: boolean }>("/feed/favorites/toggle", {
        method: "POST",
        body: {
            item_id: payload.itemId,
            favorite: payload.favorite,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function assignFeedItemsToCollection(payload: {
    itemIds: string[];
    collectionId: string;
    userId?: string;
}): Promise<{
    collection_id: string;
    assigned_count: number;
    missing_count: number;
    missing_item_ids: string[];
}> {
    return fetchApi("/feed/collections/assign", {
        method: "POST",
        body: {
            item_ids: payload.itemIds,
            collection_id: payload.collectionId,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function exportFeedItems(payload: {
    itemIds?: string[];
    platform?: "youtube" | "instagram" | "tiktok";
    mode?: "profile" | "hashtag" | "keyword" | "audio";
    query?: string;
    timeframe?: "24h" | "7d" | "30d" | "90d" | "all";
    sort_by?: "trending_score" | "engagement_rate" | "views_per_hour" | "views" | "likes" | "comments" | "shares" | "saves" | "posted_at" | "created_at";
    sort_direction?: "asc" | "desc";
    limit?: number;
    maxRows?: number;
    format: "csv" | "json";
    userId?: string;
}): Promise<{
    export_id: string;
    status: string;
    format: "csv" | "json";
    item_count: number;
    signed_url: string;
}> {
    return fetchApi("/feed/export", {
        method: "POST",
        body: {
            item_ids: payload.itemIds,
            platform: payload.platform,
            mode: payload.mode,
            query: payload.query || "",
            timeframe: payload.timeframe || "all",
            sort_by: payload.sort_by || "trending_score",
            sort_direction: payload.sort_direction || "desc",
            limit: payload.limit || 100,
            max_rows: payload.maxRows || 500,
            format: payload.format,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedBulkJobItem {
    item_id: string;
    job_id?: string | null;
    status: string;
    queue_job_id?: string | null;
    error_code?: string | null;
    error_message?: string | null;
}

export interface FeedBulkDownloadResponse {
    submitted_count: number;
    queued_count: number;
    failed_count: number;
    skipped_count: number;
    jobs: FeedBulkJobItem[];
}

export interface FeedBulkDownloadStatusItem {
    job_id: string;
    status: string;
    progress: number;
    queue_job_id?: string | null;
    media_asset_id?: string | null;
    upload_id?: string | null;
    error_code?: string | null;
    error_message?: string | null;
}

export interface FeedBulkDownloadStatusResponse {
    requested_count: number;
    jobs: FeedBulkDownloadStatusItem[];
}

export interface FeedBulkTranscriptStatusItem {
    job_id: string;
    status: string;
    progress: number;
    queue_job_id?: string | null;
    item_id?: string | null;
    transcript_source?: string | null;
    transcript_preview?: string | null;
    error_code?: string | null;
    error_message?: string | null;
}

export interface FeedBulkTranscriptStatusResponse {
    requested_count: number;
    jobs: FeedBulkTranscriptStatusItem[];
}

export async function startFeedBulkDownload(payload: {
    itemIds: string[];
    userId?: string;
}): Promise<FeedBulkDownloadResponse> {
    return fetchApi<FeedBulkDownloadResponse>("/feed/download/bulk", {
        method: "POST",
        body: {
            item_ids: payload.itemIds,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function getFeedBulkDownloadStatus(payload: {
    jobIds: string[];
    userId?: string;
}): Promise<FeedBulkDownloadStatusResponse> {
    return fetchApi<FeedBulkDownloadStatusResponse>("/feed/download/status", {
        method: "POST",
        body: {
            job_ids: payload.jobIds,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function startFeedTranscriptBulk(payload: {
    itemIds: string[];
    userId?: string;
}): Promise<FeedBulkDownloadResponse> {
    return fetchApi<FeedBulkDownloadResponse>("/feed/transcripts/bulk", {
        method: "POST",
        body: {
            item_ids: payload.itemIds,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function getFeedTranscriptBulkStatus(payload: {
    jobIds: string[];
    userId?: string;
}): Promise<FeedBulkTranscriptStatusResponse> {
    return fetchApi<FeedBulkTranscriptStatusResponse>("/feed/transcripts/status", {
        method: "POST",
        body: {
            job_ids: payload.jobIds,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedFollow {
    id: string;
    platform: "youtube" | "instagram" | "tiktok";
    mode: "profile" | "hashtag" | "keyword" | "audio";
    query: string;
    timeframe: "24h" | "7d" | "30d" | "90d" | "all";
    sort_by: "trending_score" | "engagement_rate" | "views_per_hour" | "views" | "likes" | "comments" | "shares" | "saves" | "posted_at" | "created_at";
    sort_direction: "asc" | "desc";
    limit: number;
    cadence_minutes: number;
    is_active: boolean;
    last_run_at?: string | null;
    next_run_at?: string | null;
    last_error?: string | null;
    created_at?: string | null;
}

export interface FeedIngestRun {
    run_id: string;
    follow_id: string;
    status: string;
    item_count: number;
    item_ids: string[];
    error_message?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    created_at?: string | null;
}

export async function upsertFeedFollow(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    mode: "profile" | "hashtag" | "keyword" | "audio";
    query: string;
    timeframe?: "24h" | "7d" | "30d" | "90d" | "all";
    sort_by?: "trending_score" | "engagement_rate" | "views_per_hour" | "views" | "likes" | "comments" | "shares" | "saves" | "posted_at" | "created_at";
    sort_direction?: "asc" | "desc";
    limit?: number;
    cadence?: "15m" | "1h" | "3h" | "6h" | "12h" | "24h";
    cadenceMinutes?: number;
    isActive?: boolean;
    userId?: string;
}): Promise<{ created: boolean; follow: FeedFollow }> {
    return fetchApi<{ created: boolean; follow: FeedFollow }>("/feed/follows/upsert", {
        method: "POST",
        body: {
            platform: payload.platform,
            mode: payload.mode,
            query: payload.query,
            timeframe: payload.timeframe || "7d",
            sort_by: payload.sort_by || "trending_score",
            sort_direction: payload.sort_direction || "desc",
            limit: payload.limit || 20,
            cadence: payload.cadence || "6h",
            cadence_minutes: payload.cadenceMinutes,
            is_active: payload.isActive ?? true,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function listFeedFollows(payload?: {
    platform?: "youtube" | "instagram" | "tiktok";
    activeOnly?: boolean;
    userId?: string;
}): Promise<{ count: number; follows: FeedFollow[] }> {
    const params = new URLSearchParams();
    if (payload?.platform) {
        params.set("platform", payload.platform);
    }
    params.set("active_only", String(payload?.activeOnly ?? true));
    params.set("user_id", resolveUserId(payload?.userId));
    const query = params.toString();
    return fetchApi<{ count: number; follows: FeedFollow[] }>(`/feed/follows${query ? `?${query}` : ""}`, {
        method: "GET",
    });
}

export async function deleteFeedFollow(payload: {
    followId: string;
    userId?: string;
}): Promise<{ deleted: boolean; follow_id: string }> {
    const params = new URLSearchParams();
    params.set("user_id", resolveUserId(payload.userId));
    return fetchApi<{ deleted: boolean; follow_id: string }>(
        `/feed/follows/${payload.followId}?${params.toString()}`,
        { method: "DELETE" }
    );
}

export async function runFeedFollowIngest(payload?: {
    followIds?: string[];
    runDueOnly?: boolean;
    maxFollows?: number;
    userId?: string;
}): Promise<{
    scheduled_count: number;
    completed_count: number;
    failed_count: number;
    runs: FeedIngestRun[];
}> {
    return fetchApi<{
        scheduled_count: number;
        completed_count: number;
        failed_count: number;
        runs: FeedIngestRun[];
    }>("/feed/follows/ingest", {
        method: "POST",
        body: {
            follow_ids: payload?.followIds,
            run_due_only: payload?.runDueOnly ?? false,
            max_follows: payload?.maxFollows ?? 25,
            user_id: resolveUserId(payload?.userId),
        },
    });
}

export async function listFeedIngestRuns(payload?: {
    followId?: string;
    limit?: number;
    userId?: string;
}): Promise<{ count: number; runs: FeedIngestRun[] }> {
    const params = new URLSearchParams();
    if (payload?.followId) {
        params.set("follow_id", payload.followId);
    }
    params.set("limit", String(payload?.limit ?? 50));
    params.set("user_id", resolveUserId(payload?.userId));
    return fetchApi<{ count: number; runs: FeedIngestRun[] }>(
        `/feed/follows/runs?${params.toString()}`,
        { method: "GET" }
    );
}

export interface FeedRepostPackage {
    package_id: string;
    source_item_id: string;
    status: "draft" | "scheduled" | "published" | "archived";
    target_platforms: Array<"youtube" | "instagram" | "tiktok">;
    package: Record<string, any>;
    created_at?: string | null;
    updated_at?: string | null;
}

export async function createFeedRepostPackage(payload: {
    sourceItemId: string;
    targetPlatforms?: Array<"youtube" | "instagram" | "tiktok">;
    objective?: string;
    tone?: string;
    userId?: string;
}): Promise<FeedRepostPackage> {
    return fetchApi<FeedRepostPackage>("/feed/repost/package", {
        method: "POST",
        body: {
            source_item_id: payload.sourceItemId,
            target_platforms: payload.targetPlatforms,
            objective: payload.objective || "maximize_reach",
            tone: payload.tone || "direct",
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function listFeedRepostPackages(payload?: {
    sourceItemId?: string;
    limit?: number;
    userId?: string;
}): Promise<{ count: number; packages: FeedRepostPackage[] }> {
    const params = new URLSearchParams();
    if (payload?.sourceItemId) {
        params.set("source_item_id", payload.sourceItemId);
    }
    params.set("limit", String(payload?.limit ?? 20));
    params.set("user_id", resolveUserId(payload?.userId));
    return fetchApi<{ count: number; packages: FeedRepostPackage[] }>(
        `/feed/repost/packages?${params.toString()}`,
        { method: "GET" }
    );
}

export async function getFeedRepostPackage(payload: {
    packageId: string;
    userId?: string;
}): Promise<FeedRepostPackage> {
    const params = new URLSearchParams();
    params.set("user_id", resolveUserId(payload.userId));
    return fetchApi<FeedRepostPackage>(`/feed/repost/packages/${payload.packageId}?${params.toString()}`, {
        method: "GET",
    });
}

export async function updateFeedRepostPackageStatus(payload: {
    packageId: string;
    status: "draft" | "scheduled" | "published" | "archived";
    userId?: string;
}): Promise<FeedRepostPackage> {
    return fetchApi<FeedRepostPackage>(`/feed/repost/packages/${payload.packageId}/status`, {
        method: "POST",
        body: {
            status: payload.status,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedLoopVariantResult {
    source_item_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    topic: string;
    audience: string;
    objective: string;
    optimizer: Record<string, any>;
    credits: {
        charged: number;
        balance_after: number;
    };
}

export async function runFeedLoopVariantGenerate(payload: {
    sourceItemId: string;
    platform?: "youtube" | "instagram" | "tiktok";
    topic?: string;
    audience?: string;
    objective?: string;
    tone?: string;
    durationS?: number;
    generationMode?: "ai_first_fallback";
    constraints?: Record<string, any>;
    userId?: string;
}): Promise<FeedLoopVariantResult> {
    return fetchApi<FeedLoopVariantResult>("/feed/loop/variant_generate", {
        method: "POST",
        body: {
            source_item_id: payload.sourceItemId,
            platform: payload.platform,
            topic: payload.topic,
            audience: payload.audience,
            objective: payload.objective,
            tone: payload.tone || "bold",
            duration_s: payload.durationS,
            generation_mode: payload.generationMode || "ai_first_fallback",
            constraints: payload.constraints,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedLoopAuditResult {
    audit_id: string;
    status: string;
    source_item_id: string;
    upload_id: string;
    report_path: string;
    credits: {
        charged: number;
        balance_after: number;
    };
}

export async function runFeedLoopAudit(payload: {
    sourceItemId: string;
    platform?: "youtube" | "instagram" | "tiktok";
    retentionPoints?: Array<{ time: number; retention: number }>;
    platformMetrics?: Record<string, any>;
    draftSnapshotId?: string;
    repostPackageId?: string;
    userId?: string;
}): Promise<FeedLoopAuditResult> {
    return fetchApi<FeedLoopAuditResult>("/feed/loop/audit", {
        method: "POST",
        body: {
            source_item_id: payload.sourceItemId,
            platform: payload.platform,
            retention_points: payload.retentionPoints,
            platform_metrics: payload.platformMetrics,
            draft_snapshot_id: payload.draftSnapshotId,
            repost_package_id: payload.repostPackageId,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface FeedLoopSummary {
    source_item_id: string;
    source_item: Record<string, any>;
    latest_repost_package?: Record<string, any> | null;
    latest_draft_snapshot?: Record<string, any> | null;
    latest_audit?: Record<string, any> | null;
    stage_completion: {
        discovered: boolean;
        packaged: boolean;
        scripted: boolean;
        audited: boolean;
        reported: boolean;
    };
    next_step: string;
}

export async function getFeedLoopSummary(payload: {
    sourceItemId: string;
    userId?: string;
}): Promise<FeedLoopSummary> {
    const params = new URLSearchParams();
    params.set("source_item_id", payload.sourceItemId);
    params.set("user_id", resolveUserId(payload.userId));
    return fetchApi<FeedLoopSummary>(`/feed/loop/summary?${params.toString()}`, {
        method: "GET",
    });
}

export interface FeedTelemetrySummary {
    window_days: number;
    event_volume: {
        total_events: number;
        by_event: Record<string, number>;
        by_status: Record<string, number>;
        error_count: number;
    };
    funnel: {
        discovered_count: number;
        packaged_count: number;
        scripted_count: number;
        audited_count: number;
        reported_count: number;
        discover_to_package_pct: number;
        package_to_script_pct: number;
        script_to_audit_pct: number;
        audit_to_report_pct: number;
    };
}

export async function getFeedTelemetrySummary(payload?: {
    days?: number;
    userId?: string;
}): Promise<FeedTelemetrySummary> {
    const params = new URLSearchParams();
    params.set("days", String(payload?.days ?? 7));
    params.set("user_id", resolveUserId(payload?.userId));
    return fetchApi<FeedTelemetrySummary>(`/feed/telemetry/summary?${params.toString()}`, {
        method: "GET",
    });
}

export interface FeedTelemetryEventItem {
    event_id: string;
    event_name: string;
    status: string;
    platform?: string | null;
    source_item_id?: string | null;
    details: Record<string, any>;
    created_at?: string | null;
}

export async function listFeedTelemetryEvents(payload?: {
    days?: number;
    limit?: number;
    eventName?: string;
    status?: string;
    userId?: string;
}): Promise<{ window_days: number; count: number; events: FeedTelemetryEventItem[] }> {
    const params = new URLSearchParams();
    params.set("days", String(payload?.days ?? 7));
    params.set("limit", String(payload?.limit ?? 50));
    if (payload?.eventName) {
        params.set("event_name", payload.eventName);
    }
    if (payload?.status) {
        params.set("status", payload.status);
    }
    params.set("user_id", resolveUserId(payload?.userId));
    return fetchApi<{ window_days: number; count: number; events: FeedTelemetryEventItem[] }>(
        `/feed/telemetry/events?${params.toString()}`,
        { method: "GET" }
    );
}

export function getFeedExportDownloadUrl(signedPath: string): string {
    if (!signedPath) {
        return "";
    }
    if (/^https?:\/\//i.test(signedPath)) {
        return signedPath;
    }
    return `${API_BASE_URL}${signedPath}`;
}

export function getApiBaseUrl(): string {
    return API_BASE_URL;
}

// ==================== Optimizer APIs ====================

export interface ScriptVariantResult {
    id: string;
    style_key: string;
    label: string;
    rationale: string;
    script: string;
    script_text: string;
    structure: {
        hook: string;
        setup: string;
        value: string;
        cta: string;
    };
    rank: number;
    expected_lift_points: number;
    score_breakdown: {
        platform_metrics: number;
        competitor_metrics: number;
        historical_metrics: number;
        combined: number;
        detector_weighted_score: number;
        confidence: "low" | "medium" | "high";
    };
    detector_rankings: Array<{
        detector_key: string;
        label: string;
        score: number;
        target_score: number;
        gap: number;
        weight: number;
        priority: "critical" | "high" | "medium" | "low";
        rank: number;
        estimated_lift_points: number;
        evidence: string[];
        edits: string[];
    }>;
    next_actions: Array<{
        title: string;
        detector_key: string;
        priority: "critical" | "high" | "medium" | "low";
        why: string;
        expected_lift_points: number;
        execution_steps: string[];
        evidence: string[];
    }>;
}

export interface VariantGenerationMeta {
    mode: "ai_first_fallback";
    provider: "openai" | "deterministic";
    model: string;
    used_fallback: boolean;
    fallback_reason?: string | null;
}

export interface VariantGenerateResponse {
    batch_id: string;
    generated_at: string;
    generation: VariantGenerationMeta;
    variants: ScriptVariantResult[];
    credits?: {
        charged: number;
        balance_after: number;
    };
}

export interface OptimizerRescoreResponse {
    score_breakdown: {
        platform_metrics: number;
        competitor_metrics: number;
        historical_metrics: number;
        combined: number;
        confidence: "low" | "medium" | "high";
        weights: Record<string, number>;
        delta_from_baseline?: number | null;
    };
    detector_rankings: ScriptVariantResult["detector_rankings"];
    next_actions: ScriptVariantResult["next_actions"];
    line_level_edits: Array<{
        detector_key: string;
        detector_label: string;
        priority: "critical" | "high" | "medium" | "low" | string;
        line_number: number;
        original_line: string;
        suggested_line: string;
        reason: string;
    }>;
    improvement_diff: {
        combined: {
            before?: number | null;
            after: number;
            delta?: number | null;
        };
        detectors: Array<{
            detector_key: string;
            before_score?: number | null;
            after_score: number;
            delta?: number | null;
        }>;
    };
    signals: Record<string, any>;
    format_type: "short_form" | "long_form" | "unknown";
    duration_seconds: number;
}

export async function generateOptimizerVariants(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    topic: string;
    audience: string;
    objective: string;
    tone: string;
    duration_s?: number;
    template_series_key?: string;
    source_item_id?: string;
    source_context?: string;
    generation_mode?: "ai_first_fallback";
    constraints?: {
        platform?: "youtube" | "instagram" | "tiktok";
        duration_s?: number;
        tone?: string;
        hook_style?: string;
        cta_style?: string;
        pacing_density?: string;
    };
    userId?: string;
}): Promise<VariantGenerateResponse> {
    return fetchApi<VariantGenerateResponse>("/optimizer/variant_generate", {
        method: "POST",
        body: {
            platform: payload.platform,
            topic: payload.topic,
            audience: payload.audience,
            objective: payload.objective,
            tone: payload.tone,
            duration_s: payload.duration_s,
            template_series_key: payload.template_series_key,
            source_item_id: payload.source_item_id,
            source_context: payload.source_context,
            generation_mode: payload.generation_mode || "ai_first_fallback",
            constraints: payload.constraints,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function rescoreOptimizerDraft(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    script_text: string;
    duration_s?: number;
    optional_metrics?: Record<string, any>;
    retention_points?: Array<{ time: number; retention: number }>;
    baseline_score?: number;
    baseline_detector_rankings?: ScriptVariantResult["detector_rankings"];
    userId?: string;
}): Promise<OptimizerRescoreResponse> {
    return fetchApi<OptimizerRescoreResponse>("/optimizer/rescore", {
        method: "POST",
        body: {
            platform: payload.platform,
            script_text: payload.script_text,
            duration_s: payload.duration_s,
            optional_metrics: payload.optional_metrics,
            retention_points: payload.retention_points,
            baseline_score: payload.baseline_score,
            baseline_detector_rankings: payload.baseline_detector_rankings,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export interface DraftSnapshot {
    id: string;
    user_id: string;
    platform: "youtube" | "instagram" | "tiktok";
    source_item_id?: string | null;
    variant_id?: string | null;
    script_text: string;
    baseline_score?: number | null;
    rescored_score: number;
    delta_score?: number | null;
    detector_rankings: ScriptVariantResult["detector_rankings"];
    next_actions: ScriptVariantResult["next_actions"];
    line_level_edits: OptimizerRescoreResponse["line_level_edits"];
    created_at?: string | null;
}

export async function createDraftSnapshot(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    source_item_id?: string;
    variant_id?: string;
    script_text: string;
    baseline_score?: number;
    rescored_score?: number;
    delta_score?: number;
    detector_rankings?: ScriptVariantResult["detector_rankings"];
    next_actions?: ScriptVariantResult["next_actions"];
    line_level_edits?: OptimizerRescoreResponse["line_level_edits"];
    score_breakdown?: OptimizerRescoreResponse["score_breakdown"];
    rescore_output?: OptimizerRescoreResponse;
    userId?: string;
}): Promise<DraftSnapshot> {
    return fetchApi<DraftSnapshot>("/optimizer/draft_snapshot", {
        method: "POST",
        body: {
            platform: payload.platform,
            source_item_id: payload.source_item_id,
            variant_id: payload.variant_id,
            script_text: payload.script_text,
            baseline_score: payload.baseline_score,
            rescored_score: payload.rescored_score,
            delta_score: payload.delta_score,
            detector_rankings: payload.detector_rankings,
            next_actions: payload.next_actions,
            line_level_edits: payload.line_level_edits,
            score_breakdown: payload.score_breakdown,
            rescore_output: payload.rescore_output,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function getDraftSnapshot(snapshotId: string, userId?: string): Promise<DraftSnapshot> {
    const qUserId = resolveUserId(userId);
    return fetchApi<DraftSnapshot>(`/optimizer/draft_snapshot/${safeEncode(snapshotId)}?user_id=${safeEncode(qUserId)}`);
}

export async function listDraftSnapshots(payload: {
    platform?: "youtube" | "instagram" | "tiktok";
    limit?: number;
    userId?: string;
} = {}): Promise<{ items: DraftSnapshot[]; count: number }> {
    const qUserId = resolveUserId(payload.userId);
    const platformPart = payload.platform ? `&platform=${safeEncode(payload.platform)}` : "";
    const limitPart = payload.limit ? `&limit=${payload.limit}` : "";
    return fetchApi<{ items: DraftSnapshot[]; count: number }>(
        `/optimizer/draft_snapshot?user_id=${safeEncode(qUserId)}${platformPart}${limitPart}`
    );
}

// ==================== Outcomes APIs ====================

export async function ingestOutcomeMetrics(payload: {
    platform: "youtube" | "instagram" | "tiktok";
    content_item_id?: string;
    draft_snapshot_id?: string;
    report_id?: string;
    video_external_id?: string;
    actual_metrics: Record<string, any>;
    retention_points?: Array<{ time: number; retention: number }>;
    posted_at: string;
    predicted_score?: number;
    userId?: string;
}): Promise<{
    outcome_id: string;
    calibration_delta?: number | null;
    actual_score: number;
    predicted_score?: number | null;
    confidence_update: Record<string, any>;
}> {
    return fetchApi("/outcomes/ingest", {
        method: "POST",
        body: {
            platform: payload.platform,
            content_item_id: payload.content_item_id,
            draft_snapshot_id: payload.draft_snapshot_id,
            report_id: payload.report_id,
            video_external_id: payload.video_external_id,
            actual_metrics: payload.actual_metrics,
            retention_points: payload.retention_points,
            posted_at: payload.posted_at,
            predicted_score: payload.predicted_score,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function getOutcomesSummary(payload: {
    platform?: "youtube" | "instagram" | "tiktok";
    userId?: string;
} = {}): Promise<{
    platform?: "youtube" | "instagram" | "tiktok";
    sample_size?: number;
    avg_error?: number;
    hit_rate?: number;
    trend?: string;
    confidence?: "low" | "medium" | "high";
    insufficient_data?: boolean;
    recommendations?: string[];
    drift_windows?: {
        d7: {
            days: number;
            count: number;
            mean_delta: number;
            mean_abs_error: number;
            bias: "underpredicting" | "overpredicting" | "neutral";
        };
        d30: {
            days: number;
            count: number;
            mean_delta: number;
            mean_abs_error: number;
            bias: "underpredicting" | "overpredicting" | "neutral";
        };
    };
    recent_outcomes?: Array<{
        outcome_id: string;
        platform: string;
        draft_snapshot_id?: string | null;
        report_id?: string | null;
        content_item_id?: string | null;
        posted_at?: string | null;
        predicted_score?: number | null;
        actual_score?: number | null;
        calibration_delta?: number | null;
    }>;
    next_actions?: string[];
    platforms?: Array<{
        platform: string;
        sample_size: number;
        avg_error: number;
        hit_rate: number;
        trend: string;
        confidence: "low" | "medium" | "high";
        insufficient_data: boolean;
        recommendations: string[];
    }>;
}> {
    const qUserId = resolveUserId(payload.userId);
    const platformPart = payload.platform ? `&platform=${safeEncode(payload.platform)}` : "";
    return fetchApi(`/outcomes/summary?user_id=${safeEncode(qUserId)}${platformPart}`);
}

export async function recalibrateOutcomes(): Promise<{
    refreshed: number;
    skipped: number;
    errors: string[];
}> {
    return fetchApi("/outcomes/recalibrate", { method: "POST" });
}

// ==================== Billing APIs ====================

export interface CreditSummaryResponse {
    balance: number;
    period_key: string;
    free_monthly_credits: number;
    costs: {
        research_search: number;
        optimizer_variants: number;
        audit_run: number;
    };
    recent_entries: Array<{
        id: string;
        entry_type: string;
        delta_credits: number;
        balance_after: number;
        reason?: string;
        created_at?: string;
    }>;
}

export async function getCreditSummary(userId?: string): Promise<CreditSummaryResponse> {
    const qUserId = resolveUserId(userId);
    return fetchApi<CreditSummaryResponse>(`/billing/credits?user_id=${safeEncode(qUserId)}`);
}

export async function topUpCredits(payload: { credits: number; billing_reference?: string; userId?: string }) {
    return fetchApi("/billing/topup", {
        method: "POST",
        body: {
            credits: payload.credits,
            billing_reference: payload.billing_reference,
            user_id: resolveUserId(payload.userId),
        },
    });
}

export async function createBillingCheckout(payload: { credits: number; userId?: string }) {
    return fetchApi("/billing/checkout", {
        method: "POST",
        body: {
            credits: payload.credits,
            user_id: resolveUserId(payload.userId),
        },
    });
}

// ==================== Health APIs ====================

export async function checkHealth(): Promise<{ status: string; api: string }> {
    return fetchApi("/health");
}
