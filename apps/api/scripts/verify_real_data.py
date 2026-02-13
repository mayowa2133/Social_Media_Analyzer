import sys
import os
import asyncio
import json

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.youtube import create_youtube_client_with_api_key
from analysis.metrics import ChannelAnalyzer

async def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_real_data.py <YOUTUBE_API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]
    channel_handle = "@MKBHD" # Marques Brownlee (Standard videos)

    print(f"🔍 Testing Real YouTube API Integration with key: {api_key[:5]}...")
    
    try:
        # 1. Initialize Client
        client = create_youtube_client_with_api_key(api_key)
        print("✅ Client initialized")

        # 2. Resolve Channel
        print(f"\n📡 Fetching channel info for {channel_handle}...")
        channel_id = client.resolve_channel_identifier(f"https://youtube.com/{channel_handle}")
        if not channel_id:
            print("❌ Failed to resolve channel")
            return
            
        info = client.get_channel_info(channel_id)
        print(f"✅ Resolved: {info['title']} (ID: {channel_id})")
        print(f"   Subscribers: {info.get('subscriber_count')}")

        # 3. Fetch Videos
        print("\n🎥 Fetching recent videos...")
        videos = client.get_channel_videos(channel_id, max_results=10)
        print(f"✅ Fetched {len(videos)} videos")
        
        # 4. Fetch Details (Views/Likes)
        video_ids = [v["id"] for v in videos]
        print(f"   Debug: Fetching details for IDs: {video_ids[:3]}...")
        
        details = client.get_video_details(video_ids)
        print(f"   Debug: Got details for {len(details)} videos")
        print(f"   Debug: Keys in details: {list(details.keys())[:3]}...")

        
        # Merge details
        for v in videos:
            if v["id"] in details:
                v.update(details[v["id"]])
        
        if videos[0].get("view_count") is None:
             print("❌ Warning: View counts are missing!")
             # Debug mismatch
             if video_ids[0] not in details:
                 print(f"   Mismatch: ID {video_ids[0]} not found in details keys.")
        else:
             print(f"✅ Enriched video stats (Example: '{videos[0]['title']}' has {videos[0].get('view_count')} views)")

        # 5. Run Analysis
        print("\n🧠 Running Metrics Analyzer on Real Data...")
        analyzer = ChannelAnalyzer(info, videos)
        result = analyzer.analyze()
        
        print("\n📊 DIAGNOSIS RESULT:")
        print(f"   Primary Issue: {result.primary_issue}")
        print(f"   Summary: {result.summary}")
        print("\n   Evidence:")
        for e in result.evidence:
            print(f"   - {e.message}")
            
        print("\n✅ REAL DATA VERIFICATION COMPLETE")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
