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


def _ensure_tk_root():
    """Return an existing Tk root or create one (withdrawn)."""
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root
    

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
    
def _search_bing_sync(query: str, max_results: int=6) -> List[ImageCandidate]:
    """
    Falls back to Bing image search using requests + regex.
    Synchronous - called via run_in_executor so it doesn't block event loop.
    Query should be in English (uses word's meaning from dictionary)
    """
    return _search_bing_requests(query, max_results)

def _search_bing_requests(query: str, max_results: int=6) -> List[ImageCandidate]:
    """
    Bing image search using requests + regex to extract URLs.
    More reliable than downloader libraries.
    """
    try:
        import requests
        from urllib.parse import quote
        import re
        import json
    except ImportError:
        print("[Image] requests library not available for Bing search")
        return []
    
    try:
        results: List[ImageCandidate] = []
        
        # Construct Bing Image Search URL
        search_url = f"https://www.bing.com/images/search?q={quote(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Try multiple regex patterns to find image URLs
        # Pattern 1: murl in JSON-like format
        pattern1 = r'"murl":"([^"]+)"'
        matches = re.findall(pattern1, response.text)
        
        if not matches:
            # Pattern 2: Look for image URLs in data attributes
            pattern2 = r'data-src="([^"]+)"'
            matches = re.findall(pattern2, response.text)
        
        if not matches:
            # Pattern 3: Look for img src attributes
            pattern3 = r'<img[^>]*src="([^"]*\.(jpg|jpeg|png|gif|webp))"'
            matches = re.findall(pattern3, response.text)
            matches = [m[0] if isinstance(m, tuple) else m for m in matches]
        
        if not matches:
            # Pattern 4: Look for m attribute (sometimes used for thumbnails)
            pattern4 = r'"m":"([^"]+)"'
            matches = re.findall(pattern4, response.text)
        
        # Clean up and deduplicate URLs
        unique_urls = set()
        for url in matches[:max_results * 2]:  # Get more than needed for filtering
            if url and url.startswith('http'):
                # Skip placeholder/default images
                if 'a.thumbs.redditmedia' not in url and 'pbs.twimg' not in url:
                    unique_urls.add(url)
        
        for url in list(unique_urls)[:max_results]:
            results.append(ImageCandidate(
                url=url,
                thumbnail_url=url,
                title=query,
                source="bing",
            ))
        
        print(f"[Image] Bing: {len(results)} results for '{query}'")
        return results
        
    except Exception as e:
        print(f"[Image] Bing search error: {e}")
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
    concurrently, then returns candidates immediately WITHOUT waiting
    for all thumbnails to download.
    
    This allows the picker to show immediately with placeholders,
    then thumbnails load in the background.

    Args:
        word (Word): surface, dictionary_form, meaning

    Returns:
        List[ImageCandidate]: candidates without thumbnail_data (will load async)
    """
    import re
    japanese_query = word.dictionary_form or word.surface
    english_query = word.meaning or word.surface
    # Split English meanings into multiple search queries to improve result variety
    english_queries = [q.strip() for q in re.split(r"[;,、/]+", english_query) if q.strip()]
    if not english_queries:
        english_queries = [english_query]
    
    async with aiohttp.ClientSession() as session:
        loop = asyncio.get_event_loop()

        ira_task = _search_irasutoya(japanese_query, session)
        # Run multiple Bing queries in executor to diversify results
        bing_futures = [loop.run_in_executor(None, _search_bing_sync, q) for q in english_queries]
        ira_results, *bing_results_lists = await asyncio.gather(ira_task, *bing_futures)
        # Flatten bing results and deduplicate by URL
        bing_results = []
        seen_urls = set()
        for br in bing_results_lists:
            for c in br:
                if c.url not in seen_urls:
                    seen_urls.add(c.url)
                    bing_results.append(c)

        all_candidates: List[ImageCandidate] = ira_results + bing_results
        
        if not all_candidates:
            print(f"[Image] No candidates found for '{japanese_query}")
            return []
                
    print(f"[Image] {len(all_candidates)} candidates found (thumbnails load async)")
    return all_candidates


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
            # Look for profile directories (skip prefs21.db and other files)
            try:
                profiles = [d for d in os.listdir(anki_profiles_dir) 
                           if os.path.isdir(os.path.join(anki_profiles_dir, d)) and d != "addons21"]
                if profiles:
                    # Use the first available profile (usually the active one)
                    media_path = os.path.join(anki_profiles_dir, profiles[0], "collection.media")
                    if os.path.isdir(media_path):
                        return media_path
            except Exception:
                pass
    
    # Fallback: return the default path (caller should create it if needed)
    username = username or "User 1"
    return rf"C:\Users\{username}\AppData\Roaming\Anki2\User 1\collection.media"

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
        # Ensure media directory exists
        os.makedirs(media_dir, exist_ok=True)
        
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
    "bing":       ("#0078d4", "#ffffff"),   # microsoft-blue bg / white text
}

class ImagePicker:
    """
    DPI-aware tkinter window displaying image candidates in a  scrollable grid.
    Loads thumbnails asynchronously in the background for fast UI responsiveness.
    
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
        self._loader_thread: Optional[threading.Thread] = None
 
        # Keep references so GC doesn't collect PhotoImages
        self._photo_refs: List[ImageTk.PhotoImage] = []
        self._photo_labels: List[tk.Label] = []  # Keep refs to update photos
        self._thumb_cells: List[tk.Frame] = []
        self._updated_thumbnails: set = set()  # Track which thumbnails have been updated
 
        # Use a Toplevel attached to the existing Tk root to avoid multiple Tk instances
        self.root = tk.Toplevel(_ensure_tk_root())
        self.root.title("JAM — Select Image")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
 
        self._build_ui()
        self._position_window()
 
        self.root.update()
        self.root.lift()
        self.root.focus_force()
        
        # Bind keyboard shortcuts
        self.root.bind("<Return>", lambda e: self._confirm() if self.selected_idx is not None else None)
        self.root.bind("<Escape>", lambda e: self._skip())
        
        # Start background thumbnail loading after UI is ready
        self._start_thumbnail_loader()
        
    def _position_window(self):
        """Centers the picker on the screen, with minimum size for few images."""
        num_images = len(self.candidates)
        rows   = max(1, -(-num_images // _COLS))   # ceiling division, at least 1
        
        # Calculate grid height with minimum space per row
        min_row_h = _THUMB_SIZE + _THUMB_PAD * 2 + rescale(22)
        grid_h = rows * min_row_h
        
        total_h = (
            rescale(38)          # title bar
            + rescale(12)        # top gap
            + grid_h             # thumbnail rows
            + rescale(12)        # bottom gap
            + rescale(60)        # button row (increased for visibility)
        )
        
        # Ensure minimum dimensions
        total_h = max(total_h, rescale(300))
        
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
            # Make canvas window width match canvas for proper alignment
            canvas_width = canvas.winfo_width()
            if canvas_width > 1:  # Ensure canvas has been rendered
                canvas.itemconfig(canvas_window, width=canvas_width)
 
        grid_frame.bind("<Configure>", _on_grid_resize)
        # Also trigger resize after a short delay to ensure proper sizing
        self.root.after(50, lambda: _on_grid_resize(None))
 
        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
 
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
 
        # ── Divider ──
        tk.Frame(self.root, bg="#333333", height=1).pack(fill=tk.X, pady=(_P // 2, 0))
 
        # ── Button row ──
        btn_row = tk.Frame(self.root, bg="#1e1e1e", pady=rescale(12))
        btn_row.pack(fill=tk.X, padx=_P)
 
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
        self._photo_labels.append(img_lbl)  # Keep ref to update later
 
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
                # Resize to thumbnail size (default resampling is fine)
                img = img.resize((_THUMB_SIZE, _THUMB_SIZE))
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
    
    def _start_thumbnail_loader(self):
        """Starts a background thread to download thumbnails asynchronously."""
        def load_thumbnails():
            try:
                import requests
                from concurrent.futures import ThreadPoolExecutor, as_completed
            except ImportError:
                print("[Image] requests library not available for thumbnail loading")
                return

            # Use a single Session for connection pooling
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

            def fetch(idx, url):
                try:
                    resp = session.get(url, timeout=6)
                    resp.raise_for_status()
                    return idx, resp.content
                except Exception as e:
                    return idx, None

            # Fetch thumbnails in parallel to speed up loading
            max_workers = min(6, max(2, len(self.candidates)))
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(fetch, idx, c.thumbnail_url): idx for idx, c in enumerate(self.candidates)}
                for fut in as_completed(futures):
                    if not self.running:
                        break
                    try:
                        idx, content = fut.result()
                        if content and self.running:
                            self.candidates[idx].thumbnail_data = content
                            self._updated_thumbnails.add(idx)
                    except Exception:
                        pass
            try:
                session.close()
            except Exception:
                pass
        
        # Run in background thread so it doesn't block UI
        self._loader_thread = threading.Thread(target=load_thumbnails, daemon=True)
        self._loader_thread.start()
    
    def _update_thumbnail(self, index: int):
        """Updates a thumbnail image label when the download completes."""
        if index >= len(self._photo_labels) or index >= len(self.candidates):
            return
        
        candidate = self.candidates[index]
        if candidate.thumbnail_data:
            try:
                photo = self._make_photo(candidate)
                self._photo_labels[index].configure(image=photo)
                print(f"[Image] Thumbnail updated: {index + 1}/{len(self.candidates)}")
            except Exception as e:
                print(f"[Image] Failed to update thumbnail {index}: {e}")
    
    def _update_pending_thumbnails(self):
        """Check for newly downloaded thumbnails and update UI."""
        for idx in list(self._updated_thumbnails):
            self._update_thumbnail(idx)
            self._updated_thumbnails.discard(idx)
    
    # Image Selection
    def _select(self, index: int):
        """Highlights the clicked cell and enables the confirm button."""
        print(f"[Image] Image selected: {index + 1}/{len(self.candidates)}")
        for i, cell in enumerate(self._thumb_cells):
            cell.configure(
                highlightbackground="#6bff6b" if i == index else "#2a2a2a"
            )
        self.selected_idx = index
        self._confirm_btn.configure(state=tk.NORMAL, bg="#1a4a1a")
        print(f"[Image] Confirm button enabled. Now click 'Add Selected' button to confirm.")
        
    # Actions (Buttons)
    def _confirm(self):
        print(f"[Image] Confirming selection: {self.selected_idx}")
        try:
            result = (
                self.candidates[self.selected_idx]
                if self.selected_idx is not None
                else None
            )
            self.running = False
            # Prevent double-invocation
            cb = self.on_select
            self.on_select = None
            # Disable confirm button immediately
            try:
                self._confirm_btn.configure(state=tk.DISABLED)
            except Exception:
                pass
            if cb:
                print(f"[Image] Calling on_select callback")
                cb(result)
            # Ensure picker closes promptly even if main loop isn't pumping
            try:
                self.root.after(0, self._close)
            except Exception:
                try:
                    self._close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[Image] Error in _confirm: {e}")
            import traceback
            traceback.print_exc()
 
    def _skip(self):
        print(f"[Image] Skipping image selection")
        self.running = False
        # Prevent double-invocation
        cb = self.on_select
        self.on_select = None
        if cb:
            cb(None)
        try:
            self.root.after(0, self._close)
        except Exception:
            try:
                self._close()
            except Exception:
                pass
 
    def _close(self):
        """Cleanly close the picker: stop background thread, then destroy window."""
        try:
            # Signal background thread to stop
            self.running = False
            
            # Wait for background thread to exit (max 1 second)
            if self._loader_thread and self._loader_thread.is_alive():
                self._loader_thread.join(timeout=1.0)
            
            # Now safe to destroy tkinter window
            self.root.destroy()
        except Exception as e:
            print(f"[Image] Error closing picker: {e}")
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
        # Deprecated: legacy blocking show. Use pump() via main loop instead.
        logging.warning("[Image] Blocking show() called — use main loop pump instead")
        import time
        while self.running:
            try:
                self._update_pending_thumbnails()
                try:
                    self.root.update()
                except tk.TclError:
                    self.running = False
                    break
                time.sleep(0.01)
            except Exception as e:
                print(f"[Image] Unexpected error in event loop: {e}")
                break
        self._close()

    def pump(self):
        """Perform a single pump iteration for the picker; safe to call from main loop."""
        if not self.running:
            # Ensure cleanup if picker finished
            try:
                self._close()
            except Exception:
                pass
            return

        try:
            # Update any thumbnails downloaded by background threads
            self._update_pending_thumbnails()
            # Pump Tk events once
            try:
                self.root.update()
            except tk.TclError:
                self.running = False
        except Exception as e:
            print(f"[Image] Error in pump: {e}")
            
            
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
        # Create picker and register as active so main loop can pump it
        picker = ImagePicker(candidates, on_select=on_select)
        # Store active picker for pumping
        global _ACTIVE_PICKER
        _ACTIVE_PICKER = picker

    main_thread_queue.put(_show)


_ACTIVE_PICKER: Optional[ImagePicker] = None


def pump_pending_image_once():
    """Called from main loop to pump active image picker if any."""
    global _ACTIVE_PICKER
    picker = _ACTIVE_PICKER
    if picker is None:
        return
    try:
        picker.pump()
        if not picker.running:
            # picker finished; ensure on_select already called by _confirm/_skip
            _ACTIVE_PICKER = None
    except Exception as e:
        print(f"[Image] pump error: {e}")
        try:
            picker._close()
        except Exception:
            pass
        _ACTIVE_PICKER = None