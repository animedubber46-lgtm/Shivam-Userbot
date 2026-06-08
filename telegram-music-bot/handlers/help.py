from pyrogram import Client, filters
from pyrogram.types import Message

HELP_TEXT = """
🎵 **Music Bot Commands**

**Playback**
`/play <song or Spotify URL>` — Search and play a song (or load a Spotify track, playlist, or album)
`/pause` — Pause playback *(admin)*
`/resume` — Resume playback *(admin)*
`/skip` — Skip to the next song *(admin)*
`/stop` — Stop playback and clear the queue *(admin)*
`/nowplaying` — Show the current track with a progress bar

**Queue**
`/queue [page]` — Show the current queue (paginated)
`/shuffle` — Shuffle the remaining queue *(admin)*

**Volume**
`/volume [0-200]` — Get or set the playback volume *(admin)*

**Playlists**
`/playlist list` — List your saved playlists
`/playlist save <name>` — Save the current queue as a playlist
`/playlist load <name>` — Load a saved playlist into the queue
`/playlist delete <name>` — Delete a saved playlist

**Other**
`/help` — Show this message

---
💡 Spotify links are automatically resolved to YouTube audio.
🔒 Commands marked *(admin)* require group admin privileges.
"""


def register_help_handlers(bot: Client) -> None:

    @bot.on_message(filters.command("help"))
    async def help_cmd(client: Client, message: Message):
        await message.reply(HELP_TEXT, disable_web_page_preview=True)
