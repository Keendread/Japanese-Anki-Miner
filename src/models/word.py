from dataclasses import dataclass
from typing import Optional


@dataclass
class Word:
    """
    Represents a Japanese word extracted from OCR and enriched with dictionary data.
    
    Attributes:
        surface (str):          How the word appears in the original text (e.g., "日本語")
        dictionary_form (str):  Dictionary/base form (e.g., "日本語")
        reading (str):          Hiragana reading (e.g., "にほんご")
        pos (str):              Part of speech from SudachiPy (e.g., "noun")
        pos_detail (str):       Detailed POS tag from SudachiPy
        
        # Dictionary-sourced fields
        definition (str):       English definition from JMdict (e.g., "Japanese language")
        definition_pos (str):   POS from JMdict (may differ from SudachiPy)
        
        # Sentence context
        sentence (str):         Full sentence/OCR string containing this word
        
        # Media
        word_audio_path (Optional[str]):    Path to word audio file
        sentence_audio_path (Optional[str]): Path to sentence audio file
        image_path (Optional[str]):          Path to image file

    """
    
    surface: str
    dictionary_form: str
    reading: str
    pos: str
    pos_detail: str = ""
    
    definition: str = ""
    definition_pos: str = ""
    
    sentence: str = ""
    
    word_audio_path: Optional[str] = None
    sentence_audio_path: Optional[str] = None
    image_path: Optional[str] = None
    
    def is_complete(self) -> bool:
        """
        Check if word has minimum required fields for card creation.
        Returns True if: surface, reading, definition are all present.

        _Easily modifiable by adding more fields or changing requirements in the future._
        """
        
        return (not self.surface.strip()) or (not self.reading.strip()) or (not self.definition.strip())
    
    def to_dict(self) -> dict:
        """
        Convert Word to dictionary (useful for JSON serialization).
        """
        return {
            "surface": self.surface,
            "dictionary_form": self.dictionary_form,
            "reading": self.reading,
            "pos": self.pos,
            "pos_detail": self.pos_detail,
            "definition": self.definition,
            "definition_pos": self.definition_pos,
            "sentence": self.sentence,
            "word_audio_path": self.word_audio_path,
            "sentence_audio_path": self.sentence_audio_path,
            "image_path": self.image_path
        }
    
    def __str__(self) -> str:
        """ Pretty print for debugging. """
        return (
            f"Word(surface={self.surface}, reading={self.reading}, "
            f"def={self.definition[:30]}..., pos={self.pos})"
        )
    
    def __repr__(self) -> str:
        return self.__str__()
