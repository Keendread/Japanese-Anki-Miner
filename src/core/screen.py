import os
from datetime import datetime
from typing import Tuple

from mss import mss
from PIL import Image

try:
    import win32gui
    import win32ui
    import win32con
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False



def capture_full_screen() -> Image.Image:
    with mss() as sct:
        raw = sct.grab(sct.monitors[1])

    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if img.width > 2000:
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)

    return img


def save_capture(image: Image.Image, output_dir: str = "captures") -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    filepath = os.path.join(output_dir, filename)
    image.save(filepath)
    return filepath


# ── Experimental Window capture (win32 only) ───────────────────────────────────────────────

def list_windows() -> list[tuple[int, str]]:
    """
    Returns all currently visible windows as (hwnd, title) pairs.
    Used to populate a program selector UI so the user can pick a target.

    Example:
        windows = list_windows()
        # [(131234, "Notepad"), (262148, "Firefox"), ...]
    """
    if not _WIN32_AVAILABLE:
        return []

    results = []

    def _callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                results.append((hwnd, title))

    win32gui.EnumWindows(_callback, None)
    return results


def capture_window(hwnd: int) -> Image.Image:
    """
    Captures a specific window by its HWND handle.

    Works even if the window is behind other windows (not occluded by a
    fullscreen exclusive app). Uses PrintWindow with PW_RENDERFULLCONTENT
    which handles hardware-accelerated / DX windows.

    Args:
        hwnd: Window handle from list_windows()

    Returns:
        PIL Image of the window's content

    Raises:
        ValueError: if the hwnd is invalid or the window no longer exists
    """
    if not _WIN32_AVAILABLE:
        raise RuntimeError("capture_window requires pywin32 (Windows only)")

    if not win32gui.IsWindow(hwnd):
        raise ValueError(f"Invalid or closed window handle: {hwnd}")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width  = right  - left
    height = bottom - top

    if width <= 0 or height <= 0:
        raise ValueError(f"Window has zero size: {width}x{height}")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc  = src_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    mem_dc.SelectObject(bitmap)

    # PW_RENDERFULLCONTENT (2) — works for hardware-accelerated windows.
    # Falls back to flag 0 (GDI only) if it returns nothing.
    result = win32gui.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 2)
    if not result:
        win32gui.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 0)

    bmp_info = bitmap.GetInfo()
    raw      = bitmap.GetBitmapBits(True)
    image    = Image.frombuffer(
        "RGB",
        (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        raw, "raw", "BGRX", 0, 1,
    )

    # Cleanup
    mem_dc.DeleteDC()
    src_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32ui.DeleteObject(bitmap.GetHandle())

    return image


def capture_window_by_title(title: str) -> Image.Image:
    """
    Convenience wrapper — finds a window by exact title and captures it.
    Use list_windows() first to find the exact title string.

    Args:
        title: Exact window title (e.g. "Untitled - Notepad")

    Raises:
        ValueError: if no window with that title is found
    """
    hwnd = win32gui.FindWindow(None, title)
    if not hwnd:
        raise ValueError(f"No window found with title: '{title}'")
    return capture_window(hwnd)