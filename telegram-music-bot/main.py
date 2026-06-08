"""
Music Bot — Entry Point
=======================
Starts the Pyrogram bot client, the Pyrogram userbot (string session),
and the PyTgCalls voice client, then registers all command handlers.
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
from services import spotify, youtube
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
    # Validate config early
    settings.validate()

    # Connect to MongoDB
    await db.connect(settings.MONGO_URI, settings.DB_NAME)

    # Authenticate Spotify
    await spotify.authenticate(
        settings.SPOTIFY_CLIENT_ID,
        settings.SPOTIFY_CLIENT_SECRET,
    )

    # Create the command-receiver bot client (handles /commands)
    bot = Client(
        name="music_bot",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        bot_token=settings.BOT_TOKEN,
    )

    # Create the userbot (streams audio in voice chats)
    userbot = Client(
        name="music_userbot",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        session_string=settings.STRING_SESSION,
    )

    # Create the PyTgCalls client — wraps the userbot
    calls = PyTgCalls(userbot)
    voice_manager.set_client(calls)

    # Register stream-end callback for auto-advance
    @calls.on_stream_end()
    async def stream_end_handler(_, update: Update):
        if isinstance(update, StreamAudioEnded):
            await voice_manager.on_stream_end(update.chat_id)

    # Register kicked/left callback for reconnect logic
    @calls.on_kicked()
    async def kicked_handler(_, chat_id: int):
        await voice_manager.on_kicked(chat_id)
        # Attempt to reconnect after a short delay
        await asyncio.sleep(5)
        reconnected = await voice_manager.try_reconnect(chat_id)
        if not reconnected:
            logger.warning(f"[{chat_id}] Could not reconnect after being kicked")

    # Register all /command handlers with the bot client
    register_all_handlers(bot)

    logger.info("Starting Music Bot…")

    # Start both clients and the calls layer
    await bot.start()
    await userbot.start()
    await calls.start()

    logger.info("Music Bot is running. Press Ctrl+C to stop.")

    try:
        # Keep the process alive
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        logger.info("Shutting down…")
        await calls.stop()
        await userbot.stop()
        await bot.stop()
        await db.disconnect()
        await spotify.close()
        logger.info("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
