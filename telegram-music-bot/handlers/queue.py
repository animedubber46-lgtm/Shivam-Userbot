import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from helpers.decorators import error_handler, rate_limit
from helpers.formatters import format_queue

logger = logging.getLogger(__name__)


def register_queue_handlers(app: Client) -> None:

    @app.on_message(filters.command("queue") & filters.group & filters.incoming)
    @rate_limit(seconds=5)
    @error_handler
    async def queue_cmd(client: Client, message: Message):
        from voice import voice_manager
        args = message.command[1:]
        page = 1
        if args and args[0].isdigit():
            page = max(1, int(args[0]))

        state = voice_manager.get_state(message.chat.id)
        text = format_queue(state.tracks, state.current_index, page=page)
        await message.reply(text)
