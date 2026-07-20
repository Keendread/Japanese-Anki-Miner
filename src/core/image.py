import os
import hashlib
from io import BytesIO
from typing import Optional

from PIL import Image


def _get_anki_media_path(settings: dict) -> str:
    """Returns Anki's collection.media folder from settings, with a Windows fallback."""
    path = settings.get("anki_media_path", "")
    if path and os.path.isdir(path):
        return path

    # Try to find the active Anki profile's media folder
    username = os.getenv("USERNAME", "")
    if username:
        anki_profiles_dir = rf"C:\Users\{username}\AppData\Roaming\Anki2"
        if os.path.isdir(anki_profiles_dir):
            try:
                profiles = [d for d in os.listdir(anki_profiles_dir)
                           if os.path.isdir(os.path.join(anki_profiles_dir, d)) and d != "addons21"]
                if profiles:
                    media_path = os.path.join(anki_profiles_dir, profiles[0], "collection.media")
                    if os.path.isdir(media_path):
                        return media_path
            except Exception:
                pass

    username = username or "User 1"
    return rf"C:\Users\{username}\AppData\Roaming\Anki2\User 1\collection.media"


def save_captured_image(
    image:    Image.Image,
    settings: dict,
    quality:  int = 90,
) -> Optional[str]:
    try:
        buf = BytesIO()
        rgb_image = image.convert("RGB") if image.mode != "RGB" else image
        rgb_image.save(buf, format="JPEG", quality=quality)
        image_bytes = buf.getvalue()
    except Exception as e:
        print(f"[Image] Failed to encode capture: {e}")
        return None

    content_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
    filename     = f"jam_img_{content_hash}.jpg"

    media_dir = _get_anki_media_path(settings)
    filepath  = os.path.join(media_dir, filename)

    try:
        os.makedirs(media_dir, exist_ok=True)
        if not os.path.exists(filepath):
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            print(f"[Image] Saved to media: {filename}")
        else:
            print(f"[Image] Already saved (same content): {filename}")
        return filename
    except Exception as e:
        print(f"[Image] Save failed: {e}")
        return None