# One-time script to download and compile all dictionary sources into jmdict.db
# Run automatically by main.py if DB is missing our outdated
# Sources:
#   JMDict XML      - EDRDG (JMdict/EDICT project)
#   Kanjium pitch   - github.com/mifunetoshiro/kanjium
#   JPDB frequency  - github.com/Kuuuube/jpdb-frequency-list
#   JLPT data       - github.com/javdejong/nhk-pronunciation
#   Tatoeba         - downloads.tatoeba.org

import os
import sys
import sqlite3
import urllib.request
import gzip
import shutil
import csv
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk
import threading
import time


BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # data/
DATA_DIR = BASE_DIR                                    # jmdict.db goes here
RAW_DIR  = os.path.join(BASE_DIR, "raw")               # data/raw/
DB_PATH  = os.path.join(BASE_DIR, "jmdict.db")         # data/jmdict.db

DB_VERSION = "1.0.0"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

SOURCES = {
    "jmdict": {
        "url":      "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz",
        "dest":     os.path.join(RAW_DIR, "JMdict.xml"),
        "gz":       os.path.join(RAW_DIR, "JMdict.xml.gz"),
        "label":    "JMdict dictionary",
    },
    "kanjium": {
        "url":   "https://raw.githubusercontent.com/mifunetoshiro/kanjium/master/data/source_files/raw/accents.txt",
        "dest":  os.path.join(RAW_DIR, "kanjium_pitch.txt"),
        "label": "Kanjium pitch accent data",
    },
    "jpdb_freq": {
        "url":   "https://raw.githubusercontent.com/mifunetoshiro/kanjium/master/data/source_files/raw/wikipedia_freq.txt",
        "dest":  os.path.join(RAW_DIR, "jpdb_freq.txt"),
        "label": "Japanese frequency list",
    },
    "tatoeba_jpn": {
        "url":      "https://downloads.tatoeba.org/exports/per_language/jpn/jpn_sentences.tsv.bz2",
        "dest":     os.path.join(RAW_DIR, "tatoeba_jpn.tsv"),
        "bz2":      os.path.join(RAW_DIR, "tatoeba_jpn.tsv.bz2"),
        "label":    "Tatoeba Japanese sentences",
    },
    "tatoeba_links": {
        "url":      "https://downloads.tatoeba.org/exports/links.tar.bz2",
        "dest":     os.path.join(RAW_DIR, "links.csv"),
        "bz2":      os.path.join(RAW_DIR, "links.tar.bz2"),
        "label":    "Tatoeba sentence links",
    },
    "tatoeba_eng": {
        "url":      "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
        "dest":     os.path.join(RAW_DIR, "tatoeba_eng.tsv"),
        "bz2":      os.path.join(RAW_DIR, "tatoeba_eng.tsv.bz2"),
        "label":    "Tatoeba English sentences",
    },
}


class ProgressWindow:
    """
    Tkinter progress window shown during DB build.
    Supports being driven from a background thread via update queue.
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JAM — Building Dictionary Database")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
 
        # Center window
        w, h = 500, 140
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
 
        outer = tk.Frame(self.root, padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)
 
        self.title_label = tk.Label(
            outer,
            text="Building dictionary database (first run only)",
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )
        self.title_label.pack(fill=tk.X)
 
        self.step_label = tk.Label(
            outer,
            text="Starting...",
            font=("Segoe UI", 9),
            fg="#555555",
            anchor="w"
        )
        self.step_label.pack(fill=tk.X, pady=(4, 8))
 
        # Progress bar and percentage on the same row using grid
        bar_row = tk.Frame(outer)
        bar_row.pack(fill=tk.X)
        bar_row.columnconfigure(0, weight=1)  # bar expands
        bar_row.columnconfigure(1, minsize=40) # percentage fixed width
 
        self.progress = ttk.Progressbar(
            bar_row,
            orient="horizontal",
            mode="determinate"
        )
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
 
        self.pct_label = tk.Label(
            bar_row,
            text="0%",
            font=("Segoe UI", 9),
            anchor="e",
            width=4
        )
        self.pct_label.grid(row=0, column=1, sticky="e")
 
        self._pending_step  = None
        self._pending_pct   = None
        self._close_flag    = False
 
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent close
        self.root.update()
 
    def set_step(self, text: str, pct: float):
        """Thread-safe: schedule a label + progress bar update."""
        self._pending_step = text
        self._pending_pct  = pct
 
    def pump(self) -> bool:
        """
        Call repeatedly from the main thread to flush pending updates.
        Returns False when the window has been closed (build finished).
        """
        if self._pending_step is not None:
            self.step_label.config(text=self._pending_step)
            self._pending_step = None
        if self._pending_pct is not None:
            self.progress["value"] = self._pending_pct
            self.pct_label.config(text=f"{int(self._pending_pct)}%")
            self._pending_pct = None
        if self._close_flag:
            try:
                self.root.destroy()
            except Exception:
                pass
            return False
        try:
            self.root.update()
        except tk.TclError:
            return False
        return True
 
    def close(self):
        self._close_flag = True
        
        
def _download(url: str, dest: str, label: str):
    print(f"[Build] Downloading {label}...")
    req = urllib.request.Request(url, headers={"User-Agent": "JAM/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(dest, "wb") as f:
                shutil.copyfileobj(response, f)
    except Exception as e:
        raise RuntimeError(f"Failed to download {label}: {e}")
 
 
def _decompress_gz(gz_path: str, dest_path: str):
    print(f"[Build] Decompressing {os.path.basename(gz_path)}...")
    with gzip.open(gz_path, "rb") as f_in:
        with open(dest_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
 
 
def _decompress_bz2(bz2_path: str, dest_path: str):
    import bz2
    import tarfile
    print(f"[Build] Decompressing {os.path.basename(bz2_path)}...")
    if bz2_path.endswith(".tar.bz2"):
        with tarfile.open(bz2_path, "r:bz2") as tar:
            for member in tar.getmembers():
                if member.name.endswith((".csv", ".tsv")):
                    member.name = os.path.basename(dest_path)
                    tar.extract(member, path=os.path.dirname(dest_path))
                    break
    else:
        with bz2.open(bz2_path, "rb") as f_in:
            with open(dest_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)


SCHEMA = """
CREATE TABLE IF NOT EXISTS db_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
 
