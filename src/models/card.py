from dataclasses import dataclass
from typing import Optional, Dict
from models.word import Word


@dataclass
class Card:
    """
    Represents an Anki flashcard.
    Maps Word data -> Anki note fields.
    
    Anki fields (standard Japanese Mining Note):
        Word (expression): The Japanese word in kanji/hiragana
        Reading: Furigana reading (handled by AJT Japanese addon)
        Meaning: English definition
        Sentence: Full sentence with word highlighted
        Word Audio: Audio of the word
        Sentence Audio: Audio of the sentence
        Image: Context image (could also be a mnemonic?)
    
    Attributes:
        deck_name (str):        Anki deck to add card to
        word (Word):            The underlying Word object
        
        # Card fields (maps to Anki template)
        expression (str):       Japanese word
        reading (str):          Hiragana reading
        meaning (str):          English definition
        sentence (str):         Full sentence with context
        
        # Media
        word_audio (str):       Filepath or encoded audio for word
        sentence_audio (str):   Filepath or encoded audio for sentence
        image (str):            Filepath or encoded image
        
        # Metadata
        source_url (Optional[str]): Where the word came from (for tracking)
    """
    
    # Anki target
    deck_name: str
    
    # Core word data
    word: Optional[Word] = None
    
    # Mapped fields
    expression: str = ""
    reading: str = ""
    meaning: str = ""
    sentence: str = ""
    
    # Media
    word_audio: str = ""
    sentence_audio: str = ""
    image: str = ""
    
    # Metadata
    source_url: Optional[str] = None
    
    @classmethod
    def from_word(
        cls,
        word: Word,
        deck_name: str = "Japanese Mining",
    ) -> "Card":
        """
        Create a Card from a Word object.
        
        Args:
            word (Word): The enriched word with dictionary data
            deck_name (str): Anki deck to add to
        
        Returns:
            Card: A new Card instance
        """
        card = cls(
            deck_name=deck_name,
            word=word,
            expression=word.surface,
            reading=word.reading,
            meaning=word.definition,
            sentence=word.sentence,
            word_audio=word.word_audio_path or "",
            sentence_audio=word.sentence_audio_path or "",
            image=word.image_path or "",
        )
           
        return card
    
    def is_valid(self) -> bool:
        """
        Check if card has minimum required fields for Anki.
        Requires: expression, reading, meaning
        """
        return bool(self.word and self.word.is_complete())
    
    def to_anki_fields(self) -> Dict[str, str]:
        """
        Convert Card fields to Anki note field format.
        Returns dict mapping field name → value.
        
        Standard Japanese Mining Note fields:
            Front: Expression + Reading + Sentence
            Back: Meaning + Word Audio + Sentence Audio + Image
        """
        return {
            "Word": self.expression,
            "Reading": self.reading,
            "Meaning": self.meaning,
            "Sentence": self.sentence,
            "Word Audio": self.word_audio,
            "Sentence Audio": self.sentence_audio,
            "Image": self.image,
        }
    
    def to_dict(self) -> dict[str, str]:
        """
        Convert Card to dictionary (useful for JSON serialization).
        """
        return {
            "deck_name": self.deck_name,
            "expression": self.expression,
            "reading": self.reading,
            "meaning": self.meaning,
            "sentence": self.sentence,
            "word_audio": self.word_audio,
            "sentence_audio": self.sentence_audio,
            "image": self.image,
            "source_url": "" if not self.source_url else self.source_url,
        }
    
    def __str__(self) -> str:
        """Pretty print."""
        return (
            f"Card(expr={self.expression}, read={self.reading}, "
            f"mean={self.meaning[:20]}..., deck={self.deck_name})"
        )
    
    def __repr__(self) -> str:
        return self.__str__()
