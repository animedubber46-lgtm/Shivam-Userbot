import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self._client: AsyncIOMotorClient | None = None
        self._db = None

    async def connect(self, uri: str, db_name: str) -> None:
        """Connect to MongoDB."""
        try:
            self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            # Verify connection
            await self._client.admin.command("ping")
            self._db = self._client[db_name]
            logger.info("Connected to MongoDB successfully")
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            logger.info("Disconnected from MongoDB")

    # ── Queue operations ──────────────────────────────────────────────────────

    async def get_queue(self, chat_id: int) -> list[dict]:
        """Return the full queue for a chat."""
        doc = await self._db.queues.find_one({"chat_id": chat_id})
        return doc.get("tracks", []) if doc else []

    async def set_queue(self, chat_id: int, tracks: list[dict]) -> None:
        """Persist the entire queue for a chat."""
        await self._db.queues.update_one(
            {"chat_id": chat_id},
            {"$set": {"tracks": tracks}},
            upsert=True,
        )

    async def clear_queue(self, chat_id: int) -> None:
        """Remove all queued tracks for a chat."""
        await self._db.queues.delete_one({"chat_id": chat_id})

    # ── Group settings ────────────────────────────────────────────────────────

    async def get_settings(self, chat_id: int) -> dict:
        """Return settings for a chat, with defaults."""
        doc = await self._db.settings.find_one({"chat_id": chat_id})
        defaults = {"volume": 100, "loop": False, "shuffle": False}
        if doc:
            doc.pop("_id", None)
            return {**defaults, **doc}
        return {"chat_id": chat_id, **defaults}

    async def update_settings(self, chat_id: int, **kwargs) -> None:
        """Update one or more settings for a chat."""
        await self._db.settings.update_one(
            {"chat_id": chat_id},
            {"$set": kwargs},
            upsert=True,
        )

    # ── Playlists ─────────────────────────────────────────────────────────────

    async def save_playlist(self, user_id: int, name: str, tracks: list[dict]) -> None:
        """Save or overwrite a named playlist for a user."""
        await self._db.playlists.update_one(
            {"user_id": user_id, "name": name},
            {"$set": {"tracks": tracks, "count": len(tracks)}},
            upsert=True,
        )

    async def get_playlist(self, user_id: int, name: str) -> list[dict]:
        """Retrieve a named playlist for a user."""
        doc = await self._db.playlists.find_one({"user_id": user_id, "name": name})
        return doc.get("tracks", []) if doc else []

    async def list_playlists(self, user_id: int) -> list[dict]:
        """List all playlists owned by a user."""
        cursor = self._db.playlists.find(
            {"user_id": user_id},
            {"name": 1, "count": 1, "_id": 0},
        )
        return await cursor.to_list(length=100)

    async def delete_playlist(self, user_id: int, name: str) -> bool:
        """Delete a named playlist. Returns True if it existed."""
        result = await self._db.playlists.delete_one({"user_id": user_id, "name": name})
        return result.deleted_count > 0

    # ── Statistics ────────────────────────────────────────────────────────────

    async def record_play(self, chat_id: int, track: dict) -> None:
        """Increment play count for a track and update global stats."""
        await self._db.stats.update_one(
            {"chat_id": chat_id},
            {
                "$inc": {"total_plays": 1},
                "$push": {
                    "history": {
                        "$each": [{"title": track.get("title"), "artist": track.get("artist")}],
                        "$slice": -50,  # keep last 50 entries
                    }
                },
            },
            upsert=True,
        )

    async def get_stats(self, chat_id: int) -> dict:
        """Return play statistics for a chat."""
        doc = await self._db.stats.find_one({"chat_id": chat_id})
        if doc:
            doc.pop("_id", None)
        return doc or {"chat_id": chat_id, "total_plays": 0, "history": []}
