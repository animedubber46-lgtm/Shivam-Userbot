import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from database.models import Track
from helpers.decorators import error_handler, rate_limit
from helpers.formatters import format_duration

logger = logging.getLogger(__name__)

NO_COOKIES_MSG = (
    "⚠️ **YouTube is blocking audio extraction.**\n\n"
    "This happens on server IPs without YouTube cookies.\n"
    "Ask the bot admin to add `cookies.txt` — see the README for instructions."
)


def register_play_handlers(app: Client) -> None:

    @app.on_message(filters.command("play") & filters.group & filters.incoming)
    @rate_limit(seconds=3)
    @error_handler
    async def play_cmd(client: Client, message: Message):
        from database import db
        from services import spotify, youtube
        from voice import voice_manager

        args = message.command[1:]
        if not args:
            await message.reply("🎵 Usage: `/play <song name or Spotify URL>`")
            return

        query = " ".join(args).strip()
        status_msg = await message.reply("🔍 Searching…")
        chat_id = message.chat.id

        tracks_to_add: list[dict] = []

        # ── Spotify URL → rich metadata, audio sourced from YouTube ──────────
        sp_parsed = spotify.parse_spotify_url(query)
        if sp_parsed:
            sp_type, sp_id = sp_parsed
            try:
                if sp_type == "track":
                    t = await spotify.get_track(sp_id)
                    if t:
                        tracks_to_add = [t]
                elif sp_type == "playlist":
                    await status_msg.edit("📋 Loading Spotify playlist…")
                    tracks_to_add = await spotify.get_playlist_tracks(sp_id)
                elif sp_type == "album":
                    await status_msg.edit("💿 Loading Spotify album…")
                    tracks_to_add = await spotify.get_album_tracks(sp_id)
            except Exception as exc:
                logger.warning(f"Spotify metadata fetch failed: {exc}")
                sp_parsed = None  # fall through to YouTube search

        # ── Plain text → search YouTube directly ──────────────────────────────
        if not sp_parsed:
            await status_msg.edit("🔍 Searching YouTube…")
            yt_results = await youtube.search(query, max_results=1)
            if yt_results:
                r = yt_results[0]
                tracks_to_add = [{
                    "title": r["title"],
                    "artist": "YouTube",
                    "duration": r["duration"],
                    "album": "",
                    "thumbnail": r.get("thumbnail", ""),
                    "youtube_url": r["url"],
                }]
            else:
                await status_msg.edit("❌ No results found. Try a different search term.")
                return

        if not tracks_to_add:
            await status_msg.edit("❌ No results found. Try a different search term.")
            return

        state = voice_manager.get_state(chat_id)
        added_count = 0
        cookies_error = False

        for meta in tracks_to_add:
            yt_url = meta.pop("youtube_url", None)

            if not yt_url:
                yt_result = await youtube.find_for_track(meta["title"], meta["artist"])
                if not yt_result:
                    logger.warning(f"No YouTube match for {meta['title']}")
                    continue
                yt_url = yt_result["url"]

            audio_url = await youtube.get_stream_url(yt_url)
            if not audio_url:
                cookies_error = True
                continue

            track = Track(
                title=meta.get("title", "Unknown"),
                artist=meta.get("artist", "Unknown"),
                duration=meta.get("duration", 0),
                url=audio_url,
                thumbnail=meta.get("thumbnail", ""),
                album=meta.get("album", ""),
                requested_by=message.from_user.id if message.from_user else 0,
                chat_id=chat_id,
            )
            state.add_track(track)
            added_count += 1

        if added_count == 0:
            # Give a helpful error if the issue is cookies vs. a genuine miss
            if cookies_error:
                await status_msg.edit(NO_COOKIES_MSG)
            else:
                await status_msg.edit("❌ Could not find playable audio. Try a different query.")
            return

        await db.set_queue(chat_id, [t.to_dict() for t in state.tracks])

        # Start playback if not already playing
        if not state.is_playing:
            current = state.current_track
            if current:
                success = await voice_manager.play(chat_id, current)
                if success:
                    await db.record_play(chat_id, current.to_dict())
                    caption = (
                        f"🎵 **Now Playing**\n"
                        f"**{current.title}**\n"
                        f"👤 {current.artist}\n"
                        f"⏱ {format_duration(current.duration)}"
                    )
                    if added_count > 1:
                        caption += f"\n\n📋 +{added_count - 1} more tracks queued"
                    if current.thumbnail:
                        await status_msg.delete()
                        await message.reply_photo(current.thumbnail, caption=caption)
                    else:
                        await status_msg.edit(caption)
                else:
                    await status_msg.edit(
                        "❌ Failed to join voice chat. Make sure an active voice chat exists in this group."
                    )
        else:
            msg = (
                f"➕ Added **{tracks_to_add[0].get('title', 'track')}** to the queue"
                if added_count == 1
                else f"➕ Added **{added_count} tracks** to the queue"
            )
            await status_msg.edit(msg)
