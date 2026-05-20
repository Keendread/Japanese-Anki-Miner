# Module for Anki Integration
# Automatically create cards
# AnkiConnect API calls

import os
import json
import sqlite3
import threading
import urllib.request
import urllib.error
import base64

from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from src.models.card import Card
from src.models.audio import AudioFile

def _get_data_dir() -> str:
    core_dir: str = os.path.dirname(os.path.abspath(__file__)) # src/core/
    src_dir: str = os.path.dirname(core_dir)                   # src/
    root_dir: str = os.path.dirname(src_dir)                   # project root
    return os.path.join(root_dir, "data")

MINED_DB_PATH: str = os.path.join(_get_data_dir(), "mined.db")
ANKICONNECT_URL: str = "http://localhost:8765"
ANKICONNECT_VER: int = 6

_mined_conn: Optional[sqlite3.Connection] = None
_mined_conn_lock: threading.Lock = threading.Lock()

_MINED_SCHEMA = """
CREATE TABLE IF NOT EXISTS mined_words (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dictionary_form TEXT NOT NULL,
    reading         TEXT NOT NULL,
    mined_at        TEXT NOT NULL,
    anki_note_id    INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mined_word
    ON mined_words(dictionary_form, reading);
"""

def _get_mined_conn() -> sqlite3.Connection:
    print(f"[Anki] Mined DB path: {MINED_DB_PATH}")
    global _mined_conn
    with _mined_conn_lock:
        if _mined_conn is None:
            db_path = MINED_DB_PATH
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            _mined_conn = sqlite3.connect(db_path, check_same_thread=False)
            _mined_conn.row_factory = sqlite3.Row
            _mined_conn.executescript(_MINED_SCHEMA)
            _mined_conn.commit()
            print("[Anki] Mined words database ready.")
    return _mined_conn

def is_already_mined(dictionary_form: str, reading: str) -> bool:
    """
    Returns True if the word has already been mined.
    Checks local mined.db - much faster than querying AnkiConnect.

    Args:
        dictionary_form (str): base form of the word
        reading (str):         hiragana reading
    """
    try:
        conn = _get_mined_conn()
        with _mined_conn_lock:
            row = conn.execute(
                "SELECT id FROM mined_words WHERE dictionary_form=? AND reading=?",
                (dictionary_form, reading)
            ).fetchone()
        return row is not None
    except Exception as e:
        print(f"[Anki] Mined check failed: {e}")
        return False
    
def _record_mined(dictionary_form: str, reading: str, note_id: Optional[int]) -> None:
    """Records the word as mined in the local DB."""
    try:
        conn = _get_mined_conn()
        with _mined_conn_lock:
            conn.execute(
                """INSERT OR IGNORE INTO mined_words
                   (dictionary_form, reading, mined_at, anki_note_id)
                   VALUES (?,?,?,?)""",
                (
                    dictionary_form,
                    reading,
                    datetime.now().isoformat(),
                    note_id,
                )
            )
            conn.commit()
    except Exception as e:
        print(f"[Anki] Failed to record mined word: {e}")
        
def sync_mined_from_anki(deck_name: str) -> None:
    """
    Pulls existing note expressions from AnkiConnect and records them
    in mined.db so duplicates are detected even for cards made by Yomitan.
    Called once at startup (non-fatal if Anki is not open).

    Args:
        deck_name (str): Anki deck name to sync from
    """
    try:
        note_ids = _ankiconnect("findNotes", query=f'deck:"{deck_name}"')
        if not note_ids:
            return
        
        notes = _ankiconnect("notesInfo", notes=note_ids)
        conn = _get_mined_conn()

        with _mined_conn_lock:
            for note in notes:
                fields = note.get("fields", {})
                expr = fields.get("Expression", {}).get("value", "")
                reading = fields.get("ExpressionReading", {}).get("value", "")
                if expr:
                    conn.execute(
                        """INSERT OR IGNORE INTO mined_words
                           (dictionary_form, reading, mined_at, anki_note_id)
                           VALUES (?,?,?,?)""",
                        (expr, reading, "synced", note.get("noteId"))
                    )
            conn.commit()

        print(f"[Anki] Synced {len(notes)} existing cards from '{deck_name}'.")
    except Exception as e:
        print(f"[Anki] Sync skipped (Anki may not be open): {e}")
        

def _ankiconnect(action: str, **params: Any) -> Any:
    """
    Sends a request to AnkiConnect and returns the result.
    Raises RuntimeError on failure.

    Args:
        action (str): AnkiConnect action string
        **params:     action parameters
    """
    payload = json.dumps({
        "action":  action,
        "version": ANKICONNECT_VER,
        "params":  params,
    }).encode("utf-8")

    req = urllib.request.Request(
        ANKICONNECT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ankiconnect not reachable. Is Anki open? ({e})"
        )
        
    if data.get("error"):
        raise RuntimeError(f"Ankiconnect error: {data['error']}")

    return data.get("result")

