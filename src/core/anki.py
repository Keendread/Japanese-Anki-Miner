# Module for Anki Integration
# Automatically create cards
# AnkiConnect API calls

import os
import json
import sqlite3
import threading
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from src.models.word import Word

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
    

def _build_glossary_html(glossary: List[Dict[str, Any]]) -> str:
    """
    Builds HTML glossary from sense dictionaries.
    Format matches Lapis's expected <ol> structure.

    Args:
        glossary: List of sense dictionaries from dictionary.py

    Returns:
        HTML string representing the glossary
    """
    if not glossary:
        return ""

    items: List[Any] = []
    for sense in glossary:
        pos = sense.get("pos", "")
        gloss = sense.get("gloss", "")
        domain = sense.get("domain", "")
 
        pos_tag = ""
        if pos:
            # Take first POS tag only for display
            first_pos = pos.split(",")[0].strip()
            pos_tag = (
                f'<span style="font-weight:bold;font-size:0.8em;'
                f'color:white;background-color:#565656;'
                f'border-radius:0.3em;padding:0.2em 0.3em;'
                f'margin-right:0.25em;">{first_pos}</span>'
            )
 
        domain_tag = ""
        if domain:
            domain_tag = (
                f'<span style="font-size:0.8em;color:#888;'
                f'margin-right:0.25em;">[{domain}]</span>'
            )
 
        items.append(f"<li>{pos_tag}{domain_tag}{gloss}</li>")
 
    return f'<div class="jam-glossary"><ol>{"".join(items)}</ol></div>'

def _build_sentence_cloze(sentence: str, surface: str) -> str:
    """
    Wraps the targeet word in the sentence <b> tags for cloze format.
    Lapis Sentence field format: prefix<b>word</b>suffix

    Args:
        sentence (str): full OCR sentence
        surface (str):  target word surface form
    """
    if surface and surface in sentence:
        return sentence.replace(surface, f"<b>{surface}</b>", 1)
    return sentence

def _build_furigana_expression(surface: str, reading: str) -> str:
    """
    Builds ExpressionFurigana in Lapis format: word[reading]
    Only adds furgina if surface contains kanji

    Args:
        surface (str): word as it appears in text
        reading (str): hiragana reading
    """
    import re
    kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    if kanji_re.search(surface) and reading and reading != surface:
        return f"{surface}[{reading}]"
    return surface


def add_card(payload: Word, settings: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    """
    Creates an Anki card from a Word object.
    Records the word in mined.db on success.

    Args:
        payload: Word object with all enriched word data
        settings: Settings dictionary with anki_deck, anki_note_type, etc.

    Returns:
        Tuple of (success: bool, message: str, note_id: Optional[int])
    """
    dictionary_form = payload.dictionary_form
    reading         = payload.reading
    surface         = payload.surface
    sentence        = payload.full_sentence or ""
    sentence_furi   = payload.sentence_furigana or ""
    main_def        = payload.meaning or ""
    glossary        = payload.glossary or []
    pitch_pattern   = payload.pitch_pattern or ""
    pitch_category  = payload.pitch_category or ""
    frequency_rank  = payload.frequency_rank or None
    jlpt_level      = payload.jlpt_level or None # type: ignore
    capture_path    = payload.capture_path or ""
    audio_path      = payload.audio or "" # type: ignore
    image_path      = payload.capture_path or "" # type: ignore
 
    deck_name  = settings.get("anki_deck", "Test Deck")
    note_type  = settings.get("anki_note_type", "Lapis")
    misc_info  = settings.get("anki_misc_info", "JAM")
    
    # Build Fields
    glossary_html    = _build_glossary_html(glossary)
    sentence_cloze   = _build_sentence_cloze(sentence, surface)
    expr_furigana    = _build_furigana_expression(surface, reading)
    freq_display     = str(frequency_rank) if frequency_rank else ""
    freq_sort        = str(frequency_rank) if frequency_rank else ""
 
    fields: Dict[str, Any] = {
        "Expression":        surface,
        "ExpressionFurigana": expr_furigana,
        "ExpressionReading": reading,
        "MainDefinition":    main_def,
        "Glossary":          glossary_html,
        "Sentence":          sentence_cloze,
        "SentenceFurigana":  sentence_furi,
        "PitchPosition":     pitch_pattern,
        "PitchCategories":   pitch_category,
        "Frequency":         freq_display,
        "FreqSort":          freq_sort,
        "MiscInfo":          misc_info,
        # Audio and image left empty for now — filled in by future modules
        "ExpressionAudio":   "",
        "SentenceAudio":     "",
        "Picture":           "",
        "DefinitionPicture": "",
        "SelectionText":     surface,
    }
    
    # Add capture screenshot as Picture if available
    if capture_path and os.path.exists(capture_path):
        media_filename = os.path.basename(capture_path)
        anki_media     = settings.get("anki_media_path", "")
        if anki_media:
            try:
                import shutil
                dest = os.path.join(anki_media, media_filename)
                shutil.copy2(capture_path, dest)
                fields["Picture"] = f'<img src="{media_filename}">'
            except Exception as e:
                print(f"[Anki] Could not copy capture image: {e}")
        else:
            # Use AnkiConnect storeMediaFile as fallback
            try:
                with open(capture_path, "rb") as f:
                    import base64
                    data = base64.b64encode(f.read()).decode()
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
        existing_decks = _ankiconnect("deckNames")
        if deck_name not in existing_decks:
            _ankiconnect("createDeck", deck=deck_name)
            print(f"[Anki] Created deck '{deck_name}'.")
    except Exception as e:
        return False, f"Could not verify/create deck: {e}", None
 
    # Add note
    try:
        note_id = _ankiconnect(
            "addNote",
            note={
                "deckName":  deck_name,
                "modelName": note_type,
                "fields":    fields,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                },
                "tags": ["JAM"],
            }
        )
 
        _record_mined(dictionary_form, reading, note_id)
        print(f"[Anki] Card added: '{surface}' (note ID: {note_id})")
        return True, f"Card added: {surface}", note_id
 
    except RuntimeError as e:
        error = str(e)
        if "duplicate" in error.lower():
            # Also record locally so we catch it next time without hitting Anki
            _record_mined(dictionary_form, reading, None)
            return False, f"Duplicate in Anki: {surface}", None
        return False, error, None
    except Exception as e:
        return False, str(e), None