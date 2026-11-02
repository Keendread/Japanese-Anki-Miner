"""Anki integration adapter: high-level interface using inner adapters.

This module provides the legacy interface (add_card, is_already_mined, etc.)
using the new adapter modules for clean separation of concerns.

For new code, prefer directly consuming:
  - core.ankiconnect.AnkiConnect
  - core.anki_media.AnkiMediaManager
  - core.mined_words_db.MinedWordsTracker
"""
import os
import shutil
import base64
from typing import Optional, Dict, Any, Tuple, List
from src.models.card import Card
from src.models.audio import AudioFile

# Import adapters
from .ankiconnect import AnkiConnect
from .anki_media import AnkiMediaManager
from .mined_words_db import MinedWordsTracker


# Global clients (singleton instances)
_ankiconnect_client = None
_mined_tracker = None
_media_manager = None


def _get_ankiconnect_client() -> AnkiConnect:
    """Get or create the singleton AnkiConnect client."""
    global _ankiconnect_client
    if _ankiconnect_client is None:
        _ankiconnect_client = AnkiConnect()
    return _ankiconnect_client


def _get_mined_tracker() -> MinedWordsTracker:
    """Get or create the singleton mined words tracker."""
    global _mined_tracker
    if _mined_tracker is None:
        _mined_tracker = MinedWordsTracker()
    return _mined_tracker


def _get_media_manager() -> AnkiMediaManager:
    """Get or create the singleton media manager."""
    global _media_manager
    if _media_manager is None:
        _media_manager = AnkiMediaManager(client=_get_ankiconnect_client(), anki_media_path=None)
    return _media_manager


# ── Public API (backward compatibility) ─────────────────────────────────────────

def is_already_mined(
    dictionary_form: str,
    reading: str,
    surface: Optional[str] = None,
) -> bool:
    """Check if a word has already been mined."""
    return _get_mined_tracker().is_already_mined(dictionary_form, reading, surface)


def sync_mined_from_anki(rebuild: bool = False) -> bool:
    """Sync mined words from Anki on startup."""
    try:
        client = _get_ankiconnect_client()
        tracker = _get_mined_tracker()

        deck_names = client.deck_names()
        if not isinstance(deck_names, list):
            raise RuntimeError("AnkiConnect did not return valid deck names.")

        note_ids = set()
        for deck_name in deck_names:
            deck_note_ids = client.find_notes(f'deck:"{deck_name}"') or []
            note_ids.update(deck_note_ids)

        notes = []
        note_id_list = sorted(note_ids)
        for offset in range(0, len(note_id_list), 500):
            batch = client.notes_info(note_id_list[offset:offset + 500])
            if isinstance(batch, list):
                notes.extend(batch)

        mined_rows = []
        for note in notes:
            fields = note.get("fields", {})

            # Use dynamic mapping based on what's available
            expr = fields.get("Expression", {}).get("value") or \
                   fields.get("Word", {}).get("value") or \
                   fields.get("Kanji", {}).get("value") or \
                   fields.get("Name", {}).get("value") or ""

            reading = fields.get("ExpressionReading", {}).get("value") or \
                      fields.get("Reading", {}).get("value") or \
                      fields.get("Kana", {}).get("value") or \
                      fields.get("Readings", {}).get("value") or ""

            if expr:
                mined_rows.append((expr, reading, "synced", note.get("noteId")))

        tracker.save_mined_batch(mined_rows, rebuild=rebuild)
        tracker.mark_sync_complete()

        print(f"[Anki] Synced {len(mined_rows)} mined words from {len(deck_names)} decks.")
        return True
    except Exception as e:
        print(f"[Anki] Full-profile sync failed: {e}")
        return False


def record_mined(dictionary_form: str, reading: str, note_id: Optional[int]) -> None:
    """Record a mined word."""
    _get_mined_tracker().record_mined(dictionary_form, reading, note_id)


def has_completed_initial_sync() -> bool:
    """Check if initial sync completed."""
    return _get_mined_tracker().has_initial_sync_completed()


