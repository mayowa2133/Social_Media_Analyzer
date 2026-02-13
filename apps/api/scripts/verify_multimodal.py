import sys
import os
import asyncio
import httpx
from httpx import AsyncClient, ASGITransport
from main import app
from database import engine, Base

# Add parent dir to path to find main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def verify_multimodal_audit_async():
    print("🔍 Verifying Multimodal Audit Pipeline (Async)...")
    
    # Check API Key
    from config import settings
    # We assume valid key if user said so
    
    # Ensure tables exist and user exists
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "INSERT INTO users (id, email) VALUES ('verify_script_user', 'test@example.com') ON CONFLICT (id) DO NOTHING"
        ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
    
        # 1. Start Audit
        video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # Me at the zoo (18s)
        print(f"📡 Requesting audit for: {video_url}")
        
        response = await client.post("/audit/run_multimodal", json={
            "video_url": video_url,
            "user_id": "verify_script_user"
        })
        
        if response.status_code != 200:
            print(f"❌ Failed to start audit: {response.text}")
            return
            
        data = response.json()
        audit_id = data["audit_id"]
        print(f"✅ Audit started. ID: {audit_id}")
        
        # 2. Poll for completion
        print("⏳ Polling for completion (max 60s)...")
        
        for i in range(20): # Poll for 60s (20 * 3s)
            await asyncio.sleep(3)
            response = await client.get(f"/audit/{audit_id}")
            if response.status_code != 200:
                print(f"❌ Failed to get status: {response.text}")
                continue
                
            result = response.json()
            status = result["status"]
            progress = result.get("progress", "0")
            print(f"   [{i*3}s] Status: {status} ({progress}%)")
            
            if status == "completed":
                print("✅ Audit Completed Successfully!")
                print("📝 Output Summary:")
                output = result.get("output", {})
                print(f"   Score: {output.get('overall_score')}/10")
                print(f"   Summary: {output.get('summary')}")
                print("   Feedback Items:")
                for item in output.get("timestamp_feedback", [])[:3]:
                    print(f"   - [{item.get('timestamp')}] {item.get('category')}: {item.get('observation')}")
                return
            
            if status == "failed":
                print(f"❌ Audit finished with status: {status}")
                print(f"   Error: {result.get('error')}")
                return
                
        print("❌ Timeout waiting for audit completion.")

if __name__ == "__main__":
    asyncio.run(verify_multimodal_audit_async())
