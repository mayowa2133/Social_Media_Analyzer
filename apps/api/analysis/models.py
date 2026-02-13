"""
Analysis models and schemas.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum


class IssueType(str, Enum):
    PACKAGING = "PACKAGING"      # Titles/Thumbnails/Clickability
    RETENTION = "RETENTION"      # Content quality/Hook/Pacing
    TOPIC_FIT = "TOPIC_FIT"      # Subject matter mismatch
    CONSISTENCY = "CONSISTENCY"  # Upload schedule irregular
    UNDEFINED = "UNDEFINED"


class EvidenceType(str, Enum):
    STATISTIC = "STATISTIC"      # "Avg views 500 vs 10k subscribers"
    COMPARISON = "COMPARISON"    # "3x lower CTR than top video"
    PATTERN = "PATTERN"          # "Questions in titles perform 20% better"


class MetricEvidence(BaseModel):
    """Specific data point supporting a diagnosis."""
    type: EvidenceType
    message: str
    value: Optional[float] = None
    benchmark: Optional[float] = None


class ActionItem(BaseModel):
    """Specific recommendation."""
    title: str
    description: str
    priority: int  # 1 (Highest) to 3 (Lowest)


class DiagnosisResult(BaseModel):
    """Final output of the channel/video analysis."""
    channel_id: str
    analyzed_video_count: int
    primary_issue: IssueType
    summary: str
    evidence: List[MetricEvidence]
    recommendations: List[ActionItem]
    
    # Raw metrics for UI visualization
    metrics: Dict[str, Any] = {}
