import os
import logging
import ffmpeg
from openai import OpenAI
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def extract_audio(video_path: str, output_path: str) -> str:
    """
    Extract audio from video file to MP3 format.
    Returns path to audio file.
    """
    try:
        # ffmpeg -i video.mp4 -q:a 0 -map a output.mp3
        (
            ffmpeg
            .input(video_path)
            .output(output_path, format='mp3', audio_bitrate='32k') # Low bitrate for API size limit
            .overwrite_output()
            .run(quiet=True)
        )
        return output_path
    except ffmpeg.Error as e:
        logger.error(f"Error extracting audio: {e.stderr.decode() if e.stderr else str(e)}")
        raise

def transcribe_audio(audio_path: str, api_key: str) -> Dict:
    """
    Transcribe audio using OpenAI Whisper API.
    Returns standard transcription object with segments/timestamps.
    """
    # Mock for testing if key is invalid
    if not api_key or "your_" in api_key or api_key == "test-key":
        logger.warning("Using MOCK transcription because OpenAI API Key is missing or invalid.")
        return {
            "text": "This is a mock transcription of the video audio. The video seems to be about a zoo trip.",
            "segments": [
                type("Segment", (), {"start": 0.0, "text": "Alright, so here we are in front of the elephants."}),
                type("Segment", (), {"start": 5.0, "text": "The cool thing about these guys is that they have really, really, really long trunks."}),
                type("Segment", (), {"start": 10.0, "text": "And that's, that's cool."}),
                type("Segment", (), {"start": 15.0, "text": "And that's pretty much all there is to say."})
            ]
        }

    client = OpenAI(api_key=api_key)
    
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        return transcript
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        # Return mock on failure to unblock dev flow? 
        # Better to raise, but for MVP verification we might want fallback.
        raise
