import base64
import logging
import json
from typing import List, Dict, Any
from openai import OpenAI
from .models import AuditResult, AuditSection, TimestampFeedback

logger = logging.getLogger(__name__)

def get_openai_client(api_key: str) -> OpenAI:
    """Get OpenAI client, handling placeholders."""
    if not api_key or "your_" in api_key or api_key == "test-key":
        return None
    return OpenAI(api_key=api_key)

def encode_image(image_path: str) -> str:
    """Encode image to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_content(
    frames: List[str], 
    transcript: Any, 
    video_metadata: Dict[str, Any],
    api_key: str
) -> AuditResult:
    """
    Analyze video content using Multimodal LLM (GPT-4o).
    
    Args:
        frames: List of paths to keyframes
        transcript: Whisper transcription object (or dict)
        video_metadata: Title, description, etc.
        api_key: OpenAI API key
    """
    client = get_openai_client(api_key)
    
    # 1. Prepare visual context
    # Limit frames to avoid token limits / costs (e.g. max 10 frames for MVP)
    # Uniformly sample if too many
    max_frames = 10
    if len(frames) > max_frames:
        step = len(frames) // max_frames
        selected_frames = frames[::step][:max_frames]
    else:
        selected_frames = frames

    visual_parts = []
    for frame_path in selected_frames:
        base64_image = encode_image(frame_path)
        visual_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        })

    # 2. Prepare text context
    # Extract text from transcript segments with timestamps
    transcript_text = ""
    if hasattr(transcript, "segments"):
        # Helper to format transcript with timestamps
        for seg in transcript.segments:
            start = int(seg.start)
            mm = start // 60
            ss = start % 60
            transcript_text += f"[{mm:02d}:{ss:02d}] {seg.text}\n"
    elif isinstance(transcript, dict):
        transcript_text = transcript.get("text", "") # Fallback if raw text
    else:
        transcript_text = str(transcript)
        
    # Trim transcript if too long (approx token limit check)
    if len(transcript_text) > 10000:
        transcript_text = transcript_text[:10000] + "...(truncated)"

    # 3. Construct Prompt
    system_prompt = """
    You are an expert YouTube Strategist and Video Editor. 
    Analyze the provided video frames and transcript to give actionable feedback.
    
    Focus on:
    1. The "Hook" (0-30s): Is it visually engaging? Does the audio match?
    2. Pacing: Are there visual changes? Is the speech engaging?
    3. Retention Killers: Identify boring visual sections or confusing audio.
    
    Return the analysis as a strict JSON object matching this schema:
    {
      "video_id": "string",
      "overall_score": 0-10,
      "summary": "string",
      "sections": [
        {"name": "Intro", "score": 0-10, "feedback": ["string"]}
      ],
      "timestamp_feedback": [
        {
          "timestamp": "MM:SS",
          "category": "Hook|Pacing|Visuals|Audio",
          "observation": "string",
          "impact": "Positive|Negative",
          "suggestion": "string"
        }
      ]
    }
    """
    
    user_message = [
        {
            "type": "text", 
            "text": f"Analyze this video:\nTitle: {video_metadata.get('title')}\n\nTranscript:\n{transcript_text}\n\nVisual Keyframes (sampled):"
        },
        *visual_parts
    ]

    try:
        if client is None:
            logger.warning("Using MOCK LLM Analysis.")
            transcript_length = len(transcript_text or "")
            intro_score = 7 if transcript_length > 40 else 6
            content_score = 8 if transcript_length > 120 else 7
            return AuditResult(
                video_id=video_metadata.get("id", "unknown"),
                overall_score=round((intro_score + content_score) / 2),
                summary="Local fallback analysis: visuals are clear, but stronger pacing and hook clarity would improve retention.",
                sections=[
                    AuditSection(name="Intro", score=intro_score, feedback=["Hook is understandable but could be sharper in first 3 seconds."]),
                    AuditSection(name="Content", score=content_score, feedback=["Narration is clear; add faster visual changes to keep momentum."])
                ],
                timestamp_feedback=[
                    TimestampFeedback(
                        timestamp="00:05", 
                        category="Visuals", 
                        observation="Scene remains static for too long.",
                        impact="Negative",
                        suggestion="Add a cutaway/B-roll insert by 00:05 to re-capture attention."
                    )
                ]
            )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Ensure video_id matches input
        data["video_id"] = video_metadata.get("id", "unknown")
        
        return AuditResult(**data)
        
    except Exception as e:
        logger.error(f"Error in LLM analysis: {e}")
        # Return fallback or re-raise
        raise
