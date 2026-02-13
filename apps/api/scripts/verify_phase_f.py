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

async def verify_phase_f_async():
    print("🔍 Verifying Phase F: Consolidated Reporting...")
    
    # 1. Ensure Data Exists
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add test user and a mock audit
        await conn.execute(text(
            "INSERT INTO users (id, email) VALUES ('test-user', 'phase_f@example.com') ON CONFLICT (id) DO NOTHING"
        ))
        
        # Add mock audit with Phase C/D data
        mock_output = {
            "diagnosis": {
                "primary_issue": "RETENTION",
                "recommendations": ["Optimize the first 5 seconds", "Clearer call to action"],
                "metrics": {"overall_score": 75}
            },
            "video_analysis": {
                "summary": "The intro is strong but the middle drags.",
                "overall_score": 68,
                "sections": [{"name": "Intro", "score": 9, "feedback": ["Hook is effective"]}]
            }
        }
        
        await conn.execute(text(
            "INSERT INTO audits (id, user_id, status, output_json) "
            "VALUES ('audit-f-123', 'test-user', 'completed', :output) "
            "ON CONFLICT (id) DO NOTHING"
        ), {"output": json.dumps(mock_output)})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 2. Add a competitor so breakpoint works
        await client.post("/competitors/", json={
            "channel_url": "https://www.youtube.com/@MKBHD", 
            "user_id": "test-user"
        })

        # 3. Fetch Consolidated Report
        print("🚀 Fetching Consolidated Report...")
        response = await client.get("/report/latest?user_id=test-user")
        
        if response.status_code != 200:
            print(f"❌ Report fetch failed: {response.text}")
            return
            
        report = response.json()
        print("✅ Consolidated Report Retrieved Successfully!")
        
        # 4. Validate Aggregation
        print(f"📊 Overall Coach Score: {report.get('overall_score')}")
        assert "diagnosis" in report
        assert "video_analysis" in report
        assert "blueprint" in report
        assert len(report.get("recommendations", [])) > 0
        
        print("\n✅ Evidence of Aggregation:")
        print(f"  - Stats issue: {report['diagnosis']['primary_issue']}")
        print(f"  - Video summary: {report['video_analysis']['summary'][:50]}...")
        print(f"  - Strategy pillars: {report['blueprint']['content_pillars'][:2]}")

if __name__ == "__main__":
    import json
    asyncio.run(verify_phase_f_async())