CREATE TABLE IF NOT EXISTS entries (
    entry_id        INTEGER PRIMARY KEY,
    kanji_forms     TEXT,   -- JSON array of kanji writings
    kana_forms      TEXT    -- JSON array of kana readings
);
 
CREATE TABLE IF NOT EXISTS senses (
    sense_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER NOT NULL,
    pos             TEXT,   -- part of speech (comma-separated)
    domain          TEXT,   -- domain/field tags (comma-separated)
    gloss           TEXT,   -- English definition
    example_jp      TEXT,   -- example sentence Japanese (from JMdict or Tatoeba)
    example_en      TEXT,   -- example sentence English
    FOREIGN KEY (entry_id) REFERENCES entries(entry_id)
);
 
CREATE TABLE IF NOT EXISTS pitch_accent (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER,
    expression      TEXT NOT NULL,
    reading         TEXT NOT NULL,
    pitch_pattern   TEXT NOT NULL,  -- NHK format e.g. "0" "1" "2＼"
    pitch_category  TEXT,           -- 平板 頭高 中高 尾高
    FOREIGN KEY (entry_id) REFERENCES entries(entry_id)
);
 
CREATE TABLE IF NOT EXISTS frequency (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    expression      TEXT NOT NULL,
    frequency_rank  INTEGER NOT NULL
);
 
CREATE TABLE IF NOT EXISTS jlpt (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    expression      TEXT NOT NULL,
    level           TEXT NOT NULL   -- N1 N2 N3 N4 N5
);
 
CREATE TABLE IF NOT EXISTS tatoeba (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    japanese        TEXT NOT NULL,
    english         TEXT
);
 
CREATE TABLE IF NOT EXISTS tatoeba_links (
    entry_id        INTEGER NOT NULL,
    tatoeba_id      INTEGER NOT NULL,
    FOREIGN KEY (entry_id)   REFERENCES entries(entry_id),
    FOREIGN KEY (tatoeba_id) REFERENCES tatoeba(id)
);
 
