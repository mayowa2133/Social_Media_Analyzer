/**
 * API client for communication with the FastAPI backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEFAULT_USER_ID = "test-user";
const USER_ID_STORAGE_KEY = "spc_user_id";

interface ApiOptions {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: any;
    accessToken?: string;
}

function safeEncode(value: string): string {
    return encodeURIComponent(value);
}

function resolveUserId(userId?: string): string {
    return userId || getCurrentUserId() || DEFAULT_USER_ID;
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

async function fetchApi<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
    const { method = "GET", body, accessToken } = options;

    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };

    if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
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
    return result;
}

export async function getCurrentUserProfile(params: { userId?: string; email?: string } = {}): Promise<CurrentUserResponse> {
    const query = params.userId
        ? `user_id=${safeEncode(params.userId)}`
        : `email=${safeEncode(params.email || "")}`;
    return fetchApi<CurrentUserResponse>(`/auth/me?${query}`);
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

export async function removeCompetitor(competitorId: string): Promise<void> {
    return fetchApi(`/competitors/${competitorId}`, {
        method: "DELETE",
    });
}

export async function getCompetitorVideos(competitorId: string, limit = 10): Promise<VideoInfo[]> {
    return fetchApi(`/competitors/${competitorId}/videos?limit=${limit}`);
}

export interface BlueprintResult {
    gap_analysis: string[];
    content_pillars: string[];
    video_ideas: { title: string; concept: string }[];
}

export async function generateBlueprint(userId?: string): Promise<BlueprintResult> {
    return fetchApi("/competitors/blueprint", {
        method: "POST",
        body: { user_id: resolveUserId(userId) },
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

// ==================== Audit APIs ====================

export interface RetentionPoint {
    time: number;
    retention: number;
}

export interface RunAuditRequest {
    source_mode: "url" | "upload";
    video_url?: string;
    retention_points?: RetentionPoint[];
    user_id?: string;
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

export async function getAuditStatus(auditId: string): Promise<AuditStatus> {
    return fetchApi<AuditStatus>(`/audit/${auditId}`);
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
