import asyncio
import httpx
from httpx import AsyncClient, ASGITransport
import sys
import os

# Add parent dir to path to find main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import engine, Base
from sqlalchemy import text

async def verify_blueprint_async():
    print("🔍 Verifying Competitor Blueprint Pipeline...")
    
    # 1. Setup DB and Test User
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "INSERT INTO users (id, email) VALUES ('test-user', 'competitor_test@example.com') ON CONFLICT (id) DO NOTHING"
        ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 2. Add Competitors
        competitor_urls = [
            "https://www.youtube.com/@MKBHD",
            "https://www.youtube.com/@MrBeast"
        ]
        
        print("💡 Adding competitors...")
        for url in competitor_urls:
            response = await client.post("/competitors/", json={"channel_url": url, "user_id": "test-user"})
            if response.status_code == 200:
                print(f"✅ Added: {url}")
            else:
                print(f"⚠️ Warning: Could not add {url}: {response.text}")

        # 3. Generate Blueprint
        print("🚀 Generating Strategy Blueprint (calling LLM)...")
        response = await client.post("/competitors/blueprint", json={"user_id": "test-user"})
        
        if response.status_code != 200:
            print(f"❌ Blueprint generation failed: {response.text}")
            return
            
        blueprint = response.json()
        print("✅ Blueprint Generated Successfully!")
        
        print("\n📊 Gap Analysis:")
        for gap in blueprint.get("gap_analysis", []):
            print(f"  - {gap}")
            
        print("\n📍 Content Pillars:")
        for pillar in blueprint.get("content_pillars", []):
            print(f"  - {pillar}")
            
        print("\n💡 Video Ideas:")
        for idea in blueprint.get("video_ideas", []):
            print(f"  - {idea.get('title')}: {idea.get('concept')[:100]}...")

if __name__ == "__main__":
    asyncio.run(verify_blueprint_async())