CREATE INDEX IF NOT EXISTS idx_entries_kanji  ON entries(kanji_forms);
CREATE INDEX IF NOT EXISTS idx_entries_kana   ON entries(kana_forms);
CREATE INDEX IF NOT EXISTS idx_senses_entry   ON senses(entry_id);
CREATE INDEX IF NOT EXISTS idx_pitch_expr     ON pitch_accent(expression);
CREATE INDEX IF NOT EXISTS idx_pitch_entry    ON pitch_accent(entry_id);
CREATE INDEX IF NOT EXISTS idx_freq_expr      ON frequency(expression);
CREATE INDEX IF NOT EXISTS idx_jlpt_expr      ON jlpt(expression);
CREATE INDEX IF NOT EXISTS idx_tatoeba_links  ON tatoeba_links(entry_id);
"""


import json
import re

def _parse_jmdict(xml_path: str, conn: sqlite3.Connection, progress_cb=None):
    """
    Parse JMDict XML and insert entries.
    Only extracts English glosses.
    """
    print("[Build] Parsing JMdict XML...")
    tree  = ET.parse(xml_path)
    root  = tree.getroot()
    entries = root.findall("entry")
    total   = len(entries)
    cur     = conn.cursor()
 
    for i, entry in enumerate(entries):
        entry_id    = int(entry.findtext("ent_seq"))
        kanji_forms = [k.findtext("keb") for k in entry.findall("k_ele")]
        kana_forms  = [r.findtext("reb") for r in entry.findall("r_ele")]
 
        cur.execute(
            "INSERT OR REPLACE INTO entries (entry_id, kanji_forms, kana_forms) VALUES (?,?,?)",
            (
                entry_id,
                json.dumps(kanji_forms, ensure_ascii=False),
                json.dumps(kana_forms,  ensure_ascii=False),
            )
        )
 
        for sense in entry.findall("sense"):
            pos_tags    = [p.text for p in sense.findall("pos")   if p.text]
            domain_tags = [d.text for d in sense.findall("field") if d.text]
            misc_tags   = [m.text for m in sense.findall("misc")  if m.text]
            all_pos     = pos_tags + misc_tags
 
            glosses = [
                g.text for g in sense.findall("gloss")
                if g.get("{http://www.w3.org/XML/1998/namespace}lang", "eng") == "eng"
                and g.text
            ]
 
            example_jp = example_en = None
            ex_elem = sense.find("example")
            if ex_elem is not None:
                for ex_sent in ex_elem.findall("ex_sent"):
                    lang = ex_sent.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    if lang == "jpn":
                        example_jp = ex_sent.text
                    elif lang == "eng":
                        example_en = ex_sent.text
 
            if glosses:
                cur.execute(
                    """INSERT INTO senses
                       (entry_id, pos, domain, gloss, example_jp, example_en)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        entry_id,
                        ", ".join(all_pos),
                        ", ".join(domain_tags),
                        "; ".join(glosses),
                        example_jp,
                        example_en,
                    )
                )
 
        if i % 1000 == 0:
            print(f"[Build] JMdict: {i}/{total} entries processed...")
 
    conn.commit()
    print(f"[Build] JMdict: inserted {total} entries.")
 
 
def _parse_kanjium(txt_path: str, conn: sqlite3.Connection):
    print("[Build] Parsing Kanjium pitch accent data...")
    cur = conn.cursor()

    expr_to_id = {}
    for row in cur.execute("SELECT entry_id, kanji_forms, kana_forms FROM entries"):
        eid, kj, kn = row
        for form in json.loads(kj or "[]") + json.loads(kn or "[]"):
            expr_to_id[form] = eid

    rows = []
    with open(txt_path, encoding="utf-8") as f:
        for line in f:
            # Format: expression\treading\tpitch_number
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            expression = parts[0].strip()
            reading    = parts[1].strip()
            pitch      = parts[2].strip()
            if not expression or not reading or not pitch:
                continue

            entry_id = expr_to_id.get(expression) or expr_to_id.get(reading)

            try:
                n = int(pitch)
                if n == 0:
                    category = "平板"
                elif n == 1:
                    category = "頭高"
                elif n == len(reading):
                    category = "尾高"
                else:
                    category = "中高"
            except ValueError:
                category = ""

            rows.append((entry_id, expression, reading, pitch, category))

    cur.executemany(
        """INSERT INTO pitch_accent
           (entry_id, expression, reading, pitch_pattern, pitch_category)
           VALUES (?,?,?,?,?)""",
        rows
    )
    conn.commit()
    print(f"[Build] Kanjium: inserted {len(rows)} pitch accent entries.")
 
def _parse_jpdb_freq(txt_path: str, conn: sqlite3.Connection):
    print("[Build] Parsing frequency list...")
    cur  = conn.cursor()
    rows = []

    with open(txt_path, encoding="utf-8") as f:
        for rank, line in enumerate(f, start=1):
            parts = line.strip().split("\t")
            if not parts or not parts[0].strip():
                continue
            expression = parts[0].strip()
            rows.append((expression, rank))

    cur.executemany(
        "INSERT INTO frequency (expression, frequency_rank) VALUES (?,?)",
        rows
    )
    conn.commit()
    print(f"[Build] Frequency list: inserted {len(rows)} entries.")
 
