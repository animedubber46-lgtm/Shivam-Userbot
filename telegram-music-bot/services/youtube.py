import asyncio
import logging
import os
import re
import tempfile
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

# yt-dlp options for audio extraction
YDL_OPTS_SEARCH = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "default_search": "ytsearch",
}

YDL_OPTS_INFO = {
    "quiet": True,
    "no_warnings": True,
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "noplaylist": True,
}


def _build_download_opts(output_path: str, audio_quality: str = "192") -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality,
            }
        ],
    }


class YouTubeService:
    def __init__(self, audio_quality: str = "192", download_dir: str = "/tmp/musicbot"):
        self.audio_quality = audio_quality
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    async def search(self, query: str, max_results: int = 1) -> list[dict]:
        """
        Search YouTube for `query`. Returns a list of result dicts with
        id, title, url, duration keys.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, max_results)

    def _search_sync(self, query: str, max_results: int) -> list[dict]:
        try:
            with yt_dlp.YoutubeDL(YDL_OPTS_SEARCH) as ydl:
                results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                entries = results.get("entries", [])
                out = []
                for e in entries:
                    if not e:
                        continue
                    out.append({
                        "id": e.get("id", ""),
                        "title": e.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={e.get('id', '')}",
                        "duration": e.get("duration", 0) or 0,
                        "thumbnail": e.get("thumbnail", ""),
                    })
                return out
        except Exception as exc:
            logger.error(f"YouTube search error: {exc}")
            return []

    async def get_stream_url(self, youtube_url: str) -> Optional[str]:
        """
        Extract a direct audio stream URL (no download). Good for low-latency
        playback when yt-dlp returns a CDN link.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_stream_url_sync, youtube_url)

    def _get_stream_url_sync(self, youtube_url: str) -> Optional[str]:
        try:
            with yt_dlp.YoutubeDL(YDL_OPTS_INFO) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                return info.get("url")
        except Exception as exc:
            logger.error(f"YouTube stream URL error for {youtube_url}: {exc}")
            return None

    async def download_audio(self, youtube_url: str, track_id: str) -> Optional[str]:
        """
        Download audio to a local MP3 file and return the file path.
        Falls back to streaming URL if download fails.
        """
        output_template = os.path.join(self.download_dir, f"{track_id}.%(ext)s")
        mp3_path = os.path.join(self.download_dir, f"{track_id}.mp3")

        # Return cached file if it already exists
        if os.path.exists(mp3_path):
            return mp3_path

        loop = asyncio.get_event_loop()
        opts = _build_download_opts(output_template, self.audio_quality)
        success = await loop.run_in_executor(
            None, self._download_sync, youtube_url, opts
        )
        if success and os.path.exists(mp3_path):
            return mp3_path

        # Fallback: return a direct stream URL
        logger.warning(f"Download failed for {youtube_url}, falling back to stream URL")
        return await self.get_stream_url(youtube_url)

    def _download_sync(self, url: str, opts: dict) -> bool:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return True
        except Exception as exc:
            logger.error(f"YouTube download error: {exc}")
            return False

    async def find_for_track(self, title: str, artist: str) -> Optional[dict]:
        """
        Build a search query from Spotify metadata and return the best YouTube match.
        """
        query = f"{title} {artist} official audio"
        results = await self.search(query, max_results=1)
        if results:
            return results[0]

        # Broader fallback
        results = await self.search(f"{title} {artist}", max_results=1)
        return results[0] if results else None

    def cleanup_file(self, file_path: str) -> None:
        """Delete a downloaded audio file after it has been streamed."""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError as exc:
            logger.warning(f"Failed to delete {file_path}: {exc}")