def is_anki_connect_available() -> bool:
    """Quick check whether AnkiConnect is reachable."""
    try:
        _ankiconnect("version")
        return True
    except Exception:
        return False
    



def add_card(card: Card, settings: Dict[str, Any], image_filename: Optional[str] = None) -> Tuple[bool, str, Optional[int]]:
    """
    Creates an Anki card from a Card object.
    Records the word in mined.db on success.

    Args:
        card: Card object with formatted content ready for Anki
        settings: Settings dictionary with anki_deck, anki_note_type, etc.
        image_filename: Optional media filename for downloaded/selected image

    Returns:
        Tuple of (success: bool, message: str, note_id: Optional[int])
    """
    if not card.is_valid():
        return False, f"Card validation failed for '{card.source_word.surface}'", None
    
    deck_name: str = settings.get("anki_deck", "Test Deck")
    note_type: str = settings.get("anki_note_type", "Basic")
    
    # Convert Card to Anki field format
    fields: Dict[str, str] = card.to_anki_format()
    
    # Handle image if provided (from user selection or download) - PRIORITY 1
    if image_filename and note_type == "Lapis":
        fields["Picture"] = f'<img src="{image_filename}">'
    # Handle capture image only if no fetched image was provided - PRIORITY 2
    elif note_type == "Lapis":
        capture_path: str = card.source_word.capture_path or ""
        if capture_path and os.path.exists(capture_path):
            media_filename: str = os.path.basename(capture_path)
            anki_media: str = settings.get("anki_media_path", "")
            
            if anki_media:
                try:
                    import shutil
                    dest: str = os.path.join(anki_media, media_filename)
                    shutil.copy2(capture_path, dest)
                    fields["Picture"] = f'<img src="{media_filename}">'
                except Exception as e:
                    print(f"[Anki] Could not copy capture image: {e}")
            else:
                # Use AnkiConnect storeMediaFile as fallback
                try:
                    with open(capture_path, "rb") as f:
                        import base64
                        data: str = base64.b64encode(f.read()).decode()
                    _ankiconnect(
                        "storeMediaFile",
                        filename=media_filename,
                        data=data
                    )
                    fields["Picture"] = f'<img src="{media_filename}">'
                except Exception as e:
                    print(f"[Anki] Could not store capture image via AnkiConnect: {e}")
    
    # Ensure deck exists
    try:
        existing_decks: List[str] = _ankiconnect("deckNames")
        if deck_name not in existing_decks:
            _ankiconnect("createDeck", deck=deck_name)
            print(f"[Anki] Created deck '{deck_name}'.")
    except Exception as e:
        return False, f"Could not verify/create deck: {e}", None
    
    # Add note to Anki
    try:
        note_id: Optional[int] = _ankiconnect(
            "addNote",
            note={
                "deckName": deck_name,
                "modelName": note_type,
                "fields": fields,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                },
                "tags": card.tags,
            }
        )
        
        # Record in local database
        _record_mined(
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
            _record_mined(
                card.source_word.dictionary_form,
                card.source_word.reading,
                None
            )
            return False, f"Duplicate in Anki: {card.source_word.surface}", None
        return False, error, None
    except Exception as e:
        return False, str(e), None
    
def update_card_audio(note_id: int, audio_file: AudioFile) -> None:
    """
    Updates an existing Anki note with audio after the fact.
    Called asynchronously after card creation since audio may take time.

    Args:
        note_id: Anki note ID to update
        audio_file: AudioFile object with paths to word and sentence audio
    """
    try:
        fields = {}

        # Word audio
        if os.path.exists(audio_file.word_audio):
            with open(audio_file.word_audio, "rb") as f:
                data = base64.b64encode(f.read()).decode()

            media_filename = os.path.basename(audio_file.word_audio)
            _ankiconnect("storeMediaFile", filename=media_filename, data=data)
            fields["ExpressionAudio"] = f"[sound:{media_filename}]"
        else:
            print(f"[Anki] Word audio file not found: {audio_file.word_audio}")

        # Sentence audio (optional)
        if audio_file.sentence_audio and os.path.exists(audio_file.sentence_audio):
            with open(audio_file.sentence_audio, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            media_filename = os.path.basename(audio_file.sentence_audio)
            _ankiconnect("storeMediaFile", filename=media_filename, data=data)
            fields["SentenceAudio"] = f"[sound:{media_filename}]"

        if not fields:
            print(f"[Anki] No valid audio files to update for note {note_id}.")
            return

        _ankiconnect("updateNoteFields", note={"id": note_id, "fields": fields})
        print(f"[Anki] Updated note {note_id} with audio.")

        # Remove after saving to Anki to avoid cluttering local storage. Anki manages its own media folder.
        if (os.path.exists(audio_file.word_audio)):
            os.remove(audio_file.word_audio)
        if (audio_file.sentence_audio and os.path.exists(audio_file.sentence_audio)):
            os.remove(audio_file.sentence_audio)

    except Exception as e:
        print(f"[Anki] Failed to update note with audio: {e}")