import easyocr
import numpy as np

class TextDetector:
    def __init__(self):
        # detection only
        self.reader = easyocr.Reader(
            ['ja'],
            gpu=False
        )

    def detect(self, image):
        """
        Returns list of detected text boxes
        """

        results = self.reader.detect(
            np.array(image)
        )

        horizontal_boxes = results[0][0]

        return horizontal_boxes