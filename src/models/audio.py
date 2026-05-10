from dataclasses import dataclass
from typing import Optional

@dataclass(frozen = True) # immutable
class AudioFile:
    """Represents an audio file for a word"""
    word: str # word surface form (for reference, not necessarily used in filename)
    word_audio: str # path to the audio file of the word pronunciation 
    sentence_audio: Optional[str] = None # path to the audio file of the full sentence pronunciation (optional)

    def is_complete(self) -> bool:
        """Checks if the audio file has at least the word audio."""
        return bool(self.word_audio)