import asyncio
import logging
import time
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, AudioParameters
from pytgcalls.exceptions import NotInCallError, AlreadyJoinedError

from database.models import QueueState, Track

logger = logging.getLogger(__name__)


class VoiceManager:
    """
    Manages per-chat voice chat sessions and coordinates playback with
    the in-memory queue state.
    """

    def __init__(self):
        self._calls: PyTgCalls | None = None
        # chat_id -> QueueState
        self._queues: dict[int, QueueState] = {}
        # chat_id -> unix timestamp of when current track started
        self._play_start: dict[int, float] = {}

    def set_client(self, calls: PyTgCalls) -> None:
        """Inject the PyTgCalls instance after it is created."""
        self._calls = calls

    # ── Queue state helpers ───────────────────────────────────────────────────

    def get_state(self, chat_id: int) -> QueueState:
        if chat_id not in self._queues:
            self._queues[chat_id] = QueueState(chat_id=chat_id)
        return self._queues[chat_id]

    def elapsed(self, chat_id: int) -> int:
        """Seconds elapsed in the current track."""
        start = self._play_start.get(chat_id, 0)
        return int(time.monotonic() - start) if start else 0

    # ── Playback control ──────────────────────────────────────────────────────

    async def play(self, chat_id: int, track: Track) -> bool:
        """
        Start streaming `track` in `chat_id`'s voice chat.
        Joins the voice chat first if not already present.
        Returns True on success.
        """
        try:
            audio = AudioPiped(
                track.url,
                audio_parameters=AudioParameters(bitrate=192),
            )
            state = self.get_state(chat_id)

            try:
                await self._calls.join_group_call(chat_id, audio)
            except AlreadyJoinedError:
                await self._calls.change_stream(chat_id, audio)

            state.is_playing = True
            state.is_paused = False
            self._play_start[chat_id] = time.monotonic()
            logger.info(f"[{chat_id}] Playing: {track.title} by {track.artist}")
            return True

        except Exception as exc:
            logger.error(f"[{chat_id}] Play error: {exc}")
            return False

    async def pause(self, chat_id: int) -> bool:
        state = self.get_state(chat_id)
        if not state.is_playing or state.is_paused:
            return False
        try:
            await self._calls.pause_stream(chat_id)
            state.is_paused = True
            return True
        except NotInCallError:
            return False

    async def resume(self, chat_id: int) -> bool:
        state = self.get_state(chat_id)
        if not state.is_paused:
            return False
        try:
            await self._calls.resume_stream(chat_id)
            state.is_paused = False
            return True
        except NotInCallError:
            return False

    async def skip(self, chat_id: int) -> Optional[Track]:
        """Advance to the next track and start playing it. Returns the new track."""
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
            await self._calls.leave_group_call(chat_id)
        except (NotInCallError, Exception):
            pass
        state.is_playing = False
        state.is_paused = False
        state.tracks.clear()
        state.current_index = 0
        self._play_start.pop(chat_id, None)
        return True

    async def set_volume(self, chat_id: int, volume: int) -> bool:
        """Set volume (0-200)."""
        volume = max(0, min(200, volume))
        try:
            await self._calls.change_volume_call(chat_id, volume)
            self.get_state(chat_id).volume = volume
            return True
        except Exception as exc:
            logger.error(f"[{chat_id}] Volume error: {exc}")
            return False

    # ── Auto-advance callback ─────────────────────────────────────────────────

    async def on_stream_end(self, chat_id: int) -> None:
        """
        Called by the PyTgCalls stream-end event. Automatically plays the next
        track if one exists, otherwise leaves the voice chat.
        """
        from database import db

        logger.info(f"[{chat_id}] Stream ended, advancing queue")
        state = self.get_state(chat_id)
        next_track = state.advance()

        if next_track:
            # Resolve a fresh audio URL in case the cached one expired
            from services import youtube
            yt_result = await youtube.find_for_track(next_track.title, next_track.artist)
            if yt_result:
                audio_url = await youtube.get_stream_url(yt_result["url"])
                if audio_url:
                    next_track.url = audio_url

            await self.play(chat_id, next_track)
            await db.record_play(chat_id, next_track.to_dict())
        else:
            await self.stop(chat_id)
            logger.info(f"[{chat_id}] Queue exhausted, left voice chat")

    # ── Auto-reconnect ────────────────────────────────────────────────────────

    async def on_kicked(self, chat_id: int) -> None:
        """Called when the userbot is removed from a voice chat."""
        logger.warning(f"[{chat_id}] Kicked from voice chat")
        state = self.get_state(chat_id)
        state.is_playing = False
        state.is_paused = False

    async def try_reconnect(self, chat_id: int, retries: int = 3) -> bool:
        """Attempt to rejoin and resume playback after a disconnect."""
        state = self.get_state(chat_id)
        track = state.current_track
        if not track:
            return False

        for attempt in range(1, retries + 1):
            logger.info(f"[{chat_id}] Reconnect attempt {attempt}/{retries}")
            await asyncio.sleep(2 ** attempt)
            success = await self.play(chat_id, track)
            if success:
                return True

        logger.error(f"[{chat_id}] All reconnect attempts failed")
        return False
