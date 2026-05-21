import ctypes
ctypes.windll.user32.SetProcessDPIAware()

import pyautogui

from ocr.capture import capture_region
from ocr.engine import OCREngine
from nlp.tokenizer import Tokenizer

from ocr.detector import TextDetector

BOX_SIZE = 300

class JAMPipeline:
    def __init__(self):
        self.ocr = OCREngine()
        self.tokenizer = Tokenizer()
        self.detector = TextDetector()

    def run(self):
        # 1. get cursor position
        x, y = pyautogui.position()

        # 2. capture screen around cursor
        left = x - BOX_SIZE // 2
        top = y - BOX_SIZE // 2

        img = capture_region(left, top, BOX_SIZE, BOX_SIZE)
        

        # 3. OCR
        boxes = self.detector.detect(img)

        if not boxes:
            return {"text": "", "tokens": []}

        # choose first detected box for now
        # center of capture box
        cx = BOX_SIZE // 2
        cy = BOX_SIZE // 2

        best_box = None
        best_distance = float("inf")

        for box in boxes:
            x1, x2, y1, y2 = map(int, box)

            # center of detected text box
            bx = (x1 + x2) / 2
            by = (y1 + y2) / 2

            dist = ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5

            if dist < best_distance:
                best_distance = dist
                best_box = box

        x1, x2, y1, y2 = map(int, best_box)

        cropped = img.crop((x1, y1, x2, y2))

        text = self.ocr.extract_text(cropped)

        if not text:
            return {"text": "", "tokens": []}

        # 4. NLP tokenization
        tokens = self.tokenizer.tokenize(text, mode="C")

        return {
            "text": text,
            "tokens": tokens
        }
