import threading
from typing import Any, Optional
import joyokanji
from sudachipy import tokenizer, dictionary
from src.models.word import Word

_parser_ready: threading.Event = threading.Event()

_tokenizer: Optional[Any] = None
_tokenizer_lock: threading.Lock = __import__("threading").Lock()

def normalize_kanji(text: str) -> str:
    if not text:
        return text
    return joyokanji.convert(text, variants=True)


def get_tokenizer() -> Any:
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

def tokenize(text: str) -> list[Any]:
    if not text or not text.strip():
        return []

    text = normalize_kanji(text)

    try:
        t = get_tokenizer()
        return t.tokenize(text)
    except Exception as e:
        print(f"[Parser] Tokenization failed: {e}")
        return []
    
def identify_target(morphemes: list[Any], cursor_offset: int = 0) -> Optional[Any]:
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

def build_sentence_furigana(morphemes: list[Any]) -> str:
    import re
    kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    parts: list[Any] = []
    for m in morphemes:
        surface = m.surface()
        reading = _kata_to_hira(m.reading_form())
        if kanji_re.search(surface) and reading and reading != surface:
            if parts:
                parts.append(f" {surface}[{reading}]")
            else:
                parts.append(f"{surface}[{reading}]")
        else:
            parts.append(surface)
    return "".join(parts)

def _kata_to_hira(text: str) -> str:
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c
        for c in text
    )

def parse(text: str, cursor_offset: int = 0) -> Optional[dict[str, Any]]:
    morphemes = tokenize(text)
    if not morphemes:
        print("[Parser] No morphemes found.")
        return None
    
    target = identify_target(morphemes, cursor_offset)
    if target is None:
        print("[Parser] Could not identify target word.")
        return None
    
    result: dict[str, Any] = {
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

def to_word_object(parse_result: dict[str, Any]) -> Word:
    return Word(
        surface=parse_result.get("surface", ""),
        dictionary_form=parse_result.get("dictionary_form", ""),
        reading=parse_result.get("reading", ""),
        pos=parse_result.get("pos", ""),
        meaning="",  # to be filled in by dictionary.py
        full_sentence=parse_result.get("sentence", "")
    )