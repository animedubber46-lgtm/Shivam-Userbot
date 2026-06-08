"""
Audio service — SoundCloud primary source
==========================================
YouTube stream extraction is blocked on datacenter IPs (Replit, etc.).
SoundCloud user-uploaded tracks have full audio with no server-IP restrictions.

Search flow:
  1. scsearch via yt-dlp → returns direct CDN stream URL + metadata in one call
  2. Prefer full-length tracks (> 60 s); fall back to whatever is found
"""
import asyncio
import logging
import os
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
}

_SC_OPTS = {
    **_BASE_OPTS,
    "format": "bestaudio/best",
    "noplaylist": True,
}

_YT_FLAT_OPTS = {
    **_BASE_OPTS,
    "extract_flat": True,
    "default_search": "ytsearch",
}


class YouTubeService:
    """
    Despite the class name (kept for import compatibility), this service uses
    SoundCloud as the primary audio source because YouTube stream URLs are
    blocked on datacenter IPs.
    """

    def __init__(self, audio_quality: str = "192", download_dir: str = "/tmp/musicbot"):
        self.audio_quality = audio_quality
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search SoundCloud and return track metadata list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sc_search_sync, query, max_results)

    def _sc_search_sync(self, query: str, max_results: int) -> list[dict]:
        # Fetch more candidates so we can prefer full-length tracks
        fetch_n = max(max_results, 5)
        sc_query = f"scsearch{fetch_n}:{query}"
        try:
            with yt_dlp.YoutubeDL(_SC_OPTS) as ydl:
                info = ydl.extract_info(sc_query, download=False)
            entries = info.get("entries", []) if info else []

            full: list[dict] = []
            previews: list[dict] = []

            for e in entries:
                if not e:
                    continue
                stream_url = e.get("url", "")
                if not stream_url:
                    continue
                duration = e.get("duration") or 0
                record = {
                    "id": e.get("id", ""),
                    "title": e.get("title", ""),
                    "url": e.get("webpage_url") or e.get("url", ""),
                    "stream_url": stream_url,
                    "duration": int(duration),
                    "thumbnail": e.get("thumbnail", ""),
                    "uploader": e.get("uploader", ""),
                }
                # Anything longer than 60 s is a full track
                if duration > 60:
                    full.append(record)
                else:
                    previews.append(record)

            # Return full-length tracks first; include previews only as a last resort
            combined = (full + previews)[:max_results]
            return combined

        except Exception as exc:
            logger.error(f"SoundCloud search error: {exc}")
            return []

    # ── Stream URL ────────────────────────────────────────────────────────────

    async def get_stream_url(self, url: str) -> Optional[str]:
        """
        If `url` is already a SoundCloud CDN URL, return it as-is.
        Otherwise extract a fresh stream URL from the track page.
        """
        if "sndcdn.com" in url:
            return url
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_stream_sync, url)

    def _extract_stream_sync(self, url: str) -> Optional[str]:
        try:
            with yt_dlp.YoutubeDL(_SC_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url") if info else None
        except Exception as exc:
            logger.error(f"Stream URL extraction error: {exc}")
            return None

    # ── Find audio for a Spotify track ───────────────────────────────────────

    async def find_for_track(self, title: str, artist: str) -> Optional[dict]:
        """
        Given Spotify metadata, find the best SoundCloud match.
        Tries progressively broader queries until a full-length result is found.
        """
        queries = [
            f"{artist} - {title}",
            f"{title} {artist}",
            f"{title}",
        ]
        for query in queries:
            results = await self.search(query, max_results=5)
            # Prefer full-length results (> 60 s)
            full = [r for r in results if r["duration"] > 60]
            if full:
                # Pick the one whose duration is closest to a typical song length (3.5 min)
                return sorted(full, key=lambda r: abs(r["duration"] - 210))[0]
            # Fall back to whatever is available
            if results:
                return results[0]
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def has_cookies(self) -> bool:
        return False

    def cleanup_file(self, file_path: str) -> None:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError as exc:
            logger.warning(f"Failed to delete {file_path}: {exc}")

    async def close(self) -> None:
        pass
