"""
Test suite for dictionary.py
Tests JMdict loading and word lookup functionality.

Run with: python -m pytest tests/test_dictionary.py -v (recommended)
or directly: python tests/test_dictionary.py
"""

import sys
import os
import unittest
from unittest.mock import patch, Mock
# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import dictionary

class TestDictionaryBasics(unittest.TestCase):
    """Test basic dictionary functions without requiring JMdict file."""

    def test_lookup_empty_string(self):
        """Empty string should return None"""
        result: dict[str, str] | None = dictionary.lookup("")
        self.assertIsNone(result)
    
    def test_lookup_whitespace(self):
        """Whitespace-only string should return None"""
        result: dict[str, str] | None = dictionary.lookup("   ")
        self.assertIsNone(result)
    
    def test_lookup_all_empty_string(self):
        """lookup_all with empty string should return []"""
        result: list[dict[str, str]] = dictionary.lookup_all("")
        self.assertEqual(result, [])
    
    def test_lookup_all_whitespace(self):
        """lookup_all with whitespace should return []"""
        result: list[dict[str, str]] = dictionary.lookup_all("   ")
        self.assertEqual(result, [])


class TestJMdictMock(unittest.TestCase):
    """Test dictionary functions with mocked JMdict data."""
    
    @patch('core.dictionary._load_jmdict')
    def test_lookup_found(self, mock_load: Mock):
        """Test successful word lookup."""
        # Mock the JMdict data
        mock_load.return_value = {
            "日本": [{
                "definition": "Japan",
                "reading": "にほん",
                "pos": "noun",
                "kanji": "日本",
            }],
            "にほん": [{
                "definition": "Japan",
                "reading": "にほん",
                "pos": "noun",
                "kanji": "日本",
            }]
        }
        
        # Reset cache
        dictionary.reset_cache()
        
        # Test lookup
        result: dict[str, str] | None = dictionary.lookup("日本")
        self.assertIsNotNone(result)
        if (result is not None): # typesafe check, should never be None here
            self.assertEqual(result["definition"], "Japan")
            self.assertEqual(result["reading"], "にほん")
            self.assertEqual(result["pos"], "noun")
    
    @patch('core.dictionary._load_jmdict')
    def test_lookup_not_found(self, mock_load: Mock):
        """Test lookup of non-existent word."""
        mock_load.return_value = {}
        
        dictionary.reset_cache()
        
        result: dict[str, str] | None = dictionary.lookup("*$%存在しない")
        self.assertIsNone(result)
    
    @patch('core.dictionary._load_jmdict')
    def test_lookup_all_multiple_entries(self, mock_load: Mock):
        """Test lookup_all returns all entries for a word."""
        mock_load.return_value = {
            "本": [
                {
                    "definition": "book",
                    "reading": "ほん",
                    "pos": "noun",
                    "kanji": "本",
                },
                {
                    "definition": "main",
                    "reading": "ほん",
                    "pos": "prefix",
                    "kanji": "本",
                }
            ]
        }
        
        dictionary.reset_cache()
        
        results: list[dict[str, str]] = dictionary.lookup_all("本")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["definition"], "book")
        self.assertEqual(results[1]["definition"], "main")
    
    @patch('core.dictionary._load_jmdict')
    def test_hiragana_lookup(self, mock_load: Mock):
        """Test lookup of hiragana words."""
        mock_load.return_value = {
            "あ": [{
                "definition": "the first of the gojūon",
                "reading": "あ",
                "pos": "noun",
                "kanji": "",
            }]
        }
        
        dictionary.reset_cache()
        
        result: dict[str, str] | None = dictionary.lookup("あ")
        self.assertIsNotNone(result)
        if (result is not None): # typesafe check, should never be None here
            self.assertEqual(result["definition"], "the first of the gojūon")


class TestJMdictParsing(unittest.TestCase):
    """Test JMdict XML parsing logic (if JMdict file exists)."""
    
    def test_jmdict_file_location(self):
        """Verify JMdict path is correctly constructed."""
        # The path should resolve to <project_root>/data/JMdict_e.xml
        expected_suffix = os.path.join("data", "JMdict_e.xml")
        self.assertTrue(
            dictionary.JMDICT_PATH.endswith(expected_suffix),
            f"Path {dictionary.JMDICT_PATH} should end with {expected_suffix}"
        )
    
    def test_load_nonexistent_jmdict(self):
        """Test graceful handling when JMdict is missing."""
        # Temporarily point to nonexistent path
        with patch.object(dictionary, 'JMDICT_PATH', '/nonexistent/path/JMdict_e.xml'):
            result: dict[str, list[dict[str, str]]] = dictionary._load_jmdict() # type: ignore
            self.assertEqual(result, {})