def _insert_jlpt_from_jmdict(conn: sqlite3.Connection):
    """
    Extracts JLPT level tags embedded directly in JMdict entries.
    JMdict tags entries with nf01-nf48 (news frequency) and jlpt tags.
    This avoids needing a separate download entirely.
    """
    print("[Build] Extracting JLPT data from JMdict tags...")
    cur = conn.cursor()
    
    # JMdict uses these misc tags for JLPT levels
    JLPT_TAGS = {
        "jlpt-1": "N1",
        "jlpt-2": "N2", 
        "jlpt-3": "N3",
        "jlpt-4": "N4",
        "jlpt-5": "N5", # Note: JMdict doesn't always have N5 tagged
    }
    
    xml_path = SOURCES["jmdict"]["dest"]
    if not os.path.exists(xml_path):
        print("[Build] JMdict XML not found, skipping JLPT extraction.")
        return

    tree  = ET.parse(xml_path)
    root  = tree.getroot()
    rows  = []

    for entry in root.findall("entry"):
        kanji_forms = [k.findtext("keb") for k in entry.findall("k_ele")]
        kana_forms  = [r.findtext("reb") for r in entry.findall("r_ele")]
        all_forms   = kanji_forms + kana_forms

        for sense in entry.findall("sense"):
            for misc in sense.findall("misc"):
                level = JLPT_TAGS.get(misc.text)
                if level:
                    for form in all_forms:
                        if form:
                            rows.append((form, level))
                    break  # one level per entry is enough

    cur.executemany("INSERT INTO jlpt (expression, level) VALUES (?,?)", rows)
    conn.commit()
    print(f"[Build] JLPT: inserted {len(rows)} entries from JMdict tags.")
 
