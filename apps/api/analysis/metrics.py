"""
Core metrics analysis logic.
"""

import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .models import ActionItem, DiagnosisResult, EvidenceType, IssueType, MetricEvidence


class ChannelAnalyzer:
    """Analyzes channel performance data to diagnose issues."""

    SHORT_FORM_MAX_SECONDS = 60
    HOOK_KEYWORDS = {
        "secret",
        "mistake",
        "truth",
        "before",
        "after",
        "vs",
        "never",
        "reason",
        "warning",
        "fix",
    }
    STORY_KEYWORDS = {
        "story",
        "journey",
        "lesson",
        "mistake",
        "behind",
        "case study",
        "challenge",
        "experiment",
    }

    def __init__(self, channel_data: Dict[str, Any], videos: List[Dict[str, Any]]):
        self.channel = channel_data
        self.videos = sorted(videos, key=lambda v: v.get("published_at", ""), reverse=True)
        # Keep only videos with at least some view signal.
        self.valid_videos = [v for v in self.videos if v.get("view_count", 0) > 0]
        self._feature_cache: Optional[List[Dict[str, Any]]] = None

    def analyze(self) -> DiagnosisResult:
        """Perform full analysis and return diagnosis."""
        if not self.valid_videos:
            return self._create_empty_diagnosis()

        consistency_stats = self._analyze_consistency()
        packaging_stats = self._analyze_packaging()
        outliers = self._detect_outliers()
        topic_clusters = self._cluster_topics()
        winner_analysis = self._analyze_winner_patterns()
        format_breakdown = self._analyze_format_performance()
        social_signal_summary = self._build_social_signal_summary(
            winner_analysis, format_breakdown, consistency_stats
        )
        strategy_playbook = self._build_strategy_playbook(
            winner_analysis,
            format_breakdown,
            social_signal_summary,
            topic_clusters,
        )
        video_scorecards = self._build_video_scorecards(winner_analysis, format_breakdown)

        primary_issue, evidence = self._determine_primary_issue(
            consistency_stats, packaging_stats, outliers
        )
        evidence.extend(self._build_winner_evidence(winner_analysis, format_breakdown))
        evidence.extend(self._build_signal_evidence(social_signal_summary))

        recommendations = self._generate_recommendations(
            issue=primary_issue,
            outliers=outliers,
            top_topics=topic_clusters,
            winner_analysis=winner_analysis,
            format_breakdown=format_breakdown,
            social_signal_summary=social_signal_summary,
            strategy_playbook=strategy_playbook,
        )

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
                "winner_analysis": winner_analysis,
                "format_breakdown": format_breakdown,
                "social_signal_summary": social_signal_summary,
                "strategy_playbook": strategy_playbook,
                "video_scorecards": video_scorecards,
                "platform_context": {
                    "platform": "youtube",
                    "format_definition": (
                        f"short_form <= {self.SHORT_FORM_MAX_SECONDS}s, "
                        f"long_form > {self.SHORT_FORM_MAX_SECONDS}s"
                    ),
                    "limitations": (
                        "Public YouTube Data API exposes likes/comments but not per-video "
                        "shares, saves, or retention curves; these are estimated with "
                        "transparent proxies."
                    ),
                },
            },
        )

    def _create_empty_diagnosis(self) -> DiagnosisResult:
        return DiagnosisResult(
            channel_id=self.channel.get("id", ""),
            analyzed_video_count=0,
            primary_issue=IssueType.UNDEFINED,
            summary="Not enough data to analyze.",
            evidence=[],
            recommendations=[],
        )

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.astimezone()
            return dt
        except Exception:
            return None

    def _analyze_consistency(self) -> Dict[str, Any]:
        """Analyze upload schedule consistency."""
        dates: List[datetime] = []
        for video in self.valid_videos:
            parsed = self._parse_datetime(video.get("published_at", ""))
            if parsed:
                dates.append(parsed)

        if len(dates) < 2:
            return {
                "median_days": 0.0,
                "variance": 0.0,
                "std_dev": 0.0,
                "last_upload_days": 0,
                "posts_per_week": 0.0,
            }

        dates.sort()
        diffs = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        now = datetime.now().astimezone()
        last_upload_days = (now - dates[-1]).days

        span_days = max(1, (dates[-1] - dates[0]).days)
        posts_per_week = (len(dates) * 7.0) / span_days

        return {
            "median_days": float(np.median(diffs)),
            "variance": float(np.var(diffs)),
            "std_dev": float(np.std(diffs)),
            "last_upload_days": int(last_upload_days),
            "posts_per_week": float(posts_per_week),
        }

    def _analyze_packaging(self) -> Dict[str, Any]:
        """Analyze titles and potential CTR-style signals."""
        titles = [v.get("title", "") for v in self.valid_videos]
        avg_len = np.mean([len(t) for t in titles])
        question_mark_pct = sum(1 for t in titles if "?" in t) / len(titles)
        uppercase_ratio = np.mean(
            [sum(1 for c in t if c.isupper()) / len(t) if len(t) > 0 else 0 for t in titles]
        )

        return {
            "avg_title_length": float(avg_len),
            "question_mark_usage": float(question_mark_pct),
            "uppercase_ratio": float(uppercase_ratio),
        }

    def _detect_outliers(self, percentile: float = 90.0) -> List[Dict[str, Any]]:
        """Identify top-performing videos by view count."""
        views = [v.get("view_count", 0) for v in self.valid_videos]
        if not views:
            return []

        threshold = np.percentile(views, percentile)
        return [v for v in self.valid_videos if v.get("view_count", 0) >= threshold]

    def _cluster_topics(self) -> List[Dict[str, Any]]:
        """Basic keyword frequency analysis."""
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
        }

        all_words = []
        for video in self.valid_videos:
            words = re.findall(r"\w+", video.get("title", "").lower())
            all_words.extend([w for w in words if w not in stop_words and len(w) > 3])

        counts = Counter(all_words)
        total = sum(counts.values()) or 1
        return [
            {"topic": word, "count": count, "percentage": count / total}
            for word, count in counts.most_common(5)
        ]

    def _safe_rate(self, numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return float(numerator / denominator)

    def _classify_format(self, duration_seconds: int) -> str:
        if duration_seconds <= 0:
            return "unknown"
        if duration_seconds <= self.SHORT_FORM_MAX_SECONDS:
            return "short_form"
        return "long_form"

    def _has_story_signal(self, title: str) -> bool:
        lower = title.lower()
        if any(term in lower for term in self.STORY_KEYWORDS):
            return True
        return re.search(r"\b(i|we)\s+(tried|tested|learned|built)\b", lower) is not None

    def _has_thought_prompt(self, title: str) -> bool:
        lower = title.lower()
        return (
            "?" in lower
            or re.search(r"\bwhat if\b", lower) is not None
            or re.search(r"\bshould (you|we)\b", lower) is not None
            or re.search(r"\bis .* worth it\b", lower) is not None
            or re.search(r"\bcan (you|we)\b", lower) is not None
        )

    def _hook_signal_score(self, title: str) -> int:
        lower = title.lower()
        score = 0
        if "?" in title:
            score += 1
        if re.search(r"\b\d+\b", title):
            score += 1
        if re.search(r"\b(how|why|what|when|can|should|is|are|will)\b", lower):
            score += 1
        if any(term in lower for term in self.HOOK_KEYWORDS):
            score += 1
        return score

    def _video_features(self, video: Dict[str, Any]) -> Dict[str, Any]:
        title = (video.get("title") or "").strip()
        views = float(video.get("view_count", 0) or 0)
        likes = float(video.get("like_count", 0) or 0)
        comments = float(video.get("comment_count", 0) or 0)
        shares = float(video.get("shares", 0) or 0)
        saves = float(video.get("saves", 0) or 0)
        has_true_shares = ("shares" in video) and (video.get("shares") is not None)
        has_true_saves = ("saves" in video) and (video.get("saves") is not None)
        retention_points = video.get("retention_points")
        has_true_retention = isinstance(retention_points, list) and len(retention_points) > 0
        duration_seconds = int(video.get("duration_seconds", 0) or 0)
        hook_signal = self._hook_signal_score(title)
        story_signal = self._has_story_signal(title)
        thought_prompt = self._has_thought_prompt(title)

        like_rate = self._safe_rate(likes, views)
        comment_rate = self._safe_rate(comments, views)
        engagement_rate = self._safe_rate(likes + (comments * 2.0), views)

        retention_proxy = min(1.0, (engagement_rate * 4.0) + (0.08 if hook_signal >= 2 else 0.0))
        if has_true_retention:
            valid_points = []
            for point in retention_points:
                if not isinstance(point, dict):
                    continue
                value = point.get("retention")
                try:
                    valid_points.append(float(value))
                except (TypeError, ValueError):
                    continue
            if valid_points:
                retention_proxy = min(1.0, max(0.0, float(np.mean(valid_points)) / 100.0))

        share_rate_true = self._safe_rate(shares, views) if has_true_shares else 0.0
        save_rate_true = self._safe_rate(saves, views) if has_true_saves else 0.0
        amplification_proxy = (
            min(1.0, share_rate_true * 20.0)
            if has_true_shares
            else min(
                1.0,
                (engagement_rate * 2.4)
                + (0.12 if thought_prompt else 0.0)
                + (0.08 if story_signal else 0.0),
            )
        )
        save_intent_proxy = (
            min(1.0, save_rate_true * 20.0)
            if has_true_saves
            else min(
                1.0,
                (engagement_rate * 1.8)
                + (0.10 if duration_seconds > 300 else 0.04)
                + (0.07 if hook_signal >= 2 else 0.0),
            )
        )

        return {
            "video_id": video.get("id"),
            "title": title,
            "published_at": video.get("published_at"),
            "view_count": int(views),
            "like_count": int(likes),
            "comment_count": int(comments),
            "duration_seconds": duration_seconds,
            "format_type": self._classify_format(duration_seconds),
            "like_rate": float(like_rate),
            "comment_rate": float(comment_rate),
            "engagement_rate": float(engagement_rate),
            "retention_proxy": float(retention_proxy),
            "amplification_proxy": float(amplification_proxy),
            "save_intent_proxy": float(save_intent_proxy),
            "has_true_shares": bool(has_true_shares),
            "has_true_saves": bool(has_true_saves),
            "has_true_retention": bool(has_true_retention),
            "share_rate_true": float(share_rate_true),
            "save_rate_true": float(save_rate_true),
            "hook_signal": hook_signal,
            "story_signal": bool(story_signal),
            "thought_prompt_signal": bool(thought_prompt),
        }

    def _get_features(self) -> List[Dict[str, Any]]:
        if self._feature_cache is None:
            self._feature_cache = [self._video_features(v) for v in self.valid_videos]
        return self._feature_cache

    def _avg(self, rows: List[Dict[str, Any]], key: str) -> float:
        if not rows:
            return 0.0
        return float(np.mean([r.get(key, 0.0) for r in rows]))

    def _rate(self, rows: List[Dict[str, Any]], predicate) -> float:
        if not rows:
            return 0.0
        matched = sum(1 for r in rows if predicate(r))
        return float(matched / len(rows))

    def _analyze_winner_patterns(self) -> Dict[str, Any]:
        features = self._get_features()
        if not features:
            return {
                "winner_count": 0,
                "baseline_count": 0,
                "winner_video_ids": [],
                "top_videos": [],
            }

        views = [f["view_count"] for f in features]
        winner_threshold = float(np.percentile(views, 80))
        winners = [f for f in features if f["view_count"] >= winner_threshold]
        if not winners:
            winners = sorted(features, key=lambda f: f["view_count"], reverse=True)[:1]

        winner_ids = {w.get("video_id") for w in winners}
        baseline = [f for f in features if f.get("video_id") not in winner_ids]
        if not baseline:
            baseline = winners

        top_videos = [
            {
                "video_id": v.get("video_id"),
                "title": v.get("title"),
                "view_count": v.get("view_count"),
                "duration_seconds": v.get("duration_seconds"),
                "format_type": v.get("format_type"),
                "engagement_rate": round(v.get("engagement_rate", 0.0), 4),
                "retention_proxy": round(v.get("retention_proxy", 0.0), 4),
                "amplification_proxy": round(v.get("amplification_proxy", 0.0), 4),
                "save_intent_proxy": round(v.get("save_intent_proxy", 0.0), 4),
                "hook_signal": v.get("hook_signal", 0),
            }
            for v in sorted(winners, key=lambda row: row["view_count"], reverse=True)[:3]
        ]

        return {
            "winner_threshold_views": winner_threshold,
            "winner_count": len(winners),
            "baseline_count": len(baseline),
            "winner_video_ids": [w.get("video_id") for w in winners if w.get("video_id")],
            "winner_avg_views": self._avg(winners, "view_count"),
            "baseline_avg_views": self._avg(baseline, "view_count"),
            "winner_avg_like_rate": self._avg(winners, "like_rate"),
            "baseline_avg_like_rate": self._avg(baseline, "like_rate"),
            "winner_avg_comment_rate": self._avg(winners, "comment_rate"),
            "baseline_avg_comment_rate": self._avg(baseline, "comment_rate"),
            "winner_avg_engagement_rate": self._avg(winners, "engagement_rate"),
            "baseline_avg_engagement_rate": self._avg(baseline, "engagement_rate"),
            "winner_avg_retention_proxy": self._avg(winners, "retention_proxy"),
            "baseline_avg_retention_proxy": self._avg(baseline, "retention_proxy"),
            "winner_avg_amplification_proxy": self._avg(winners, "amplification_proxy"),
            "baseline_avg_amplification_proxy": self._avg(baseline, "amplification_proxy"),
            "winner_avg_save_intent_proxy": self._avg(winners, "save_intent_proxy"),
            "baseline_avg_save_intent_proxy": self._avg(baseline, "save_intent_proxy"),
            "winner_hook_signal_rate": self._rate(winners, lambda v: v.get("hook_signal", 0) >= 2),
            "baseline_hook_signal_rate": self._rate(baseline, lambda v: v.get("hook_signal", 0) >= 2),
            "winner_story_signal_rate": self._rate(winners, lambda v: v.get("story_signal", False)),
            "baseline_story_signal_rate": self._rate(baseline, lambda v: v.get("story_signal", False)),
            "winner_thought_prompt_rate": self._rate(
                winners, lambda v: v.get("thought_prompt_signal", False)
            ),
            "baseline_thought_prompt_rate": self._rate(
                baseline, lambda v: v.get("thought_prompt_signal", False)
            ),
            "winner_avg_duration_seconds": self._avg(winners, "duration_seconds"),
            "baseline_avg_duration_seconds": self._avg(baseline, "duration_seconds"),
            "top_videos": top_videos,
        }

    def _analyze_format_performance(self) -> Dict[str, Any]:
        features = self._get_features()
        groups = {"short_form": [], "long_form": [], "unknown": []}
        for video in features:
            groups[video["format_type"]].append(video)

        total_views = float(sum(v["view_count"] for v in features) or 1.0)

        def _summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not rows:
                return {
                    "count": 0,
                    "avg_views": 0.0,
                    "median_views": 0.0,
                    "avg_duration_seconds": 0.0,
                    "avg_like_rate": 0.0,
                    "avg_comment_rate": 0.0,
                    "avg_engagement_rate": 0.0,
                    "avg_retention_proxy": 0.0,
                    "avg_amplification_proxy": 0.0,
                    "avg_save_intent_proxy": 0.0,
                    "view_share": 0.0,
                    "top_video_title": None,
                }

            top_video = max(rows, key=lambda r: r.get("view_count", 0))
            views = [r.get("view_count", 0) for r in rows]
            views_sum = float(sum(views))
            return {
                "count": len(rows),
                "avg_views": float(np.mean(views)),
                "median_views": float(np.median(views)),
                "avg_duration_seconds": self._avg(rows, "duration_seconds"),
                "avg_like_rate": self._avg(rows, "like_rate"),
                "avg_comment_rate": self._avg(rows, "comment_rate"),
                "avg_engagement_rate": self._avg(rows, "engagement_rate"),
                "avg_retention_proxy": self._avg(rows, "retention_proxy"),
                "avg_amplification_proxy": self._avg(rows, "amplification_proxy"),
                "avg_save_intent_proxy": self._avg(rows, "save_intent_proxy"),
                "view_share": views_sum / total_views,
                "top_video_title": top_video.get("title"),
            }

        short_form = _summary(groups["short_form"])
        long_form = _summary(groups["long_form"])

        dominant_format = "mixed"
        if short_form["count"] >= 2 and long_form["count"] >= 2:
            if short_form["avg_views"] > (long_form["avg_views"] * 1.2):
                dominant_format = "short_form"
            elif long_form["avg_views"] > (short_form["avg_views"] * 1.2):
                dominant_format = "long_form"

        return {
            "short_form": short_form,
            "long_form": long_form,
            "unknown": _summary(groups["unknown"]),
            "dominant_format": dominant_format,
            "definition": (
                f"short_form <= {self.SHORT_FORM_MAX_SECONDS}s, "
                f"long_form > {self.SHORT_FORM_MAX_SECONDS}s"
            ),
        }

    def _build_social_signal_summary(
        self,
        winner_analysis: Dict[str, Any],
        format_breakdown: Dict[str, Any],
        consistency_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        features = self._get_features()
        avg_like_rate = self._avg(features, "like_rate")
        avg_comment_rate = self._avg(features, "comment_rate")
        avg_engagement_rate = self._avg(features, "engagement_rate")
        avg_amplification_proxy = self._avg(features, "amplification_proxy")
        avg_save_intent_proxy = self._avg(features, "save_intent_proxy")
        true_share_ratio = self._rate(features, lambda v: v.get("has_true_shares", False))
        true_save_ratio = self._rate(features, lambda v: v.get("has_true_saves", False))
        true_retention_ratio = self._rate(features, lambda v: v.get("has_true_retention", False))

        posts_per_week = float(consistency_stats.get("posts_per_week", 0.0))
        if posts_per_week < 2.0:
            cadence_health = "low"
        elif posts_per_week <= 5.0:
            cadence_health = "healthy"
        else:
            cadence_health = "high"

        dominant_format = format_breakdown.get("dominant_format", "mixed")
        if dominant_format == "short_form":
            cadence_recommendation = "Aim for 3-5 quality uploads/week with strong opening hooks."
        elif dominant_format == "long_form":
            cadence_recommendation = "Aim for 1-3 long-form uploads/week and support with Shorts clips."
        else:
            cadence_recommendation = "Aim for consistent cadence: usually 3-5 quality uploads/week."

        shares_interpretation = (
            "Calculated from true share counts imported from platform analytics."
            if true_share_ratio >= 0.6
            else "Estimated from engagement + curiosity/story cues (direct share count unavailable)."
        )
        saves_interpretation = (
            "Calculated from true save counts imported from platform analytics."
            if true_save_ratio >= 0.6
            else "Estimated from evergreen/value cues + engagement (direct save count unavailable)."
        )

        return {
            "likes": {
                "avg_rate": avg_like_rate,
                "winner_rate": winner_analysis.get("winner_avg_like_rate", 0.0),
                "baseline_rate": winner_analysis.get("baseline_avg_like_rate", 0.0),
                "interpretation": "Fast validation signal; useful but weaker than comments/shares/saves.",
            },
            "comments": {
                "avg_rate": avg_comment_rate,
                "winner_rate": winner_analysis.get("winner_avg_comment_rate", 0.0),
                "baseline_rate": winner_analysis.get("baseline_avg_comment_rate", 0.0),
                "interpretation": "Deep engagement signal; strong indicator of conversation and relevance.",
            },
            "shares": {
                "avg_proxy": avg_amplification_proxy,
                "winner_proxy": winner_analysis.get("winner_avg_amplification_proxy", 0.0),
                "baseline_proxy": winner_analysis.get("baseline_avg_amplification_proxy", 0.0),
                "interpretation": shares_interpretation,
            },
            "saves": {
                "avg_proxy": avg_save_intent_proxy,
                "winner_proxy": winner_analysis.get("winner_avg_save_intent_proxy", 0.0),
                "baseline_proxy": winner_analysis.get("baseline_avg_save_intent_proxy", 0.0),
                "interpretation": saves_interpretation,
            },
            "posting_cadence": {
                "posts_per_week": posts_per_week,
                "health": cadence_health,
                "recommendation": cadence_recommendation,
            },
            "engagement": {
                "avg_rate": avg_engagement_rate,
                "winner_rate": winner_analysis.get("winner_avg_engagement_rate", 0.0),
                "baseline_rate": winner_analysis.get("baseline_avg_engagement_rate", 0.0),
            },
            "metric_coverage": {
                "likes": "available",
                "comments": "available",
                "shares": "true" if true_share_ratio >= 0.6 else "proxy",
                "saves": "true" if true_save_ratio >= 0.6 else "proxy",
                "retention_curve": "true" if true_retention_ratio >= 0.6 else "proxy",
            },
        }

    def _build_signal_evidence(self, social_signal_summary: Dict[str, Any]) -> List[MetricEvidence]:
        evidence: List[MetricEvidence] = []

        comments = social_signal_summary.get("comments", {})
        if comments.get("winner_rate", 0.0) > (comments.get("baseline_rate", 0.0) * 1.2):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="Higher comment rate strongly correlates with your winning videos.",
                    value=comments.get("winner_rate", 0.0),
                    benchmark=comments.get("baseline_rate", 0.0),
                )
            )

        shares = social_signal_summary.get("shares", {})
        if shares.get("winner_proxy", 0.0) > (shares.get("baseline_proxy", 0.0) * 1.15):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="Winning videos have stronger amplification/shareability signals.",
                    value=shares.get("winner_proxy", 0.0),
                    benchmark=shares.get("baseline_proxy", 0.0),
                )
            )

        saves = social_signal_summary.get("saves", {})
        if saves.get("winner_proxy", 0.0) > (saves.get("baseline_proxy", 0.0) * 1.15):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="Winning videos show stronger save-intent (long-term value) signals.",
                    value=saves.get("winner_proxy", 0.0),
                    benchmark=saves.get("baseline_proxy", 0.0),
                )
            )

        cadence = social_signal_summary.get("posting_cadence", {})
        if cadence.get("posts_per_week", 0.0) < 2.0:
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.STATISTIC,
                    message="Posting cadence is low, limiting repeat exposure and momentum.",
                    value=cadence.get("posts_per_week", 0.0),
                    benchmark=3.0,
                )
            )

        return evidence

    def _build_winner_evidence(
        self,
        winner_analysis: Dict[str, Any],
        format_breakdown: Dict[str, Any],
    ) -> List[MetricEvidence]:
        evidence: List[MetricEvidence] = []
        if winner_analysis.get("winner_count", 0) == 0:
            return evidence

        winner_views = winner_analysis.get("winner_avg_views", 0.0)
        baseline_views = winner_analysis.get("baseline_avg_views", 0.0)
        if baseline_views > 0 and winner_views > (baseline_views * 1.5):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.COMPARISON,
                    message=(
                        f"Top videos average {winner_views / baseline_views:.1f}x more views "
                        "than the rest of the channel."
                    ),
                    value=winner_views,
                    benchmark=baseline_views,
                )
            )

        winner_eng = winner_analysis.get("winner_avg_engagement_rate", 0.0)
        baseline_eng = winner_analysis.get("baseline_avg_engagement_rate", 0.0)
        if baseline_eng > 0 and winner_eng > (baseline_eng * 1.2):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message=(
                        f"Winning videos show stronger engagement "
                        f"({winner_eng:.3f} vs {baseline_eng:.3f})."
                    ),
                    value=winner_eng,
                    benchmark=baseline_eng,
                )
            )

        hook_delta = (
            winner_analysis.get("winner_hook_signal_rate", 0.0)
            - winner_analysis.get("baseline_hook_signal_rate", 0.0)
        )
        if hook_delta >= 0.2:
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="Winners use stronger hook/title patterns more often.",
                    value=winner_analysis.get("winner_hook_signal_rate", 0.0),
                    benchmark=winner_analysis.get("baseline_hook_signal_rate", 0.0),
                )
            )

        thought_delta = (
            winner_analysis.get("winner_thought_prompt_rate", 0.0)
            - winner_analysis.get("baseline_thought_prompt_rate", 0.0)
        )
        if thought_delta >= 0.2:
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="Winners ask more thought-provoking questions in titles.",
                    value=winner_analysis.get("winner_thought_prompt_rate", 0.0),
                    benchmark=winner_analysis.get("baseline_thought_prompt_rate", 0.0),
                )
            )

        short_stats = format_breakdown.get("short_form", {})
        long_stats = format_breakdown.get("long_form", {})
        if short_stats.get("count", 0) >= 2 and long_stats.get("count", 0) >= 2:
            short_views = short_stats.get("avg_views", 0.0)
            long_views = long_stats.get("avg_views", 0.0)
            if long_views > 0 and short_views > (long_views * 1.3):
                evidence.append(
                    MetricEvidence(
                        type=EvidenceType.COMPARISON,
                        message="Short-form videos currently outperform long-form on average views.",
                        value=short_views,
                        benchmark=long_views,
                    )
                )
            elif short_views > 0 and long_views > (short_views * 1.3):
                evidence.append(
                    MetricEvidence(
                        type=EvidenceType.COMPARISON,
                        message="Long-form videos currently outperform short-form on average views.",
                        value=long_views,
                        benchmark=short_views,
                    )
                )

        return evidence

    def _determine_primary_issue(
        self,
        consistency: Dict[str, Any],
        packaging: Dict[str, Any],
        outliers: List[Dict[str, Any]],
    ) -> Tuple[IssueType, List[MetricEvidence]]:
        """Heuristics to determine the biggest bottleneck."""
        evidence = []

        if consistency["std_dev"] > 3.0 and consistency["median_days"] > 2:
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.STATISTIC,
                    message=f"Upload schedule varies by +/- {consistency['std_dev']:.1f} days",
                    value=consistency["std_dev"],
                )
            )
            return IssueType.CONSISTENCY, evidence

        views = [v.get("view_count", 0) for v in self.valid_videos]
        median_views = np.median(views) if views else 0

        if len(self.valid_videos) >= 5:
            recent_views = [v.get("view_count", 0) for v in self.valid_videos[:3]]
            avg_recent = np.mean(recent_views) if recent_views else 0

            if avg_recent < median_views * 0.5:
                evidence.append(
                    MetricEvidence(
                        type=EvidenceType.COMPARISON,
                        message="Recent 3 videos underperforming average by 50%+",
                        value=avg_recent,
                        benchmark=median_views,
                    )
                )
                return IssueType.TOPIC_FIT, evidence

        max_views = np.max(views) if views else 0
        if len(views) > 3 and max_views < (median_views * 1.5):
            evidence.append(
                MetricEvidence(
                    type=EvidenceType.PATTERN,
                    message="No breakout videos recently (max views < 1.5x median)",
                    value=max_views,
                    benchmark=median_views * 1.5,
                )
            )
            return IssueType.PACKAGING, evidence

        evidence.append(
            MetricEvidence(
                type=EvidenceType.STATISTIC,
                message="Consistency and hooks appear stable, suggesting mid-video dropoff",
            )
        )
        return IssueType.RETENTION, evidence

    def _generate_summary(self, issue: IssueType, evidence: List[MetricEvidence]) -> str:
        """Generate human-readable summary."""
        if issue == IssueType.CONSISTENCY:
            return "Your irregular upload schedule is likely preventing algorithm momentum."
        if issue == IssueType.PACKAGING:
            return "Your videos are not getting enough early momentum. Strengthen hooks and click intent."
        if issue == IssueType.TOPIC_FIT:
            return "Your recent topics are not resonating with your established audience profile."
        if issue == IssueType.RETENTION:
            return "You are getting clicks, but delivery quality and pacing likely reduce watch-through."
        return "Analysis complete."

    def _to_algorithm_value_score(self, feature: Dict[str, Any]) -> float:
        engagement_norm = min(1.0, feature.get("engagement_rate", 0.0) / 0.08)
        score = (
            (engagement_norm * 0.35)
            + (feature.get("retention_proxy", 0.0) * 0.25)
            + (feature.get("amplification_proxy", 0.0) * 0.20)
            + (feature.get("save_intent_proxy", 0.0) * 0.20)
        )
        return round(float(score * 100.0), 1)

    def _build_video_hypothesis(
        self,
        feature: Dict[str, Any],
        median_views: float,
        median_engagement: float,
        dominant_format: str,
    ) -> str:
        reasons: List[str] = []

        if feature.get("hook_signal", 0) >= 2:
            reasons.append("strong hook framing")
        if feature.get("thought_prompt_signal", False):
            reasons.append("thought-provoking title")
        if feature.get("story_signal", False):
            reasons.append("story-led setup")
        if feature.get("engagement_rate", 0.0) > (median_engagement * 1.2):
            reasons.append("above-baseline engagement")
        if dominant_format in {"short_form", "long_form"} and feature.get("format_type") == dominant_format:
            reasons.append(f"matches current {dominant_format.replace('_', '-')} winner format")

        if feature.get("view_count", 0) < (median_views * 0.7):
            if reasons:
                return "Underperforming despite some positives; test tighter hook + clearer value promise."
            return "Underperforming likely due to weak hook-value alignment in title/early delivery."

        if reasons:
            return "Likely outperforming due to " + ", ".join(reasons[:3]) + "."

        return "Performance is close to channel baseline; test stronger hooks and clearer audience promise."

    def _build_video_scorecards(
        self,
        winner_analysis: Dict[str, Any],
        format_breakdown: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        features = self._get_features()
        if not features:
            return []

        views = [f.get("view_count", 0) for f in features]
        median_views = float(np.median(views)) if views else 0.0
        p80_views = float(np.percentile(views, 80)) if views else 0.0
        median_engagement = float(np.median([f.get("engagement_rate", 0.0) for f in features]))
        winner_ids = set(winner_analysis.get("winner_video_ids", []))
        dominant_format = format_breakdown.get("dominant_format", "mixed")

        scorecards: List[Dict[str, Any]] = []
        for feature in features:
            views_val = feature.get("view_count", 0)
            tier = "baseline"
            if feature.get("video_id") in winner_ids or views_val >= p80_views:
                tier = "winner"
            elif views_val < (median_views * 0.7):
                tier = "underperformer"
            elif views_val > (median_views * 1.1):
                tier = "above_average"

            scorecards.append(
                {
                    "video_id": feature.get("video_id"),
                    "title": feature.get("title"),
                    "published_at": feature.get("published_at"),
                    "format_type": feature.get("format_type"),
                    "duration_seconds": feature.get("duration_seconds"),
                    "performance_tier": tier,
                    "view_count": feature.get("view_count"),
                    "like_count": feature.get("like_count"),
                    "comment_count": feature.get("comment_count"),
                    "like_rate": round(feature.get("like_rate", 0.0), 4),
                    "comment_rate": round(feature.get("comment_rate", 0.0), 4),
                    "engagement_rate": round(feature.get("engagement_rate", 0.0), 4),
                    "retention_proxy": round(feature.get("retention_proxy", 0.0), 4),
                    "amplification_proxy": round(feature.get("amplification_proxy", 0.0), 4),
                    "save_intent_proxy": round(feature.get("save_intent_proxy", 0.0), 4),
                    "algorithm_value_score": self._to_algorithm_value_score(feature),
                    "hook_signal": feature.get("hook_signal", 0),
                    "story_signal": feature.get("story_signal", False),
                    "thought_prompt_signal": feature.get("thought_prompt_signal", False),
                    "hypothesis": self._build_video_hypothesis(
                        feature,
                        median_views=median_views,
                        median_engagement=median_engagement,
                        dominant_format=dominant_format,
                    ),
                }
            )

        return sorted(scorecards, key=lambda row: row.get("view_count", 0), reverse=True)

    def _build_strategy_playbook(
        self,
        winner_analysis: Dict[str, Any],
        format_breakdown: Dict[str, Any],
        social_signal_summary: Dict[str, Any],
        top_topics: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        playbook: List[Dict[str, Any]] = []

        if (
            winner_analysis.get("winner_hook_signal_rate", 0.0)
            >= winner_analysis.get("baseline_hook_signal_rate", 0.0) + 0.15
        ):
            playbook.append(
                {
                    "title": "Replicate winning hooks",
                    "reason": "High-performing videos use hook-style titles more often.",
                    "how_to_apply": "Open with a bold claim, tension, or question in the first line and first 5 seconds.",
                    "target_metric": "hook_signal_rate",
                    "priority": 1,
                }
            )

        if (
            winner_analysis.get("winner_avg_comment_rate", 0.0)
            > winner_analysis.get("baseline_avg_comment_rate", 0.0) * 1.2
        ):
            playbook.append(
                {
                    "title": "Design for comments, not just likes",
                    "reason": "Comment rate is materially higher on your winners.",
                    "how_to_apply": "End videos with one concrete, opinionated question to trigger replies.",
                    "target_metric": "comment_rate",
                    "priority": 1,
                }
            )

        if (
            winner_analysis.get("winner_avg_amplification_proxy", 0.0)
            > winner_analysis.get("baseline_avg_amplification_proxy", 0.0) * 1.15
        ):
            playbook.append(
                {
                    "title": "Build share-worthy takes",
                    "reason": "Amplification/share proxy is stronger on winners.",
                    "how_to_apply": "Use clear POVs, surprising stats, and quotable one-liners people want to repost.",
                    "target_metric": "amplification_proxy",
                    "priority": 2,
                }
            )

        if (
            winner_analysis.get("winner_avg_save_intent_proxy", 0.0)
            > winner_analysis.get("baseline_avg_save_intent_proxy", 0.0) * 1.15
        ):
            playbook.append(
                {
                    "title": "Increase save-worthy utility",
                    "reason": "Save-intent proxy is stronger on winners.",
                    "how_to_apply": "Package repeatable frameworks, checklists, or step-by-step examples users revisit.",
                    "target_metric": "save_intent_proxy",
                    "priority": 2,
                }
            )

        dominant_format = format_breakdown.get("dominant_format", "mixed")
        if dominant_format == "short_form":
            playbook.append(
                {
                    "title": "Scale short-form winners",
                    "reason": "Short-form currently leads on average views.",
                    "how_to_apply": "Publish 3-5 quality short videos weekly and port top topics into one deeper long-form piece.",
                    "target_metric": "short_form.avg_views",
                    "priority": 2,
                }
            )
        elif dominant_format == "long_form":
            playbook.append(
                {
                    "title": "Double down on long-form depth",
                    "reason": "Long-form currently leads on average views.",
                    "how_to_apply": "Keep long-form as core while using short clips as distribution hooks.",
                    "target_metric": "long_form.avg_views",
                    "priority": 2,
                }
            )

        cadence = social_signal_summary.get("posting_cadence", {})
        if cadence.get("health") == "low":
            playbook.append(
                {
                    "title": "Fix posting consistency",
                    "reason": "Low posting frequency reduces repeated exposure and recommendation opportunities.",
                    "how_to_apply": cadence.get("recommendation", "Maintain a consistent weekly cadence."),
                    "target_metric": "posts_per_week",
                    "priority": 1,
                }
            )

        if top_topics:
            topic = top_topics[0].get("topic")
            playbook.append(
                {
                    "title": f"Reinforce proven topic: {topic}",
                    "reason": "This topic appears most often in your strongest title clusters.",
                    "how_to_apply": "Produce a 3-video sequence around this theme with varied hooks and angles.",
                    "target_metric": "topic_fit",
                    "priority": 3,
                }
            )

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in sorted(playbook, key=lambda x: int(x.get("priority", 3))):
            title = item.get("title")
            if title in seen:
                continue
            seen.add(title)
            deduped.append(item)

        return deduped[:6]

    def _generate_recommendations(
        self,
        issue: IssueType,
        outliers: List[Dict[str, Any]],
        top_topics: List[Dict[str, Any]],
        winner_analysis: Dict[str, Any],
        format_breakdown: Dict[str, Any],
        social_signal_summary: Dict[str, Any],
        strategy_playbook: List[Dict[str, Any]],
    ) -> List[ActionItem]:
        """Generate actionable advice."""
        actions: List[ActionItem] = []

        if issue == IssueType.CONSISTENCY:
            actions.append(
                ActionItem(
                    title="Establish a Schedule",
                    description="Pick a sustainable weekly cadence and keep it stable for 4 weeks.",
                    priority=1,
                )
            )
        elif issue == IssueType.PACKAGING:
            actions.append(
                ActionItem(
                    title="Revamp Hooks and Titles",
                    description="Use shorter, clearer hooks that state tension or value in the first line.",
                    priority=1,
                )
            )
        elif issue == IssueType.TOPIC_FIT and top_topics:
            topic = top_topics[0]["topic"]
            actions.append(
                ActionItem(
                    title=f"Return to Core Topic: {topic}",
                    description=f"Your best videos align with '{topic}'. Build the next 3 videos around adjacent angles.",
                    priority=1,
                )
            )
        elif issue == IssueType.RETENTION:
            actions.append(
                ActionItem(
                    title="Tighten First 30 Seconds",
                    description="Deliver the core promise immediately and remove slow intros.",
                    priority=1,
                )
            )

        hook_delta = (
            winner_analysis.get("winner_hook_signal_rate", 0.0)
            - winner_analysis.get("baseline_hook_signal_rate", 0.0)
        )
        if hook_delta >= 0.15:
            actions.append(
                ActionItem(
                    title="Mirror Winning Hook Structure",
                    description="Winning videos use stronger hook patterns. Reuse those opening structures in new uploads.",
                    priority=1,
                )
            )

        comments = social_signal_summary.get("comments", {})
        if comments.get("winner_rate", 0.0) > comments.get("baseline_rate", 0.0) * 1.2:
            actions.append(
                ActionItem(
                    title="Engineer Comment Loops",
                    description="Close each video with one specific question to drive discussion and session depth.",
                    priority=1,
                )
            )

        cadence = social_signal_summary.get("posting_cadence", {})
        if cadence.get("health") == "low":
            actions.append(
                ActionItem(
                    title="Increase Weekly Publishing Consistency",
                    description=cadence.get("recommendation", "Aim for a consistent weekly schedule."),
                    priority=1,
                )
            )

        short_stats = format_breakdown.get("short_form", {})
        long_stats = format_breakdown.get("long_form", {})
        if short_stats.get("count", 0) >= 2 and long_stats.get("count", 0) >= 2:
            short_views = short_stats.get("avg_views", 0.0)
            long_views = long_stats.get("avg_views", 0.0)
            if long_views > 0 and short_views > (long_views * 1.3):
                actions.append(
                    ActionItem(
                        title="Prioritize Shorts Distribution",
                        description="Short-form currently drives more reach. Increase Shorts while reusing winning long-form topics.",
                        priority=2,
                    )
                )
            elif short_views > 0 and long_views > (short_views * 1.3):
                actions.append(
                    ActionItem(
                        title="Lean Into Long-Form Depth",
                        description="Long-form currently performs better; keep it primary and use Shorts as top-of-funnel.",
                        priority=2,
                    )
                )

        for item in strategy_playbook[:3]:
            actions.append(
                ActionItem(
                    title=item.get("title", "Apply Winning Pattern"),
                    description=item.get("how_to_apply", "Replicate patterns from winning videos."),
                    priority=int(item.get("priority", 2)),
                )
            )

        if outliers:
            best = outliers[0]
            actions.append(
                ActionItem(
                    title="Analyze Best Performer",
                    description=(
                        f"Study '{best.get('title')}' ({best.get('view_count')} views) and clone its topic + hook format."
                    ),
                    priority=2,
                )
            )

        deduped: List[ActionItem] = []
        seen = set()
        for action in sorted(actions, key=lambda x: x.priority):
            if action.title in seen:
                continue
            seen.add(action.title)
            deduped.append(action)

        return deduped
