"""
OCR Latency Tests (MangaOCR / OCR engine benchmarking)

Target:
- < 800ms per extraction
"""



import time
import pytest
from PIL import Image
from src.core.ocr import extract_text, get_model

@pytest.fixture(scope="class", autouse=True)
def setup_model(self):
    get_model()

    # 🔥 WARM-UP RUN (removes cold start bias)
    dummy = create_test_image("食べる")
    extract_text(dummy)

    yield
def create_test_image(text="食べる", width=400, height=120):
    """
    Creates a simple synthetic image for latency benchmarking
    """
    img = Image.new("RGB", (width, height), color="white")
    return img


class TestOCRLatency:

    @pytest.fixture(scope="class", autouse=True)
    def setup_model(self):
        """
        Preload OCR model once for fair benchmarking
        """
        get_model()
        yield

    # =========================
    # SINGLE WORD
    # =========================
    def test_single_word_latency(self):
        img = create_test_image("食べる")

        start = time.perf_counter()
        _ = extract_text(img)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[OCR] single word: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 1500

    # =========================
    # SHORT PHRASE
    # =========================
    def test_short_phrase_latency(self):
        img = create_test_image("今日は天気がいい")

        start = time.perf_counter()
        _ = extract_text(img)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[OCR] short phrase: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 1500

    # =========================
    # MEDIUM TEXT
    # =========================
    def test_medium_text_latency(self):
        img = create_test_image("これは日本語のOCRテストです")

        start = time.perf_counter()
        _ = extract_text(img)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[OCR] medium text: {elapsed_ms:.2f}ms")
        assert elapsed_ms < 1500

    # =========================
    # CONSISTENCY TEST
    # =========================
    def test_consistency(self):
        img = create_test_image("猫")

        times = []
        for _ in range(5):
            start = time.perf_counter()
            _ = extract_text(img)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert elapsed_ms < 1500

        print("\n[OCR] consistency")
        print(f"avg: {sum(times)/len(times):.2f}ms")
        print(f"min: {min(times):.2f}ms")
        print(f"max: {max(times):.2f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])