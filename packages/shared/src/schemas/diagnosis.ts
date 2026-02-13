import { z } from 'zod';

/**
 * Diagnosis evidence schema
 */
export const DiagnosisEvidenceSchema = z.object({
    metric: z.string(),
    value: z.string(),
    interpretation: z.string(),
});

export type DiagnosisEvidence = z.infer<typeof DiagnosisEvidenceSchema>;

/**
 * Recommendation schema
 */
export const RecommendationSchema = z.object({
    title: z.string(),
    description: z.string(),
    priority: z.enum(['high', 'medium', 'low']),
});

export type Recommendation = z.infer<typeof RecommendationSchema>;

/**
 * Primary issue types
 */
export const PrimaryIssueSchema = z.enum([
    'PACKAGING',
    'RETENTION',
    'TOPIC_FIT',
    'CONSISTENCY',
]);

export type PrimaryIssue = z.infer<typeof PrimaryIssueSchema>;

/**
 * Full diagnosis response schema
 */
export const DiagnosisResponseSchema = z.object({
    summary: z.string(),
    primary_issue: PrimaryIssueSchema,
    evidence: z.array(DiagnosisEvidenceSchema),
    recommendations: z.array(RecommendationSchema),
});

export type DiagnosisResponse = z.infer<typeof DiagnosisResponseSchema>;
