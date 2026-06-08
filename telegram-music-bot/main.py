"""
Music Userbot — Entry Point
============================
Your own Telegram account (STRING_SESSION) connects, listens for commands
in any group it's a member of, and streams music through voice chats.

No BOT_TOKEN needed — this is a pure userbot.
"""
import asyncio
import logging
import sys

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import Update, StreamAudioEnded

from config import settings
from database import db
from handlers import register_all_handlers
from services import spotify
from voice import voice_manager

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # Validate config early — fail fast if anything is missing
    settings.validate()

    # Connect to MongoDB
    await db.connect(settings.MONGO_URI, settings.DB_NAME)

    # Authenticate Spotify (token-only, no user login required)
    await spotify.authenticate(
        settings.SPOTIFY_CLIENT_ID,
        settings.SPOTIFY_CLIENT_SECRET,
    )

    # Create the userbot client — this IS your Telegram account
    userbot = Client(
        name="music_userbot",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        session_string=settings.STRING_SESSION,
    )

    # PyTgCalls wraps the same userbot to handle voice chat streaming
    calls = PyTgCalls(userbot)
    voice_manager.set_client(calls)

    # Auto-advance to the next track when the current one finishes
    @calls.on_stream_end()
    async def stream_end_handler(_, update: Update):
        if isinstance(update, StreamAudioEnded):
            await voice_manager.on_stream_end(update.chat_id)

    # Handle being kicked/removed from a voice chat
    @calls.on_kicked()
    async def kicked_handler(_, chat_id: int):
        await voice_manager.on_kicked(chat_id)
        await asyncio.sleep(5)
        reconnected = await voice_manager.try_reconnect(chat_id)
        if not reconnected:
            logger.warning(f"[{chat_id}] Could not reconnect after being kicked")

    # Register all command handlers on the userbot (your account)
    register_all_handlers(userbot)

    logger.info("Starting Music Userbot…")

    await userbot.start()
    await calls.start()

    me = await userbot.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username or me.id})")
    logger.info(f"Listening for commands with prefix: '{settings.CMD_PREFIX}'")
    logger.info("Userbot is running. Press Ctrl+C to stop.")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        logger.info("Shutting down…")
        await calls.stop()
        await userbot.stop()
        await db.disconnect()
        await spotify.close()
        logger.info("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
