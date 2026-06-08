from dataclasses import dataclass, field


@dataclass
class Track:
    """Represents a single music track ready for playback."""
    title: str
    artist: str
    duration: int          # seconds
    url: str               # streamable audio URL or file path
    thumbnail: str = ""    # album art URL
    album: str = ""
    requested_by: int = 0  # user_id who requested it
    chat_id: int = 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "url": self.url,
            "thumbnail": self.thumbnail,
            "album": self.album,
            "requested_by": self.requested_by,
            "chat_id": self.chat_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class QueueState:
    """In-memory state for one chat's playback queue."""
    chat_id: int
    tracks: list[Track] = field(default_factory=list)
    current_index: int = 0
    is_playing: bool = False
    is_paused: bool = False
    volume: int = 100
    loop: bool = False
    shuffle: bool = False

    @property
    def current_track(self) -> Track | None:
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    @property
    def next_track(self) -> Track | None:
        next_idx = self.current_index + 1
        if next_idx < len(self.tracks):
            return self.tracks[next_idx]
        return None

    def add_track(self, track: Track) -> None:
        self.tracks.append(track)

    def remove_track(self, index: int) -> Track | None:
        if 0 <= index < len(self.tracks):
            return self.tracks.pop(index)
        return None

    def advance(self) -> Track | None:
        """Move to the next track and return it, or None if queue is done."""
        if self.loop and self.tracks:
            self.current_index = (self.current_index + 1) % len(self.tracks)
        elif self.current_index + 1 < len(self.tracks):
            self.current_index += 1
        else:
            self.is_playing = False
            return None
        return self.current_track

    def shuffle_queue(self) -> None:
        import random
        current = self.current_track
        remaining = self.tracks[self.current_index + 1 :]
        random.shuffle(remaining)
        self.tracks = self.tracks[: self.current_index + 1] + remaining
