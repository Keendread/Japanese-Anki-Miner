# Module for the Optical Character Recognition capability of the application
# Primarily uses MangaOCR but you can add fallback OCR models
# Feeds into parser.py

from PIL import Image
import threading
import time
import logging
import warnings
from typing import Any
import numpy as np

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
    import cv2

    if image.mode != "RGB":
        image = image.convert("RGB")

    gray = np.array(image.convert("L"))
    mean_brightness = gray.mean()

    # Determine binarization direction based on background brightness
    if mean_brightness < 128:
        # Dark background, bright text → threshold to white text on black
        _, bw = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
    else:
        # Light background, dark text → invert so text becomes white on black
        _, bw = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)

    # If binarization produced almost nothing (wrong polarity), flip it
    white_pct = np.sum(bw == 255) / bw.size
    if white_pct < 0.02 or white_pct > 0.95:
        bw = cv2.bitwise_not(bw)

    image = Image.fromarray(bw).convert("RGB")

    # Now upscale with NEAREST — crisp edges on binary, no halo artifacts
    w, h = image.size
    TARGET_H = 64
    TARGET_W = 64
    scale = max(
        TARGET_H / h if h < TARGET_H else 1.0,
        TARGET_W / w if w < TARGET_W else 1.0,
    )
    if scale > 1.0:
        image = image.resize((int(w * scale), int(h * scale)), Image.NEAREST)

    return image

def get_model() -> Any:
    global _ocr_model
    with _model_lock:
        if _ocr_model is None:
            try:
                from manga_ocr import MangaOcr
                import sys

                logging.getLogger("manga_ocr").setLevel(logging.ERROR)
                warnings.filterwarnings("ignore")
                
                import io
                if sys.stdout is None:
                    sys.stdout = io.StringIO()
                if sys.stderr is None:
                    sys.stderr = io.StringIO()

                stop_spinner = threading.Event()
                spinner = threading.Thread(target=_loading_spinner, args=(stop_spinner,), daemon=True)
                spinner.start()

                _ocr_model = MangaOcr()

                stop_spinner.set()
                spinner.join()

                warnings.filterwarnings("default")
                _model_ready.set()
                logging.info("[OCR] Model loaded successfully.")

            except Exception as e:
                logging.exception(f"[OCR] Model failed to load: {e}")
                _model_ready.set()  # unblock the toast even on failure
                warnings.filterwarnings("default")

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