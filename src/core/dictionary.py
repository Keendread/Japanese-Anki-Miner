# Module for dictionary lookup of words
# Lookup on primary dictionary JMDict but you can add additional fallback dictionaries

import os
import threading
from lxml import etree
from typing import Optional, Dict, List

_jmdict_cache = None
_cache_lock = threading.Lock()
_cache_ready = threading.Event()

# Get project root directory (one level up from src/core)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JMDICT_PATH = os.path.join(_PROJECT_ROOT, "data", "JMdict_e.xml")

def _load_jmdict() -> Dict[str, List[Dict[str, str]]]:
    """
    Parses JMdict XML file into an in-memory dict.
    Key: Japanese surface form (kanji or hiragana)
    Value: List of entry dicts with (definition, reading, pos)
    
    Returns:
        Dict[str, List[Dict]]: Cached dictionary database
    """
    if not os.path.exists(JMDICT_PATH):
        print(f"[Dictionary] WARNING: JMdict not found at {JMDICT_PATH}")
        print(f"[Dictionary] Download from: https://www.edrdg.org/jmdict/edict_doc.html")
        return {}
    
    print(f"[Dictionary] Loading JMdict from {JMDICT_PATH}...")
    cache: Dict[str, List[Dict[str, str]]] = {}
    
    try:
        tree = etree.parse(JMDICT_PATH)
        root = tree.getroot()
        
        entry_count = 0
        for entry in root.findall("entry"):
            # Get kanji + kana reading pairs
            kanji_elements = entry.findall("k_ele")
            kana_elements = entry.findall("r_ele")
            
            # Get definitions (senses = meanings)
            senses = entry.findall("sense")
            
            if not kanji_elements and not kana_elements:
                continue
            
            # For each kanji form (those with kanji)
            for k_ele in kanji_elements:
                kanji = k_ele.findtext("keb")
                if not kanji:
                    continue
                
                # Get primary kana reading (typically from first r_ele)
                reading = ""
                if kana_elements:
                    reading = kana_elements[0].findtext("reb", "")
                
                # Extract definitions from first sense only (most common)
                definition = ""
                pos_tag = ""
                if senses:
                    sense = senses[0]
                    
                    # Get POS (part of speech) tag
                    pos_elem = sense.find("pos")
                    if pos_elem is not None:
                        pos_tag = pos_elem.text or ""
                    
                    # Get first English gloss
                    gloss_elem = sense.find("gloss")
                    if gloss_elem is not None:
                        definition = gloss_elem.text or ""
                
                if kanji not in cache:
                    cache[kanji] = []
                
                cache[kanji].append({
                    "definition": definition,
                    "reading": reading,
                    "pos": pos_tag,
                    "kanji": kanji,
                })
                
                entry_count += 1
            
            # For each kana-only form (those with both hiragana/katakana)
            for r_ele in kana_elements:
                kana = r_ele.findtext("reb")
                if not kana or kana in cache:
                    continue
                
                definition = ""
                pos_tag = ""
                if senses:
                    sense = senses[0]
                    pos_elem = sense.find("pos")
                    if pos_elem is not None:
                        pos_tag = pos_elem.text or ""
                    gloss_elem = sense.find("gloss")
                    if gloss_elem is not None:
                        definition = gloss_elem.text or ""
                
                if kana not in cache:
                    cache[kana] = []
                
                cache[kana].append({
                    "definition": definition,
                    "reading": kana,
                    "pos": pos_tag,
                    "kanji": "",
                })
        
        print(f"[Dictionary] Loaded {entry_count} entries into cache.")
        _cache_ready.set()
        return cache
        
    except Exception as e:
        print(f"[Dictionary] Failed to parse JMdict: {e}")
        _cache_ready.set()
        return {}

def get_dictionary() -> Dict[str, List[Dict[str, str]]]:
    """
    Returns the loaded JMdict cache, loading on first call.
    Blocks until cache is ready.
    
    Returns:
        Dict[str, List[Dict]]: Word → list of definitions
    """
    global _jmdict_cache
    with _cache_lock:
        if _jmdict_cache is None:
            _jmdict_cache = _load_jmdict()
    return _jmdict_cache

def lookup(word: str) -> Optional[Dict[str, str]]:
    """
    Look up a Japanese word in JMdict.
    Returns the first (most common) entry.
    
    Args:
        word (str): Japanese word (kanji, hiragana, or katakana)
    
    Returns:
        Dict | None: {
            "definition": str,      # English definition
            "reading": str,         # Hiragana reading
            "pos": str,             # Part of speech (e.g., "noun", "verb")
            "kanji": str,           # Kanji form (if applicable)
        }
        or None if not found
    """
    if not word or not word.strip():
        return None
    
    word = word.strip()
    
    # First time: may need to wait for load
    dictionary = get_dictionary()
    
    if word in dictionary and dictionary[word]:
        return dictionary[word][0]  # Return most common entry
    
    return None

def lookup_all(word: str) -> List[Dict[str, str]]:
    """
    Look up a Japanese word and return ALL entries (multiple definitions).
    
    Args:
        word (str): Japanese word
    
    Returns:
        List[Dict]: List of all matching entries, or [] if not found
    """
    if not word.strip():
        return []
    
    word = word.strip()
    dictionary = get_dictionary()
    
    return dictionary.get(word, [])

def is_ready() -> bool:
    """Check if JMdict is fully loaded."""
    return _cache_ready.is_set()