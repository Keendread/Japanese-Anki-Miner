"""
Card data model for Anki flashcards.
Transforms Word objects into Anki-ready cards with proper formatting.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from datetime import datetime
import re

from src.models.word import Word


@dataclass(frozen=True)
class Card:
    """
    Immutable Anki flashcard representation.
    
    A Card encapsulates all information needed to create an Anki note.
    Once created, it cannot be modified, ensuring data integrity.
    """
    
    # Core card content
    front: str                              # Question side
    back: str                               # Answer side
    
    # Metadata
    tags: List[str]                         # Card tags for organization
    source_word: Word                       # Original Word object
    note_type: str                          # Anki note type (e.g., "Basic", "Lapis")
    created_at: str                         # ISO timestamp
    
    # Optional fields for richer cards
    glossary_html: Optional[str] = None     # Full glossary with formatting
    sentence_cloze: Optional[str] = None    # Sentence with target word highlighted
    pitch_pattern: Optional[str] = None     # Pitch accent pattern
    frequency_rank: Optional[int] = None    # Word frequency ranking
    
    @staticmethod
    def from_word(word: Word, settings: Dict[str, Any]) -> "Card":
        """
        Factory method: Creates a Card from a Word object.
        
        This is the main entry point for card creation. It applies all formatting
        rules and converts linguistic data into a readable flashcard.
        
        Args:
            word: Enriched Word object from the pipeline
            settings: Settings dict with anki_note_type, etc.
            
        Returns:
            Fully formatted and validated Card object
            
        Raises:
            ValueError: If word is invalid or cannot be converted
        """
        if not word.is_valid():
            raise ValueError(f"Word '{word.surface}' is invalid and cannot create a card")
        
        note_type: str = settings.get("anki_note_type", "Basic")
        
        # Build card based on note type
        if note_type == "Basic":
            front = Card._build_front_basic(word)
            back = Card._build_back_basic(word)
        else:
            # For Lapis or other custom types, use generic format
            front = Card._build_front_generic(word)
            back = Card._build_back_generic(word)
        
        # Build shared formatting
        glossary_html = Card._build_glossary_html(word.glossary or [])
        sentence_cloze = Card._build_sentence_cloze(word.full_sentence or "", word.surface)
        
        # Create card
        card = Card(
            front=front,
            back=back,
            tags=["JAM"],  # Default tag
            source_word=word,
            note_type=note_type,
            created_at=datetime.now().isoformat(),
            glossary_html=glossary_html,
            sentence_cloze=sentence_cloze,
            pitch_pattern=word.pitch_pattern,
            frequency_rank=word.frequency_rank,
        )
        
        if not card.is_valid():
            raise ValueError(f"Created card for '{word.surface}' failed validation")
        
        return card
    
    @staticmethod
    def _build_front_basic(word: Word) -> str:
        """Builds front for Basic note type: Japanese word with reading."""
        return f"{word.surface} ({word.reading})"
    
    @staticmethod
    def _build_front_generic(word: Word) -> str:
        """Builds front with furigana notation when kanji present."""
        kanji_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
        if kanji_re.search(word.surface) and word.reading and word.reading != word.surface:
            return f"{word.surface}[{word.reading}]"
        return word.surface
    
    @staticmethod
    def _build_back_basic(word: Word) -> str:
        """Builds back for Basic note type with meaning, glossary, and context."""
        parts: List[str] = []
        
        # Main definition (bold)
        if word.meaning:
            parts.append(f"<b>{word.meaning}</b>")
        
        # Glossary with all definitions
        glossary_html = Card._build_glossary_html(word.glossary or [])
        if glossary_html:
            parts.append(glossary_html)
        
        # Example sentence if available
        if word.full_sentence:
            sentence_cloze = Card._build_sentence_cloze(word.full_sentence, word.surface)
            parts.append(f"<i>{sentence_cloze}</i>")
        
        # Metadata (small text)
        metadata_parts: List[str] = []
        if word.frequency_rank:
            metadata_parts.append(f"Freq: #{word.frequency_rank}")
        if word.pitch_pattern:
            metadata_parts.append(f"Pitch: {word.pitch_pattern} ({word.pitch_category})")
        if word.jlpt_level:
            metadata_parts.append(f"JLPT: N{word.jlpt_level}")
        
        if metadata_parts:
            parts.append(f"<small>{' | '.join(metadata_parts)}</small>")
        
        return "<br>".join(parts)
    
    @staticmethod
    def _build_back_generic(word: Word) -> str:
        """Builds back for generic/Lapis note types."""
        return Card._build_back_basic(word)  # Same for now
    
    @staticmethod
    def _build_glossary_html(glossary: List[Dict[str, Any]]) -> str:
        """
        Builds formatted HTML glossary from sense dictionaries.
        
        Args:
            glossary: List of sense dicts with gloss, pos, domain, examples
            
        Returns:
            HTML ordered list of definitions
        """
        if not glossary:
            return ""
        
        items: List[str] = []
        for sense in glossary:
            pos: str = sense.get("pos", "")
            gloss: str = sense.get("gloss", "")
            domain: str = sense.get("domain", "")
            
            # Format POS tag
            pos_tag = ""
            if pos:
                first_pos = pos.split(",")[0].strip()
                pos_tag = (
                    f'<span style="font-weight:bold;font-size:0.8em;'
                    f'color:white;background-color:#565656;'
                    f'border-radius:0.3em;padding:0.2em 0.3em;'
                    f'margin-right:0.25em;">{first_pos}</span>'
                )
            
            # Format domain tag
            domain_tag = ""
            if domain:
                domain_tag = (
                    f'<span style="font-size:0.8em;color:#888;'
                    f'margin-right:0.25em;">[{domain}]</span>'
                )
            
            items.append(f"<li>{pos_tag}{domain_tag}{gloss}</li>")
        
        return f'<div class="jam-glossary"><ol>{"".join(items)}</ol></div>'
    
    @staticmethod
    def _build_sentence_cloze(sentence: str, surface: str) -> str:
        """
        Wraps target word in sentence with <b> tags for emphasis.
        
        Args:
            sentence: Full sentence context
            surface: Target word to highlight
            
        Returns:
            Sentence HTML with target word bolded
        """
        if surface and surface in sentence:
            return sentence.replace(surface, f"<b>{surface}</b>", 1)
        return sentence
    
    def to_anki_format(self) -> Dict[str, str]:
        """
        Converts Card to Anki's field format.
        
        Returns different field structures based on note_type.
        This is the interface between Card and AnkiConnect.
        
        Returns:
            Dictionary mapping field names to field values
        """
        if self.note_type == "Basic":
            return {
                "Front": self.front,
                "Back": self.back,
            }
        
        # For Lapis or custom types - extended fields
        word = self.source_word
        freq_display = str(self.frequency_rank) if self.frequency_rank else ""
        
        return {
            "Expression": word.surface,
            "ExpressionFurigana": self._build_front_generic(word),
            "ExpressionReading": word.reading,
            "MainDefinition": word.meaning or "",
            "Glossary": self.glossary_html or "",
            "Sentence": self.sentence_cloze or (word.full_sentence or ""),
            "SentenceFurigana": word.sentence_furigana or "",
            "PitchPosition": self.pitch_pattern or "",
            "PitchCategories": word.pitch_category or "",
            "Frequency": freq_display,
            "FreqSort": freq_display,
            "MiscInfo": "JAM",
            "ExpressionAudio": "",
            "SentenceAudio": "",
            "Picture": "",
            "DefinitionPicture": "",
            "SelectionText": word.surface,
        }
    
    def to_json(self) -> Dict[str, Any]:
        """
        Converts Card to JSON-serializable format for logging/storage.
        
        Returns:
            Dictionary with all card data in serializable format
        """
        return {
            "front": self.front,
            "back": self.back,
            "tags": self.tags,
            "note_type": self.note_type,
            "created_at": self.created_at,
            "source": {
                "surface": self.source_word.surface,
                "dictionary_form": self.source_word.dictionary_form,
                "reading": self.source_word.reading,
            },
        }
    
    def is_valid(self) -> bool:
        """
        Validates that the card has all required fields.
        
        Returns:
            True if card is complete and ready for Anki
        """
        # Required fields
        if not self.front or not self.back:
            return False
        
        # Tags should be non-empty
        if not self.tags:
            return False
        
        # Source word must be valid
        if not self.source_word or not self.source_word.is_valid():
            return False
        
        return True
