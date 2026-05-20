import pyautogui

from ocr.capture import capture_region
from ocr.engine import OCREngine
from nlp.tokenizer import Tokenizer

BOX_SIZE = 300

class JAMPipeline:
    def __init__(self):
        self.ocr = OCREngine()
        self.tokenizer = Tokenizer()

    def run(self):
        # 1. get cursor position
        x, y = pyautogui.position()

        # 2. capture screen around cursor
        left = x - BOX_SIZE // 2
        top = y - BOX_SIZE // 2

        img = capture_region(left, top, BOX_SIZE, BOX_SIZE)

        # 3. OCR
        text = self.ocr.extract_text(img)

        if not text:
            return {"text": "", "tokens": []}

        # 4. NLP tokenization
        tokens = self.tokenizer.tokenize(text, mode="C")

        return {
            "text": text,
            "tokens": tokens
        }