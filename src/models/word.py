from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Word:
    # Basic properties from parser.py
    surface: str
    dictionary_form: str
    reading: str
    pos: str

    # Enriched properties from dictionary.py
    meaning: Optional[str] # English translation

    # Optional data (from audio.py)
    audio: Optional[str] = None

    # Metadata
    full_sentence: Optional[str] = None # The full OCR sentence for context
    capture_path: Optional[str] = None # Path to the captured image (filled in by capture.py)

    # NEW: Additional dictionary data
    glossary: Optional[list[dict[str, str]]] = None # All definitions with POS/domain
    pitch_pattern: Optional[str] = None # Pitch accent pattern
    pitch_category: Optional[str] = None # Pitch accent type
    frequency_rank: Optional[int] = None # How common (1 = most common)
    jlpt_level: Optional[int] = None # JLPT level (1-4, N1-N4)
    example_sentences: Optional[list[dict[str, str]]] = None # Multiple examples
    sentence_furigana: Optional[str] = None # Furigana for the full sentence (for Anki card)

    def is_valid(self) -> bool:
        """
        Checks if the Word has minimum valid data for Anki card creation.
        - Must have: surface, dictionary_form, reading, meaning
        - Optional but helpful: audio
        """
        # Require basic fields
        if not all([self.surface, self.dictionary_form, self.reading, self.meaning]):
            return False
        
        # Log warning if missing context
        if not self.full_sentence:
            print(f"[Word] Warning: '{self.surface}' missing full_sentence context")
        
        return True
    
    def to_dict(self) -> dict[str, Optional[str]]:
      """Converts the Word dataclass to a dictionary."""
      from dataclasses import asdict
      return asdict(self)
    
    def __str__(self) -> str:
        """String representation of the Word."""
        return f"{self.surface} ({self.reading}): {self.meaning} [{self.pos}]"
    
    def update_from_dictionary(self, lookup_result: Dict[str, Any] | None) -> None:
        """
        Updates the Word object with enriched dictionary data.
        
        Args:
            lookup_result (dict): Result from dictionary.lookup()
        """
        if lookup_result is None:
            return
        
        self.meaning = lookup_result.get("main_definition")
        self.glossary = lookup_result.get("glossary")
        self.pitch_pattern = lookup_result.get("pitch_pattern")
        self.pitch_category = lookup_result.get("pitch_category")
        self.frequency_rank = lookup_result.get("frequency_rank")
        self.jlpt_level = lookup_result.get("jlpt_level")
        self.example_sentences = lookup_result.get("example_sentences")
        self.sentence_furigana = lookup_result.get("sentence_furigana")