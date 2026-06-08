from pyrogram import Client, filters
from pyrogram.types import Message

HELP_TEXT = """
🎵 **Music Userbot Commands**

**Playback**
`/play <song or Spotify URL>` — Search and play a song, or load a full Spotify playlist/album
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
💡 Spotify links automatically resolve to YouTube audio.
🔒 Commands marked *(admin)* require group admin privileges or being in ADMIN_IDS.
👤 This is a userbot — it runs as your Telegram account.
"""


def register_help_handlers(app: Client) -> None:

    @app.on_message(filters.command("help") & filters.incoming)
    async def help_cmd(client: Client, message: Message):
        await message.reply(HELP_TEXT, disable_web_page_preview=True)
