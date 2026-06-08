"""
Video/Audio reply handler
==========================
Users can play any video or audio file from a group chat in the voice chat
by replying to it (with or without a command):

  • Reply to a video/audio message with `/play` (no text after)
  • Or just reply with `/vplay`
  • Also handles forwarded videos — same reply mechanic

Supported media types:
  - Video messages
  - Video notes (round videos)
  - Audio messages
  - Voice notes
  - Documents that are video/audio files

The file is downloaded to a temp path and streamed directly via PyTgCalls.
"""
import logging
import os
import tempfile

from pyrogram import Client, filters
from pyrogram.types import Message

from database.models import Track
from helpers.decorators import error_handler, rate_limit
from helpers.formatters import format_duration

logger = logging.getLogger(__name__)

# MIME types recognised as playable media
_VIDEO_MIME = {"video/mp4", "video/webm", "video/x-matroska", "video/avi", "video/quicktime"}
_AUDIO_MIME = {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav", "audio/flac", "audio/aac"}
_PLAYABLE_MIME = _VIDEO_MIME | _AUDIO_MIME


def _get_media_from_message(msg: Message):
    """Return (media_object, kind_str) or (None, None) if no playable media."""
    if msg.video:
        return msg.video, "video"
    if msg.video_note:
        return msg.video_note, "video note"
    if msg.audio:
        return msg.audio, "audio"
    if msg.voice:
        return msg.voice, "voice"
    if msg.document and msg.document.mime_type in _PLAYABLE_MIME:
        return msg.document, "file"
    return None, None


def _media_title(msg: Message, media, kind: str) -> str:
    if kind == "audio" and msg.audio:
        parts = []
        if msg.audio.performer:
            parts.append(msg.audio.performer)
        if msg.audio.title:
            parts.append(msg.audio.title)
        return " — ".join(parts) if parts else (msg.audio.file_name or "Audio")
    if kind == "file" and msg.document.file_name:
        return msg.document.file_name
    sender = ""
    if msg.from_user:
        sender = msg.from_user.first_name or ""
    elif msg.forward_origin:
        # pyrogram 2.x uses forward_origin
        try:
            sender = msg.forward_origin.sender_user.first_name or ""
        except AttributeError:
            sender = ""
    return f"{kind.title()} from {sender}" if sender else kind.title()


def register_video_handlers(app: Client) -> None:

    # ── /vplay command OR /play with a replied-to media message ──────────────
    @app.on_message(
        (filters.command(["vplay", "play"]) | filters.regex(r"^/vplay")) &
        filters.group &
        filters.incoming
    )
    @rate_limit(seconds=5)
    @error_handler
    async def vplay_cmd(client: Client, message: Message):
        from voice import voice_manager
        from database import db

        # Only intercept when the user replied to a media message
        # (plain /play with text is handled by the play handler)
        replied = message.reply_to_message
        if not replied:
            return  # pass to normal play handler

        # If /play with additional text args → let the normal play handler run
        if message.command[0] == "play" and len(message.command) > 1:
            return

        media, kind = _get_media_from_message(replied)
        if not media:
            await message.reply(
                "⚠️ Reply to a **video**, **audio**, **voice note**, or **document** to play it."
            )
            return

        chat_id = message.chat.id
        status_msg = await message.reply("⬇️ Downloading media…")

        # Download to a temp file
        tmp_dir = "/tmp/musicbot_dl"
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            file_path = await client.download_media(
                replied,
                file_name=os.path.join(tmp_dir, f"{replied.id}_{chat_id}"),
            )
        except Exception as exc:
            logger.error(f"Media download failed: {exc}")
            await status_msg.edit("❌ Could not download the media. Try again.")
            return

        if not file_path or not os.path.exists(file_path):
            await status_msg.edit("❌ Download failed — file not found after download.")
            return

        title = _media_title(replied, media, kind)
        duration = getattr(media, "duration", 0) or 0
        requester = message.from_user.id if message.from_user else 0

        track = Track(
            title=title,
            artist="Telegram Media",
            duration=int(duration),
            url=file_path,          # local file path — PyTgCalls accepts these
            thumbnail="",
            album="",
            requested_by=requester,
            chat_id=chat_id,
        )

        state = voice_manager.get_state(chat_id)
        state.add_track(track)
        await db.set_queue(chat_id, [t.to_dict() for t in state.tracks])

        if not state.is_playing:
            success = await voice_manager.play(chat_id, track)
            if success:
                await db.record_play(chat_id, track.to_dict())
                caption = (
                    f"🎬 **Now Playing**\n"
                    f"**{title}**\n"
                    f"⏱ {format_duration(int(duration))}"
                )
                await status_msg.edit(caption)
            else:
                await status_msg.edit(
                    "❌ Failed to join voice chat. Make sure a voice chat is active in this group."
                )
        else:
            await status_msg.edit(f"➕ Added **{title}** to the queue")

    # ── Auto-detect: any forwarded video posted in a group ───────────────────
    @app.on_message(
        (filters.video | filters.video_note | filters.audio | filters.voice) &
        filters.group &
        filters.incoming &
        filters.forwarded
    )
    @error_handler
    async def forwarded_media_autoplay(client: Client, message: Message):
        """
        When a forwarded video/audio is posted in the group, reply with a hint.
        Users can then reply to it with /vplay to play it.
        """
        media, kind = _get_media_from_message(message)
        if not media:
            return
        await message.reply(
            f"🎬 Forwarded **{kind}** detected!\n"
            f"Reply to it with `/vplay` to play it in the voice chat.",
            quote=True,
        )
