import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from helpers.decorators import admin_only, error_handler, rate_limit
from helpers.formatters import format_now_playing

logger = logging.getLogger(__name__)


def register_control_handlers(app: Client) -> None:

    @app.on_message(filters.command("pause") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def pause_cmd(client: Client, message: Message):
        from voice import voice_manager
        ok = await voice_manager.pause(message.chat.id)
        if ok:
            await message.reply("⏸ Paused.")
        else:
            await message.reply("⚠️ Nothing is playing or already paused.")

    @app.on_message(filters.command("resume") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def resume_cmd(client: Client, message: Message):
        from voice import voice_manager
        ok = await voice_manager.resume(message.chat.id)
        if ok:
            await message.reply("▶️ Resumed.")
        else:
            await message.reply("⚠️ Not paused.")

    @app.on_message(filters.command("skip") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def skip_cmd(client: Client, message: Message):
        from voice import voice_manager
        next_track = await voice_manager.skip(message.chat.id)
        if next_track:
            await message.reply(
                f"⏭ Skipped! Now playing:\n**{next_track.title}** — {next_track.artist}"
            )
        else:
            await message.reply("⏹ Queue finished. No more tracks.")

    @app.on_message(filters.command("stop") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def stop_cmd(client: Client, message: Message):
        from voice import voice_manager
        from database import db
        await voice_manager.stop(message.chat.id)
        await db.clear_queue(message.chat.id)
        await message.reply("⏹ Stopped and cleared the queue.")

    @app.on_message(filters.command("volume") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def volume_cmd(client: Client, message: Message):
        from voice import voice_manager
        args = message.command[1:]
        if not args or not args[0].isdigit():
            state = voice_manager.get_state(message.chat.id)
            await message.reply(
                f"🔊 Current volume: **{state.volume}**\nUsage: `/volume 0-200`"
            )
            return
        vol = int(args[0])
        ok = await voice_manager.set_volume(message.chat.id, vol)
        if ok:
            await message.reply(f"🔊 Volume set to **{min(200, max(0, vol))}**.")
        else:
            await message.reply("❌ Failed to change volume. Join a voice chat first.")

    @app.on_message(filters.command("nowplaying") & filters.group & filters.incoming)
    @rate_limit(seconds=5)
    @error_handler
    async def nowplaying_cmd(client: Client, message: Message):
        from voice import voice_manager
        state = voice_manager.get_state(message.chat.id)
        track = state.current_track
        if not track or not state.is_playing:
            await message.reply("🔇 Nothing is playing right now.")
            return
        elapsed = voice_manager.elapsed(message.chat.id)
        text = format_now_playing(track, elapsed)
        if track.thumbnail:
            await message.reply_photo(track.thumbnail, caption=text)
        else:
            await message.reply(text)

    @app.on_message(filters.command("shuffle") & filters.group & filters.incoming)
    @admin_only
    @error_handler
    async def shuffle_cmd(client: Client, message: Message):
        from voice import voice_manager
        from database import db
        state = voice_manager.get_state(message.chat.id)
        if len(state.tracks) < 2:
            await message.reply("⚠️ Not enough tracks in the queue to shuffle.")
            return
        state.shuffle_queue()
        await db.set_queue(message.chat.id, [t.to_dict() for t in state.tracks])
        await message.reply("🔀 Queue shuffled!")
