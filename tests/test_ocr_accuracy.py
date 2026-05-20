"""
OCR Accuracy Evaluation (CER-based)

Goal:
- Compare OCR output vs ground truth
- Compute Character Error Rate (CER)

No external dependencies.
"""

import os
import pytest
from PIL import Image
from difflib import SequenceMatcher
from src.core.ocr import extract_text


# =========================
# DATASET PATHS
# =========================
ICDAR_DIR = "data/icdar/"
MANGA109_DIR = "data/manga109/"


# =========================
# CER METRIC
# =========================
def cer(pred, gt):
    """
    Character Error Rate (0 = perfect, 1 = worst)
    """
    return 1 - SequenceMatcher(None, pred, gt).ratio()


# =========================
# DATA LOADER
# =========================
def load_dataset(path):
    samples = []

    if not os.path.exists(path):
        return samples

    for file in os.listdir(path):
        if file.endswith((".png", ".jpg", ".jpeg")):
            img_path = os.path.join(path, file)
            txt_path = os.path.splitext(img_path)[0] + ".txt"

            if not os.path.exists(txt_path):
                continue

            with open(txt_path, "r", encoding="utf-8") as f:
                gt = f.read().strip()

            samples.append((img_path, gt))

    return samples


# =========================
# TEST CLASS
# =========================
class TestOCRAccuracy:

    def run_eval(self, dataset, name):
        assert len(dataset) > 0, f"{name} dataset empty"

        total_cer = 0

        for img_path, gt in dataset:
            image = Image.open(img_path)

            pred = extract_text(image).strip()

            error = cer(pred, gt)
            total_cer += error

            print("\n====================")
            print(name, img_path)
            print("GT  :", gt)
            print("PRED:", pred)
            print("CER :", round(error, 4))

        avg = total_cer / len(dataset)

        print(f"\n{name} AVG CER: {avg:.4f}")
        return avg

    # =========================
    # ICDAR TEST
    # =========================
    def test_icdar(self):
        data = load_dataset(ICDAR_DIR)
        avg = self.run_eval(data, "ICDAR")
        assert avg < 0.30

    # =========================
    # MANGA109 TEST
    # =========================
    def test_manga109(self):
        data = load_dataset(MANGA109_DIR)
        avg = self.run_eval(data, "MANGA109")
        assert avg < 0.35


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])