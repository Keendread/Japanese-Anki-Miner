# Fetches image candidates from Irasutoya
# Shows DPI-aware tkinter picker so the user can select the right image
# Saves chosen image directly to Anki's collection.media folder
# Called from capture.py on_confirm() callback after card toast is confirmed

import os
import re
import asyncio
import aiohttp
import hashlib
import ctypes
import tkinter as tk
import threading

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Optional, List, Callable
 
from PIL import Image, ImageTk
from io import BytesIO
 
from src.models.word import Word


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    
def rescale(x: int) -> int:
    """Scales a pixel value by the system DPI factor (96 DPI = 100%)."""
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except Exception:
        return x
    

@dataclass
class ImageCandidate:
    """Represents one image result from a search source."""
    url: str                                # Full-res image URL
    thumbnail_url: str                      # Smaller preview URL
    title: str                              # Image title or alt text
    source: str                             # "irasutoya" or "duckduckgo"
    thumbnail_data: Optional[bytes] = None  # Downloaded bytes
    

async def _search_irasutoya(
    query: str,
    session: aiohttp.ClientSession,
    max_results: int=6,
) -> List[ImageCandidate]:
    """
    Searches Irasutoya via its public Blogger JSON feed.
    Query should be in Japanese (site indexes are in Japanese)

    URL pattern:
        https://www.irasutoya.com/feeds/posts/summary?q={query}&alt=json&max-results=N
    Each entry has a media$thumbnail field containing the image URL.
    We enlarge the thumbnail from s72-c → s400 for full resolution.
    """
    try:
        params = {"q": query, "alt": "json", "max-results": max_results}
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with session.get(
            "https://www.irasutoya.com/feeds/posts/summary",
            params=params,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            
        entries = data.get("feed", {}).get("entry", [])
        results: List[ImageCandidate] = []

        for entry in entries:
            meta = entry.get("media$thumbnail", {})
            raw_url = meta.get("url", "")
            if not raw_url:
                continue
            
            title = entry.get("title", {}).get("$t", "")

            full_url = re.sub(r"/s\d+-c/", "/s400/",  raw_url)
            thumb_url = re.sub(r"/s\d+-c/", "/s200/",  raw_url)
            
            results.append(ImageCandidate(
                url=full_url,
                thumbnail_url=thumb_url,
                title=title,
                source="irasutoya",
            ))
            
        print(f"[Image] Irasutoya: {len(results)} results for '{query}'")
        return results
    
    except aiohttp.ClientConnectionError:
        print("[Image] Irasutoya unreachable (no internet?)")
        return []
    except Exception as e:
        print(f"[Image] Irasutoya search error: {e}")
        return []
    
def _search_duckduckgo_sync(query: str, max_results: int=6) -> List[ImageCandidate]:
    """
    Falls back to DuckDuckGo image search using duckduckgo-search library.
    Synchronous - called via run_in_executor so it doesn't block event loop.
    Query should be in English (uses word's meaning from dictionary)
    """
    try:
        from duckduckgo_search import DDGS
 
        results: List[ImageCandidate] = []
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                img_url = r.get("image", "")
                thumb_url = r.get("thumbnail", img_url)
                if not img_url:
                    continue
                results.append(ImageCandidate(
                    url=img_url,
                    thumbnail_url=thumb_url,
                    title=r.get("title", ""),
                    source="duckduckgo",
                ))
 
        print(f"[Image] DuckDuckGo: {len(results)} results for '{query}'")
        return results
 
    except ImportError:
        print("[Image] duckduckgo-search not installed — run: pip install duckduckgo-search")
        return []
    except Exception as e:
        print(f"[Image] DuckDuckGo search error: {e}")
        return []
    
    
async def _download_thumbnail(
    url: str,
    session: aiohttp.ClientSession,
) -> Optional[bytes]:
    """Downloads thumbnail bytes for display in the picker."""
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.read()
    except Exception as e:
        print(f"[Image] Thumbnail fetch failed ({url[:55]}…): {e}")
        return None
    
async def fetch_candidates(word: Word) -> List[ImageCandidate]:
    """
    Main entry point: searches Irasutoya (JP) and DuckDuckGo (EN)
    concurrentyl, then downloads  all thumbnails concurrently.
    
    Returns candidates with thumbnail_data filled in, Irasutoya first.

    Args:
        word (Word): surface, dictionary_form, meaning

    Returns:
        List[ImageCandidate]: used for display in ImagePicker.
    """
    japanese_query = word.dictionary_form or word.surface
    english_query = word.meaning or word.surface
    
    async with aiohttp.ClientSession() as session:
        loop = asyncio.get_event_loop()

        ira_task = _search_irasutoya(japanese_query, session)
        ddg_task = loop.run_in_executor(
            None, _search_duckduckgo_sync, english_query
        )
        ira_results, ddg_results = await asyncio.gather(ira_task, ddg_task)

        all_candidates: List[ImageCandidate] = ira_results + ddg_results
        
        if not all_candidates:
            print(f"[Image] No candidates found for '{japanese_query}")
            return []
        
        thumb_tasks = [
            _download_thumbnail(c.thumbnail_url, session)
            for c in all_candidates
        ]
        thumb_bytes_list = await asyncio.gather(*thumb_tasks)
        
        ready: List[ImageCandidate] = []
        for candidate, data in zip(all_candidates, thumb_bytes_list):
            if data:
                ready.append(ImageCandidate(
                    url=candidate.url,
                    thumbnail_url=candidate.thumbnail_url,
                    title=candidate.title,
                    source=candidate.source,
                    thumbnail_data=data,
                ))
                
    print(f"[Image] {len(ready)} candidates with thumbnails ready")
    return ready


def _get_anki_media_path(settings: dict) -> str:
    """Returns Anki's collection.media folder from settings, with a Windows fallback."""
    path = settings.get("anki_media_path", "")
    if path and os.path.isdir(path):
        return path
    username = os.getenv("USERPROFILE", os.path.expanduser("~"))
    anki_profile = settings.get("anki_profile", "User 1")
    return os.path.join(username, "AppData", "Roaming", "Anki2", anki_profile, "collection.media")

def save_to_media(
    candidate: ImageCandidate,
    word: Word,
    settings: dict,
) -> Optional[str]:
    """
    Downloads full-res image and saves it to Anki's collection.media.
    
    Anki references media files by filename only (not full path), so we
    return just the filename for use in the card's Picture field.

    Args:
        candidate (ImageCandidate): candidate selected by user
        word (Word): used for filename generation
        settings (dict): for anki_media_path

    Returns:
        Filename saved to collection.media (e.g. "jam_img_abc123.jpg"),
        or None if download/save failed.
    """
    print(f"[Image] Downloading full image: {candidate.url[:60]}...")

    try:
        image_bytes = asyncio.run(_download_full(candidate.url))
    except Exception as e:
        print(f"[Image] Full image download failed: {e}")
        return None
    
    if not image_bytes:
        return None

    url_lower = candidate.url.lower()
    if ".png" in url_lower:
        ext = ".png"
    elif ".gif" in url_lower:
        ext = ".gif"
    elif ".webp" in url_lower:
        ext = ".webp"
    else:
        ext = ".jpg"
        
    url_hash = hashlib.sha256(candidate.url.encode()).hexdigest()[:12]
    filename = f"jam_img_{url_hash}{ext}"

    media_dir = _get_anki_media_path(settings)
    filepath = os.path.join(media_dir, filename)

    try:
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        print(f"[Image] Saved to media: {filename}")
        return filename
    except Exception as e:
        print(f"[Image] Save failed: {e}")
        return None

async def _download_full(url: str) -> Optional[bytes]:
    """Downloads full-res image bytes."""
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.read()
    except Exception as e:
        print(f"[Image] Full download error: {e}")
        return None


_THUMB_SIZE   = rescale(130)   # Thumbnail display size in pixels
_THUMB_PAD    = rescale(6)     # Padding around each cell
_COLS         = 3              # Thumbnails per row
_PICKER_W     = rescale(480)   # Window width
_P            = rescale(12)    # General padding
 
_SOURCE_BADGE = {
    "irasutoya":  ("#e85d04", "#ffffff"),   # orange bg / white text
    "duckduckgo": ("#4285f4", "#ffffff"),   # google-blue bg / white text
}

class ImagePicker:
    """
    DPI-aware tkinter window displaying image candidates in a  scrollable grid.
    
    Layout:
        ┌─────────────────────────────────────┐
        │  Select an image  ·  N found        │  ← title bar
        ├─────────────────────────────────────┤
        │  [img] [img] [img]                  │  ← thumbnail grid (scrollable)
        │  [img] [img] [img]                  │
        ├─────────────────────────────────────┤
        │  [Skip Image]        [Add Selected] │  ← action row
        └─────────────────────────────────────┘
 
    Clicking a thumbnail highlights it in green and enables "Add Selected".
    """
    
    def __init__(
        self,
        candidates: List[ImageCandidate],
        on_select: Callable[[Optional[ImageCandidate]], None],
    ):
        self.candidates = candidates
        self.on_select = on_select
        self.selected_idx: Optional[int] = None
        self.running = True
 
        # Keep references so GC doesn't collect PhotoImages
        self._photo_refs: List[ImageTk.PhotoImage] = []
        self._thumb_cells: List[tk.Frame] = []
 
        self.root = tk.Tk()
        self.root.title("JAM — Select Image")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
 
        self._build_ui()
        self._position_window()
 
        self.root.update()
        self.root.lift()
        self.root.focus_force()
        
    def _position_window(self):
        """Centers the picker on the screen."""
        self.root.update_idletasks()
        total_h = self.root.winfo_reqheight()
        
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - _PICKER_W) // 2
        y  = (sh - total_h)   // 2
        self.root.geometry(f"{_PICKER_W}x{total_h}+{x}+{y}")
 
    def _build_ui(self):
        # ── Title bar ──
        title_row = tk.Frame(self.root, bg="#2a2a2a", pady=rescale(8))
        title_row.pack(fill=tk.X)
 
        tk.Label(
            title_row,
            text="Select an image for the card",
            font=("Segoe UI", 10, "bold"),
            bg="#2a2a2a", fg="#ffffff",
            padx=_P,
        ).pack(side=tk.LEFT)
 
        tk.Label(
            title_row,
            text=f"{len(self.candidates)} found",
            font=("Segoe UI", 8),
            bg="#2a2a2a", fg="#888888",
            padx=_P,
        ).pack(side=tk.RIGHT)
 
        # ── Scrollable thumbnail grid ──
        # Canvas + scrollbar so long result lists don't overflow
        outer = tk.Frame(self.root, bg="#1e1e1e")
        outer.pack(fill=tk.BOTH, expand=True, padx=_P, pady=(_P // 2, 0))
 
        canvas = tk.Canvas(outer, bg="#1e1e1e", highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
 
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
 
        grid_frame = tk.Frame(canvas, bg="#1e1e1e")
        canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")
 
        # Populate grid
        for idx, candidate in enumerate(self.candidates):
            row = idx // _COLS
            col = idx % _COLS
            self._build_cell(grid_frame, candidate, idx, row, col)
 
        # Update scroll region after all cells are placed
        def _on_grid_resize(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
 
        grid_frame.bind("<Configure>", _on_grid_resize)
 
        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
 
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
 
        # ── Divider ──
        tk.Frame(self.root, bg="#333333", height=1).pack(fill=tk.X, pady=(_P // 2, 0))
 
        # ── Button row ──
        btn_row = tk.Frame(self.root, bg="#1e1e1e", pady=rescale(10))
        btn_row.pack(fill=tk.X)
 
        tk.Button(
            btn_row,
            text="Skip Image",
            font=("Segoe UI", 9),
            bg="#2a2a2a", fg="#aaaaaa",
            activebackground="#3a3a3a", activeforeground="#ffffff",
            bd=0, padx=rescale(14), pady=rescale(6),
            cursor="hand2",
            command=self._skip,
        ).pack(side=tk.LEFT, padx=(_P, rescale(4)))
 
        # Store ref to confirm button so _select() can enable it
        self._confirm_btn = tk.Button(
            btn_row,
            text="Add Selected  ✓",
            font=("Segoe UI", 9, "bold"),
            bg="#1a3a1a", fg="#6bff6b",
            activebackground="#2a4a2a", activeforeground="#6bff6b",
            bd=0, padx=rescale(14), pady=rescale(6),
            cursor="hand2",
            state=tk.DISABLED,     # enabled once a thumbnail is clicked
            command=self._confirm,
        )
        self._confirm_btn.pack(side=tk.RIGHT, padx=(rescale(4), _P))
 
    def _build_cell(
        self,
        parent: tk.Frame,
        candidate: ImageCandidate,
        index: int,
        row: int,
        col: int,
    ):
        """Builds one clickable thumbnail cell with a source badge."""
        cell = tk.Frame(
            parent,
            bg="#2a2a2a",
            highlightbackground="#2a2a2a",   # default: dark border (not selected)
            highlightthickness=rescale(2),
            cursor="hand2",
        )
        cell.grid(
            row=row, column=col,
            padx=_THUMB_PAD // 2,
            pady=_THUMB_PAD // 2,
        )
        self._thumb_cells.append(cell)
 
        # Thumbnail image
        photo = self._make_photo(candidate)
        img_lbl = tk.Label(
            cell, image=photo,
            bg="#2a2a2a", cursor="hand2",
        )
        img_lbl.pack(padx=rescale(4), pady=(rescale(4), 0))
 
        # Source badge (coloured strip at the bottom of the cell)
        badge_bg, badge_fg = _SOURCE_BADGE.get(candidate.source, ("#555555", "#ffffff"))
        badge = tk.Label(
            cell,
            text=candidate.source,
            font=("Segoe UI", 7, "bold"),
            bg=badge_bg, fg=badge_fg,
            padx=rescale(4), pady=rescale(2),
        )
        badge.pack(fill=tk.X)
 
        # Bind click on every sub-widget so the whole cell is clickable
        for widget in (cell, img_lbl, badge):
            widget.bind("<Button-1>", lambda _e, i=index: self._select(i))
 
    def _make_photo(self, candidate: ImageCandidate) -> ImageTk.PhotoImage:
        """Converts thumbnail bytes → PIL Image → PhotoImage for tkinter."""
        try:
            if candidate.thumbnail_data:
                img = Image.open(BytesIO(candidate.thumbnail_data))
                img.thumbnail((_THUMB_SIZE, _THUMB_SIZE), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._photo_refs.append(photo)
                return photo
        except Exception as e:
            print(f"[Image] Thumbnail render error: {e}")
 
        # Fallback: solid grey placeholder
        placeholder = Image.new("RGB", (_THUMB_SIZE, _THUMB_SIZE), "#444444")
        photo = ImageTk.PhotoImage(placeholder)
        self._photo_refs.append(photo)
        return photo
    
    # Image Selection
    def _select(self, index: int):
        """Highlights the clicked cell and enables the confirm button."""
        for i, cell in enumerate(self._thumb_cells):
            cell.configure(
                highlightbackground="#6bff6b" if i == index else "#2a2a2a"
            )
        self.selected_idx = index
        self._confirm_btn.configure(state=tk.NORMAL, bg="#1a4a1a")
        
    # Actions (Buttons)
    def _confirm(self):
        result = (
            self.candidates[self.selected_idx]
            if self.selected_idx is not None
            else None
        )
        self.running = False
        self._close()
        if self.on_select:
            self.on_select(result)
 
    def _skip(self):
        self.running = False
        self._close()
        if self.on_select:
            self.on_select(None)
 
    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        
    # Event Loop
    def show(self):
        """
        Blocking: drives the tkinter event loop manually until the user
        picks an image or skips. Same pattern as CardToast.show().
        """
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
            
            
def show_image_picker(
    candidates: List[ImageCandidate],
    main_thread_queue,
    on_select: Callable[[Optional[ImageCandidate]], None],
):
    """
    Posts the ImagePicker to the main thread queue.
 
    If candidates is empty the picker is skipped and on_select(None) is called
    immediately so the caller never blocks indefinitely.
 
    Args:
        candidates:         Results from fetch_candidates()
        main_thread_queue:  queue.Queue owned by main.py
        on_select:          Called with chosen ImageCandidate or None
    """
    def _show():
        if not candidates:
            print("[Image] No candidates — skipping picker.")
            on_select(None)
            return
        picker = ImagePicker(candidates, on_select=on_select)
        picker.show()
 
    main_thread_queue.put(_show)