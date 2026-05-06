# Module for NLP and tokenizing sentences

import threading
from sudachipy import tokenizer, dictionary
from src.models.word import Word

_parser_ready = threading.Event()

_tokenizer = None
_tokenizer_lock = __import__("threading").Lock()


def get_tokenizer():
    """Returns the shared global SudachiPy tokenizer, loaded on the first call"""
    global _tokenizer
    with _tokenizer_lock:
        if _tokenizer is None:
            print("[Parser] Loading SudachiPy tokenizer...")
            try:
                _dict = dictionary.Dictionary(dict_type="full")
            except ModuleNotFoundError:
                print("[Parser] sudachidict_full not found, falling back to core.")
                _dict = dictionary.Dictionary(dict_type="core")
 
            _tokenizer = _dict.create(mode=tokenizer.Tokenizer.SplitMode.C)
            _parser_ready.set()
            print("[Parser] Tokenizer ready.")
    return _tokenizer

def tokenize(text: str) -> list:
    """
    Splits a Japanese string into morpheme tokens using SudachiPy.

    Args:
        text (str): Japanese string from text extracted by ocr.py

    Returns:
        list: Morpheme Objects wich contain the following:
            .surface()              how it is shown in the original text
            .dictionary_form()      base/dictionary form
            .reading_form()         hiragana reading
            .part_of_speech()       tuple of POS tags
    """
    if not text or not text.strip():
        return []

    try:
        t = get_tokenizer()
        return t.tokenize(text)
    except Exception as e:
        print(f"[Parser] Tokenization failed: {e}")
        return []
    
def identify_target(morphemes: list, cursor_offset: int = 0):
    """
    Gives a list of morphemes for selection, returns the one at the cursor's position.
    If cursor_offset is 0 or unknown, returns the first content word found
    (skips particles, punctuation, whitespace)

    Args:
        morphemes (list):               List of SudachiPy morphemes from tokenize()
        cursor_offset (int, optional):  Character index within the OCR string where
                                        the cursor was positioned.
                                        
    Returns:
        Target SudachiPy morpheme, or None if nothing found
    """
    if not morphemes:
        return None

    # POS tags to skip (taken from SudachiPy documentation)
    SKIP_POS = {
        "助詞",      # particle  (は, が, を, に...)
        "助動詞",    # auxiliary verb
        "補助記号",  # punctuation
        "空白",      # whitespace
    }
    
    if cursor_offset > 0:
        char_pos = 0
        for morpheme in morphemes:
            char_pos += len(morpheme.surface())
            if char_pos >= cursor_offset:
                return morpheme
        return morphemes[-1]

    for morpheme in morphemes:
        pos = morpheme.part_of_speech()[0]
        if pos not in SKIP_POS:
            return morpheme

    return morphemes[0]

def build_sentence_furigana(morphemes: list) -> str:
    """
    Builds a SentenceFurigana string in Lapis format.
    Kanji-containing tokens become word[reading], kana-only tokens are plain.
 
    Example output: "完全[かんぜん]なる 空[くう]"
 
    Args:
        morphemes: List of SudachiPy morphemes
 
    Returns:
        Furigana-annotated sentence string
    """
    import re
    kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    parts = []
    for m in morphemes:
        surface = m.surface()
        reading = _kata_to_hira(m.reading_form())
        if kanji_re.search(surface) and reading and reading != surface:
            parts.append(f"{surface}[{reading}]")
        else:
            parts.append(surface)
    return "".join(parts)

def _kata_to_hira(text: str) -> str:
    """Converts katakana to hiragana."""
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c
        for c in text
    )

def parse(text: str, cursor_offset: int = 0) -> dict | None:
    """
    Main entry point for parser.py
    Takes extracted OCR text and returns a clean dict of the target word's data

    Args:
        text (str):                     raw extracted Japanese string from OCR
        cursor_offset (int, optional):  Character position of cursor within the string

    Returns:
        dict | None: dict with keys (surface, dictionary_form, reading, pos, sentence) | None
    """
    morphemes = tokenize(text)
    if not morphemes:
        print("[Parser] No morphemes found.")
        return None
    
    target = identify_target(morphemes, cursor_offset)
    if target is None:
        print("[Parser] Could not identify target word.")
        return None
    
    result = {
        "surface":           target.surface(),
        "dictionary_form":   target.dictionary_form(),
        "reading":           _kata_to_hira(target.reading_form()),
        "pos":               target.part_of_speech()[0],   # broad POS category
        "pos_detail":        target.part_of_speech()[1],   # finer POS detail
        "sentence":          text.strip(),
        "sentence_furigana": build_sentence_furigana(morphemes),
        "capture_path":      None,  # filled in by capture.py
    }
    
    print(f"[Parser] Target: {result['surface']} ({result['reading']}) "
          f"[{result['pos']}] → dict form: {result['dictionary_form']}")

    return result

def to_word_object(parse_result: dict) -> "Word":
    """Converts a parse result dict to a Word dataclass object."""
    return Word(
        surface=parse_result.get("surface", ""),
        dictionary_form=parse_result.get("dictionary_form", ""),
        reading=parse_result.get("reading", ""),
        pos=parse_result.get("pos", ""),
        meaning="",  # to be filled in by dictionary.py
        full_sentence=parse_result.get("sentence", "")
    )