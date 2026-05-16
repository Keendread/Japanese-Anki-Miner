"""
Performance tests for Parser module (SudachiPy tokenization).
Target: < 100ms for tokenization + parsing
"""

import time
import pytest
from src.core.parser import tokenize, parse, get_tokenizer


class TestParserLatency:
    """Latency tests for tokenization and parsing"""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_tokenizer(self):
        """Pre-load tokenizer once for all tests"""
        get_tokenizer()
        yield
    
    def test_tokenize_single_word_latency(self):
        """
        Tokenization latency for single word.
        Target: < 100ms (primarily tokenization)
        """
        text = "食べる"
        
        start = time.perf_counter()
        tokens = tokenize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Tokenize single word: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Tokenization took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert len(tokens) > 0
    
    def test_tokenize_short_sentence_latency(self):
        """
        Tokenization latency for short sentence.
        Target: < 100ms
        """
        text = "今日は天気がいい"
        
        start = time.perf_counter()
        tokens = tokenize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Tokenize short sentence: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Tokenization took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert len(tokens) > 0
    
    def test_tokenize_long_sentence_latency(self):
        """
        Tokenization latency for longer sentence.
        Target: < 100ms
        """
        text = "昨日公園で友達と会って、一緒にコーヒーを飲みました。"
        
        start = time.perf_counter()
        tokens = tokenize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Tokenize long sentence: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Tokenization took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert len(tokens) > 0
    
    def test_parse_with_single_word_latency(self):
        """
        Full parse (tokenize + identify target + build furigana) latency for single word.
        Target: < 100ms (total parsing operations)
        """
        text = "食べる"
        
        start = time.perf_counter()
        result = parse(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Parse single word: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Parse took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert result is not None
    
    def test_parse_short_sentence_latency(self):
        """
        Full parse latency for short sentence with cursor position.
        Target: < 100ms
        """
        text = "今日は天気がいい"
        cursor_offset = 4  # Position at "天"
        
        start = time.perf_counter()
        result = parse(text, cursor_offset=cursor_offset)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Parse short sentence with cursor: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Parse took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert result is not None
    
    def test_parse_long_sentence_latency(self):
        """
        Full parse latency for longer sentence.
        Target: < 100ms
        """
        text = "昨日公園で友達と会って、一緒にコーヒーを飲みました。"
        
        start = time.perf_counter()
        result = parse(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[Parser] Parse long sentence: {elapsed_ms:.2f}ms (target: 100ms)")
        assert elapsed_ms < 100, f"Parse took {elapsed_ms:.2f}ms, exceeds 100ms target"
        assert result is not None
    
    def test_parse_consistency(self):
        """
        Run parse multiple times on same text to check consistency.
        All runs should stay under 100ms.
        """
        text = "猫は可愛いです"
        times = []
        
        for i in range(5):
            start = time.perf_counter()
            result = parse(text)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 100, f"Run {i+1} took {elapsed_ms:.2f}ms, exceeds target"
        
        avg_ms = sum(times) / len(times)
        min_ms = min(times)
        max_ms = max(times)
        print(f"\n[Parser] Parse consistency (5 runs):")
        print(f"  Average: {avg_ms:.2f}ms")
        print(f"  Min: {min_ms:.2f}ms")
        print(f"  Max: {max_ms:.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
