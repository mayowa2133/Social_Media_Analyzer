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
