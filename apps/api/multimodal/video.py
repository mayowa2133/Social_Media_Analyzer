import os
import glob
import logging
import yt_dlp
import ffmpeg

logger = logging.getLogger(__name__)

def download_video(url: str, output_path: str) -> str:
    """
    Download video from URL using yt-dlp.
    Returns the absolute path to the downloaded file.
    """
    # Configure yt-dlp to download lowest quality video (for speed) 
    # but good enough for frame extraction.
    ydl_opts = {
        'format': 'worstvideo[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]/worst',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'overwrites': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            # yt-dlp might append extension if not in template, 
            # but we forced mp4 in format or outtmpl usually handles it.
            # Let's simple check if file exists, or if a similar file exists.
            if os.path.exists(output_path):
                return output_path
            
            # If yt-dlp added an extension despite outtmpl
            # Find the file that matches the prefix
            base_name = os.path.splitext(output_path)[0]
            matches = glob.glob(f"{base_name}*")
            if matches:
                return matches[0]
                
            raise FileNotFoundError("Video not found after download")

    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        raise

def extract_frames(video_path: str, output_dir: str, interval: int = 5) -> list[str]:
    """
    Extract frames from video every `interval` seconds.
    Returns list of paths to extracted frames.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Output filename pattern
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")

    try:
        # ffmpeg -i video.mp4 -vf fps=1/5 frame_%04d.jpg
        (
            ffmpeg
            .input(video_path)
            .filter('fps', fps=1.0/interval)
            .output(output_pattern)
            .overwrite_output()
            .run(quiet=True)
        )
        
        # Return list of created files
        frames = sorted(glob.glob(os.path.join(output_dir, "frame_*.jpg")))
        return frames

    except ffmpeg.Error as e:
        logger.error(f"Error extracting frames: {e.stderr.decode() if e.stderr else str(e)}")
        raise
