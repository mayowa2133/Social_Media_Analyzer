"""
YouTube Data API client for fetching channel and video data.
"""

import re
from typing import Optional, List, Dict, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeClient:
    """Client for interacting with YouTube Data API v3."""
    
    def __init__(self, api_key: Optional[str] = None, credentials: Any = None):
        """
        Initialize YouTube client.
        
        Args:
            api_key: API key for public data access
            credentials: OAuth2 credentials for authenticated access
        """
        if credentials:
            self.youtube = build("youtube", "v3", credentials=credentials)
        elif api_key:
            self.youtube = build("youtube", "v3", developerKey=api_key)
        else:
            raise ValueError("Either api_key or credentials must be provided")
    
    def resolve_channel_identifier(self, identifier: str) -> Optional[str]:
        """
        Resolve various channel identifiers to a channel ID.
        
        Supports:
        - Channel ID (UC...)
        - Channel URL (youtube.com/channel/UC...)
        - Handle (@username or youtube.com/@username)
        - Custom URL (youtube.com/c/...)
        - Username (youtube.com/user/...)
        """
        identifier = identifier.strip()
        
        # Already a channel ID
        if identifier.startswith("UC") and len(identifier) == 24:
            return identifier
        
        # Extract from various URL formats
        patterns = [
            r"youtube\.com/channel/(UC[\w-]{22})",  # Channel URL
            r"youtube\.com/@([\w.-]+)",  # Handle URL
            r"youtube\.com/c/([\w.-]+)",  # Custom URL
            r"youtube\.com/user/([\w.-]+)",  # Username URL
            r"^@([\w.-]+)$",  # Handle only
        ]
        
        for pattern in patterns:
            match = re.search(pattern, identifier)
            if match:
                extracted = match.group(1)
                # If it's already a channel ID, return it
                if extracted.startswith("UC"):
                    return extracted
                # Otherwise, search for the channel
                return self._search_channel(extracted)
        
        # Try searching directly
        return self._search_channel(identifier)
    
    def _search_channel(self, query: str) -> Optional[str]:
        """Search for a channel by name/handle and return its ID."""
        try:
            # Try forHandle first (for @username)
            if not query.startswith("@"):
                handle_query = query
            else:
                handle_query = query[1:]
            
            response = self.youtube.channels().list(
                part="id",
                forHandle=handle_query
            ).execute()
            
            if response.get("items"):
                return response["items"][0]["id"]
            
            # Fall back to search
            response = self.youtube.search().list(
                part="snippet",
                q=query,
                type="channel",
                maxResults=1
            ).execute()
            
            if response.get("items"):
                return response["items"][0]["snippet"]["channelId"]
            
            return None
        except HttpError:
            return None

    def search_channels(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search channels by a niche/query and return enriched channel metrics.

        Returns:
            List of channel dicts with:
            id, title, description, custom_url, thumbnail_url,
            subscriber_count, video_count, view_count
        """
        query = (query or "").strip()
        if not query:
            return []

        max_results = max(1, min(max_results, 50))

        try:
            response = self.youtube.search().list(
                part="snippet",
                q=query,
                type="channel",
                maxResults=max_results,
            ).execute()

            channel_ids: List[str] = []
            for item in response.get("items", []):
                channel_id = item.get("snippet", {}).get("channelId") or item.get("id", {}).get("channelId")
                if channel_id and channel_id not in channel_ids:
                    channel_ids.append(channel_id)

            if not channel_ids:
                return []

            details: Dict[str, Dict[str, Any]] = {}
            for i in range(0, len(channel_ids), 50):
                batch = channel_ids[i:i + 50]
                detail_response = self.youtube.channels().list(
                    part="snippet,statistics",
                    id=",".join(batch),
                ).execute()

                for item in detail_response.get("items", []):
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    details[item["id"]] = {
                        "id": item["id"],
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "custom_url": snippet.get("customUrl", ""),
                        "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                        "subscriber_count": int(stats.get("subscriberCount", 0)),
                        "video_count": int(stats.get("videoCount", 0)),
                        "view_count": int(stats.get("viewCount", 0)),
                    }

            channels = [details[cid] for cid in channel_ids if cid in details]
            channels.sort(
                key=lambda c: (c.get("subscriber_count", 0), c.get("view_count", 0)),
                reverse=True,
            )
            return channels[:max_results]
        except HttpError as e:
            print(f"Error searching channels for query '{query}': {e}")
            return []
    
    def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Get channel metadata.
        
        Returns:
            Dict with: id, title, description, customUrl, publishedAt,
                       thumbnail, subscriberCount, videoCount, viewCount
        """
        try:
            response = self.youtube.channels().list(
                part="snippet,statistics,contentDetails",
                id=channel_id
            ).execute()
            
            if not response.get("items"):
                return None
            
            item = response["items"][0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            
            return {
                "id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "custom_url": snippet.get("customUrl", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "uploads_playlist_id": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            }
        except HttpError as e:
            print(f"Error fetching channel {channel_id}: {e}")
            return None

    def get_my_channel_info(self) -> Optional[Dict[str, Any]]:
        """
        Get authenticated user's channel metadata.

        Requires OAuth credentials with youtube.readonly scope.
        """
        try:
            response = self.youtube.channels().list(
                part="snippet,statistics,contentDetails",
                mine=True
            ).execute()

            if not response.get("items"):
                return None

            item = response["items"][0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            return {
                "id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "custom_url": snippet.get("customUrl", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "uploads_playlist_id": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            }
        except HttpError as e:
            print(f"Error fetching authenticated channel: {e}")
            return None
    
    def get_channel_videos(
        self, 
        channel_id: str, 
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent videos from a channel.
        
        Returns:
            List of video dicts with: id, title, description, publishedAt, 
                                       thumbnailUrl, duration (from separate call)
        """
        try:
            # First get the uploads playlist ID
            channel_info = self.get_channel_info(channel_id)
            if not channel_info or not channel_info.get("uploads_playlist_id"):
                return []
            
            uploads_playlist_id = channel_info["uploads_playlist_id"]
            
            # Get videos from uploads playlist
            videos = []
            next_page_token = None
            
            while len(videos) < max_results:
                response = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=min(50, max_results - len(videos)),
                    pageToken=next_page_token
                ).execute()
                
                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    videos.append({
                        "id": item.get("contentDetails", {}).get("videoId"),
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                        "channel_id": channel_id,
                    })
                
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break
            
            return videos[:max_results]
        except HttpError as e:
            print(f"Error fetching videos for channel {channel_id}: {e}")
            return []
    
    def get_video_details(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed stats for videos.
        
        Args:
            video_ids: List of video IDs (max 50 per call)
            
        Returns:
            Dict mapping video_id to stats dict with: views, likes, comments,
                                                       duration, durationSeconds
        """
        result = {}
        
        # Process in batches of 50
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            
            try:
                response = self.youtube.videos().list(
                    part="statistics,contentDetails",
                    id=",".join(batch)
                ).execute()
                
                for item in response.get("items", []):
                    video_id = item["id"]
                    stats = item.get("statistics", {})
                    content = item.get("contentDetails", {})
                    
                    # Parse duration (ISO 8601 format: PT1H2M3S)
                    duration_str = content.get("duration", "PT0S")
                    duration_seconds = self._parse_duration(duration_str)
                    
                    result[video_id] = {
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)),
                        "comment_count": int(stats.get("commentCount", 0)),
                        "duration": duration_str,
                        "duration_seconds": duration_seconds,
                    }
            except HttpError as e:
                print(f"Error fetching video details: {e}")
        
        return result
    
    def _parse_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    
    def get_video_captions(self, video_id: str) -> Optional[str]:
        """
        Get captions/transcript for a video if available.
        
        Note: This requires OAuth with youtube.force-ssl scope for 
        third-party videos. For public videos, consider using 
        youtube_transcript_api library instead.
        """
        try:
            response = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            ).execute()
            
            captions = response.get("items", [])
            if not captions:
                return None
            
            # Prefer English captions
            caption_id = None
            for caption in captions:
                lang = caption.get("snippet", {}).get("language", "")
                if lang.startswith("en"):
                    caption_id = caption["id"]
                    break
            
            if not caption_id and captions:
                caption_id = captions[0]["id"]
            
            # Note: Actually downloading captions requires additional auth
            # For MVP, we'll return caption availability
            return f"Captions available: {caption_id}"
        except HttpError:
            return None


def create_youtube_client_with_api_key(api_key: str) -> YouTubeClient:
    """Create a YouTube client using an API key."""
    return YouTubeClient(api_key=api_key)


def create_youtube_client_with_oauth(access_token: str) -> YouTubeClient:
    """Create a YouTube client using OAuth credentials."""
    from google.oauth2.credentials import Credentials
    credentials = Credentials(token=access_token)
    return YouTubeClient(credentials=credentials)
