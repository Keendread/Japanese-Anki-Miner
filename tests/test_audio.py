from src.core.audio import fetch_audio 
from src.models.word import Word
from src.models.audio import AudioFile
from typing import Optional

async def test_fetch_audio():
    word1 = Word(
        surface = "食べる",
        dictionary_form = "食べる",
        reading = "たべる", # taberu 
        pos = "動詞",
        meaning = None)
    
    audio_file1: Optional[AudioFile] = await fetch_audio(word1)
    assert audio_file1 is not None
    
    word2 = Word(
        surface = "気をつけて", 
        dictionary_form = "気をつける", 
        reading = "きをつける", # kiotsukeru
        pos = "動詞",
        meaning = None)
    
    audio_file2: Optional[AudioFile] = await fetch_audio(word2)
    assert audio_file2 is not None
    
    word3 = Word(
        surface = "猫",
        dictionary_form = "猫",
        reading = "ねこ", # neko
        pos = "名詞",
        meaning = None)
    audio_file3: Optional[AudioFile] = await fetch_audio(word3)
    assert audio_file3 is not None

    word4 = Word(surface="食べた", dictionary_form="食べる", reading="たべる", 
            pos="動詞", meaning=None, full_sentence="昨日、寿司を食べた。", sentence_furigana="きのう、すしをたべた。") # kinou, sushi o tabeta
    audio_file4: Optional[AudioFile] = await fetch_audio(word4)
    assert audio_file4 is not None
    assert audio_file4.word_audio is not None
    assert audio_file4.sentence_audio is not None