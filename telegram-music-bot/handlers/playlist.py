import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from helpers.decorators import error_handler, rate_limit, admin_only

logger = logging.getLogger(__name__)


def register_playlist_handlers(bot: Client) -> None:

    @bot.on_message(filters.command("playlist") & filters.group)
    @rate_limit(seconds=3)
    @error_handler
    async def playlist_cmd(client: Client, message: Message):
        """
        Subcommands:
          /playlist list            — show your saved playlists
          /playlist save <name>     — save current queue as a playlist
          /playlist load <name>     — load a playlist into the queue
          /playlist delete <name>   — delete a saved playlist
        """
        from database import db
        from voice import voice_manager
        from services import youtube
        from database.models import Track

        args = message.command[1:]
        user_id = message.from_user.id if message.from_user else 0
        chat_id = message.chat.id

        if not args:
            await message.reply(
                "📋 **Playlist commands:**\n"
                "`/playlist list` — show saved playlists\n"
                "`/playlist save <name>` — save current queue\n"
                "`/playlist load <name>` — load a playlist\n"
                "`/playlist delete <name>` — delete a playlist"
            )
            return

        sub = args[0].lower()

        if sub == "list":
            playlists = await db.list_playlists(user_id)
            if not playlists:
                await message.reply("📭 You have no saved playlists.")
                return
            lines = ["📋 **Your Playlists:**\n"]
            for pl in playlists:
                lines.append(f"• **{pl['name']}** — {pl.get('count', 0)} tracks")
            await message.reply("\n".join(lines))

        elif sub == "save":
            if len(args) < 2:
                await message.reply("Usage: `/playlist save <name>`")
                return
            name = " ".join(args[1:]).strip()
            state = voice_manager.get_state(chat_id)
            if not state.tracks:
                await message.reply("⚠️ The queue is empty. Nothing to save.")
                return
            await db.save_playlist(user_id, name, [t.to_dict() for t in state.tracks])
            await message.reply(f"✅ Saved **{len(state.tracks)} tracks** as playlist \"**{name}**\".")

        elif sub == "load":
            if len(args) < 2:
                await message.reply("Usage: `/playlist load <name>`")
                return
            name = " ".join(args[1:]).strip()
            tracks_data = await db.get_playlist(user_id, name)
            if not tracks_data:
                await message.reply(f"❌ Playlist \"**{name}**\" not found.")
                return

            status_msg = await message.reply(f"⏳ Loading playlist \"**{name}**\" ({len(tracks_data)} tracks)…")
            state = voice_manager.get_state(chat_id)
            loaded = 0

            for td in tracks_data:
                # Re-resolve audio URL in case it expired
                yt_result = await youtube.find_for_track(td["title"], td["artist"])
                if not yt_result:
                    continue
                audio_url = await youtube.get_stream_url(yt_result["url"])
                if not audio_url:
                    continue
                td["url"] = audio_url
                track = Track.from_dict({**td, "chat_id": chat_id, "requested_by": user_id})
                state.add_track(track)
                loaded += 1

            await db.set_queue(chat_id, [t.to_dict() for t in state.tracks])

            if not state.is_playing and state.current_track:
                success = await voice_manager.play(chat_id, state.current_track)
                if success:
                    await status_msg.edit(
                        f"▶️ Loaded playlist \"**{name}**\" and started playing "
                        f"({loaded} tracks)."
                    )
                else:
                    await status_msg.edit(
                        f"✅ Loaded {loaded} tracks. Use /play to start (no active voice chat found)."
                    )
            else:
                await status_msg.edit(f"➕ Added {loaded} tracks from \"**{name}**\" to the queue.")

        elif sub == "delete":
            if len(args) < 2:
                await message.reply("Usage: `/playlist delete <name>`")
                return
            name = " ".join(args[1:]).strip()
            deleted = await db.delete_playlist(user_id, name)
            if deleted:
                await message.reply(f"🗑 Playlist \"**{name}**\" deleted.")
            else:
                await message.reply(f"❌ Playlist \"**{name}**\" not found.")

        else:
            await message.reply("❓ Unknown subcommand. Use `/playlist` to see options.")
