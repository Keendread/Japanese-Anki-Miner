import os
import json
import sqlite3
import threading
import urllib.request
import urllib.error
import base64
from contextlib import closing

from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from src.models.card import Card
from src.models.audio import AudioFile

def _get_data_dir() -> str:
    core_dir: str = os.path.dirname(os.path.abspath(__file__)) # src/core/
    src_dir: str = os.path.dirname(core_dir)                   # src/
    root_dir: str = os.path.dirname(src_dir)                   # project root
    return os.path.join(root_dir, "data")

MINED_DB_PATH: str = os.path.join(_get_data_dir(), "mined_words.db")
_LEGACY_MINED_DB_PATH: str = os.path.join(_get_data_dir(), "mined.db")
ANKICONNECT_URL: str = "http://localhost:8765"
ANKICONNECT_VER: int = 6

_mined_conn: Optional[sqlite3.Connection] = None
_mined_conn_lock: threading.Lock = threading.Lock()
_anki_sync_lock: threading.Lock = threading.Lock()

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
CREATE TABLE IF NOT EXISTS mined_sync_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
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
            if os.path.isfile(_LEGACY_MINED_DB_PATH):
                with closing(sqlite3.connect(_LEGACY_MINED_DB_PATH)) as legacy_conn:
                    legacy_table = legacy_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mined_words'"
                    ).fetchone()
                    if legacy_table:
                        legacy_rows = legacy_conn.execute(
                            """SELECT dictionary_form, reading, mined_at, anki_note_id
                               FROM mined_words"""
                        ).fetchall()
                        _mined_conn.executemany(
                            """INSERT OR IGNORE INTO mined_words
                               (dictionary_form, reading, mined_at, anki_note_id)
                               VALUES (?, ?, ?, ?)""",
                            legacy_rows,
                        )
            _mined_conn.commit()
            print("[Anki] Mined words database ready.")
    return _mined_conn

def is_already_mined(dictionary_form: str, reading: str) -> bool:
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
        
def has_completed_initial_sync() -> bool:
    conn = _get_mined_conn()
    with _mined_conn_lock:
        row = conn.execute(
            "SELECT value FROM mined_sync_metadata WHERE key='initial_sync_complete'"
        ).fetchone()
    return row is not None and row["value"] == "1"

def sync_mined_from_anki(rebuild: bool = False) -> bool:
    try:
        with _anki_sync_lock:
            conn = _get_mined_conn()
            deck_names = _ankiconnect("deckNames")
            if not isinstance(deck_names, list) or not all(
                isinstance(name, str) for name in deck_names
            ):
                raise RuntimeError("AnkiConnect did not return valid deck names.")

            note_ids = set()
            for deck_name in deck_names:
                deck_note_ids = _ankiconnect(
                    "findNotes",
                    query=f'deck:"{deck_name}"'
                ) or []
                if not isinstance(deck_note_ids, list):
                    raise RuntimeError(
                        f"AnkiConnect returned invalid note IDs for '{deck_name}'."
                    )
                note_ids.update(deck_note_ids)

            notes = []
            note_id_list = sorted(note_ids)
            for offset in range(0, len(note_id_list), 500):
                batch = _ankiconnect(
                    "notesInfo",
                    notes=note_id_list[offset:offset + 500]
                )
                if not isinstance(batch, list):
                    raise RuntimeError("AnkiConnect returned invalid note information.")
                notes.extend(batch)

            mined_rows = []
            for note in notes:
                fields = note.get("fields", {})
                expr = fields.get("Expression", {}).get("value", "")
                reading = fields.get("ExpressionReading", {}).get("value", "")
                if expr:
                    mined_rows.append(
                        (expr, reading, "synced", note.get("noteId"))
                    )

            with _mined_conn_lock:
                if rebuild:
                    conn.execute(
                        "DELETE FROM mined_words"
                    )
                conn.executemany(
                    """INSERT OR IGNORE INTO mined_words
                       (dictionary_form, reading, mined_at, anki_note_id)
                       VALUES (?, ?, ?, ?)""",
                    mined_rows,
                )
                conn.execute(
                    """INSERT OR REPLACE INTO mined_sync_metadata (key, value)
                       VALUES ('initial_sync_complete', '1')"""
                )
                conn.commit()

        print(
            f"[Anki] Synced {len(mined_rows)} mined words from "
            f"{len(deck_names)} decks."
        )
        return True
    except Exception as e:
        print(f"[Anki] Full-profile sync failed (Anki may not be open): {e}")
        return False
        

def _ankiconnect(action: str, **params: Any) -> Any:
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
    try:
        _ankiconnect("version")
        return True
    except Exception:
        return False
    



def add_card(card: Card, settings: Dict[str, Any], image_filename: Optional[str] = None) -> Tuple[bool, str, Optional[int]]:
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

        if audio_file.sentence_audio:
            if os.path.exists(audio_file.sentence_audio):
                with open(audio_file.sentence_audio, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                media_filename = os.path.basename(audio_file.sentence_audio)
                _ankiconnect("storeMediaFile", filename=media_filename, data=data)
                fields["SentenceAudio"] = f"[sound:{media_filename}]"
            else:
                # Already uploaded elsewhere, just reference it.
                fields["SentenceAudio"] = f"[sound:{audio_file.sentence_audio}]"

        if not fields:
            print(f"[Anki] No valid audio files to update for note {note_id}.")
            return

        _ankiconnect("updateNoteFields", note={"id": note_id, "fields": fields})
        print(f"[Anki] Updated note {note_id} with audio.")

        if (os.path.exists(audio_file.word_audio)):
            os.remove(audio_file.word_audio)
        if (audio_file.sentence_audio and os.path.exists(audio_file.sentence_audio)):
            os.remove(audio_file.sentence_audio)

    except Exception as e:
        print(f"[Anki] Failed to update note with audio: {e}")