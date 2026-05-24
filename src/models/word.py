from dataclasses import dataclass
from typing import Optional, Dict, List, Any


@dataclass
class Word:
    # Basic properties from parser.py
    surface: str
    dictionary_form: str
    reading: str
    pos: str

    # Enriched properties from dictionary.py
    meaning: Optional[str] = None

    # Optional data (from audio.py)
    audio: Optional[str] = None

    # Metadata
    full_sentence: Optional[str] = None
    capture_path: Optional[str] = None

    # Additional dictionary data
    glossary: Optional[List[Dict[str, Any]]] = None
    pitch_pattern: Optional[str] = None
    pitch_category: Optional[str] = None
    frequency_rank: Optional[int] = None
    jlpt_level: Optional[int] = None
    example_sentences: Optional[List[Dict[str, Any]]] = None
    sentence_furigana: Optional[str] = None
    sense_groups: Optional[List[Dict[str, Any]]] = None
    jitendex_version: Optional[str] = None

    def is_valid(self) -> bool:
        if not all([self.surface, self.dictionary_form, self.reading, self.meaning]):
            return False
        if not self.full_sentence:
            print(f"[Word] Warning: '{self.surface}' missing full_sentence context")
        return True

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.surface} ({self.reading}): {self.meaning} [{self.pos}]"

    def update_from_dictionary(self, lookup_result: Optional[Dict[str, Any]]) -> None:
        if lookup_result is None:
            return
        self.meaning = lookup_result.get("main_definition")
        self.glossary = lookup_result.get("glossary")
        self.pitch_pattern = lookup_result.get("pitch_pattern")
        self.pitch_category = lookup_result.get("pitch_category")
        self.frequency_rank = lookup_result.get("frequency_rank")
        self.jlpt_level = lookup_result.get("jlpt_level")
        self.example_sentences = lookup_result.get("example_sentences")
        self.sense_groups = lookup_result.get("sense_groups")
        self.jitendex_version = lookup_result.get("jitendex_version")
        
    def best_sentence(self) -> str:
        """
        Returns the best available sentence for display and audio.
        Prefers OCR context, but only when it's actually a sentence
        (i.e. contains more than just the word itself).
        Falls back to Tatoeba, then Jitendex inline example.
        """
        ocr = self.full_sentence or ""
        if len(ocr.strip()) > 10:
            return ocr
        if self.example_sentences:
            tatoeba = self.example_sentences[0].get("japanese", "")
            if tatoeba:
                return tatoeba
        if self.glossary:
            jitendex = self.glossary[0].get("example_jp") or ""
            if jitendex:
                return jitendex
        return ocr  # last resort: bare word, better than empty