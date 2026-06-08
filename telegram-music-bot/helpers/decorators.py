import logging
import time
from functools import wraps
from collections import defaultdict

from pyrogram import Client
from pyrogram.types import Message

logger = logging.getLogger(__name__)

# Simple in-memory rate-limit store: {user_id: last_command_time}
_rate_store: dict[int, float] = defaultdict(float)


def admin_only(func):
    """Allow command only for group admins or bot ADMIN_IDS."""
    @wraps(func)
    async def wrapper(client: Client, message: Message):
        from config import settings

        user_id = message.from_user.id if message.from_user else 0

        # Always allow global admins
        if user_id in settings.ADMIN_IDS:
            return await func(client, message)

        # Check Telegram chat admin status
        try:
            member = await client.get_chat_member(message.chat.id, user_id)
            is_admin = member.status.name in ("OWNER", "ADMINISTRATOR")
        except Exception:
            is_admin = False

        if not is_admin:
            await message.reply("⛔ This command is for group admins only.")
            return

        return await func(client, message)

    return wrapper


def rate_limit(seconds: float = 2.0):
    """Prevent a user from spamming the same command faster than `seconds`."""
    def decorator(func):
        @wraps(func)
        async def wrapper(client: Client, message: Message):
            user_id = message.from_user.id if message.from_user else 0
            now = time.monotonic()
            if now - _rate_store[user_id] < seconds:
                await message.reply(
                    f"⏳ Slow down! Please wait {seconds:.0f}s between commands."
                )
                return
            _rate_store[user_id] = now
            return await func(client, message)
        return wrapper
    return decorator


def error_handler(func):
    """Catch unhandled exceptions in handlers and reply with a user-friendly message."""
    @wraps(func)
    async def wrapper(client: Client, message: Message):
        try:
            return await func(client, message)
        except Exception as exc:
            logger.exception(f"Error in {func.__name__}: {exc}")
            await message.reply(
                "❌ An unexpected error occurred. Please try again later."
            )
    return wrapper
