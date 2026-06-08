"""
Music Userbot — Entry Point
============================
Your own Telegram account (STRING_SESSION) connects, listens for commands
in groups, and streams music through voice chats. No BOT_TOKEN needed.
"""
import asyncio
import logging
import sys

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import StreamEnded, ChatUpdate, Update

from config import settings
from database import db
from handlers import register_all_handlers
from services import spotify
from voice import voice_manager

# ── Logging ───────────────────────────────────────────────────────────────────
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
    settings.validate()

    await db.connect(settings.MONGO_URI, settings.DB_NAME)
    await spotify.authenticate(settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET)

    # Your Telegram account
    userbot = Client(
        name="music_userbot",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        session_string=settings.STRING_SESSION,
    )

    # PyTgCalls wraps the same account for voice streaming
    calls = PyTgCalls(userbot)
    voice_manager.set_client(calls)

    # ── Single update handler for all PyTgCalls events ────────────────────────
    @calls.on_update()
    async def update_handler(client: PyTgCalls, update: Update):
        # Track finished — advance queue
        if isinstance(update, StreamEnded):
            await voice_manager.on_stream_end(update.chat_id)
            return

        # Kicked / voice chat closed — attempt reconnect
        if isinstance(update, ChatUpdate):
            disconnect_flags = (
                ChatUpdate.Status.KICKED
                | ChatUpdate.Status.LEFT_GROUP
                | ChatUpdate.Status.CLOSED_VOICE_CHAT
                | ChatUpdate.Status.DISCARDED_CALL
            )
            if update.status & disconnect_flags:
                await voice_manager.on_kicked(update.chat_id)
                await asyncio.sleep(5)
                if not await voice_manager.try_reconnect(update.chat_id):
                    logger.warning(f"[{update.chat_id}] Could not reconnect")

    # Register /play, /pause, /skip, etc. on the userbot
    register_all_handlers(userbot)

    logger.info("Starting Music Userbot…")
    await userbot.start()
    await calls.start()

    me = await userbot.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username or me.id})")
    logger.info(f"Admin IDs: {settings.ADMIN_IDS}")
    logger.info("Ready. Press Ctrl+C to stop.")

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
