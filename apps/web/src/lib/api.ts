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
        throw new Error("No authenticated user found. Connect YouTube to continue.");
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
    custom_url?: string;
    subscriber_count?: number | string;
    video_count?: number;
    thumbnail_url?: string;
    created_at: string;
}

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

export type CompetitorSuggestionSortBy =
    | "subscriber_count"
    | "avg_views_per_video"
    | "view_count";
export type CompetitorSuggestionSortDirection = "desc" | "asc";

export async function generateBlueprint(userId?: string): Promise<BlueprintResult> {
    return fetchApi("/competitors/blueprint", {
        method: "POST",
        body: { user_id: resolveUserId(userId) },
    });
}

export async function recommendCompetitors(
    niche: string,
    options: {
        userId?: string;
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
                user_id: resolveUserId(options.userId),
                limit: options.limit ?? 8,
                page: options.page ?? 1,
                sort_by: options.sortBy ?? "subscriber_count",
                sort_direction: options.sortDirection ?? "desc",
            },
        }
    );
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

// ==================== Audit APIs ====================

export interface RetentionPoint {
    time: number;
    retention: number;
}

export interface RunAuditRequest {
    source_mode: "url" | "upload";
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
    recommendations: string[];
}

export async function getConsolidatedReport(auditId?: string, userId?: string): Promise<ConsolidatedReport> {
    const qUserId = resolveUserId(userId);
    const endpoint = auditId
        ? `/report/${auditId}?user_id=${safeEncode(qUserId)}`
        : `/report/latest?user_id=${safeEncode(qUserId)}`;
    return fetchApi(endpoint);
}

// ==================== Health APIs ====================

export async function checkHealth(): Promise<{ status: string; api: string }> {
    return fetchApi("/health");
}
