"""
Performance tests for OCR module (MangaOCR).
Target: < 800ms per extraction
"""

import time
import pytest
from PIL import Image, ImageDraw, ImageFont
from src.core.ocr import extract_text, get_model


def create_test_image_with_text(text: str, width: int = 400, height: int = 100) -> Image.Image:
    """
    Creates a simple image with Japanese text for testing OCR.
    
    Args:
        text: Japanese text to write on image
        width: Image width
        height: Image height
    
    Returns:
        PIL Image with text
    """
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)
    
    try:
        # Try to use a font that supports Japanese
        # On Windows, this might be MS Gothic or similar
        font = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 40)
    except (OSError, IOError):
        # Fallback to default font if Japanese font unavailable
        font = ImageFont.load_default()
    
    draw.text((10, 20), text, fill="black", font=font)
    return image


class TestOCRLatency:
    """Latency tests for OCR extraction"""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_model(self):
        """Pre-load model once for all tests"""
        get_model()
        yield
    
    def test_ocr_single_word_latency(self):
        """
        OCR latency for single Japanese word.
        Target: < 800ms
        """
        image = create_test_image_with_text("食べる", width=300, height=80)
        
        start = time.perf_counter()
        text = extract_text(image)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[OCR] Single word extraction: {elapsed_ms:.2f}ms (target: 800ms)")
        assert elapsed_ms < 800, f"OCR took {elapsed_ms:.2f}ms, exceeds 800ms target"
        assert text  # Verify text was extracted
    
    def test_ocr_short_phrase_latency(self):
        """
        OCR latency for short phrase (typical usage).
        Target: < 800ms
        """
        image = create_test_image_with_text("今日は天気がいい", width=500, height=100)
        
        start = time.perf_counter()
        text = extract_text(image)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[OCR] Short phrase extraction: {elapsed_ms:.2f}ms (target: 800ms)")
        assert elapsed_ms < 800, f"OCR took {elapsed_ms:.2f}ms, exceeds 800ms target"
        assert text
    
    def test_ocr_medium_text_latency(self):
        """
        OCR latency for medium text block.
        Target: < 800ms
        """
        image = create_test_image_with_text("これは日本語のテストです。", width=600, height=120)
        
        start = time.perf_counter()
        text = extract_text(image)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n[OCR] Medium text extraction: {elapsed_ms:.2f}ms (target: 800ms)")
        assert elapsed_ms < 800, f"OCR took {elapsed_ms:.2f}ms, exceeds 800ms target"
        assert text
    
    def test_ocr_consistency(self):
        """
        Run OCR multiple times on same image to check consistency.
        All runs should stay under 800ms.
        """
        image = create_test_image_with_text("猫", width=200, height=80)
        times = []
        
        for i in range(3):
            start = time.perf_counter()
            text = extract_text(image)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 800, f"Run {i+1} took {elapsed_ms:.2f}ms, exceeds target"
        
        avg_ms = sum(times) / len(times)
        print(f"\n[OCR] Average of 3 runs: {avg_ms:.2f}ms")
        print(f"[OCR] Individual times: {[f'{t:.2f}ms' for t in times]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
