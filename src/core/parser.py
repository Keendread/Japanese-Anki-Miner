# Module for NLP and tokenizing sentences

from sudachipy import tokenizer, dictionary

_tokenizer = None
_tokenizer_lock = __import__("threading").Lock()


def get_tokenizer():
    """Returns the shared global SudachiPy tokenizer, loaded on the first call"""
    global _tokenizer
    with _tokenizer_lock:
        if _tokenizer is None:
            print("[Parser] Loading SudachiPy tokenizer...")
            _dict = dictionary.Dictionary(dict_type="full")
            _tokenizer = _dict.create(
                mode=tokenizer.Tokenizer.SplitMode.C
            )
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
        "surface":          target.surface(),
        "dictionary_form":  target.dictionary_form(),
        "reading":          target.reading_form(),
        "pos":              target.part_of_speech()[0],   # broad POS category
        "pos_detail":       target.part_of_speech()[1],   # finer POS detail
        "sentence":         text.strip(),                 # full OCR string as sentence context
    }
    
    print(f"[Parser] Target: {result['surface']} ({result['reading']}) "
          f"[{result['pos']}] → dict form: {result['dictionary_form']}")

    return result