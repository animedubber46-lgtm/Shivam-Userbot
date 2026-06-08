import logging
import base64
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SpotifyService:
    def __init__(self):
        self._token: str = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def authenticate(self, client_id: str, client_secret: str) -> None:
        """Fetch a client-credentials token from Spotify."""
        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        session = await self._get_session()
        async with session.post(SPOTIFY_TOKEN_URL, headers=headers, data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Spotify auth failed ({resp.status}): {text}")
            body = await resp.json()
            self._token = body["access_token"]
            logger.info("Spotify authenticated successfully")

    async def _api_get(self, endpoint: str, params: dict | None = None) -> dict:
        """Authenticated GET to the Spotify API, with one auto-retry on 401."""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"{SPOTIFY_API_BASE}/{endpoint}"

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 401:
                # Token expired — caller should re-auth
                raise PermissionError("Spotify token expired")
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Spotify API error ({resp.status}): {text}")
            return await resp.json()

    async def search_track(self, query: str) -> Optional[dict]:
        """
        Search for a single track. Returns a normalised track dict or None.
        """
        data = await self._api_get("search", {"q": query, "type": "track", "limit": 1})
        items = data.get("tracks", {}).get("items", [])
        if not items:
            return None
        return self._normalise_track(items[0])

    async def get_track(self, track_id: str) -> Optional[dict]:
        """Fetch a track by its Spotify ID."""
        data = await self._api_get(f"tracks/{track_id}")
        return self._normalise_track(data)

    async def get_playlist_tracks(self, playlist_id: str) -> list[dict]:
        """Fetch all tracks from a Spotify playlist."""
        tracks = []
        endpoint = f"playlists/{playlist_id}/tracks"
        params: dict = {"limit": 100, "offset": 0}

        while True:
            data = await self._api_get(endpoint, params)
            items = data.get("items", [])
            for item in items:
                track = item.get("track")
                if track and track.get("id"):
                    tracks.append(self._normalise_track(track))
            if data.get("next") is None:
                break
            params["offset"] += 100

        return tracks

    async def get_album_tracks(self, album_id: str) -> list[dict]:
        """Fetch all tracks from a Spotify album."""
        album_data = await self._api_get(f"albums/{album_id}")
        album_name = album_data.get("name", "")
        thumbnail = ""
        images = album_data.get("images", [])
        if images:
            thumbnail = images[0].get("url", "")

        tracks = []
        items = album_data.get("tracks", {}).get("items", [])
        for item in items:
            tracks.append({
                "title": item.get("name", "Unknown"),
                "artist": ", ".join(a["name"] for a in item.get("artists", [])),
                "duration": item.get("duration_ms", 0) // 1000,
                "album": album_name,
                "thumbnail": thumbnail,
                "spotify_id": item.get("id", ""),
            })
        return tracks

    @staticmethod
    def _normalise_track(raw: dict) -> dict:
        """Convert a raw Spotify track object to our internal format."""
        artists = ", ".join(a["name"] for a in raw.get("artists", []))
        album = raw.get("album", {})
        images = album.get("images", [])
        thumbnail = images[0]["url"] if images else ""
        return {
            "title": raw.get("name", "Unknown"),
            "artist": artists,
            "duration": raw.get("duration_ms", 0) // 1000,
            "album": album.get("name", ""),
            "thumbnail": thumbnail,
            "spotify_id": raw.get("id", ""),
        }

    @staticmethod
    def parse_spotify_url(url: str) -> tuple[str, str] | None:
        """
        Parse a Spotify URL into (type, id).
        Supported types: track, playlist, album
        Returns None if not a recognised Spotify URL.
        """
        import re
        pattern = r"spotify\.com/(track|playlist|album)/([A-Za-z0-9]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
        return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
