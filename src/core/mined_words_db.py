"""Mined words database adapter: track mined words locally with SQLite."""
import os
import threading
from datetime import datetime
from typing import Optional, Any, List, Tuple
import sqlite3
import unicodedata

import joyokanji


_IDENTITY_NORMALIZATION_VERSION = "2"


def normalize_word_identity(dictionary_form: str, reading: str) -> Tuple[str, str]:
    """Return the canonical local identity for a word and its reading."""
    dictionary_form = unicodedata.normalize("NFKC", dictionary_form or "").strip()
    dictionary_form = joyokanji.convert(dictionary_form, variants=True)
    reading = unicodedata.normalize("NFKC", reading or "").strip()
    reading = "".join(
        chr(ord(char) - 0x60) if "\u30a1" <= char <= "\u30f6" else char
        for char in reading
    )
    return dictionary_form, reading


class MinedWordsTracker:
    """Interface for tracking mined words locally.

    Constructor config:
        - db_path: Path to the mined_words.db SQLite file.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            core_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(core_dir)
            root_dir = os.path.dirname(src_dir)
            db_path = os.path.join(root_dir, "data", "mined_words.db")

        self._db_path = db_path
        self._conn_lock: threading.Lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        _init_schema(self._db_path)

    def is_already_mined(
        self,
        dictionary_form: str,
        reading: str,
        surface: Optional[str] = None,
    ) -> bool:
        """Check the dictionary form and surface against synced Anki entries."""
        dictionary_form, reading = normalize_word_identity(dictionary_form, reading)
        forms = {dictionary_form}
        if surface:
            normalized_surface, _ = normalize_word_identity(surface, reading)
            forms.add(normalized_surface)
        placeholders = ",".join("?" for _ in forms)
        conn = self._get_conn()
        with self._conn_lock:
            row = conn.execute(
                f"""SELECT id FROM mined_words
                    WHERE dictionary_form IN ({placeholders})
                      AND (reading=? OR reading='')""",
                (*forms, reading)
            ).fetchone()
        return row is not None

    def record_mined(self, dictionary_form: str, reading: str, note_id: Optional[int]) -> None:
        """Record a mined word in the database."""
        dictionary_form, reading = normalize_word_identity(dictionary_form, reading)
        conn = self._get_conn()
        with self._conn_lock:
            conn.execute(
                """INSERT OR IGNORE INTO mined_words
                   (dictionary_form, reading, mined_at, anki_note_id)
                   VALUES (?,?,?,?)""",
                (dictionary_form, reading, datetime.now().isoformat(), note_id)
            )
            conn.commit()

    def has_initial_sync_completed(self) -> bool:
        """Check if initial full-profile sync has completed."""
        conn = self._get_conn()
        with self._conn_lock:
            row = conn.execute(
                "SELECT value FROM mined_sync_metadata WHERE key='initial_sync_complete'"
            ).fetchone()
        return row is not None and row["value"] == "1"

    def mark_sync_complete(self) -> None:
        """Mark initial sync as complete."""
        conn = self._get_conn()
        with self._conn_lock:
            conn.execute(
                """INSERT OR REPLACE INTO mined_sync_metadata (key, value)
                   VALUES ('initial_sync_complete', '1')"""
            )
            conn.commit()

    def save_mined_batch(self, mined_rows: List[tuple], rebuild: bool = False) -> None:
        """Save a batch of mined words."""
        normalized_rows = [
            (*normalize_word_identity(dictionary_form, reading), mined_at, note_id)
            for dictionary_form, reading, mined_at, note_id in mined_rows
        ]
        conn = self._get_conn()
        with self._conn_lock:
            if rebuild:
                conn.execute("DELETE FROM mined_words")
            conn.executemany(
                """INSERT OR IGNORE INTO mined_words
                   (dictionary_form, reading, mined_at, anki_note_id)
                   VALUES (?, ?, ?, ?)""",
                normalized_rows,
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            _init_schema(self._db_path)
        return self._conn


def _init_schema(db_path: str) -> None:
    """Initialize database schema if it doesn't exist."""
    schema = """
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
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(schema)
    conn.commit()

    # Legacy DB migration
    LEGACY_DB_PATH = db_path.replace("mined_words.db", "mined.db")
    if os.path.isfile(LEGACY_DB_PATH):
        legacy_conn = sqlite3.connect(LEGACY_DB_PATH)
        legacy_table = legacy_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mined_words'"
        ).fetchone()
        if legacy_table:
            legacy_rows = legacy_conn.execute(
                """SELECT dictionary_form, reading, mined_at, anki_note_id
                   FROM mined_words"""
            ).fetchall()
            legacy_rows = [
                (*normalize_word_identity(dictionary_form, reading), mined_at, note_id)
                for dictionary_form, reading, mined_at, note_id in legacy_rows
            ]
            conn.executemany(
                """INSERT OR IGNORE INTO mined_words
                   (dictionary_form, reading, mined_at, anki_note_id)
                   VALUES (?, ?, ?, ?)""",
                legacy_rows,
            )
        legacy_conn.close()

    identity_version = conn.execute(
        "SELECT value FROM mined_sync_metadata "
        "WHERE key='word_identity_normalization_version'"
    ).fetchone()
    if identity_version is None or identity_version[0] != _IDENTITY_NORMALIZATION_VERSION:
        rows = conn.execute(
            """SELECT dictionary_form, reading, mined_at, anki_note_id
               FROM mined_words ORDER BY id"""
        ).fetchall()
        normalized_rows = []
        seen_identities = set()
        for dictionary_form, reading, mined_at, note_id in rows:
            identity = normalize_word_identity(dictionary_form, reading)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            normalized_rows.append((*identity, mined_at, note_id))

        conn.execute("DELETE FROM mined_words")
        conn.executemany(
            """INSERT INTO mined_words
               (dictionary_form, reading, mined_at, anki_note_id)
               VALUES (?, ?, ?, ?)""",
            normalized_rows,
        )
        conn.execute(
            """INSERT OR REPLACE INTO mined_sync_metadata (key, value)
               VALUES ('word_identity_normalization_version', ?)""",
            (_IDENTITY_NORMALIZATION_VERSION,),
        )
        conn.commit()
    conn.close()