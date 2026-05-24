# One-time script to download and compile all dictionary sources into jmdict.db
# Run automatically by main.py if DB is missing or outdated
# Sources:
#   Jitendex (Yomitan zip)  - jitendex.org  (replaces raw JMDict XML)
#   Kanjium pitch           - github.com/mifunetoshiro/kanjium
#   Wikipedia frequency     - github.com/mifunetoshiro/kanjium
#   Tatoeba                 - downloads.tatoeba.org

import os
import sys
import sqlite3
import urllib.request
import shutil
import json
import zipfile
import re
import time
import threading
import tkinter as tk
from tkinter import ttk


def _get_runtime_dirs():
    """
    Returns (base_dir, raw_dir, db_path) rooted at the correct location
    whether running from source or as a frozen exe.
    """
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    base_dir = os.path.join(app_dir, "data")
    raw_dir  = os.path.join(base_dir, "raw")
    db_path  = os.path.join(base_dir, "jmdict.db")
    return base_dir, raw_dir, db_path


BASE_DIR, RAW_DIR, DB_PATH = _get_runtime_dirs()
DATA_DIR = BASE_DIR

DB_VERSION = "2.0.0"  # bumped — Jitendex replaces raw JMDict

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RAW_DIR,  exist_ok=True)

SOURCES = {
    "jitendex": {
        "url":   "https://github.com/stephenmk/stephenmk.github.io/releases/latest/download/jitendex-yomitan.zip",
        "dest":  os.path.join(RAW_DIR, "jitendex-yomitan.zip"),
        "label": "Jitendex dictionary (Yomitan format)",
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
        "url":   "https://downloads.tatoeba.org/exports/per_language/jpn/jpn_sentences.tsv.bz2",
        "dest":  os.path.join(RAW_DIR, "tatoeba_jpn.tsv"),
        "bz2":   os.path.join(RAW_DIR, "tatoeba_jpn.tsv.bz2"),
        "label": "Tatoeba Japanese sentences",
    },
    "tatoeba_links": {
        "url":   "https://downloads.tatoeba.org/exports/links.tar.bz2",
        "dest":  os.path.join(RAW_DIR, "links.csv"),
        "bz2":   os.path.join(RAW_DIR, "links.tar.bz2"),
        "label": "Tatoeba sentence links",
    },
    "tatoeba_eng": {
        "url":   "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
        "dest":  os.path.join(RAW_DIR, "tatoeba_eng.tsv"),
        "bz2":   os.path.join(RAW_DIR, "tatoeba_eng.tsv.bz2"),
        "label": "Tatoeba English sentences",
    },
}


# ── Progress window ───────────────────────────────────────────────────────────

class ProgressWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JAM — Building Dictionary Database")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        w, h = 500, 140
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        outer = tk.Frame(self.root, padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text="Building dictionary database (first run only)",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(fill=tk.X)

        self.step_label = tk.Label(
            outer, text="Starting...", font=("Segoe UI", 9),
            fg="#555555", anchor="w",
        )
        self.step_label.pack(fill=tk.X, pady=(4, 8))

        bar_row = tk.Frame(outer)
        bar_row.pack(fill=tk.X)
        bar_row.columnconfigure(0, weight=1)
        bar_row.columnconfigure(1, minsize=40)

        self.progress = ttk.Progressbar(bar_row, orient="horizontal", mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.pct_label = tk.Label(
            bar_row, text="0%", font=("Segoe UI", 9), anchor="e", width=4
        )
        self.pct_label.grid(row=0, column=1, sticky="e")

        self._pending_step = None
        self._pending_pct  = None
        self._close_flag   = False

        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.update()

    def set_step(self, text: str, pct: float):
        self._pending_step = text
        self._pending_pct  = pct

    def pump(self) -> bool:
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


# ── Download helpers ──────────────────────────────────────────────────────────

def _download(url: str, dest: str, label: str):
    print(f"[Build] Downloading {label}...")
    req = urllib.request.Request(url, headers={"User-Agent": "JAM/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            with open(dest, "wb") as f:
                shutil.copyfileobj(response, f)
    except Exception as e:
        raise RuntimeError(f"Failed to download {label}: {e}")


def _decompress_bz2(bz2_path: str, dest_path: str):
    import bz2, tarfile
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


# ── DB schema ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS db_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    entry_id        INTEGER PRIMARY KEY,
    kanji_forms     TEXT,
    kana_forms      TEXT
);

CREATE TABLE IF NOT EXISTS senses (
    sense_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER NOT NULL,
    pos             TEXT,
    domain          TEXT,
    gloss           TEXT,
    example_jp      TEXT,
    example_en      TEXT,
    FOREIGN KEY (entry_id) REFERENCES entries(entry_id)
);

CREATE TABLE IF NOT EXISTS pitch_accent (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER,
    expression      TEXT NOT NULL,
    reading         TEXT NOT NULL,
    pitch_pattern   TEXT NOT NULL,
    pitch_category  TEXT,
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
    level           TEXT NOT NULL
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


# ── Structured-content helpers ────────────────────────────────────────────────

def _leaf_text(node) -> str:
    """Plain-text content of a node, skipping furigana rt tags and SVG."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(p for p in (_leaf_text(c) for c in node) if p).strip()
    if isinstance(node, dict):
        if node.get("tag") in ("svg", "path", "circle", "rt"):
            return ""
        return _leaf_text(node.get("content", ""))
    return ""


def _dc(node) -> str:
    """Returns node['data']['content'] or ''."""
    if isinstance(node, dict):
        return (node.get("data") or {}).get("content", "")
    return ""


def _flat(content) -> list:
    """Normalises content to a flat list."""
    if content is None:
        return []
    if isinstance(content, list):
        return content
    return [content]


def _parse_sense_group(sg: dict) -> list:
    """
    Parses a sense-group node (div or li with data.content="sense-group").
    Returns list of dicts: {pos, glosses, example_jp, example_en, domain}.
    """
    pos_parts   = []
    sense_nodes = []

    for child in _flat(sg.get("content")):
        dc = _dc(child)
        if dc == "part-of-speech-info":
            t = _leaf_text(child.get("content", ""))
            if t:
                pos_parts.append(t)
        elif dc == "sense":
            sense_nodes.append(child)
        elif child.get("tag") in ("ol", "ul") and not dc:
            # Jitendex wraps sense li nodes in an ol/ul with no data.content marker.
            # e.g. sense-group > ol > li[data.content="sense"]
            for li in _flat(child.get("content")):
                if isinstance(li, dict) and _dc(li) == "sense":
                    sense_nodes.append(li)

    pos_str = ", ".join(pos_parts)
    results = []

    for sense in sense_nodes:
        glosses    = []
        example_jp = None
        example_en = None
        domain     = ""

        for item in _flat(sense.get("content")):
            dc = _dc(item)

            if dc == "glossary":
                for li in _flat(item.get("content")):
                    if isinstance(li, dict):
                        text = _leaf_text(li.get("content", ""))
                    else:
                        text = _leaf_text(li)
                    if text:
                        glosses.append(text)

            elif dc in ("extra-info", "example", "examples"):
                jp, en = _find_example(item)
                if jp and not example_jp:
                    example_jp = jp
                    example_en = en

            elif dc in ("domain", "field"):
                domain = _leaf_text(item.get("content", ""))

        if glosses:
            results.append({
                "pos":        pos_str,
                "glosses":    glosses,
                "example_jp": example_jp,
                "example_en": example_en,
                "domain":     domain,
            })

    return results


def _find_example(node) -> tuple:
    """
    Recursively finds the first example-sentence node.
    Returns (japanese_str, english_str) or (None, None).
    """
    if isinstance(node, list):
        for child in node:
            jp, en = _find_example(child)
            if jp:
                return jp, en
        return None, None
    if not isinstance(node, dict):
        return None, None

    if _dc(node) == "example-sentence":
        jp_parts, en_parts = [], []
        _collect_lang(node.get("content", []), jp_parts, en_parts)
        jp = "".join(jp_parts).strip()
        en = "".join(en_parts).strip()
        return (jp or None), (en or None)

    for child in _flat(node.get("content")):
        jp, en = _find_example(child)
        if jp:
            return jp, en
    return None, None


def _collect_lang(node, jp: list, en: list):
    """Walk node tree, sorting text into jp/en by lang attribute."""
    if node is None:
        return
    if isinstance(node, str):
        jp.append(node)
        return
    if isinstance(node, list):
        for child in node:
            _collect_lang(child, jp, en)
        return
    if isinstance(node, dict):
        if node.get("tag") == "rt":
            return
        lang = node.get("lang", "")
        if lang == "en":
            en.append(_leaf_text(node))
        else:
            _collect_lang(node.get("content", []), jp, en)


def _parse_structured_content(sc: dict) -> list:
    """
    Parses one top-level structured-content object (field[5][0]).
    Handles both:
      - div[data.content="sense-group"]  (original structure)
      - ul[data.content="sense-groups"] > li[data.content="sense-group"]  (newer structure)
    Returns flat list of sense dicts.
    """
    senses = []
    for child in _flat(sc.get("content")):
        dc = _dc(child)
        if dc == "sense-group":
            # Original structure: sense-group directly in root content
            senses.extend(_parse_sense_group(child))
        elif dc == "sense-groups":
            # Newer structure: sense-groups container (ul) > sense-group items (li)
            for li in _flat(child.get("content")):
                if isinstance(li, dict) and _dc(li) == "sense-group":
                    senses.extend(_parse_sense_group(li))
    return senses


def _extract_pos_from_tags(tag_string: str) -> str:
    """Fallback POS from field[2] tag codes (often empty in Jitendex)."""
    TAG_MAP = {
        "n": "noun", "v1": "verb", "v5": "verb", "vk": "verb",
        "vs": "verb", "vi": "verb", "vt": "verb",
        "adj-i": "adjective", "adj-na": "adjective", "adj-no": "adjective",
        "adv": "adverb", "prt": "particle", "conj": "conjunction",
        "int": "interjection", "pref": "prefix", "suf": "suffix",
        "aux": "auxiliary", "aux-v": "auxiliary", "aux-adj": "auxiliary",
        "exp": "expression", "num": "numeral", "pn": "pronoun",
    }
    tags = tag_string.split() if tag_string else []
    seen = []
    for t in tags:
        m = TAG_MAP.get(t)
        if m and m not in seen:
            seen.append(m)
    return ", ".join(seen)


# ── Jitendex parser ───────────────────────────────────────────────────────────

def parse_jitendex(zip_path: str, conn: sqlite3.Connection):
    """
    Reads all term_bank_N.json files from the Jitendex Yomitan zip and
    populates entries + senses tables.

    Yomitan term bank entry format:
        [0] term         str
        [1] reading      str  (kana; may be "" if term is already kana)
        [2] def_tags     str  (often empty in Jitendex — POS is in structured-content)
        [3] rules        str  (conjugation rules, unused)
        [4] score        int  (unused)
        [5] definitions  list (one structured-content object per entry)
        [6] sequence     int  (stable entry ID)
        [7] term_tags    str  (JLPT tags etc.)
    """
    print("[Build] Parsing Jitendex zip...")
    cur = conn.cursor()

    kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    entries_map: dict = {}   # seq_id -> {kanji: set, kana: set}
    senses_rows = []

    jitendex_version = "unknown"
    with zipfile.ZipFile(zip_path, "r") as zf:
        if "index.json" in zf.namelist():
            with zf.open("index.json") as f:
                meta = json.load(f)
                jitendex_version = meta.get("revision", meta.get("version", "unknown"))

        term_banks = sorted(
            [n for n in zf.namelist() if re.match(r"term_bank_\d+\.json$", n)],
            key=lambda n: int(re.search(r"\d+", n).group()),
        )
        total_banks = len(term_banks)
        print(f"[Build] {total_banks} term bank file(s) found.")

        for bank_idx, bank_name in enumerate(term_banks):
            with zf.open(bank_name) as f:
                entries = json.load(f)

            for raw in entries:
                if len(raw) < 7:
                    continue

                term     = raw[0]
                reading  = raw[1] or raw[0]
                def_tags = raw[2]
                defs     = raw[5]
                seq_id   = raw[6]

                if seq_id not in entries_map:
                    entries_map[seq_id] = {"kanji": set(), "kana": set()}

                if kanji_re.search(term):
                    entries_map[seq_id]["kanji"].add(term)
                else:
                    entries_map[seq_id]["kana"].add(term)
                entries_map[seq_id]["kana"].add(reading)

                # Fallback POS from field[2] (often empty)
                fallback_pos = _extract_pos_from_tags(def_tags)

                for def_node in defs:
                    if isinstance(def_node, str):
                        gloss = def_node.strip()
                        if gloss:
                            senses_rows.append((seq_id, fallback_pos, "", gloss, None, None))
                        continue
                    if not isinstance(def_node, dict):
                        continue
                    if def_node.get("type") != "structured-content":
                        continue

                    parsed_senses = _parse_structured_content(def_node)

                    if not parsed_senses:
                        # Only fall back if there are genuinely no sense-groups
                        content = def_node.get("content", [])
                        has_sense_group = any(
                            isinstance(c, dict) and _dc(c) in ("sense-group", "sense-groups")
                            for c in _flat(content)
                        )
                        if not has_sense_group:
                            # Try to extract glossary list items directly
                            glosses_found = []
                            for child in _flat(content):
                                if isinstance(child, dict) and _dc(child) in ("glossary", "sense"):
                                    for li in _flat(child.get("content", [])):
                                        text = _leaf_text(li.get("content", "") if isinstance(li, dict) else li).strip()
                                        if text:
                                            glosses_found.append(text)
                            if glosses_found:
                                senses_rows.append((seq_id, fallback_pos, "", "; ".join(glosses_found), None, None))
                        continue

                    for s in parsed_senses:
                        pos   = s["pos"] or fallback_pos
                        domain = s["domain"]
                        gloss  = "; ".join(s["glosses"])
                        senses_rows.append((
                            seq_id, pos, domain, gloss,
                            s["example_jp"], s["example_en"],
                        ))

            if bank_idx % 10 == 0:
                print(f"[Build] Jitendex: processed {bank_idx+1}/{total_banks} banks...")

    print(f"[Build] Inserting {len(entries_map)} entries...")
    for seq_id, forms in entries_map.items():
        kanji_list = sorted(forms["kanji"])
        kana_list  = sorted(forms["kana"])
        cur.execute(
            "INSERT OR REPLACE INTO entries (entry_id, kanji_forms, kana_forms) VALUES (?,?,?)",
            (seq_id,
             json.dumps(kanji_list, ensure_ascii=False),
             json.dumps(kana_list,  ensure_ascii=False)),
        )

    print(f"[Build] Inserting {len(senses_rows)} senses...")
    cur.executemany(
        "INSERT INTO senses (entry_id, pos, domain, gloss, example_jp, example_en) VALUES (?,?,?,?,?,?)",
        senses_rows,
    )

    cur.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('jitendex_version', ?)",
        (jitendex_version,),
    )
    conn.commit()
    print(f"[Build] Jitendex: {len(entries_map)} entries, {len(senses_rows)} senses.")
    print(f"[Build] Jitendex version: {jitendex_version}")


# ── Pitch accent ──────────────────────────────────────────────────────────────

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
        rows,
    )
    conn.commit()
    print(f"[Build] Kanjium: inserted {len(rows)} pitch accent entries.")


# ── Frequency ─────────────────────────────────────────────────────────────────

def _parse_jpdb_freq(txt_path: str, conn: sqlite3.Connection):
    print("[Build] Parsing frequency list...")
    cur  = conn.cursor()
    rows = []
    with open(txt_path, encoding="utf-8") as f:
        for rank, line in enumerate(f, start=1):
            parts = line.strip().split("\t")
            if not parts or not parts[0].strip():
                continue
            rows.append((parts[0].strip(), rank))
    cur.executemany("INSERT INTO frequency (expression, frequency_rank) VALUES (?,?)", rows)
    conn.commit()
    print(f"[Build] Frequency: inserted {len(rows)} entries.")


# ── JLPT ──────────────────────────────────────────────────────────────────────

def _extract_jlpt_from_jitendex(zip_path: str, conn: sqlite3.Connection):
    """
    Jitendex carries JLPT level as term tags (field[7] of each bank entry).
    """
    print("[Build] Extracting JLPT levels from Jitendex...")
    cur = conn.cursor()
    rows = []

    JLPT_TAGS = {"jlpt-1": "N1", "jlpt-2": "N2", "jlpt-3": "N3",
                 "jlpt-4": "N4", "jlpt-5": "N5"}

    with zipfile.ZipFile(zip_path, "r") as zf:
        term_banks = sorted(
            [n for n in zf.namelist() if re.match(r"term_bank_\d+\.json$", n)],
            key=lambda n: int(re.search(r"\d+", n).group()),
        )
        for bank_name in term_banks:
            with zf.open(bank_name) as f:
                entries = json.load(f)
            for raw in entries:
                if len(raw) < 8:
                    continue
                term      = raw[0]
                term_tags = raw[7] if raw[7] else ""
                for tag, level in JLPT_TAGS.items():
                    if tag in term_tags.split():
                        rows.append((term, level))
                        break

    cur.executemany("INSERT INTO jlpt (expression, level) VALUES (?,?)", rows)
    conn.commit()
    print(f"[Build] JLPT: inserted {len(rows)} entries from Jitendex tags.")


# ── Tatoeba ───────────────────────────────────────────────────────────────────

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
        tatoeba_rows,
    )
    conn.commit()
    print(f"[Build] Tatoeba: inserted {len(tatoeba_rows)} sentence pairs.")

    print("[Build] Linking words to example sentences...")
    _link_tatoeba_to_entries(conn)


def _link_tatoeba_to_entries(conn: sqlite3.Connection):
    from collections import defaultdict
    cur = conn.cursor()
    print("[Build] Building sentence word index...")

    sentences = cur.execute("SELECT id, japanese FROM tatoeba").fetchall()

    index    = defaultdict(list)
    kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

    print(f"[Build] Indexing {len(sentences)} sentences...")
    for tat_id, japanese in sentences:
        seen = set()
        for i in range(len(japanese)):
            for length in range(2, 6):
                chunk = japanese[i:i+length]
                if len(chunk) == length and kanji_re.search(chunk) and chunk not in seen:
                    seen.add(chunk)
                    if len(index[chunk]) < 5:
                        index[chunk].append(tat_id)

    print("[Build] Matching entries to sentences...")
    entries = cur.execute("SELECT entry_id, kanji_forms, kana_forms FROM entries").fetchall()
    links   = []

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
        links,
    )
    conn.commit()
    print(f"[Build] Tatoeba links: created {len(links)} word↔sentence links.")


# ── Main build pipeline ───────────────────────────────────────────────────────

def build(progress_window: ProgressWindow = None):
    def step(label: str, pct: float):
        print(f"[Build] {label} ({int(pct)}%)")
        if progress_window:
            progress_window.set_step(label, pct)

    try:
        step("Creating database...", 2)
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA)
        conn.commit()

        # ── Downloads ──────────────────────────────────────────────────────
        download_steps = [
            ("jitendex",      5,  "Downloading Jitendex dictionary..."),
            ("kanjium",       14, "Downloading Kanjium pitch data..."),
            ("jpdb_freq",     18, "Downloading frequency list..."),
            ("tatoeba_jpn",   24, "Downloading Tatoeba Japanese sentences..."),
            ("tatoeba_eng",   32, "Downloading Tatoeba English sentences..."),
            ("tatoeba_links", 40, "Downloading Tatoeba links..."),
        ]

        for key, pct, label in download_steps:
            src  = SOURCES[key]
            dest = src["dest"]
            bz2  = src.get("bz2")

            step(label, pct)

            if not os.path.exists(dest):
                if bz2:
                    if not os.path.exists(bz2):
                        _download(src["url"], bz2, src["label"])
                    _decompress_bz2(bz2, dest)
                else:
                    _download(src["url"], dest, src["label"])
            else:
                print(f"[Build] {src['label']} already downloaded, skipping.")

        # ── Parse Jitendex ─────────────────────────────────────────────────
        step("Parsing Jitendex entries...", 44)
        parse_jitendex(SOURCES["jitendex"]["dest"], conn)

        # ── Pitch accent ───────────────────────────────────────────────────
        step("Parsing pitch accent data...", 62)
        _parse_kanjium(SOURCES["kanjium"]["dest"], conn)

        # ── Frequency ──────────────────────────────────────────────────────
        step("Parsing frequency list...", 70)
        _parse_jpdb_freq(SOURCES["jpdb_freq"]["dest"], conn)

        # ── JLPT from Jitendex tags ────────────────────────────────────────
        step("Extracting JLPT levels...", 74)
        _extract_jlpt_from_jitendex(SOURCES["jitendex"]["dest"], conn)

        # ── Tatoeba ────────────────────────────────────────────────────────
        step("Parsing Tatoeba sentences...", 78)
        _parse_tatoeba(
            SOURCES["tatoeba_jpn"]["dest"],
            SOURCES["tatoeba_eng"]["dest"],
            SOURCES["tatoeba_links"]["dest"],
            conn,
        )

        # ── Finalise ───────────────────────────────────────────────────────
        step("Finalising database...", 96)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('version', ?)",
            (DB_VERSION,),
        )
        cur.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('built_at', ?)",
            (str(int(time.time())),),
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


# ── Entry points ──────────────────────────────────────────────────────────────

def run_with_progress():
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
    if not os.path.exists(DB_PATH):
        return True
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute("SELECT value FROM db_meta WHERE key='version'").fetchone()
        conn.close()
        return (row is None or row[0] != DB_VERSION)
    except Exception:
        return True


if __name__ == "__main__":
    run_with_progress()