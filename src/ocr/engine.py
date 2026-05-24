from manga_ocr import MangaOcr

class OCREngine:
    def __init__(self):
        from manga_ocr import MangaOcr
        self.model = MangaOcr()

    def extract_text(self, img):
        text = self.model(img)  # ✅ correct usage

        return {
            "text": text,
            "confidence": 1.0  # MangaOCR doesn't return confidence
        }