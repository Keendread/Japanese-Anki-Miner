from manga_ocr import MangaOcr

class OCREngine:
    def __init__(self):
        # load ONCE (very important for latency < 2s)
        self.model = MangaOcr()

    def extract_text(self, image):
        return self.model(image)