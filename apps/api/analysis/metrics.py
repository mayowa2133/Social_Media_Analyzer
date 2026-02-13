"""
Core metrics analysis logic.
"""

import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Tuple
import re
from collections import Counter

from .models import DiagnosisResult, IssueType, MetricEvidence, EvidenceType, ActionItem


class ChannelAnalyzer:
    """Analyzes channel performance data to diagnose issues."""

    def __init__(self, channel_data: Dict[str, Any], videos: List[Dict[str, Any]]):
        self.channel = channel_data
        self.videos = sorted(videos, key=lambda v: v.get("published_at", ""), reverse=True)
        # Filter out videos with no views (shorts/upcoming) if needed, but keeping all for now
        self.valid_videos = [v for v in self.videos if v.get("view_count", 0) > 0]

    def analyze(self) -> DiagnosisResult:
        """Perform full analysis and return diagnosis."""
        if not self.valid_videos:
            return self._create_empty_diagnosis()

        # 1. Compute Base Metrics
        consistency_stats = self._analyze_consistency()
        packaging_stats = self._analyze_packaging()
        outliers = self._detect_outliers()
        topic_clusters = self._cluster_topics()

        # 2. Determine Primary Issue
        primary_issue, evidence = self._determine_primary_issue(
            consistency_stats, packaging_stats, outliers
        )

        # 3. Generate Recommendations
        recommendations = self._generate_recommendations(primary_issue, outliers, topic_clusters)

        return DiagnosisResult(
            channel_id=self.channel.get("id", ""),
            analyzed_video_count=len(self.valid_videos),
            primary_issue=primary_issue,
            summary=self._generate_summary(primary_issue, evidence),
            evidence=evidence,
            recommendations=recommendations,
            metrics={
                "consistency": consistency_stats,
                "packaging": packaging_stats,
                "top_topics": topic_clusters,
            }
        )

    def _create_empty_diagnosis(self) -> DiagnosisResult:
        return DiagnosisResult(
            channel_id=self.channel.get("id", ""),
            analyzed_video_count=0,
            primary_issue=IssueType.UNDEFINED,
            summary="Not enough data to analyze.",
            evidence=[],
            recommendations=[]
        )

    def _analyze_consistency(self) -> Dict[str, Any]:
        """Analyze upload schedule consistency."""
        if len(self.valid_videos) < 2:
            return {"variance": 0, "median_days": 0}

        dates = []
        for v in self.valid_videos:
            dt = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.astimezone()
            dates.append(dt)
            
        # Sort oldest to newest
        dates.sort()
    
        diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        
        now = datetime.now().astimezone()
        last_upload_days = (now - dates[-1]).days
        
        return {
            "median_days": float(np.median(diffs)),
            "variance": float(np.var(diffs)),
            "std_dev": float(np.std(diffs)),
            "last_upload_days": last_upload_days
        }

    def _analyze_packaging(self) -> Dict[str, Any]:
        """Analyze titles and potential CTR signals."""
        titles = [v.get("title", "") for v in self.valid_videos]
        
        avg_len = np.mean([len(t) for t in titles])
        question_mark_pct = sum(1 for t in titles if "?" in t) / len(titles)
        uppercase_ratio = np.mean([sum(1 for c in t if c.isupper()) / len(t) if len(t) > 0 else 0 for t in titles])
        
        return {
            "avg_title_length": float(avg_len),
            "question_mark_usage": float(question_mark_pct),
            "uppercase_ratio": float(uppercase_ratio)
        }

    def _detect_outliers(self, percentile: float = 90.0) -> List[Dict[str, Any]]:
        """Identify top performing videos."""
        views = [v.get("view_count", 0) for v in self.valid_videos]
        if not views:
            return []
            
        threshold = np.percentile(views, percentile)
        return [v for v in self.valid_videos if v.get("view_count", 0) >= threshold]

    def _cluster_topics(self) -> List[Dict[str, Any]]:
        """Basic keyword frequency analysis."""
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
        
        all_words = []
        for v in self.valid_videos:
            # Simple tokenization
            words = re.findall(r'\w+', v.get("title", "").lower())
            all_words.extend([w for w in words if w not in stop_words and len(w) > 3])
            
        counts = Counter(all_words)
        total = sum(counts.values()) or 1
        
        return [
            {"topic": word, "count": count, "percentage": count/total}
            for word, count in counts.most_common(5)
        ]

    def _determine_primary_issue(
        self, 
        consistency: Dict[str, Any], 
        packaging: Dict[str, Any],
        outliers: List[Dict[str, Any]]
    ) -> Tuple[IssueType, List[MetricEvidence]]:
        """Heuristics to determine the biggest bottleneck."""
        evidence = []
        
        # 1. Check Consistency
        # lowered threshold to 3.0 to catch moderate inconsistency
        # median_days > 2 allows for frequent but erratic schedules to be flagged
        if consistency["std_dev"] > 3.0 and consistency["median_days"] > 2:
            evidence.append(MetricEvidence(
                type=EvidenceType.STATISTIC,
                message=f"Upload schedule varies by +/- {consistency['std_dev']:.1f} days",
                value=consistency["std_dev"]
            ))
            return IssueType.CONSISTENCY, evidence

        # 2. Check Topic Fit (Prioritize this over packaging if recent drop is severe)
        views = [v.get("view_count", 0) for v in self.valid_videos]
        median_views = np.median(views) if views else 0
        
        # Check if outliers exist but most recent videos are low
        if len(self.valid_videos) >= 5:
            recent_views = [v.get("view_count", 0) for v in self.valid_videos[:3]]
            avg_recent = np.mean(recent_views) if recent_views else 0
            
            if avg_recent < median_views * 0.5:
                evidence.append(MetricEvidence(
                    type=EvidenceType.COMPARISON,
                    message="Recent 3 videos underperforming average by 50%+",
                    value=avg_recent,
                    benchmark=median_views
                ))
                return IssueType.TOPIC_FIT, evidence

        # 3. Check Packaging (CTR proxy)
        # Only trigger if we have enough data and no recent breakout
        max_views = np.max(views) if views else 0
        
        if len(views) > 3 and max_views < (median_views * 1.5):
             evidence.append(MetricEvidence(
                type=EvidenceType.PATTERN,
                message="No breakout videos recently (max views < 1.5x median)",
                value=max_views,
                benchmark=median_views * 1.5
            ))
             return IssueType.PACKAGING, evidence

        # If everything looks okay or specific retention data missing, default to Retention
        # (Retention is usually the problem if they get clicks but algorithm stops pushing)
        evidence.append(MetricEvidence(
            type=EvidenceType.STATISTIC,
            message="Consistency and hooks appear stable, suggesting mid-video dropoff",
        ))
        return IssueType.RETENTION, evidence

    def _generate_summary(self, issue: IssueType, evidence: List[MetricEvidence]) -> str:
        """Generate human-readable summary."""
        if issue == IssueType.CONSISTENCY:
            return "Your irregular upload schedule is likely preventing algorithm momentum."
        elif issue == IssueType.PACKAGING:
            return "Your videos aren't getting enough initial clicks. Titles or thumbnails may be the bottleneck."
        elif issue == IssueType.TOPIC_FIT:
            return "Your recent topics aren't resonating with your established audience."
        elif issue == IssueType.RETENTION:
            return "You're getting clicks, but viewers are dropping off. Pacing or content delivery needs work."
        return "Analysis complete."

    def _generate_recommendations(
        self, 
        issue: IssueType, 
        outliers: List[Dict[str, Any]],
        top_topics: List[Dict[str, Any]]
    ) -> List[ActionItem]:
        """Generate actionable advice."""
        actions = []
        
        if issue == IssueType.CONSISTENCY:
            actions.append(ActionItem(
                title="Establish a Schedule",
                description="Pick 2 days a week and stick to them for 4 weeks.",
                priority=1
            ))
            
        elif issue == IssueType.PACKAGING:
            actions.append(ActionItem(
                title="Revamp Titles",
                description="Try shorter, punchier titles (under 50 chars) with strong verbs.",
                priority=1
            ))
            
        elif issue == IssueType.TOPIC_FIT:
            if top_topics:
                topic = top_topics[0]["topic"]
                actions.append(ActionItem(
                    title=f"Return to Core Topic: {topic}",
                    description=f"Your best performing videos mention '{topic}'. Make 3 more on this.",
                    priority=1
                ))
            
        elif issue == IssueType.RETENTION:
            actions.append(ActionItem(
                title="Audit the Hook",
                description="Check the first 30 seconds of your last video. Does it deliver on the title instantly?",
                priority=1
            ))

        # General recommendation from outliers
        if outliers:
            best = outliers[0]
            actions.append(ActionItem(
                title="Analyze Best Performer",
                description=f"Study '{best.get('title')}' - it got {best.get('view_count')} views. Replicate its format.",
                priority=2
            ))
            
        return actions
