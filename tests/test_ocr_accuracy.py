import sys
import os
import json
from rapidfuzz.distance import Levenshtein

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from src.ocr.engine import OCREngine

ocr = OCREngine()

def cer(pred, gt):
    return Levenshtein.distance(pred, gt) / max(len(gt), 1)

def test_ocr_accuracy():
    with open("data/labels.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    total_cer = 0

    for sample in data:
        image_path = os.path.join("dataset", sample["image"])
        gt = sample["text"]

        result = ocr.extract_text(image_path)
        pred = result["text"]

        score = cer(pred, gt)

        print("=" * 40)
        print("GT:   ", gt)
        print("PRED: ", pred)
        print("CER:  ", score)

        total_cer += score

    avg = total_cer / len(data)

    print("\nAVERAGE CER:", avg)

    assert avg < 0.5