"""AnkiConnect adapter: HTTP client for Anki remote API."""
import json
import urllib.request
import urllib.error
import base64
from typing import Optional, Dict, Any, List


class AnkiConnect:
    """Interface to AnkiConnect REST API.

    Constructor config:
        - url: AnkiConnect service URL (default 'http://localhost:8765')
        - timeout: HTTP timeout in seconds (default 10)
        - retry_count: Number of retry attempts on failure (default 0)
        - retry_delay: Delay between retries in seconds (default 0.5)
    """

    def __init__(
        self,
        url: str = "http://localhost:8765",
        timeout: int = 10,
        retry_count: int = 0,
        retry_delay: float = 0.5,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._retry_count = retry_count
        self._retry_delay = retry_delay

    def _request(self, action: str, **params: Any) -> Any:
        """Send request to AnkiConnect and return result.

        Raises:
            RuntimeError: On HTTP error or AnkiConnect error.
        """
        payload = json.dumps({
            "action": action,
            "version": 6,
            "params": params,
        }).encode("utf-8")

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ankiconnect not reachable. Is Anki open? ({e})"
            )

        if data.get("error"):
            raise RuntimeError(f"Ankiconnect error: {data['error']}")

        return data.get("result")

    # ── Query operations ────────────────────────────────────────────────────────

    def version(self) -> Dict[str, Any]:
        """Query AnkiConnect version information."""
        return self._request("version")

    def deck_names(self) -> List[str]:
        """List all deck names from Anki."""
        return self._request("deckNames")

    def find_notes(self, query: str) -> List[int]:
        """Find note IDs matching an Anki search query."""
        return self._request("findNotes", query=query)

    def notes_info(self, notes: List[int]) -> List[Dict[str, Any]]:
        """Get detailed information for multiple notes."""
        return self._request("notesInfo", notes=notes)

    # ── Mutation operations ─────────────────────────────────────────────────────

    def create_deck(self, deck: str) -> None:
        """Create a new deck if it doesn't exist."""
        self._request("createDeck", deck=deck)

    def add_note(self, note: Dict[str, Any]) -> Optional[int]:
        """Create a new note in Anki.

        Returns:
            noteId: The ID of the created note, or None if failed.
        """
        return self._request("addNote", note=note)

    def update_note_fields(self, note: Dict[str, Any]) -> None:
        """Update fields of an existing note."""
        self._request("updateNoteFields", note=note)

    def store_media_file(self, filename: str, base64_data) -> None:
        """Store a media file in Anki's media directory.

        Args:
            filename: Media filename (without path).
            base64_Base64-encoded media data.
        """
        self._request("storeMediaFile", filename=filename, data=base64_data)