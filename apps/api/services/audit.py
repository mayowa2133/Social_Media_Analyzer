import os
import shutil
import logging
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from datetime import datetime, timezone
import json

from database import async_session_maker
from models.audit import Audit
from multimodal.video import download_video, extract_frames
from multimodal.audio import extract_audio, transcribe_audio
from multimodal.llm import analyze_content
from config import settings

logger = logging.getLogger(__name__)

async def process_video_audit(audit_id: str, video_url: str):
    """
    Background task to process video audit.
    """
    # Create new Async DB session
    async with async_session_maker() as db:
        
        # Temp directories
        temp_dir = f"/tmp/spc_audit_{audit_id}"
        video_path = os.path.join(temp_dir, "video.mp4")
        frames_dir = os.path.join(temp_dir, "frames")
        audio_path = os.path.join(temp_dir, "audio.mp3")
        
        try:
            # 1. Update status -> downloading
            logger.info(f"Starting audit {audit_id} for video {video_url}")
            await _update_status(db, audit_id, "downloading", 10)

            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            # Download (Blocking -> Thread)
            downloaded_file = await asyncio.to_thread(download_video, video_url, video_path)
            
            # 2. Update status -> processing_video
            await _update_status(db, audit_id, "processing_video", 30)
            
            # Extract frames (Blocking -> Thread)
            frames = await asyncio.to_thread(extract_frames, downloaded_file, frames_dir, 5)
            logger.info(f"Extracted {len(frames)} frames")

            # 3. Update status -> processing_audio
            await _update_status(db, audit_id, "processing_audio", 50)
            
            # Extract audio & Transcribe (Blocking -> Thread)
            await asyncio.to_thread(extract_audio, downloaded_file, audio_path)
            
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                 # Fallback for dev - though audio.py handles it
                 pass
                 
            transcript = await asyncio.to_thread(transcribe_audio, audio_path, api_key)
            logger.info("Audio transcription complete")

            # 4. Update status -> analyzing
            await _update_status(db, audit_id, "analyzing", 70)
            
            # LLM Analysis (Blocking -> Thread)
            metadata = {"title": "Unknown Video", "url": video_url, "id": audit_id}
            
            # analyze_content does file IO (reading images), so also thread it
            result = await asyncio.to_thread(analyze_content, frames, transcript, metadata, api_key)
            
            # 5. Complete
            # Fetch audit again to attach to session? No, select works.
            result_audit = await db.execute(select(Audit).where(Audit.id == audit_id))
            audit = result_audit.scalar_one_or_none()
            
            if audit:
                audit.status = "completed"
                audit.progress = "100"
                audit.output_json = result.model_dump()
                audit.completed_at = datetime.now(timezone.utc)
                await db.commit()
                
            logger.info(f"Audit {audit_id} completed successfully")

        except Exception as e:
            logger.error(f"Audit {audit_id} failed: {e}")
            result_audit = await db.execute(select(Audit).where(Audit.id == audit_id))
            audit = result_audit.scalar_one_or_none()
            if audit:
                audit.status = "failed"
                audit.error_message = str(e)
                await db.commit()
        
        finally:
            # Cleanup temp files
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.error(f"Error cleaning up temp dir: {e}")

async def _update_status(db, audit_id: str, status: str, progress: int):
    result = await db.execute(select(Audit).where(Audit.id == audit_id))
    audit = result.scalar_one_or_none()
    if audit:
        audit.status = status
        audit.progress = str(progress)
        await db.commit()
