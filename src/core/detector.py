# Text region detection using OpenCV connected component analysis.
# Works like Google Lens: finds rectangular bounding boxes around
# each cluster of text in an image, regardless of font or background.
#
# Used by:
#   capture.py  — smart mouse mode (auto-expand to full text line)
#   capture.py  — whole screen mode (detect all text regions on screen)
#   word_selector.py — receives pre-detected regions ready for OCR
#
# No ML model needed — pure OpenCV, fast enough for real-time use.
# For a given 400x120 mouse capture, detection takes ~3ms.
# For a 1440x900 full screen image, detection takes ~30ms.
 
from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import logging
import os

import numpy as np
from PIL import Image

_log = logging.getLogger(__name__)
 
 
# ─── Data Class ───────────────────────────────────────────────────────────────
 
@dataclass
class TextRegion:
    """
    Bounding box of a detected text cluster within an image.
    Coordinates are in the image's own pixel space (not screen space).
    """
    x: int          # left edge
    y: int          # top edge
    w: int          # width
    h: int          # height
    text: str = ""  # OCR result, filled later by ocr.extract_text()
 
    # ── Derived geometry ──────────────────────────────────────────────────────
 
    @property
    def right(self) -> int:
        return self.x + self.w
 
    @property
    def bottom(self) -> int:
        return self.y + self.h
 
    @property
    def area(self) -> int:
        return self.w * self.h
 
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)
 
    def contains_point(self, px: int, py: int) -> bool:
        """True if (px, py) lies within this region."""
        return self.x <= px <= self.right and self.y <= py <= self.bottom
 
    def distance_to_point(self, px: int, py: int) -> float:
        """Euclidean distance from the region's center to (px, py)."""
        cx, cy = self.center
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
 
    # ── Crop helpers ──────────────────────────────────────────────────────────
 
    def to_pil_box(self) -> Tuple[int, int, int, int]:
        """Returns (left, top, right, bottom) for PIL.Image.crop()."""
        return (self.x, self.y, self.right, self.bottom)
 
    def padded(self, pad: int, img_w: int = 99999, img_h: int = 99999) -> "TextRegion":
        """Returns a copy expanded by `pad` pixels on every side, clamped to image bounds."""
        return TextRegion(
            x=max(0,     self.x - pad),
            y=max(0,     self.y - pad),
            w=min(img_w, self.w + pad * 2),
            h=min(img_h, self.h + pad * 2),
        )
 
    def crop_from(self, image: Image.Image, pad: int = 6) -> Image.Image:
        """Crops this region (with optional padding) from `image`."""
        img_w, img_h = image.size
        box = self.padded(pad, img_w, img_h).to_pil_box()
        return image.crop(box)
 
 
# ─── Core Detection ───────────────────────────────────────────────────────────
 
