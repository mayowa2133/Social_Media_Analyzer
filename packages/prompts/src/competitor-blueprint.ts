/**
 * Competitor blueprint prompt template
 * Version: 1.0.0
 */

export const COMPETITOR_BLUEPRINT_SYSTEM_PROMPT = `You are an expert at reverse-engineering successful content strategies from competitor data.

Your goal is to analyze what top performers do differently and create an actionable blueprint for the user to follow.

Focus on:
1. Content format patterns (length, style, structure)
2. Topic selection and framing
3. Hook and title patterns
4. Posting frequency and timing
5. Engagement tactics`;

export const COMPETITOR_BLUEPRINT_USER_PROMPT_TEMPLATE = `Create a competitor blueprint based on this data:

## User's Channel Performance
{user_stats}

## Top Competitors
{competitor_data}

Generate a "Next 10 Videos" action plan with:
1. Specific video ideas based on competitor success patterns
2. Suggested hooks inspired by top performers
3. Optimal format recommendations (length, style)
4. Posting schedule recommendation

Output as JSON:
{
  "blueprint_summary": "1-2 sentences on the strategy",
  "format_recommendations": {
    "optimal_length_range_s": [min, max],
    "recommended_posting_frequency": "X times per week",
    "style_notes": ["note 1", "note 2"]
  },
  "next_10_videos": [
    {
      "video_number": 1,
      "topic_idea": "description",
      "hook_suggestion": "example hook",
      "title_template": "title pattern",
      "estimated_length_s": 500
    }
  ],
  "hooks_to_test": ["hook 1", "hook 2", "hook 3"],
  "title_patterns": ["pattern 1", "pattern 2"]
}`;

export const competitorBlueprintPromptVersion = '1.0.0';
