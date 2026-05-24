import ctypes
ctypes.windll.user32.SetProcessDPIAware()

import time
import pyautogui
import cv2
import numpy as np

from ocr.capture import capture_region
from ocr.engine import OCREngine
from ocr.detector import TextDetector

from nlp.tokenizer import Tokenizer
from nlp.dictionary import Dictionary

from exporters.voicevox import VoiceVox
from exporters.anki import add_to_anki


BOX_SIZE = 300


class JAMPipeline:
    def __init__(self):
        self.ocr = OCREngine()
        self.detector = TextDetector()
        self.tokenizer = Tokenizer()
        self.dictionary = Dictionary()
        self.voice = VoiceVox()

        self.last_text = ""
        self.last_time = 0

    # -------------------------
    # TOKEN FILTERING
    # -------------------------
    def is_noise_token(self, t):
        text = t["surface"]

        if t.get("pos") == "補助記号":
            return True

        if text.isascii() and len(text) > 1:
            return True

        if "." in text:
            return True

        return False

    def score_token(self, t):
        score = 0

        if t.get("pos") in ["名詞", "動詞"]:
            score += 10

        if any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in t["surface"]):
            score += 5

        score += len(t["surface"])  # slight preference for meaningful words

        return score

    # -------------------------
    # BOX SELECTION
    # -------------------------
    def box_contains_cursor(self, box, cx, cy):
        x1, x2, y1, y2 = map(int, box)
        return x1 <= cx <= x2 and y1 <= cy <= y2

    def pick_best_box(self, boxes, cx, cy):
        best = None
        best_dist = float("inf")

        for b in boxes:
            x1, x2, y1, y2 = map(int, b)

            bx = (x1 + x2) / 2
            by = (y1 + y2) / 2

            dist = (bx - cx) ** 2 + (by - cy) ** 2

            if dist < best_dist:
                best_dist = dist
                best = b

        return best

    # -------------------------
    # MAIN PIPELINE
    # -------------------------
    def run(self):
        # 1. CURSOR POSITION
        x, y = pyautogui.position()

        left = x - BOX_SIZE // 2
        top = y - BOX_SIZE // 2

        img = capture_region(left, top, BOX_SIZE, BOX_SIZE)

        # 2. DETECT TEXT BOXES
        boxes = self.detector.detect(img)

        if not boxes:
            return {"text": "", "tokens": []}

        # convert cursor into image space
        cx, cy = x - left, y - top

        # 3. PICK TARGET BOX
        target_box = None

        for b in boxes:
            if self.box_contains_cursor(b, cx, cy):
                target_box = b
                break

        if target_box is None:
            target_box = self.pick_best_box(boxes, cx, cy)

        x1, x2, y1, y2 = map(int, target_box)
        cropped = img.crop((x1, y1, x2, y2))

        # 4. OCR
        result = self.ocr.extract_text(cropped)

        text = result.get("text", "")
        confidence = result.get("confidence", 1.0)

        # clean text
        text = text.replace("\n", " ")
        text = " ".join(text.split()).strip()

        # 5. DEDUPLICATION
        now = time.time()
        if text == self.last_text and (now - self.last_time) < 2:
            return {"text": "", "tokens": []}

        self.last_text = text
        self.last_time = now

        if not text or confidence < 0.6:
            return {"text": "", "tokens": []}

        # 6. TOKENIZE
        tokens = self.tokenizer.tokenize(text, mode="C")

        clean_tokens = [t for t in tokens if not self.is_noise_token(t)]

        if not clean_tokens:
            return {"text": "", "tokens": []}

        # 7. PICK BEST WORD (real linguistic scoring)
        best_token = max(clean_tokens, key=self.score_token)

        target_word = best_token.get("dictionary", best_token["surface"])

        # 8. DICTIONARY LOOKUP
        dictionary_data = self.dictionary.lookup(target_word)

        reading = dictionary_data.get("reading", "")
        meaning = dictionary_data.get("meaning", "")

        # 9. VOICEVOX AUDIO
        word_audio = self.voice.generate_audio(
            target_word,
            f"audio/{target_word}_word.wav"
        )

        sentence_audio = self.voice.generate_audio(
            text,
            f"audio/{target_word}_sentence.wav"
        )

        # 10. ANKI EXPORT (STRUCTURED)
        note = {
            "deckName": "JAM",
            "modelName": "Basic",
            "fields": {
                "Word": target_word,
                "Reading": reading,
                "Meaning": meaning,
                "Sentence": text,
                "WordAudio": f"[sound:{word_audio}]",
                "SentenceAudio": f"[sound:{sentence_audio}]"
            },
            "tags": ["JAM", "auto"]
        }

        add_to_anki(note)

        # 11. RETURN DEBUG INFO
        return {
            "text": text,
            "tokens": tokens,
            "target_word": target_word,
            "reading": reading,
            "meaning": meaning
        }