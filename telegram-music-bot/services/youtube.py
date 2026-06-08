"""
Audio service — SoundCloud primary, YouTube fallback
======================================================
YouTube stream extraction is blocked on datacenter IPs (Replit, Railway free, etc.).
SoundCloud user-uploaded tracks have full audio and no server-IP restrictions.

Search flow:
  1. Try SoundCloud (scsearch:) — returns full-length audio reliably
  2. Fall back to YouTube flat search for metadata only (used by Spotify-URL path)
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
    Despite the class name (kept for import compatibility), this service now
    uses SoundCloud as the primary audio source because YouTube stream URLs
    are blocked on datacenter IPs.
    """

    def __init__(self, audio_quality: str = "192", download_dir: str = "/tmp/musicbot"):
        self.audio_quality = audio_quality
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, max_results: int = 1) -> list[dict]:
        """Search SoundCloud and return track metadata list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sc_search_sync, query, max_results)

    def _sc_search_sync(self, query: str, max_results: int) -> list[dict]:
        sc_query = f"scsearch{max_results}:{query}"
        try:
            with yt_dlp.YoutubeDL(_SC_OPTS) as ydl:
                info = ydl.extract_info(sc_query, download=False)
            entries = info.get("entries", []) if info else []
            out = []
            for e in entries:
                if not e:
                    continue
                # Only include tracks with a usable stream URL
                stream_url = e.get("url", "")
                if not stream_url:
                    continue
                duration = e.get("duration") or 0
                # Skip previews (≤30 s) and try to find a longer match
                if duration > 30:
                    out.append({
                        "id": e.get("id", ""),
                        "title": e.get("title", ""),
                        "url": e.get("webpage_url") or e.get("url", ""),
                        "stream_url": stream_url,
                        "duration": int(duration),
                        "thumbnail": e.get("thumbnail", ""),
                        "uploader": e.get("uploader", ""),
                    })
            return out
        except Exception as exc:
            logger.error(f"SoundCloud search error: {exc}")
            return []

    # ── Stream URL ────────────────────────────────────────────────────────────

    async def get_stream_url(self, url: str) -> Optional[str]:
        """
        If `url` is already a direct stream URL (from search results), return it.
        Otherwise extract it from the SoundCloud track page.
        """
        # Direct CDN URLs from scsearch already have the stream URL embedded
        if url.startswith("https://cf-hls-media.sndcdn.com") or \
           url.startswith("https://cf-media.sndcdn.com"):
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
            results = await self.search(query, max_results=3)
            if results:
                # Prefer the result whose duration is closest to a realistic track (2–7 min)
                best = sorted(
                    results,
                    key=lambda r: abs(r["duration"] - 210),  # 3.5 min target
                )[0]
                return best
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def has_cookies(self) -> bool:
        return False  # No longer needed — SoundCloud doesn't require cookies

    def cleanup_file(self, file_path: str) -> None:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError as exc:
            logger.warning(f"Failed to delete {file_path}: {exc}")

    async def close(self) -> None:
        pass  # No persistent session to close