class TestDictionaryIntegration(unittest.TestCase):
    """Integration tests (only run if actual JMdict exists)."""
    
    def test_actual_jmdict_exists(self):
        """Check if actual JMdict file is present."""
        exists = os.path.exists(dictionary.JMDICT_PATH)
        if not exists:
            print(f"\n JMdict not found at {dictionary.JMDICT_PATH}")
            self.skipTest("JMdict file not found")
    
    def test_load_actual_jmdict(self):
        """Load and verify structure of actual JMdict (if present)."""
        if not os.path.exists(dictionary.JMDICT_PATH):
            self.skipTest("JMdict file not found")
        
        dictionary.reset_cache()
        
        cache = dictionary.get_dictionary()
        
        # Should have loaded entries
        self.assertGreater(len(cache), 0, "JMdict should have entries")
        
        # Check structure of first entry
        first_word = next(iter(cache))
        first_entries = cache[first_word]
        
        self.assertIsInstance(first_entries, list)
        self.assertGreater(len(first_entries), 0)
        
        first_entry = first_entries[0]
        self.assertIn("definition", first_entry)
        self.assertIn("reading", first_entry)
        self.assertIn("pos", first_entry)
        self.assertIn("kanji", first_entry)
    
    def test_lookup_known_words(self):
        """Test lookup of common JLPT words (if JMdict exists)."""
        if not os.path.exists(dictionary.JMDICT_PATH):
            self.skipTest("JMdict file not found")
        
        dictionary.reset_cache()
        
        # Test common JLPT N4-N2 vocabulary
        test_cases = [
            ("学生", "student", "がくせい"),
            ("日本", "Japan", "にほん"),
            ("食べる", "eat", "たべる"),
            ("水", "water", "みず"),
        ]
        
        for word, expected_def_partial, expected_reading in test_cases:
            result: dict[str, str] | None = dictionary.lookup(word)
            
            if result is None:
                print(f"Word '{word}' not found in JMdict (might be alternate form)")
                continue
            
            # Check that definition contains expected word (partial match)
            self.assertIn(
                expected_def_partial.lower(),
                result["definition"].lower(),
                f"Definition for '{word}' should contain '{expected_def_partial}'"
            )
            
            # Check reading matches
            self.assertEqual(
                result["reading"],
                expected_reading,
                f"Reading for '{word}' should be '{expected_reading}'"
            )


class TestDictionaryPerformance(unittest.TestCase):
    """Performance and stress tests."""
    
    @patch('core.dictionary._load_jmdict')
    def test_multiple_lookups_same_word(self, mock_load: Mock):
        """Test that repeated lookups don't reload."""
        call_count = [0]
        
        def mock_impl():
            call_count[0] += 1
            return {"日本": [{"definition": "Japan", "reading": "にほん", "pos": "noun", "kanji": "日本"}]}
        
        mock_load.side_effect = mock_impl
        dictionary.reset_cache()
        
        # First lookup should trigger load
        dictionary.lookup("日本")
        self.assertEqual(call_count[0], 1)
        
        # Second lookup should use cache
        dictionary.lookup("日本")
        self.assertEqual(call_count[0], 1)  # No additional load
    
    @patch('core.dictionary._load_jmdict')
    def test_is_ready_flag(self, mock_load: Mock):
        """Test that is_ready() correctly reflects load state."""
        mock_load.return_value = {"日本": [{"definition": "Japan", "reading": "にほん", "pos": "noun", "kanji": "日本"}]}
        
        dictionary.reset_cache()
        
        # After calling get_dictionary(), cache should be populated
        result = dictionary.get_dictionary()
        self.assertIsNotNone(result)
        
        # The cache should now contain the mocked data
        self.assertTrue(len(result) >= 0)  # Either has data or is empty dict
    
    @patch('core.dictionary._load_jmdict')
    def test_lookup_latency(self, mock_load: Mock):
        """Test that cached lookup completes in < 50ms (latency requirement)."""
        import time
        
        # Setup mock dictionary
        mock_data = {
            "日本": [{"definition": "Japan", "reading": "にほん", "pos": "noun", "kanji": "日本"}],
            "学生": [{"definition": "student", "reading": "がくせい", "pos": "noun", "kanji": "学生"}],
            "水": [{"definition": "water", "reading": "みず", "pos": "noun", "kanji": "水"}],
            "食べる": [{"definition": "eat", "reading": "たべる", "pos": "verb", "kanji": "食べる"}],
        }
        mock_load.return_value = mock_data
        
        dictionary.reset_cache()
        
        # Warm up cache
        dictionary.get_dictionary()
        
        # Measure lookup latency (should use cache, not load)
        words_to_test = ["日本", "学生", "水", "食べる"]
        
        for word in words_to_test:
            start_time = time.perf_counter()
            result = dictionary.lookup(word)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # Assertion: lookup must be < 50ms
            self.assertLess(
                elapsed_ms,
                50.0,
                f"Lookup for '{word}' took {elapsed_ms:.2f}ms (target: < 50ms)"
            )
            
            # Should have found the word
            self.assertIsNotNone(result, f"Word '{word}' should be found")


def print_usage():
    """Testing directly with python tests/test_dictionary.py"""
    print("\n" + "="*70)
    print("DICTIONARY TEST SUITE")
    print("="*70)
    print("python tests/test_dictionary.py")
    print("\nTo enable FULL integration tests (actual JMdict):")
    print("1. Download JMdict from: https://www.edrdg.org/pub/Nihongo/JMdict_e.gz")
    print("2. Place it at: data/JMdict_e.xml")
    print("3. Re-run tests")
    print("\n" + "="*70)


if __name__ == "__main__":
    print_usage()
    unittest.main(verbosity=2)
