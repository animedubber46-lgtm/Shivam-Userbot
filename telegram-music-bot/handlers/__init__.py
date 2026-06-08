from handlers.play import register_play_handlers
from handlers.controls import register_control_handlers
from handlers.queue import register_queue_handlers
from handlers.playlist import register_playlist_handlers
from handlers.help import register_help_handlers
from handlers.video import register_video_handlers


def register_all_handlers(bot) -> None:
    """Register all command handlers with the bot client."""
    register_play_handlers(bot)
    register_video_handlers(bot)
    register_control_handlers(bot)
    register_queue_handlers(bot)
    register_playlist_handlers(bot)
    register_help_handlers(bot)
