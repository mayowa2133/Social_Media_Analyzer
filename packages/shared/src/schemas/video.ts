import { z } from 'zod';

/**
 * Video timestamp feedback schema
 */
export const TimestampFeedbackSchema = z.object({
    timestamp_s: z.number(),
    issue: z.string(),
    what_happened: z.string(),
    suggested_fix: z.string(),
    confidence: z.number().min(0).max(1),
});

export type TimestampFeedback = z.infer<typeof TimestampFeedbackSchema>;

/**
 * Video analysis result schema
 */
export const VideoAnalysisResultSchema = z.object({
    video_id: z.string(),
    overall_assessment: z.string(),
    hook_quality: z.enum(['weak', 'moderate', 'strong']),
    pacing_assessment: z.string(),
    retention_issues: z.array(TimestampFeedbackSchema),
    title_suggestions: z.array(z.string()),
    hook_rewrites: z.array(z.string()),
});

export type VideoAnalysisResult = z.infer<typeof VideoAnalysisResultSchema>;
