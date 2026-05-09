# Module for the Optical Character Recognition capability of the application
# Primarily uses MangaOCR but you can add fallback OCR models
# Feeds into parser.py

from PIL import Image, ImageFilter, ImageEnhance
import threading
import time
import logging
import warnings
from typing import Any

_ocr_model: Any = None
_model_lock: threading.Lock = threading.Lock()
_model_ready: threading.Event = threading.Event()

def _loading_spinner(stop_event: threading.Event):
    """
    Prints elapsed seconds on the same line while model loads.

    Args:
        stop_event (threading.Event): Function that sets the stopping condition
    """
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r[OCR] Loading model... {elapsed:.1f}s", end="", flush=True)
        time.sleep(0.1)
    
    elapsed = time.time() - start
    print(f"\r[OCR] Model loaded in {elapsed:.1f}s")

def preprocess(image: Image.Image) -> Image.Image:
    """
    Preprocess captured image before OCR.

    Args:
        image (Image.Image): Image from capture.py

    Returns:
        Image.Image: Preprocessed image
    """
    w, h = image.size
    if w < 300 or h < 60:
        scale = 2
        image = image.resize((w * scale, h * scale), Image.LANCZOS)

    image = image.filter(ImageFilter.SHARPEN)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    return  image

def get_model() -> Any:
    """Returns current used OCR model, loading it on first call."""
    global _ocr_model
    with _model_lock:
        if _ocr_model is None:
            from manga_ocr import MangaOcr
            
            logging.getLogger("manga_ocr").setLevel(logging.ERROR)
            warnings.filterwarnings("ignore")
            
            stop_spinner = threading.Event()
            spinner = threading.Thread(target=_loading_spinner, args=(stop_spinner,), daemon=True)
            spinner.start()

            _ocr_model = MangaOcr()
            
            stop_spinner.set()
            spinner.join()

            warnings.filterwarnings("default")
            _model_ready.set()
    return _ocr_model

def extract_text(image: Image.Image) -> str:
    """
    Runs MangaOCR on a PIL Image and returns the extracted Japanese text.

    Args:
        image (Image.Image): Image from capture.py

    Returns:
        str: Japanese text for Natural Language Processing
    """
    try:
        model = get_model()
        processed = preprocess(image)
        text = model(processed)
        return text.strip()
    except Exception as e:
        print(f"[OCR] Extraction failed: {e}")
        return ""