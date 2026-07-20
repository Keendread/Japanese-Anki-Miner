from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PIL import Image


@dataclass
class TextRegion:
    x: int          # left edge
    y: int          # top edge
    w: int          # width
    h: int          # height
    text: str = ""  # OCR result — filled by ocr.extract_blocks()

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
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def distance_to_point(self, px: int, py: int) -> float:
        cx, cy = self.center
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5

    # ── Crop helpers ──────────────────────────────────────────────────────────

    def to_pil_box(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.right, self.bottom)

    def padded(self, pad: int, img_w: int = 99999, img_h: int = 99999) -> "TextRegion":
        return TextRegion(
            x=max(0,     self.x - pad),
            y=max(0,     self.y - pad),
            w=min(img_w, self.w + pad * 2),
            h=min(img_h, self.h + pad * 2),
            text=self.text,
        )

    def crop_from(self, image: Image.Image, pad: int = 2) -> Image.Image:
        img_w, img_h = image.size
        box = self.padded(pad, img_w, img_h).to_pil_box()
        return image.crop(box)