def add_card(card: Card, settings: Dict[str, Any], image_filename: Optional[str] = None) -> Tuple[bool, str, Optional[int]]:
    """Add a card to Anki using adapter composition.

    Args:
        card: Card to add.
        settings: Settings dictionary with anki_deck, anki_note_type, anki_media_path.
        image_filename: Optional path to saved card image (from user selection or download).

    Returns:
        Tuple of (success, message, note_id).
    """
    if not card.is_valid():
        return False, f"Card validation failed for '{card.source_word.surface}'", None

    deck_name: str = settings.get("anki_deck", "Test Deck")
    note_type: str = settings.get("anki_note_type", "Basic")
    anki_media_path: Optional[str] = settings.get("anki_media_path", "")

    # Convert Card to Anki field format
    fields: Dict[str, str] = card.to_anki_format()

    # Handle image - delegate to media manager
    if image_filename and note_type == "Lapis":
        # Image already saved somewhere else - use the filename from settings/media path
        pass  # Legacy path - if calling code passes image_filename, it's already in a location Anki can see
    elif note_type == "Lapis":
        capture_path: str = card.source_word.capture_path or ""
        if capture_path and os.path.exists(capture_path):
            media_filename: str = os.path.basename(capture_path)

            # Use media manager to handle copy vs upload
            media_mgr = _get_media_manager()
            try:
                fields["Picture"] = f'<img src="{media_mgr.import_image(capture_path, media_filename)}">'
            except Exception as e:
                print(f"[Anki] Could not import image: {e}")
                return False, f"Failed to import image: {e}", None

    # Ensure deck exists using AnkiConnect client
    client = _get_ankiconnect_client()
    try:
        existing_decks: list[str] = client.deck_names()
        if deck_name not in existing_decks:
            client.create_deck(deck_name)
            print(f"[Anki] Created deck '{deck_name}'.")
    except Exception as e:
        return False, f"Could not verify/create deck: {e}", None

    # Add note to Anki
    note_id: Optional[int] = None
    try:
        note_id = client.add_note({
            "deckName": deck_name,
            "modelName": note_type,
            "fields": fields,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "tags": card.tags,
        })

        # Record in local database
        record_mined(
            card.source_word.dictionary_form,
            card.source_word.reading,
            note_id
        )

        print(f"[Anki] Card added: '{card.source_word.surface}' (note ID: {note_id})")
        return True, f"Card added: {card.source_word.surface}", note_id

    except RuntimeError as e:
        error: str = str(e)
        if "duplicate" in error.lower():
            # Record locally so we catch it next time
            record_mined(
                card.source_word.dictionary_form,
                card.source_word.reading,
                None
            )
            return False, f"Duplicate in Anki: {card.source_word.surface}", None
        return False, error, None
    except Exception as e:
        return False, str(e), None


def update_card_audio(note_id: int, audio_file: AudioFile) -> None:
    """Update a note with audio files.

    Args:
        note_id: Anki note ID.
        audio_file: AudioFile containing paths to word_audio and sentence_audio.
    """
    media_mgr = AnkiMediaManager(client=_get_ankiconnect_client(), anki_media_path=None)
    fields = {}

    # Word audio
    if os.path.exists(audio_file.word_audio):
        media_filename = os.path.basename(audio_file.word_audio)
        media_mgr.import_audio(audio_file.word_audio, media_filename)
        fields["ExpressionAudio"] = f"[sound:{media_filename}]"
    else:
        print(f"[Anki] Word audio file not found: {audio_file.word_audio}")

    if audio_file.sentence_audio:
        if os.path.exists(audio_file.sentence_audio):
            media_filename = os.path.basename(audio_file.sentence_audio)
            media_mgr.import_audio(audio_file.sentence_audio, media_filename)
            fields["SentenceAudio"] = f"[sound:{media_filename}]"
        else:
            # Already uploaded elsewhere, just reference it.
            fields["SentenceAudio"] = f"[sound:{audio_file.sentence_audio}]"

    if not fields:
        print(f"[Anki] No valid audio files to update for note {note_id}.")
        return

    client = _get_ankiconnect_client()
    client.update_note_fields({"id": note_id, "fields": fields})
    print(f"[Anki] Updated note {note_id} with audio.")

    if os.path.exists(audio_file.word_audio):
        os.remove(audio_file.word_audio)
    if audio_file.sentence_audio and os.path.exists(audio_file.sentence_audio):
        os.remove(audio_file.sentence_audio)


def update_card_sentence_audio(note_id: int, audio_filename: str) -> None:
    """Attach a sentence recording that has already been uploaded to Anki."""
    if not audio_filename:
        raise ValueError("Sentence audio filename is required.")

    client = _get_ankiconnect_client()
    client.update_note_fields({
        "id": note_id,
        "fields": {"SentenceAudio": f"[sound:{audio_filename}]"},
    })
    print(f"[Anki] Updated note {note_id} with recorded sentence audio.")


# ── Internal migration helpers ─────────────────────────────────────────────────

def _ankiconnect(action: str, **params: Any) -> Any:
    """Legacy method for backwards compatibility.

    In future passes, remove this and require callers to use adapters directly.
    """
    client = _get_ankiconnect_client()
    return client._request(action, **params)


def is_anki_connect_available() -> bool:
    """Check if AnkiConnect is reachable."""
    client = _get_ankiconnect_client()
    try:
        client.version()
        return True
    except Exception:
        return False