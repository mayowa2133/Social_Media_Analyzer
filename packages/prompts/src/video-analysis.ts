/**
 * Video analysis prompt template
 * Version: 1.0.0
 */

export const VIDEO_ANALYSIS_SYSTEM_PROMPT = `You are an expert video content analyst. You analyze video frames, transcripts, and audio to identify specific moments that cause viewer drop-off.

When analyzing a video, focus on:
1. Hook quality (first 3-5 seconds) - does it grab attention?
2. Pacing issues - are there dead spots, confusing transitions, or energy drops?
3. Content delivery - is the speaker engaging? Are visuals interesting?
4. Call-to-action placement - are they intrusive or well-timed?

For each retention drop timestamp, explain exactly what happened and how to fix it.`;

export const VIDEO_ANALYSIS_USER_PROMPT_TEMPLATE = `Analyze this video content:

## Video Info
Title: {title}
Duration: {duration}s

## Transcript Segment (around drop point at {drop_timestamp}s)
{transcript_segment}

## Frame Descriptions
{frame_descriptions}

## Audio Notes
{audio_notes}

Provide your analysis in the following JSON format:
{
  "timestamp_s": {drop_timestamp},
  "issue": "brief issue name",
  "what_happened": "specific description of what happened at this moment",
  "suggested_fix": "concrete actionable fix",
  "confidence": 0.0-1.0
}`;

export const videoAnalysisPromptVersion = '1.0.0';
