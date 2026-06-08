from database.models import Track


def format_duration(seconds: int) -> str:
    """Convert seconds to MM:SS or HH:MM:SS."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_track_info(track: Track, index: int | None = None) -> str:
    """Produce a one-line track summary for lists."""
    prefix = f"{index}. " if index is not None else ""
    duration = format_duration(track.duration)
    return f"{prefix}**{track.title}** — {track.artist} `[{duration}]`"


def format_queue(tracks: list[Track], current_index: int = 0, page: int = 1, page_size: int = 10) -> str:
    """Build a paginated queue display string."""
    if not tracks:
        return "📭 The queue is empty."

    total = len(tracks)
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    lines = [f"🎵 **Queue** — {total} track{'s' if total != 1 else ''}\n"]

    for i, track in enumerate(tracks[start:end], start=start):
        marker = "▶️ " if i == current_index else f"{i + 1}. "
        lines.append(f"{marker}**{track.title}** — {track.artist} `[{format_duration(track.duration)}]`")

    if total > end:
        lines.append(f"\n…and {total - end} more tracks (page {page})")

    return "\n".join(lines)


def format_now_playing(track: Track, elapsed: int = 0) -> str:
    """Build the now-playing message."""
    bar_length = 20
    if track.duration > 0:
        filled = int(bar_length * elapsed / track.duration)
    else:
        filled = 0
    bar = "▓" * filled + "░" * (bar_length - filled)

    lines = [
        "🎵 **Now Playing**",
        f"**{track.title}**",
        f"👤 {track.artist}",
    ]
    if track.album:
        lines.append(f"💿 {track.album}")
    lines += [
        f"`{format_duration(elapsed)} {bar} {format_duration(track.duration)}`",
    ]
    return "\n".join(lines)
