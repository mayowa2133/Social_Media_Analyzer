import pytest
import numpy as np
from datetime import datetime, timedelta
from analysis.metrics import ChannelAnalyzer
from analysis.models import IssueType, EvidenceType

@pytest.fixture
def mock_channel_data():
    return {
        "id": "UC_TEST",
        "title": "Test Channel"
    }

@pytest.fixture
def consistent_videos():
    """Videos uploaded exactly every 3 days."""
    base_date = datetime.now()
    return [
        {
            "id": f"vid{i}",
            "title": f"Video {i}",
            "published_at": (base_date - timedelta(days=i*3)).isoformat(),
            "view_count": 1000,
            "duration_seconds": 600
        }
        for i in range(10)
    ]

@pytest.fixture
def inconsistent_videos():
    """Videos uploaded irregularly (1, 10, 2, 8 days gap)."""
    base_date = datetime.now()
    gaps = [0, 1, 11, 13, 21, 23, 30]
    return [
        {
            "id": f"vid{i}",
            "title": f"Video {i}",
            "published_at": (base_date - timedelta(days=gap)).isoformat(),
            "view_count": 1000,
            "duration_seconds": 600
        }
        for i, gap in enumerate(gaps)
    ]

@pytest.fixture
def packaging_issue_videos():
    """Low views relative to expected, no outliers."""
    base_date = datetime.now()
    return [
        {
            "id": f"vid{i}",
            "title": "generic title",
            "published_at": (base_date - timedelta(days=i)).isoformat(),
            "view_count": 100, # consistently low
            "duration_seconds": 600
        }
        for i in range(10)
    ]

@pytest.fixture
def topic_mismatch_videos():
    """Recent videos performing poorly compared to older ones."""
    base_date = datetime.now()
    videos = []
    # Old successful videos
    for i in range(3, 10):
        videos.append({
            "id": f"vid{i}",
            "title": f"Core Topic {i}",
            "published_at": (base_date - timedelta(days=i)).isoformat(),
            "view_count": 10000,
            "duration_seconds": 600
        })
    # Recent failures
    for i in range(3):
         videos.append({
            "id": f"vid{i}",
            "title": f"New Topic {i}",
            "published_at": (base_date - timedelta(days=i)).isoformat(),
            "view_count": 500,
            "duration_seconds": 600
        })
    return videos

def test_consistency_analysis(mock_channel_data, consistent_videos, inconsistent_videos):
    # Test Consistent
    analyzer = ChannelAnalyzer(mock_channel_data, consistent_videos)
    analysis = analyzer.analyze()
    metrics = analysis.metrics["consistency"]
    assert metrics["median_days"] == 3.0
    assert metrics["variance"] == 0.0
    
    # Test Inconsistent
    analyzer = ChannelAnalyzer(mock_channel_data, inconsistent_videos)
    analysis = analyzer.analyze()
    assert analysis.primary_issue == IssueType.CONSISTENCY

def test_packaging_analysis(mock_channel_data, packaging_issue_videos):
    analyzer = ChannelAnalyzer(mock_channel_data, packaging_issue_videos)
    analysis = analyzer.analyze()
    assert analysis.primary_issue == IssueType.PACKAGING
    assert analysis.metrics["packaging"]["avg_title_length"] > 0

def test_topic_analysis(mock_channel_data, topic_mismatch_videos):
    analyzer = ChannelAnalyzer(mock_channel_data, topic_mismatch_videos)
    analysis = analyzer.analyze()
    assert analysis.primary_issue == IssueType.TOPIC_FIT

def test_clustering(mock_channel_data):
    videos = [
        {"title": "Minecraft Let's Play 1", "published_at": "2023-01-01T00:00:00Z", "view_count": 100},
        {"title": "Minecraft Let's Play 2", "published_at": "2023-01-02T00:00:00Z", "view_count": 100},
        {"title": "Fortnite Tips", "published_at": "2023-01-03T00:00:00Z", "view_count": 100},
    ]
    analyzer = ChannelAnalyzer(mock_channel_data, videos)
    clusters = analyzer._cluster_topics()
    
    topics = {c["topic"] for c in clusters}
    assert "minecraft" in topics


def test_winner_patterns_and_format_split(mock_channel_data):
    base_date = datetime.now()
    videos = [
        {
            "id": "short_winner_1",
            "title": "Why 3 AI Mistakes Kill Your Growth?",
            "published_at": (base_date - timedelta(days=1)).isoformat(),
            "view_count": 12000,
            "like_count": 900,
            "comment_count": 140,
            "duration_seconds": 45,
        },
        {
            "id": "short_winner_2",
            "title": "The Secret Hook Formula in 30 Seconds",
            "published_at": (base_date - timedelta(days=2)).isoformat(),
            "view_count": 10000,
            "like_count": 750,
            "comment_count": 120,
            "duration_seconds": 50,
        },
        {
            "id": "long_baseline_1",
            "title": "Weekly channel update",
            "published_at": (base_date - timedelta(days=3)).isoformat(),
            "view_count": 2200,
            "like_count": 70,
            "comment_count": 8,
            "duration_seconds": 720,
        },
        {
            "id": "long_baseline_2",
            "title": "Building in public day 17",
            "published_at": (base_date - timedelta(days=4)).isoformat(),
            "view_count": 2000,
            "like_count": 65,
            "comment_count": 7,
            "duration_seconds": 680,
        },
        {
            "id": "long_baseline_3",
            "title": "My story from idea to launch",
            "published_at": (base_date - timedelta(days=5)).isoformat(),
            "view_count": 2500,
            "like_count": 90,
            "comment_count": 12,
            "duration_seconds": 840,
        },
    ]
    analyzer = ChannelAnalyzer(mock_channel_data, videos)
    analysis = analyzer.analyze()

    winner = analysis.metrics["winner_analysis"]
    formats = analysis.metrics["format_breakdown"]
    signals = analysis.metrics["social_signal_summary"]
    scorecards = analysis.metrics["video_scorecards"]
    playbook = analysis.metrics["strategy_playbook"]

    assert winner["winner_count"] >= 1
    assert winner["winner_avg_views"] > winner["baseline_avg_views"]
    assert winner["winner_hook_signal_rate"] >= winner["baseline_hook_signal_rate"]
    assert "top_videos" in winner and len(winner["top_videos"]) >= 1

    assert formats["short_form"]["count"] == 2
    assert formats["long_form"]["count"] == 3
    assert formats["short_form"]["avg_views"] > formats["long_form"]["avg_views"]
    assert formats["dominant_format"] == "short_form"

    assert signals["likes"]["avg_rate"] > 0
    assert signals["comments"]["avg_rate"] > 0
    assert signals["shares"]["avg_proxy"] > 0
    assert signals["saves"]["avg_proxy"] > 0
    assert signals["metric_coverage"]["shares"] == "proxy"

    assert len(scorecards) == 5
    assert scorecards[0]["performance_tier"] in {"winner", "above_average"}
    assert scorecards[0]["algorithm_value_score"] > 0
    assert isinstance(scorecards[0]["hypothesis"], str) and len(scorecards[0]["hypothesis"]) > 0

    assert len(playbook) > 0