def _detect_regions_canny(
    image:      Image.Image,
    min_area:   int = 50,
    debug_dir:  str = "",
) -> List[TextRegion]:
    """
    Alternative edge-detection approach using Canny edge detection.
    Works better for images where text is very light, very dark, or low-contrast.
    """
    try:
        import cv2
    except ImportError:
        return []
    
    img_w, img_h = image.size
    arr  = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    
    # Save grayscale debug image if requested
    if debug_dir:
        try:
            os.makedirs(debug_dir, exist_ok=True)
            debug_gray_path = os.path.join(debug_dir, "detector_canny_grayscale.png")
            cv2.imwrite(debug_gray_path, gray)
            _log.debug(f"[Detector.Canny] Saved grayscale debug to {debug_gray_path}")
        except Exception as e:
            _log.debug(f"[Detector.Canny] Failed to save grayscale debug: {e}")
    
    # Apply slight Gaussian blur to reduce noise
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # Use Canny edge detection
    edges = cv2.Canny(gray, 50, 150)
    
    # Save edges debug image if requested
    if debug_dir:
        try:
            debug_edges_path = os.path.join(debug_dir, "detector_canny_edges.png")
            cv2.imwrite(debug_edges_path, edges)
            _log.debug(f"[Detector.Canny] Saved edges debug to {debug_edges_path}")
        except Exception as e:
            _log.debug(f"[Detector.Canny] Failed to save edges debug: {e}")
    
    # Dilate edges to connect them into regions
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    # Save dilated debug image if requested
    if debug_dir:
        try:
            debug_dilated_path = os.path.join(debug_dir, "detector_canny_dilated.png")
            cv2.imwrite(debug_dilated_path, dilated)
            _log.debug(f"[Detector.Canny] Saved dilated debug to {debug_dilated_path}")
        except Exception as e:
            _log.debug(f"[Detector.Canny] Failed to save dilated debug: {e}")
    
    # Find contours instead of connected components
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    regions: List[TextRegion] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        
        if area < min_area:
            continue
        if w < 4 or h < 4:
            continue
        if w > img_w * 0.92 and h > img_h * 0.5:
            continue
        
        regions.append(TextRegion(x=x, y=y, w=w, h=h))
    
    # Sort by reading order
    regions.sort(key=lambda r: (r.y // 40, -(r.x + r.w)))
    return regions

 
def detect_regions(
    image:        Image.Image,
    min_area:     int = 80,
    dilation_x:   int = 20,
    dilation_y:   int = 3,
    row_band:     int = 40,
    debug_dir:    str = "",
) -> List[TextRegion]:
    """
    Detects text regions in a PIL image using OpenCV connected components.
 
    Algorithm:
        1. Grayscale → Otsu binary-inverse (text = white blobs on black).
        2. Dilate horizontally: merges individual characters on the same
           line into one connected blob per text line.
        3. connectedComponentsWithStats → bounding boxes per blob.
        4. Filter noise by area and aspect; remove full-image artifacts.
        5. Sort into Japanese reading order (top → bottom, right → left).
 
    Args:
        image:      PIL Image to analyze.
        min_area:   Minimum blob area in pixels; smaller blobs are noise.
        dilation_x: Horizontal kernel width — larger merges more characters.
                    Increase for wide-spaced fonts; decrease for dense kanji.
        dilation_y: Vertical kernel height — keep small to avoid merging lines.
        row_band:   Pixel height of "row bands" for reading-order sorting.
        debug_dir:  If set, save intermediate images (grayscale, binary, dilated) for inspection.
 
    Returns:
        List[TextRegion] sorted top-to-bottom, right-to-left.
        Empty list if opencv-python is not installed.
    """
    try:
        import cv2
    except ImportError:
        print("[Detector] WARNING: opencv-python not installed")
        print("[Detector]   - Multi-word screen capture mode will not work")
        print("[Detector]   - Bbox overlay will fall back to single-word mode")
        print("[Detector]   - Install with: pip install opencv-python")
        return []
 
    img_w, img_h = image.size
    arr  = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
 
    # Save debug images if requested
    if debug_dir:
        try:
            import os
            os.makedirs(debug_dir, exist_ok=True)
            debug_gray_path = os.path.join(debug_dir, "detector_grayscale.png")
            cv2.imwrite(debug_gray_path, gray)
            _log.debug(f"[Detector] Saved grayscale debug to {debug_gray_path}")
        except Exception as e:
            _log.debug(f"[Detector] Failed to save grayscale debug: {e}")
 
    # Try OTSU binary inverse first
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
 
    # If OTSU gives mostly black or mostly white, try adaptive threshold
    white_ratio = np.sum(binary == 255) / (binary.shape[0] * binary.shape[1])
    _log.debug(f"[Detector] OTSU white ratio: {white_ratio:.2%}")
    
    if white_ratio < 0.01 or white_ratio > 0.99:
        _log.debug(f"[Detector] OTSU threshold extreme ({white_ratio:.2%}) — trying adaptive threshold")
        # Adaptive threshold often works better for variable lighting
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=21,
            C=5
        )
        white_ratio = np.sum(binary == 255) / (binary.shape[0] * binary.shape[1])
        _log.debug(f"[Detector] Adaptive white ratio: {white_ratio:.2%}")
 
    # Save binary debug image if requested
    if debug_dir:
        try:
            debug_binary_path = os.path.join(debug_dir, "detector_binary.png")
            cv2.imwrite(debug_binary_path, binary)
            _log.debug(f"[Detector] Saved binary debug to {debug_binary_path}")
        except Exception as e:
            _log.debug(f"[Detector] Failed to save binary debug: {e}")
 
    # Dilate horizontally to merge characters in the same word / line
    kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (dilation_x, dilation_y))
    dilated = cv2.dilate(binary, kernel, iterations=2)
 
    # Save dilated debug image if requested
    if debug_dir:
        try:
            debug_dilated_path = os.path.join(debug_dir, "detector_dilated.png")
            cv2.imwrite(debug_dilated_path, dilated)
            _log.debug(f"[Detector] Saved dilated debug to {debug_dilated_path}")
        except Exception as e:
            _log.debug(f"[Detector] Failed to save dilated debug: {e}")
    
    # Apply connected components analysis to find text blobs
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    
    # Log component stats if debug_dir is set
    if debug_dir:
        try:
            num_comps = max(0, len(stats) - 1)
            _log.debug(f"[Detector] connectedComponents found {num_comps} candidate(s)")
            # Print a handful of stats for inspection
            for i in range(1, min(len(stats), 8)):
                x_i = int(stats[i, cv2.CC_STAT_LEFT])
                y_i = int(stats[i, cv2.CC_STAT_TOP])
                w_i = int(stats[i, cv2.CC_STAT_WIDTH])
                h_i = int(stats[i, cv2.CC_STAT_HEIGHT])
                area_i = int(stats[i, cv2.CC_STAT_AREA])
                _log.debug(f"[Detector] comp#{i}: x={x_i} y={y_i} w={w_i} h={h_i} area={area_i}")
        except Exception:
            pass
 
    regions: List[TextRegion] = []
    for i in range(1, len(stats)):          # index 0 is always background
        x    = int(stats[i, cv2.CC_STAT_LEFT])
        y    = int(stats[i, cv2.CC_STAT_TOP])
        w    = int(stats[i, cv2.CC_STAT_WIDTH])
        h    = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
 
        if area < min_area:
            continue                        # noise
        if w < 4 or h < 4:
            continue                        # too thin to be text
        if w > img_w * 0.92 and h > img_h * 0.5:
            continue                        # covers most of image → background blob
 
        regions.append(TextRegion(x=x, y=y, w=w, h=h))
 
    # Japanese reading order: top band first, then right-to-left within band
    regions.sort(key=lambda r: (r.y // row_band, -(r.x + r.w)))
    return regions
 
 
# ─── Smart Mouse Crop ─────────────────────────────────────────────────────────
 
def smart_crop(
    image:          Image.Image,
    cursor_local_x: int,
    cursor_local_y: int,
    pad:            int = 10,
    debug_dir:      str = "",
) -> Tuple[Image.Image, TextRegion | None]:
    """
    Finds the text region the cursor is hovering over and returns a tight
    crop of that region instead of the fixed-size capture box.
 
    This replaces the fixed 200×60px box in mouse mode with a region that
    exactly fits the line of text the cursor is on — no more cut-off
    characters at the edges, no wasted background context for OCR.
 
    Args:
        image:          Captured PIL Image (centered on cursor).
        cursor_local_x: Cursor X relative to image's top-left corner.
        cursor_local_y: Cursor Y relative to image's top-left corner.
        pad:            Padding (px) to add around the detected region.
        debug_dir:      If set, save debug images for inspection.
 
    Returns:
        (cropped_image, region) — the region is in image-local coordinates.
        Falls back to (original_image, None) if nothing is detected.
    """
    img_w, img_h = image.size
    regions = detect_regions(image, debug_dir=debug_dir)
 
    if not regions:
        # Try sensitive fallback
        regions = detect_regions(image, min_area=20, dilation_x=10, dilation_y=2, debug_dir=debug_dir)
        if not regions:
            return image, None
 
    # First try: cursor is inside a region
    target = next(
        (r for r in regions if r.contains_point(cursor_local_x, cursor_local_y)),
        None,
    )
 
    # Second try: nearest region by center distance
    if target is None:
        target = min(regions, key=lambda r: r.distance_to_point(cursor_local_x, cursor_local_y))
 
    cropped = target.crop_from(image, pad=pad)
    return cropped, target
 
 
# ─── Full Screen Segmentation ─────────────────────────────────────────────────
 
def segment_screen(
    image:      Image.Image,
    max_regions: int = 30,
    min_area:   int  = 200,
) -> List[TextRegion]:
    """
    Detects all text regions across a full screen capture.
    Returns at most `max_regions` largest regions to keep OCR load manageable.
 
    For a 1440×900 downscaled image this takes ~30ms with OpenCV.
    Each returned region can then be cropped and fed to MangaOCR independently.
 
    Args:
        image:       Full screen PIL Image (should already be at logical resolution,
                     not physical — downsample before calling if needed).
        max_regions: Hard cap on number of returned regions.
        min_area:    Minimum region area — higher = fewer, larger regions.
                     Increase to 500+ if you want only paragraph-level blocks.
 
    Returns:
        List[TextRegion] sorted by reading order, capped at max_regions.
    """
    # Wider dilation for screen: more character spacing variation across apps
    regions = detect_regions(
        image,
        min_area=min_area,
        dilation_x=25,
        dilation_y=4,
        row_band=50,
    )
 
    # If too many regions, keep the largest ones (most likely to be readable text)
    if len(regions) > max_regions:
        regions.sort(key=lambda r: r.area, reverse=True)
        regions = regions[:max_regions]
        # Re-sort by reading order after filtering
        regions.sort(key=lambda r: (r.y // 50, -(r.x + r.w)))
 
    return regions
 
 
# ─── Merge Overlapping / Adjacent Regions ─────────────────────────────────────
 
def merge_nearby(
    regions: List[TextRegion],
    gap:     int = 15,
) -> List[TextRegion]:
    """
    Merges regions that are horizontally adjacent (within `gap` pixels).
    Useful for cases where a single line gets split into two blobs.
 
    Args:
        regions: List of TextRegion from detect_regions().
        gap:     Max horizontal gap between regions to still merge them.
 
    Returns:
        New list with merged regions.
    """
    if not regions:
        return []
 
    merged: List[TextRegion] = []
    used = [False] * len(regions)
 
    for i, r in enumerate(regions):
        if used[i]:
            continue
        current = TextRegion(x=r.x, y=r.y, w=r.w, h=r.h)
        for j, other in enumerate(regions):
            if i == j or used[j]:
                continue
            # Same approximate row and horizontally close
            same_row = abs(current.y - other.y) < 20
            h_gap    = other.x - current.right
            if same_row and 0 <= h_gap <= gap:
                # Expand current to include other
                new_right  = max(current.right,  other.right)
                new_bottom = max(current.bottom, other.bottom)
                current = TextRegion(
                    x=min(current.x, other.x),
                    y=min(current.y, other.y),
                    w=new_right  - min(current.x, other.x),
                    h=new_bottom - min(current.y, other.y),
                )
                used[j] = True
 
        merged.append(current)
        used[i] = True
 
    return merged