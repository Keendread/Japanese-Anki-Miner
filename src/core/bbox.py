# Module for the bounding box screen cap overlay
# Creates a fullscreen transparent tkinter window for click-and-drag selection
# Called by capture.py when capture mode is 'bbox'

import tkinter as tk
from PIL import Image
from mss import mss
 

def _ensure_tk_root():
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root
 

TRANSPARENT_COLOR = "#FEFEFE"   
OVERLAY_COLOR     = "#FFFFFF"   
 
 
class BBoxOverlay:
    def __init__(self, on_capture):
        self.on_capture = on_capture
 
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.dim_id  = None
        self.running = True
 
        self.root = tk.Toplevel(_ensure_tk_root())
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.root.attributes("-alpha", 0.25)        
        self.root.configure(bg=TRANSPARENT_COLOR)   
        self.root.overrideredirect(True)
 
        self.canvas = tk.Canvas(
            self.root,
            bg=OVERLAY_COLOR,
            highlightthickness=0,
            cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
 
        screen_w = self.root.winfo_screenwidth()
        self.canvas.create_text(
            screen_w // 2, 24,
            text="Click and drag to select a region. Press Esc to cancel.",
            fill="black",
            font=("Segoe UI", 12, "bold")
        )
 
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", self._on_cancel)
        self.canvas.bind("<Escape>", self._on_cancel)
 
        self.root.update()
        self.root.lift()
        self.root.focus_force()
        self.canvas.focus_set()
        
        self.root.after(50, self._force_focus)
 
        print("[BBox] Overlay ready, waiting for drag.")
        
    def _force_focus(self):
        try:
            self.root.lift()
            self.root.focus_force()
            self.canvas.focus_set()
        except Exception:
            pass
 
    def show(self):
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
 
    def _on_press(self, event):
        print(f"[BBox] Mouse pressed at ({event.x}, {event.y})")
        self.start_x = event.x
        self.start_y = event.y
 
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.dim_id:
            self.canvas.delete(self.dim_id)
 
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            self.start_x, self.start_y,
            outline="red",
            width=2,
            fill=""
        )
 
    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(
                self.rect_id,
                self.start_x, self.start_y,
                event.x, event.y
            )
 
        # Live dimension label
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        if self.dim_id:
            self.canvas.delete(self.dim_id)
        self.dim_id = self.canvas.create_text(
            self.start_x + 4, self.start_y + 14,
            text=f"{w} x {h}",
            fill="red",
            anchor="w",
            font=("Segoe UI", 9)
        )
 
    def _on_release(self, event):
        print(f"[BBox] Mouse released at ({event.x}, {event.y})")
        end_x = event.x
        end_y = event.y
 
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
 
        width  = x2 - x1
        height = y2 - y1
 
        if width < 5 or height < 5:
            print("[BBox] Selection too small, ignoring.")
            self._close()
            return
 
        self._close()
        image = self._capture_region(x1, y1, width, height)
        self.on_capture(image)
 
    def _on_cancel(self, event=None):
        print("[BBox] Cancelled.")
        self._close()
 
    def _close(self):
        self.running = False
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
 
    def _capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        with mss() as sct:
            region = {"top": y, "left": x, "width": width, "height": height}
            raw = sct.grab(region)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
 
 
def open_bbox_overlay(on_capture):
    overlay = BBoxOverlay(on_capture)
    overlay.show()