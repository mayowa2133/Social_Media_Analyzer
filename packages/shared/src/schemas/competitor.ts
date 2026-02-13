import { z } from 'zod';

/**
 * Competitor blueprint schema
 */
export const CompetitorBlueprintSchema = z.object({
    competitor_id: z.string(),
    competitor_name: z.string(),
    median_video_length_s: z.number(),
    avg_posting_frequency_per_week: z.number(),
    top_topics: z.array(z.string()),
    hook_patterns: z.array(z.string()),
    best_performing_formats: z.array(z.string()),
});

export type CompetitorBlueprint = z.infer<typeof CompetitorBlueprintSchema>;

/**
 * Competitor comparison schema
 */
export const CompetitorComparisonSchema = z.object({
    user_metrics: z.object({
        avg_video_length_s: z.number(),
        posting_frequency_per_week: z.number(),
        avg_views: z.number(),
        avg_engagement_rate: z.number(),
    }),
    competitor_avg_metrics: z.object({
        avg_video_length_s: z.number(),
        posting_frequency_per_week: z.number(),
        avg_views: z.number(),
        avg_engagement_rate: z.number(),
    }),
    deltas: z.object({
        video_length_diff_s: z.number(),
        posting_frequency_diff: z.number(),
        views_diff_percent: z.number(),
        engagement_diff_percent: z.number(),
    }),
    recommendations: z.array(z.string()),
});

export type CompetitorComparison = z.infer<typeof CompetitorComparisonSchema>;
