from typing import List, Optional
from pydantic import BaseModel

class TimestampFeedback(BaseModel):
    timestamp: str  # e.g., "00:45"
    category: str   # "Hook", "Pacing", "Visuals", "Audio"
    observation: str
    impact: str     # "Positive", "Negative", "Neutral"
    suggestion: Optional[str] = None

class AuditSection(BaseModel):
    name: str       # "Intro", "Body", "Outro"
    score: int      # 1-10
    feedback: List[str]

class AuditResult(BaseModel):
    video_id: str
    overall_score: int
    summary: str
    sections: List[AuditSection]
    timestamp_feedback: List[TimestampFeedback]
