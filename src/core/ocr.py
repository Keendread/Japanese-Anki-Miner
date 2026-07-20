import asyncio
import logging
import threading
from typing import Any, List

from PIL import Image

from core.detector import TextRegion

_model_ready: threading.Event = threading.Event()
_lens_lock:   threading.Lock  = threading.Lock()
_lens_api:    Any             = None


# ── Initialisation ────────────────────────────────────────────────────────────

def get_model() -> Any:
    global _lens_api
    with _lens_lock:
        if _lens_api is None:
            try:
                from chrome_lens_py import LensAPI
                _lens_api = LensAPI()
                logging.info("[OCR] LensAPI initialised.")
            except Exception as e:
                logging.exception(f"[OCR] LensAPI failed to initialise: {e}")
        _model_ready.set()   # always unblock the toast, even on failure
    return _lens_api


def _run_lens(image: Image.Image, output_format: str = "full_text",
              target_translation_language: str = None) -> dict:
    api = get_model()
    if api is None:
        return {}

    async def _call():
        return await api.process_image(
            image_path=image,
            ocr_language="ja",
            output_format=output_format,
            target_translation_language=target_translation_language,
        )

    return asyncio.run(_call())


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(image: Image.Image) -> str:
    try:
        result = _run_lens(image, output_format="full_text")
        text   = result.get("ocr_text", "") or ""
        text   = text.strip()
        logging.info(f"[OCR] extract_text: '{text[:80]}'")
        return text
    except Exception as e:
        logging.error(f"[OCR] extract_text failed: {e}", exc_info=True)
        print(f"[OCR] Extraction failed: {e}")
        return ""


def extract_blocks(image: Image.Image) -> list[TextRegion]:
    try:
        result = _run_lens(image, output_format="blocks")
        blocks = result.get("text_blocks", [])

        if not blocks:
            logging.warning("[OCR] extract_blocks: no blocks returned, falling back to full-image text")
            text = result.get("ocr_text", "").strip()
            w, h = image.size
            return [TextRegion(x=0, y=0, w=w, h=h, text=text)] if text else []

        regions: list[TextRegion] = []
        img_w, img_h = image.size

        for block in blocks:
            text = block.get("text", "").strip()
            if not text:
                continue

            # Lens geometry is normalised 0.0–1.0 relative to image dimensions
            geo = block.get("geometry", {})
            if geo:
                cx = geo.get("center_x", 0.5)
                cy = geo.get("center_y", 0.5)
                bw = geo.get("width",    0.5)
                bh = geo.get("height",   0.5)
                x  = int((cx - bw / 2) * img_w)
                y  = int((cy - bh / 2) * img_h)
                w  = int(bw * img_w)
                h  = int(bh * img_h)
                # Clamp to image bounds
                x  = max(0, min(x, img_w - 1))
                y  = max(0, min(y, img_h - 1))
                w  = max(1, min(w, img_w - x))
                h  = max(1, min(h, img_h - y))
            else:
                # No geometry — span full width, stack vertically
                x, y = 0, len(regions) * 30
                w, h = img_w, 28

            regions.append(TextRegion(x=x, y=y, w=w, h=h, text=text))
            logging.debug(f"[OCR] Block: '{text[:60]}' @ ({x},{y},{w},{h})")

        # Sort: top-to-bottom, then left-to-right (horizontal reading order)
        regions.sort(key=lambda r: (r.y, r.x))
        logging.info(f"[OCR] extract_blocks: {len(regions)} block(s)")
        return regions

    except Exception as e:
        logging.error(f"[OCR] extract_blocks failed: {e}", exc_info=True)
        print(f"[OCR] Block extraction failed: {e}")
        # Fallback: return full-image as one region
        text = extract_text(image)
        w, h = image.size
        return [TextRegion(x=0, y=0, w=w, h=h, text=text)] if text else []


def translate_blocks(
    image: Image.Image,
    regions: List[TextRegion],
    target_lang: str = "en",
) -> None:
    if not regions:
        return

    api = get_model()
    if api is None:
        logging.warning("[OCR] translate_blocks: Lens unavailable, skipping")
        return

    crops = [region.crop_from(image, pad=2) for region in regions]

    async def _translate_one(region: TextRegion, crop: Image.Image) -> None:
        try:
            result = await api.process_image(
                image_path=crop,
                ocr_language="ja",
                output_format="full_text",
                target_translation_language=target_lang,
            )
            translation = (result.get("translated_text") or "").strip()
            region.translation = translation
            logging.debug(f"[OCR] Translated '{region.text[:30]}' -> '{translation[:30]}'")
        except Exception as e:
            logging.error(f"[OCR] Block translation failed for '{region.text[:30]}': {e}")
            region.translation = ""

    async def _translate_all():
        await asyncio.gather(
            *(_translate_one(r, c) for r, c in zip(regions, crops))
        )

    try:
        asyncio.run(_translate_all())
        print(f"[OCR] Translated {len(regions)} block(s)")
    except Exception as e:
        logging.error(f"[OCR] translate_blocks batch failed: {e}", exc_info=True)