def _parse_tatoeba(jpn_path: str, eng_path: str, links_path: str,
                   conn: sqlite3.Connection):
    print("[Build] Parsing Tatoeba sentences...")
    cur = conn.cursor()
 
    print("[Build] Loading English sentences...")
    eng_sentences = {}
    if os.path.exists(eng_path):
        with open(eng_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    try:
                        eng_sentences[int(parts[0])] = parts[2]
                    except ValueError:
                        continue
 
    print("[Build] Loading sentence links...")
    jpn_to_eng = {}
    if os.path.exists(links_path):
        with open(links_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    try:
                        a, b = int(parts[0]), int(parts[1])
                        if a not in jpn_to_eng:
                            jpn_to_eng[a] = b
                    except ValueError:
                        continue
 
    print("[Build] Inserting Japanese-English pairs...")
    tatoeba_rows = []
    if os.path.exists(jpn_path):
        with open(jpn_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue
                try:
                    jpn_id = int(parts[0])
                except ValueError:
                    continue
                japanese = parts[2]
                eng_id   = jpn_to_eng.get(jpn_id)
                english  = eng_sentences.get(eng_id) if eng_id else None
                tatoeba_rows.append((japanese, english))
 
    cur.executemany(
        "INSERT INTO tatoeba (japanese, english) VALUES (?,?)",
        tatoeba_rows
    )
    conn.commit()
    print(f"[Build] Tatoeba: inserted {len(tatoeba_rows)} sentence pairs.")
 
    print("[Build] Linking words to example sentences...")
    _link_tatoeba_to_entries(conn)
 
def _link_tatoeba_to_entries(conn: sqlite3.Connection):
    cur = conn.cursor()
    print("[Build] Building sentence word index...")

    # Load all sentences once
    sentences = cur.execute("SELECT id, japanese FROM tatoeba").fetchall()

    # Build an inverted index: word_substring → list of sentence ids
    # Instead of checking every sentence for every entry,
    # we check each entry against only the sentences that contain it
    from collections import defaultdict
    import re

    # Index sentences by every 2+ character substring (covers most words)
    # We only store the first 5 sentence IDs per key to keep memory manageable
    index = defaultdict(list)
    kanji_re = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

    print(f"[Build] Indexing {len(sentences)} sentences...")
    for tat_id, japanese in sentences:
        # Extract meaningful tokens (kanji words) from sentence for indexing
        # Index every 2-4 character slice that contains kanji
        seen = set()
        for i in range(len(japanese)):
            for length in range(2, 6):
                chunk = japanese[i:i+length]
                if len(chunk) == length and kanji_re.search(chunk) and chunk not in seen:
                    seen.add(chunk)
                    if len(index[chunk]) < 5:
                        index[chunk].append(tat_id)

    # Now match entries against the index
    print("[Build] Matching entries to sentences...")
    entries = cur.execute("SELECT entry_id, kanji_forms, kana_forms FROM entries").fetchall()
    links = []

    for entry_id, kanji_json, kana_json in entries:
        forms = json.loads(kanji_json or "[]") + json.loads(kana_json or "[]")
        forms = sorted(set(f for f in forms if f and len(f) >= 2), key=len, reverse=True)
        if not forms:
            continue

        found_ids = set()
        for form in forms:
            for tat_id in index.get(form, []):
                if tat_id not in found_ids:
                    links.append((entry_id, tat_id))
                    found_ids.add(tat_id)
                if len(found_ids) >= 3:
                    break
            if len(found_ids) >= 3:
                break

    cur.executemany(
        "INSERT INTO tatoeba_links (entry_id, tatoeba_id) VALUES (?,?)",
        links
    )
    conn.commit()
    print(f"[Build] Tatoeba links: created {len(links)} word↔sentence links.")
    
def build(progress_window: ProgressWindow = None):
    """
    Full build pipeline. Called from a background thread.
    Uses progress_window.set_step() for UI updates (thread-safe).
    """
    def step(label: str, pct: float):
        print(f"[Build] {label} ({int(pct)}%)")
        if progress_window:
            progress_window.set_step(label, pct)
 
    try:
        step("Creating database...", 2)
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA)
        conn.commit()
 
 
        download_steps = [
            ("jmdict",        5,  "Downloading JMdict..."),
            ("kanjium",       12, "Downloading Kanjium pitch data..."),
            ("jpdb_freq",     18, "Downloading JPDB frequency list..."),
            ("tatoeba_jpn",   28, "Downloading Tatoeba Japanese sentences..."),
            ("tatoeba_eng",   34, "Downloading Tatoeba English sentences..."),
            ("tatoeba_links", 40, "Downloading Tatoeba links..."),
        ]
 
        for key, pct, label in download_steps:
            src  = SOURCES[key]
            dest = src["dest"]
            gz   = src.get("gz")
            bz2  = src.get("bz2")
 
            step(label, pct)
 
            if not os.path.exists(dest):
                if gz:
                    if not os.path.exists(gz):
                        _download(src["url"], gz, src["label"])
                    _decompress_gz(gz, dest)
                elif bz2:
                    if not os.path.exists(bz2):
                        _download(src["url"], bz2, src["label"])
                    _decompress_bz2(bz2, dest)
                else:
                    _download(src["url"], dest, src["label"])
            else:
                print(f"[Build] {src['label']} already downloaded, skipping.")
 
        step("Parsing JMdict entries...", 42)
        _parse_jmdict(SOURCES["jmdict"]["dest"], conn)
 
        step("Parsing pitch accent data...", 58)
        _parse_kanjium(SOURCES["kanjium"]["dest"], conn)
 
        step("Parsing frequency list...", 68)
        _parse_jpdb_freq(SOURCES["jpdb_freq"]["dest"], conn)
 
        step("Parsing JLPT levels...", 74)
        _insert_jlpt_from_jmdict(conn)
 
        step("Parsing Tatoeba sentences...", 78)
        _parse_tatoeba(
            SOURCES["tatoeba_jpn"]["dest"],
            SOURCES["tatoeba_eng"]["dest"],
            SOURCES["tatoeba_links"]["dest"],
            conn,
        )
 
        step("Finalising database...", 96)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('version', ?)",
            (DB_VERSION,)
        )
        cur.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('built_at', ?)",
            (str(int(time.time())),)
        )
        conn.commit()
 
        step("Cleaning up downloaded files...", 98)
        try:
            shutil.rmtree(RAW_DIR)
            print("[Build] Raw files cleaned up.")
        except Exception as e:
            print(f"[Build] Cleanup warning: {e}")
 
        conn.close()
        step("Database ready.", 100)
        print(f"[Build] Complete. Database saved to {DB_PATH}")
 
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Build] FAILED: {e}")
        if progress_window:
            progress_window.set_step(f"Error: {e}", 0)
        raise
    
def run_with_progress():
    """
    Launches the progress window on the main thread and runs build()
    in a background thread. Called by main.py when DB is missing.
    """
    win = ProgressWindow()
 
    build_thread = threading.Thread(target=build, args=(win,), daemon=True)
    build_thread.start()
 
    while True:
        still_running = win.pump()
        if not still_running:
            break
        if not build_thread.is_alive():
            win.close()
        time.sleep(0.05)
 
    build_thread.join()
 
 
def needs_build() -> bool:
    """Returns True if the DB is missing or version is outdated."""
    if not os.path.exists(DB_PATH):
        return True
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT value FROM db_meta WHERE key='version'"
        ).fetchone()
        conn.close()
        return (row is None or row[0] != DB_VERSION)
    except Exception:
        return True
 
 
if __name__ == "__main__":
    run_with_progress()