import asyncio
import logging
import os
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

# Cookies file path — user exports this from their browser (see README)
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "cookies.txt")
COOKIES_FILE = os.path.normpath(COOKIES_FILE)


def _cookies_opts() -> dict:
    """Return cookie options if cookies.txt exists."""
    if os.path.exists(COOKIES_FILE):
        return {"cookiefile": COOKIES_FILE}
    return {}


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        **_cookies_opts(),
    }


def _search_opts() -> dict:
    return {
        **_base_opts(),
        "extract_flat": True,
        "default_search": "ytsearch",
    }


def _info_opts() -> dict:
    return {
        **_base_opts(),
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
    }


def _download_opts(output_path: str, audio_quality: str) -> dict:
    return {
        **_base_opts(),
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

    def has_cookies(self) -> bool:
        return os.path.exists(COOKIES_FILE)

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, max_results: int = 1) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, max_results)

    def _search_sync(self, query: str, max_results: int) -> list[dict]:
        try:
            with yt_dlp.YoutubeDL(_search_opts()) as ydl:
                results = ydl.extract_info(
                    f"ytsearch{max_results}:{query}", download=False
                )
            entries = results.get("entries", []) if results else []
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

    # ── Stream URL ────────────────────────────────────────────────────────────

    async def get_stream_url(self, youtube_url: str) -> Optional[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_stream_url_sync, youtube_url)

    def _get_stream_url_sync(self, youtube_url: str) -> Optional[str]:
        try:
            with yt_dlp.YoutubeDL(_info_opts()) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                return info.get("url") if info else None
        except Exception as exc:
            logger.error(f"YouTube stream URL error: {exc}")
            return None

    # ── Download (fallback for PyTgCalls when stream URL is short-lived) ──────

    async def download_audio(self, youtube_url: str, track_id: str) -> Optional[str]:
        mp3_path = os.path.join(self.download_dir, f"{track_id}.mp3")
        if os.path.exists(mp3_path):
            return mp3_path
        loop = asyncio.get_event_loop()
        output_template = os.path.join(self.download_dir, f"{track_id}.%(ext)s")
        ok = await loop.run_in_executor(
            None, self._download_sync, youtube_url, output_template
        )
        return mp3_path if ok and os.path.exists(mp3_path) else None

    def _download_sync(self, url: str, output_template: str) -> bool:
        try:
            opts = _download_opts(output_template, self.audio_quality)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return True
        except Exception as exc:
            logger.error(f"YouTube download error: {exc}")
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def find_for_track(self, title: str, artist: str) -> Optional[dict]:
        results = await self.search(f"{title} {artist} official audio", max_results=1)
        if not results:
            results = await self.search(f"{title} {artist}", max_results=1)
        return results[0] if results else None

    def cleanup_file(self, file_path: str) -> None:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError as exc:
            logger.warning(f"Failed to delete {file_path}: {exc}")
