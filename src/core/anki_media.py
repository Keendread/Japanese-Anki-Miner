"""Anki media manager: copy files to Anki media directory or upload via AnkiConnect."""
import os
import shutil
import base64
from typing import Optional
from .ankiconnect import AnkiConnect


class AnkiMediaManager:
    """Interface for copying media to Anki."""

    def __init__(self, client: AnkiConnect, anki_media_path: Optional[str] = None) -> None:
        self._client = client
        self._anki_media_path = anki_media_path

    def import_image(self, source_path: str, filename: str) -> str:
        """Import an image file to Anki."""
        if self._anki_media_path and os.path.isdir(self._anki_media_path):
            dest_path = os.path.join(self._anki_media_path, filename)
            try:
                shutil.copy2(source_path, dest_path)
                return filename
            except Exception as e:
                print(f"[AnkiMedia] Could not copy image: {e}")

        # Fall back to AnkiConnect
        with open(source_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode()
        self._client.store_media_file(filename, base64_data)
        return filename

    def import_audio(self, source_path: str, filename: str) -> str:
        """Import an audio file to Anki."""
        if self._anki_media_path and os.path.isdir(self._anki_media_path):
            dest_path = os.path.join(self._anki_media_path, filename)
            try:
                shutil.copy2(source_path, dest_path)
                return filename
            except Exception as e:
                print(f"[AnkiMedia] Could not copy audio: {e}")

        # Fall back to AnkiConnect
        with open(source_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode()
        self._client.store_media_file(filename, base64_data)
        return filename