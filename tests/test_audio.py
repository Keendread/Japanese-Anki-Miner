"""
Performance tests for Audio module (VOICEVOX audio synthesis).
Target: < 500ms for audio fetch (word + optional sentence concurrently)

Requires VOICEVOX server running at http://localhost:50021
"""

import time
import pytest
import asyncio
from src.core.audio import fetch_audio 
from src.models.word import Word
from src.models.audio import AudioFile
from typing import Optional


async def test_fetch_audio():
    """Functional test: Audio fetch for various word types"""
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


class TestAudioLatency:
    """Latency tests for audio synthesis"""
    
    @pytest.mark.asyncio
    async def test_fetch_single_word_audio_latency(self):
        """
        Audio fetch latency for single word (no sentence).
        Target: < 500ms
        """
        word = Word(
            surface="食べる",
            dictionary_form="食べる",
            reading="たべる",
            pos="動詞",
            meaning=None
        )
        
        start = time.perf_counter()
        audio_file = await fetch_audio(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Audio] Single word fetch: {elapsed_ms:.2f}ms (target: 500ms)")
        assert elapsed_ms < 500, f"Audio fetch took {elapsed_ms:.2f}ms, exceeds 500ms target"
        assert audio_file is not None
        assert audio_file.word_audio is not None
    
    @pytest.mark.asyncio
    async def test_fetch_word_and_sentence_latency(self):
        """
        Audio fetch latency for word + sentence (concurrent).
        Concurrent fetch should take ~same as single word (async parallelism).
        Target: < 500ms (should be barely slower than single word due to concurrent fetch)
        """
        word = Word(
            surface="食べる",
            dictionary_form="食べる",
            reading="たべる",
            pos="動詞",
            meaning=None,
            full_sentence="昨日、公園で友達と一緒にご飯を食べた。",
            sentence_furigana="きのう、こうえんでともだちといっしょにごはんをたべた。"
        )
        
        start = time.perf_counter()
        audio_file = await fetch_audio(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Audio] Word + sentence concurrent fetch: {elapsed_ms:.2f}ms (target: 500ms)")
        assert elapsed_ms < 500, f"Audio fetch took {elapsed_ms:.2f}ms, exceeds 500ms target"
        assert audio_file is not None
        assert audio_file.word_audio is not None
        assert audio_file.sentence_audio is not None
    
    @pytest.mark.asyncio
    async def test_fetch_short_word_latency(self):
        """
        Audio fetch latency for short word (fastest case).
        Target: < 500ms
        """
        word = Word(
            surface="猫",
            dictionary_form="猫",
            reading="ねこ",
            pos="名詞",
            meaning=None
        )
        
        start = time.perf_counter()
        audio_file = await fetch_audio(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Audio] Short word fetch: {elapsed_ms:.2f}ms (target: 500ms)")
        assert elapsed_ms < 500, f"Audio fetch took {elapsed_ms:.2f}ms, exceeds 500ms target"
        assert audio_file is not None
    
    @pytest.mark.asyncio
    async def test_fetch_long_word_latency(self):
        """
        Audio fetch latency for longer word.
        Target: < 500ms
        """
        word = Word(
            surface="気をつけて",
            dictionary_form="気をつける",
            reading="きをつける",
            pos="動詞",
            meaning=None
        )
        
        start = time.perf_counter()
        audio_file = await fetch_audio(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Audio] Long word fetch: {elapsed_ms:.2f}ms (target: 500ms)")
        assert elapsed_ms < 500, f"Audio fetch took {elapsed_ms:.2f}ms, exceeds 500ms target"
        assert audio_file is not None
    
    @pytest.mark.asyncio
    async def test_fetch_consistency(self):
        """
        Run audio fetch multiple times to check consistency.
        All runs should stay under 500ms.
        """
        word = Word(
            surface="日本",
            dictionary_form="日本",
            reading="にほん",
            pos="名詞",
            meaning=None
        )
        times = []
        
        for i in range(3):
            start = time.perf_counter()
            audio_file = await fetch_audio(word)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 500, f"Run {i+1} took {elapsed_ms:.2f}ms, exceeds target"
            assert audio_file is not None
        
        avg_ms = sum(times) / len(times)
        print(f"\n[Audio] Fetch consistency (3 runs):")
        print(f"  Average: {avg_ms:.2f}ms")
        print(f"  Individual times: {[f'{t:.2f}ms' for t in times]}")