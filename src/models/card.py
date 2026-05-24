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
    image_filename: Optional[str] = None    # Media filename for card image
    
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
        glossary_html = Card._build_glossary_html(
            word.glossary or [],
            sense_groups=getattr(word, "sense_groups", None),
            jitendex_version=getattr(word, "jitendex_version", None),
            target_word=word.surface,
        )
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
        display_sentence = None
        if word.example_sentences:
            display_sentence = word.example_sentences[0].get("japanese", "")
        elif word.full_sentence:
            display_sentence = word.full_sentence

        if display_sentence:
            sentence_cloze = Card._build_sentence_cloze(display_sentence, word.surface)
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
    def _build_glossary_html(
        glossary: List[Dict[str, Any]],
        sense_groups: Optional[List[Dict[str, Any]]] = None,
        jitendex_version: Optional[str] = None,
        target_word: Optional[str] = None,
    ) -> str:
        """
        Router: uses Jitendex-style grouped HTML when sense_groups are available,
        otherwise falls back to the flat legacy format.
        """
        if sense_groups:
            return Card._build_jitendex_glossary(sense_groups, jitendex_version, target_word)
        if not glossary:
            return ""
        return Card._build_flat_glossary(glossary)


    @staticmethod
    def _build_jitendex_glossary(
        sense_groups: List[Dict[str, Any]],
        version: Optional[str],
        target_word: Optional[str],
    ) -> str:
        """
        Builds Yomitan/Jitendex-style glossary HTML:

            (Jitendex.org [version])
            [noun]  • gloss 1
                    • gloss 2
            ┃ 転校生は先生の... (1.3em, ruby)
            The new boy made up...  (0.8em)
        """
        ver_label = f"Jitendex.org [{version}]" if version else "Jitendex.org"
        group_parts = []

        for group in sense_groups:
            pos     = group.get("pos", "")
            domain  = group.get("domain", "")
            glosses = group.get("glosses", [])
            ex_jp   = group.get("example_jp", "")        # plain text, for keyword match
            ex_ruby = group.get("example_furigana", "")  # <ruby> HTML
            ex_en   = group.get("example_en", "")

            # POS badge
            pos_badge = ""
            if pos:
                first_pos = pos.split(",")[0].strip()
                pos_badge = (
                    f'<span style="font-weight:bold;font-size:0.8em;color:white;'
                    f'background-color:rgb(86,86,86);vertical-align:text-bottom;'
                    f'border-radius:0.3em;margin-right:0.25em;padding:0.2em 0.3em;'
                    f'word-break:keep-all;">{first_pos}</span>'
                )

            # Domain tag
            domain_html = ""
            if domain:
                domain_html = (
                    f'<span style="font-size:0.8em;color:#888;'
                    f'margin-right:0.25em;">[{domain}]</span>'
                )

            # Gloss bullet list
            gloss_items = "".join(f"<li>{g}</li>" for g in glosses)
            gloss_html = (
                f'<ul data-sc-content="glossary" '
                f'style="margin:0.2em 0 0.2em 1.2em;padding:0;">'
                f'{gloss_items}</ul>'
            )

            # Example sentence block
            # Strategy: highlight the target keyword in the *plain* example text,
            # then replace that plain span with a highlighted ruby span if ruby exists.
            example_html = ""
            if ex_jp:
                if target_word and target_word in ex_jp and ex_ruby:
                    # Build ruby HTML but wrap the target word's ruby tags in a highlight span.
                    # Since ruby is built morpheme-by-morpheme, we find the target in the
                    # plain text and apply the color to the matching ruby segment.
                    highlighted_ruby = Card._highlight_keyword_in_ruby(
                        ex_ruby, ex_jp, target_word)
                elif ex_ruby:
                    highlighted_ruby = ex_ruby
                else:
                    highlighted_ruby = ex_jp  # plain fallback

                en_html = (
                    f'<div data-sc-content="example-sentence-b" '
                    f'style="font-size:0.8em;">{ex_en}</div>'
                ) if ex_en else ""

                example_html = (
                    f'<div data-sc-content="extra-info" style="margin-left:0.5em;">'
                    f'<div data-sc-content="example-sentence" style="'
                    f'background-color:color-mix(in srgb,var(--text-color,#333) 5%,transparent);'
                    f'border-color:var(--text-color,#333);'
                    f'border-style:none none none solid;border-radius:0.4rem;'
                    f'border-width:0.21rem;margin-top:0.5rem;margin-bottom:0.5rem;'
                    f'padding:0.5rem;">'
                    f'<div data-sc-content="example-sentence-a" lang="ja" '
                    f'style="font-size:1.3em;">{highlighted_ruby}</div>'
                    f'{en_html}'
                    f'</div></div>'
                )

            group_parts.append(
                f'<div style="margin-bottom:0.5em;">'
                f'{pos_badge}{domain_html}'
                f'{gloss_html}'
                f'{example_html}'
                f'</div>'
            )

        body = "".join(group_parts)
        return (
            f'<div style="text-align:left;" class="yomitan-glossary">'
            f'<ol><li data-dictionary="{ver_label}">'
            f'<i>({ver_label})</i> '
            f'<span>{body}</span>'
            f'</li></ol></div>'
        )


    @staticmethod
    def _highlight_keyword_in_ruby(ruby_html: str, plain_text: str, keyword: str) -> str:
        """
        Highlights the target keyword inside pre-built <ruby> HTML.

        Approach: find which characters of plain_text are covered by the keyword,
        then wrap the corresponding ruby tags with a highlight <span>.

        Falls back to wrapping the entire keyword's plain text if the ruby
        structure can't be matched (e.g. the keyword spans multiple morphemes
        or is kana-only and appears verbatim in the ruby HTML).
        """
        import re

        # Simple case: keyword appears verbatim in ruby HTML (kana-only or already there)
        if keyword in ruby_html:
            highlighted = ruby_html.replace(
                keyword,
                f'<span data-sc-content="example-keyword" '
                f'style="color:color-mix(in srgb,lime,var(--text-color,#333));">'
                f'{keyword}</span>',
                1,
            )
            return highlighted

        # General case: keyword spans one or more <ruby> tags.
        # Strategy: tokenise the ruby HTML into a list of segments
        # (each segment is either a <ruby>…</ruby> block or a plain text chunk),
        # map each segment back to its plain-text characters, find which segments
        # are covered by the keyword, then wrap those segments in a highlight span.
        segment_re = re.compile(r'(<ruby>.*?</ruby>|[^<]+)', re.DOTALL)
        segments = segment_re.findall(ruby_html)

        # Build a mapping: segment index → plain characters it represents
        seg_plain = []
        for seg in segments:
            if seg.startswith("<ruby>"):
                # Extract surface text (first text node inside <ruby>, before <rt>)
                surface_match = re.match(r'<ruby>(.*?)<rt>', seg)
                seg_plain.append(surface_match.group(1) if surface_match else seg)
            else:
                seg_plain.append(seg)

        # Find start/end char offsets of keyword in plain_text
        idx = plain_text.find(keyword)
        if idx == -1:
            return ruby_html  # keyword not found, return unchanged

        kw_start = idx
        kw_end   = idx + len(keyword)

        # Walk segments accumulating char positions, mark which are inside keyword
        char_pos  = 0
        in_kw     = []
        for plain in seg_plain:
            seg_start = char_pos
            seg_end   = char_pos + len(plain)
            overlap   = seg_start < kw_end and seg_end > kw_start
            in_kw.append(overlap)
            char_pos  = seg_end

        if not any(in_kw):
            return ruby_html  # no overlap found

        # Rebuild HTML, wrapping matched segments
        OPEN  = (
            '<span data-sc-content="example-keyword" '
            'style="color:color-mix(in srgb,lime,var(--text-color,#333));">'
        )
        CLOSE = '</span>'

        result_parts = []
        in_span = False
        for seg, matched in zip(segments, in_kw):
            if matched and not in_span:
                result_parts.append(OPEN)
                in_span = True
            elif not matched and in_span:
                result_parts.append(CLOSE)
                in_span = False
            result_parts.append(seg)
        if in_span:
            result_parts.append(CLOSE)

        return "".join(result_parts)


    @staticmethod
    def _build_flat_glossary(glossary: List[Dict[str, Any]]) -> str:
        """Fallback flat glossary for non-Jitendex sources or Basic note type."""
        items = []
        for sense in glossary:
            pos   = sense.get("pos", "")
            gloss = sense.get("gloss", "")
            pos_tag = ""
            if pos:
                first_pos = pos.split(",")[0].strip()
                pos_tag = (
                    f'<span style="font-weight:bold;font-size:0.8em;color:white;'
                    f'background-color:#565656;border-radius:0.3em;'
                    f'padding:0.2em 0.3em;margin-right:0.25em;">{first_pos}</span>'
                )
            items.append(f"<li>{pos_tag}{gloss}</li>")
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
        if not surface or surface not in sentence:
            return sentence

        kanji_re = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

        pattern = re.compile(
            r'( ?)(' + re.escape(surface) + r'(?:\[[^\]]*\])?)'
        )

        def _wrap(m: re.Match) -> str:
            start = m.start(2)
            end   = m.end(2)
            # Reject if immediately preceded by kanji (mid-compound)
            if start > 0 and kanji_re.match(sentence[start - 1]):
                return m.group(0)
            # Reject if immediately followed by kanji with no space/bracket (mid-compound)
            if end < len(sentence) and kanji_re.match(sentence[end]) and '[' not in m.group(2):
                return m.group(0)
            return f'{m.group(1)}<b>{m.group(2)}</b>'

        return pattern.sub(_wrap, sentence, count=1)
    
    def to_anki_format(self) -> Dict[str, str]:
        """
        Converts Card to Anki's field format.
        
        Returns different field structures based on note_type.
        This is the interface between Card and AnkiConnect.
        
        Returns:
            Dictionary mapping field names to field values
        """
        word = self.source_word
        freq_display = str(self.frequency_rank) if self.frequency_rank else ""

        display_sentence = word.best_sentence()
        sentence_cloze = Card._build_sentence_cloze(display_sentence, word.surface) if display_sentence else ""

        return {
            "Expression":         word.surface,
            "ExpressionFurigana": self._build_front_generic(word),
            "ExpressionReading":  word.reading,
            "MainDefinition":     self.glossary_html or "",
            "Sentence":           sentence_cloze,
            "SentenceFurigana": Card._build_sentence_cloze(
                        word.sentence_furigana or "",
                        word.surface,
                    ),
            "PitchPosition":      str(word.pitch_pattern)  if word.pitch_pattern  else "",
            "PitchCategories":    str(word.pitch_category) if word.pitch_category else "",
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
