import asyncio
import logging
import time
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality
from pytgcalls.exceptions import NotInCallError

from database.models import QueueState, Track

logger = logging.getLogger(__name__)


class VoiceManager:
    """
    Manages per-chat voice chat sessions and coordinates playback with
    the in-memory queue state.

    py-tgcalls 2.x API:
      calls.play(chat_id, stream)        — join + start (or change stream if already in)
      calls.pause(chat_id)               — pause
      calls.resume(chat_id)              — resume
      calls.leave_call(chat_id)          — leave voice chat
      calls.change_volume_call(chat_id)  — set volume
    """

    def __init__(self):
        self._calls: PyTgCalls | None = None
        self._queues: dict[int, QueueState] = {}
        self._play_start: dict[int, float] = {}

    def set_client(self, calls: PyTgCalls) -> None:
        self._calls = calls

    # ── Queue state ───────────────────────────────────────────────────────────

    def get_state(self, chat_id: int) -> QueueState:
        if chat_id not in self._queues:
            self._queues[chat_id] = QueueState(chat_id=chat_id)
        return self._queues[chat_id]

    def elapsed(self, chat_id: int) -> int:
        start = self._play_start.get(chat_id, 0)
        return int(time.monotonic() - start) if start else 0

    # ── Playback ──────────────────────────────────────────────────────────────

    async def play(self, chat_id: int, track: Track) -> bool:
        """Join the voice chat and stream `track`. Returns True on success."""
        try:
            stream = MediaStream(
                track.url,
                audio_parameters=AudioQuality.HIGH,
            )
            # In 2.x, calls.play() handles both join and stream-change automatically
            await self._calls.play(chat_id, stream)

            state = self.get_state(chat_id)
            state.is_playing = True
            state.is_paused = False
            self._play_start[chat_id] = time.monotonic()
            logger.info(f"[{chat_id}] Playing: {track.title} — {track.artist}")
            return True

        except Exception as exc:
            logger.error(f"[{chat_id}] Play error: {exc}")
            return False

    async def pause(self, chat_id: int) -> bool:
        state = self.get_state(chat_id)
        if not state.is_playing or state.is_paused:
            return False
        try:
            ok = await self._calls.pause(chat_id)
            if ok:
                state.is_paused = True
            return bool(ok)
        except Exception:
            return False

    async def resume(self, chat_id: int) -> bool:
        state = self.get_state(chat_id)
        if not state.is_paused:
            return False
        try:
            ok = await self._calls.resume(chat_id)
            if ok:
                state.is_paused = False
            return bool(ok)
        except Exception:
            return False

    async def skip(self, chat_id: int) -> Optional[Track]:
        state = self.get_state(chat_id)
        next_track = state.advance()
        if next_track:
            await self.play(chat_id, next_track)
        else:
            await self.stop(chat_id)
        return next_track

    async def stop(self, chat_id: int) -> bool:
        state = self.get_state(chat_id)
        try:
            await self._calls.leave_call(chat_id)
        except Exception:
            pass
        state.is_playing = False
        state.is_paused = False
        state.tracks.clear()
        state.current_index = 0
        self._play_start.pop(chat_id, None)
        return True

    async def set_volume(self, chat_id: int, volume: int) -> bool:
        volume = max(0, min(200, volume))
        try:
            await self._calls.change_volume_call(chat_id, volume)
            self.get_state(chat_id).volume = volume
            return True
        except Exception as exc:
            logger.error(f"[{chat_id}] Volume error: {exc}")
            return False

    # ── Auto-advance ──────────────────────────────────────────────────────────

    async def on_stream_end(self, chat_id: int) -> None:
        """Plays next track or leaves chat when current track finishes."""
        from database import db

        logger.info(f"[{chat_id}] Stream ended, advancing queue")
        state = self.get_state(chat_id)
        next_track = state.advance()

        if next_track:
            from services import youtube
            # Refresh stream URL (CDN URLs expire) using SoundCloud search
            sc_result = await youtube.find_for_track(next_track.title, next_track.artist)
            if sc_result and sc_result.get("stream_url"):
                next_track.url = sc_result["stream_url"]
            await self.play(chat_id, next_track)
            await db.record_play(chat_id, next_track.to_dict())
        else:
            await self.stop(chat_id)
            logger.info(f"[{chat_id}] Queue exhausted, left voice chat")

    # ── Disconnect / reconnect ────────────────────────────────────────────────

    async def on_kicked(self, chat_id: int) -> None:
        logger.warning(f"[{chat_id}] Disconnected from voice chat")
        state = self.get_state(chat_id)
        state.is_playing = False
        state.is_paused = False

    async def try_reconnect(self, chat_id: int, retries: int = 3) -> bool:
        state = self.get_state(chat_id)
        track = state.current_track
        if not track:
            return False
        for attempt in range(1, retries + 1):
            logger.info(f"[{chat_id}] Reconnect attempt {attempt}/{retries}")
            await asyncio.sleep(2 ** attempt)
            if await self.play(chat_id, track):
                return True
        logger.error(f"[{chat_id}] All reconnect attempts failed")
        return False
