# Module for dictionary lookup of words against local jmdict.db
# Feeds into the card creation pipeline after parser.py
# Uses persistent SQLite conncetion with locks for speed

import os
import sys
import sqlite3
import threading
from typing import Optional, Any
from src.models.word import Word

_conn: Optional[sqlite3.Connection] = None
_conn_lock: threading.Lock = threading.Lock()
_db_ready: threading.Event = threading.Event()

def _get_app_dir() -> str:
    """Returns the root app directory regardless of frozen or dev mode."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller exe — data lives next to the exe
        return os.path.dirname(sys.executable)
    else:
        # Running from source — walk up from core/ to root
        core_dir = os.path.dirname(os.path.abspath(__file__))  # src/core/
        src_dir  = os.path.dirname(core_dir)                   # src/
        return os.path.dirname(src_dir)                        # root/

def _get_db_path() -> str:
    return os.path.join(_get_app_dir(), "data", "jmdict.db")

def get_connection() -> sqlite3.Connection:
    """
    Returns the shared persistent SQlite connectionn.
    Opens on first call. Thread-safe via _conn_lock.
    """
    global _conn
    with _conn_lock:
        if _conn is None:
            db_path = _get_db_path()
            if not os.path.exists(db_path):
                _db_ready.set()
                raise FileNotFoundError(
                    f"Dictionary DB not found at {db_path}."
                    "Run build_db.py first."
                )
            print("[Dictionary] Opening database connection...")
            _conn = sqlite3.connect(db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row

            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA cache_size=-64000")
            _conn.execute("PRAGMA temp_store=MEMORY")
            _db_ready.set()
            print("[Dictionary] Database ready.")
    return _conn

def init() -> None:
    """
    Pre-opens the DB connection at startup so first lookup is instant.
    Call from a background thread in main.py.
    """
    path = _get_db_path()
    data_dir = os.path.dirname(path)
    print(f"[Dictionary] Looking for DB at: {path}")
    print(f"[Dictionary] File exists: {os.path.exists(path)}")
    if os.path.isdir(data_dir):
        print(f"[Dictionary] data/ contents: {os.listdir(data_dir)}")
    else:
        print(f"[Dictionary] data/ dir not yet created at: {data_dir}")
    get_connection()


def _find_entry_id(cur: sqlite3.Cursor,
                   dictionary_form: str,
                   surface: str,
                   reading: str) -> Optional[int]:
    """
    Tries to find a matching entry_id using priority search:
        1. dictionary_form vs kanji_forms
        2. dictionary_form vs kana_forms
        3. surface vs kanji_forms
        4. reading vs kana_forms

    Args:
        cur: SQLite cursor
        dictionary_form: Base form of word from parser
        surface: Surface form from parser  
        reading: Hiragana reading from parser

    Returns:
        Entry ID if found, None otherwise
    """
    candidates = [
        (dictionary_form, "kanji_forms"),
        (dictionary_form, "kana_forms"),
        (surface,         "kanji_forms"),
        (reading,         "kana_forms"),
    ]
    
    for term, column in candidates:
        if not term:
            continue
        
        row = cur.execute(
            f"SELECT entry_id FROM entries WHERE {column} LIKE ?",
            (f'%"{term}"%',)
        ).fetchone()
        if row:
            return row["entry_id"]

    return None


_POS_MAP = {
    "名詞":   ["noun", "n"],
    "動詞":   ["verb", "v"],
    "形容詞": ["adjective", "adj-i"],
    "形容動詞": ["adjective", "adj-na"],
    "副詞":   ["adverb", "adv"],
    "助詞":   ["particle"],
    "助動詞": ["auxiliary"],
    "接続詞": ["conjunction", "conj"],
    "感動詞": ["interjection", "int"],
    "接頭辞": ["prefix"],
    "接尾辞": ["suffix", "suf"],
}

def _pos_matches(sense_pos: str, parser_pos: str) -> bool:
    """
    Returns True if the sense's POS tag is compatible with parser's POS.

    Args:
        sense_pos (str):    POS string from the senses table (JMdict tags)
        parser_pos (str):   broad POS from SudachiPy
    """
    if not sense_pos or not parser_pos:
        return True
    
    keywords = _POS_MAP.get(parser_pos, [])
    sense_lower = sense_pos.lower()
    return any(kw in sense_lower for kw in keywords)

def _score_sense(sense: sqlite3.Row, parser_pos: str, sentence:str) -> int:
    """
    Scores a sense by relevance to the current context.
    Higher score = better match.

    Scoring:
        +3  POS matches parser's POS
        +1  per domain tag word found in the sentence
        +1  sense has an example sentence (perfer illustrated senses)

    Args:
        sense (sqlite3.Row):    Row from senses table
        parser_pos (str):       broad POS from SudachiPy
        sentence (str):         full OCR sentence for domain matching

    Returns:
        int: Score
    """
    score = 0
    
    if _pos_matches(sense["pos"], parser_pos):
        score += 3
        
    domain = sense["domain"] or ""
    if domain:
        for tag in domain.split(","):
            tag = tag.strip().lower()
            if tag and tag in sentence.lower():
                score += 1

    if sense["example_jp"]:
        score += 1

    return score


def lookup(parse_result: Word) -> Optional[dict[str, Any]]:
    """
    Main entry point for dictionary.py.
    Takes Word object and returns enriched dictionary data.

    Args:
        parse_result: Word dataclass object with surface, dictionary_form, reading, pos, full_sentence

    Returns:
        Dictionary with enriched word data, or None if lookup fails
    """
    dictionary_form = parse_result.dictionary_form
    surface = parse_result.surface
    reading = parse_result.reading
    parser_pos = parse_result.pos
    sentence = parse_result.full_sentence or ""

    try:
        conn = get_connection()
        with _conn_lock:
            cur = conn.cursor()

            entry_id = _find_entry_id(cur, dictionary_form, surface, reading)

            if entry_id is None:
                print(f"[Dictionary] No entry found for '{dictionary_form}'")
                return None
            
            senses = cur.execute(
                """SELECT sense_id, pos, domain, gloss, example_jp, example_en
                   FROM senses WHERE entry_id = ?""",
                (entry_id,)
            ).fetchall()
            
            if not senses:
                print(f"[Dictionary] Entry found but no senses for '{dictionary_form}'.")
                return None
 
            scored = sorted(
                senses,
                key=lambda s: _score_sense(s, parser_pos, sentence),
                reverse=True
            )
 
            main_sense = scored[0]
            main_definition = main_sense["gloss"]
            
            # GLOSSARY
            glossary: list[dict[str, Any]] = [
                {
                    "gloss":      s["gloss"],
                    "pos":        s["pos"] or "",
                    "domain":     s["domain"] or "",
                    "example_jp": s["example_jp"],
                    "example_en": s["example_en"],
                }
                for s in scored
            ]
            
            # PITCH ACCENT
            pitch_row = cur.execute(
                """SELECT pitch_pattern, pitch_category
                   FROM pitch_accent
                   WHERE expression = ? OR expression = ?
                   LIMIT 1""",
                (dictionary_form, surface)
            ).fetchone()
 
            pitch_pattern  = pitch_row["pitch_pattern"]  if pitch_row else None
            pitch_category = pitch_row["pitch_category"] if pitch_row else None
            
            # FREQUENCY
            freq_row = cur.execute(
                """SELECT frequency_rank FROM frequency
                   WHERE expression = ? OR expression = ?
                   ORDER BY frequency_rank ASC LIMIT 1""",
                (dictionary_form, surface)
            ).fetchone()
 
            frequency_rank = freq_row["frequency_rank"] if freq_row else None

            # JLPT LEVEL
            jlpt_row = cur.execute(
                """SELECT level FROM jlpt
                   WHERE expression = ? OR expression = ?
                   LIMIT 1""",
                (dictionary_form, surface)
            ).fetchone()
 
            jlpt_level = jlpt_row["level"] if jlpt_row else None
            
            # TATOEBA EXAMPLE SENTENCES
            tat_rows = cur.execute(
                """SELECT t.japanese, t.english
                   FROM tatoeba t
                   JOIN tatoeba_links tl ON t.id = tl.tatoeba_id
                   WHERE tl.entry_id = ?
                   LIMIT 3""",
                (entry_id,)
            ).fetchall()
 
            example_sentences = [
                {"japanese": r["japanese"], "english": r["english"]}
                for r in tat_rows
            ]
 
        result: dict[str, Any] = {
            "main_definition":   main_definition,
            "glossary":          glossary,
            "pitch_pattern":     pitch_pattern,
            "pitch_category":    pitch_category,
            "frequency_rank":    frequency_rank,
            "jlpt_level":        jlpt_level,
            "example_sentences": example_sentences,
        }
 
        print(
            f"[Dictionary] '{dictionary_form}' → {main_definition} "
            f"| pitch: {pitch_pattern} ({pitch_category}) "
            f"| freq: #{frequency_rank} | JLPT: {jlpt_level}"
        )
 
        return result
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Dictionary] Lookup failed: {e}")
        return None