"""
Performance tests for Dictionary module (JMDICT lookup).
Target: < 50ms per lookup
"""

import time
import pytest
from src.models.word import Word
from src.core.dictionary import init, lookup


class TestDictionaryLatency:
    """Latency tests for dictionary lookup"""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_db(self):
        """Pre-initialize database connection"""
        try:
            init()
        except FileNotFoundError:
            pytest.skip("Dictionary DB not found - run data/build_db.py first")
        yield
    
    def test_lookup_simple_verb_latency(self):
        """
        Dictionary lookup latency for simple verb.
        Target: < 50ms
        """
        word = Word(
            surface="食べる",
            dictionary_form="食べる",
            reading="たべる",
            pos="動詞",
            meaning=None
        )
        
        start = time.perf_counter()
        result = lookup(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Dictionary] Lookup verb '食べる': {elapsed_ms:.2f}ms (target: 50ms)")
        assert elapsed_ms < 50, f"Lookup took {elapsed_ms:.2f}ms, exceeds 50ms target"
        assert result is not None
    
    def test_lookup_noun_latency(self):
        """
        Dictionary lookup latency for noun.
        Target: < 50ms
        """
        word = Word(
            surface="猫",
            dictionary_form="猫",
            reading="ねこ",
            pos="名詞",
            meaning=None
        )
        
        start = time.perf_counter()
        result = lookup(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Dictionary] Lookup noun '猫': {elapsed_ms:.2f}ms (target: 50ms)")
        assert elapsed_ms < 50, f"Lookup took {elapsed_ms:.2f}ms, exceeds 50ms target"
        assert result is not None
    
    def test_lookup_adjective_latency(self):
        """
        Dictionary lookup latency for adjective.
        Target: < 50ms
        """
        word = Word(
            surface="可愛い",
            dictionary_form="可愛い",
            reading="かわいい",
            pos="形容詞",
            meaning=None
        )
        
        start = time.perf_counter()
        result = lookup(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Dictionary] Lookup adjective '可愛い': {elapsed_ms:.2f}ms (target: 50ms)")
        assert elapsed_ms < 50, f"Lookup took {elapsed_ms:.2f}ms, exceeds 50ms target"
    
    def test_lookup_past_tense_latency(self):
        """
        Dictionary lookup for conjugated form (should be lemmatized).
        Target: < 50ms
        """
        word = Word(
            surface="食べた",
            dictionary_form="食べる",
            reading="たべた",
            pos="動詞",
            meaning=None
        )
        
        start = time.perf_counter()
        result = lookup(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Dictionary] Lookup conjugated '食べた': {elapsed_ms:.2f}ms (target: 50ms)")
        assert elapsed_ms < 50, f"Lookup took {elapsed_ms:.2f}ms, exceeds 50ms target"
    
    def test_lookup_rare_word_latency(self):
        """
        Dictionary lookup for less common word (worst case).
        Target: < 50ms
        """
        word = Word(
            surface="侘寂",
            dictionary_form="侘寂",
            reading="わびさび",
            pos="名詞",
            meaning=None
        )
        
        start = time.perf_counter()
        result = lookup(word)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Dictionary] Lookup rare word '侘寂': {elapsed_ms:.2f}ms (target: 50ms)")
        assert elapsed_ms < 50, f"Lookup took {elapsed_ms:.2f}ms, exceeds 50ms target"
    
    def test_lookup_consistency(self):
        """
        Run multiple lookups to check consistency.
        All runs should stay under 50ms.
        """
        word = Word(
            surface="走る",
            dictionary_form="走る",
            reading="はしる",
            pos="動詞",
            meaning=None
        )
        times = []
        
        for i in range(5):
            start = time.perf_counter()
            result = lookup(word)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 50, f"Run {i+1} took {elapsed_ms:.2f}ms, exceeds target"
        
        avg_ms = sum(times) / len(times)
        min_ms = min(times)
        max_ms = max(times)
        print(f"\n[Dictionary] Lookup consistency (5 runs):")
        print(f"  Average: {avg_ms:.2f}ms")
        print(f"  Min: {min_ms:.2f}ms")
        print(f"  Max: {max_ms:.2f}ms")
    
    def test_lookup_batch_latency(self):
        """
        Measure latency for batch of lookups (simulates typical session).
        Total should be < 50ms * 10 = 500ms for batch.
        """
        words = [
            Word(surface="今日", dictionary_form="今日", reading="きょう", pos="名詞", meaning=None),
            Word(surface="天気", dictionary_form="天気", reading="てんき", pos="名詞", meaning=None),
            Word(surface="いい", dictionary_form="いい", reading="いい", pos="形容詞", meaning=None),
            Word(surface="友達", dictionary_form="友達", reading="ともだち", pos="名詞", meaning=None),
            Word(surface="会う", dictionary_form="会う", reading="あう", pos="動詞", meaning=None),
        ]
        
        times = []
        for word in words:
            start = time.perf_counter()
            result = lookup(word)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 50, f"Lookup '{word.surface}' took {elapsed_ms:.2f}ms, exceeds target"
        
        total_ms = sum(times)
        avg_ms = total_ms / len(times)
        print(f"\n[Dictionary] Batch lookup (5 words):")
        print(f"  Total: {total_ms:.2f}ms")
        print(f"  Average per word: {avg_ms:.2f}ms")
        print(f"  Times: {[f'{t:.2f}ms' for t in times]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
