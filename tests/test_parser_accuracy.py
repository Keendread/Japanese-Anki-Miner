"""
Parser Accuracy Evaluation (NLP metrics)

Goal:
- Measure correctness of tokenization / parsing
- Compute Precision, Recall, F1-score

No external dependencies.
"""

import pytest
from src.core.parser import parse


# =========================
# SMALL GOLD DATASET
# (Replace later with UD Japanese GSD)
# =========================
TEST_SET = [
    (
        "今日は天気がいい",
        ["今日", "は", "天気", "が", "いい"]
    ),
    (
        "猫が好き",
        ["猫", "が", "好き"]
    ),
    (
        "昨日友達と会った",
        ["昨日", "友達", "と", "会っ", "た"]
    ),
]


# =========================
# METRICS
# =========================
def precision(tp, fp):
    return tp / (tp + fp) if (tp + fp) else 0.0


def recall(tp, fn):
    return tp / (tp + fn) if (tp + fn) else 0.0


def f1(p, r):
    return (2 * p * r / (p + r)) if (p + r) else 0.0


# =========================
# EVALUATION FUNCTION
# =========================
def evaluate(pred, gold):
    pred_set = set(pred)
    gold_set = set(gold)

    tp = len(pred_set & gold_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)

    p = precision(tp, fp)
    r = recall(tp, fn)
    f = f1(p, r)

    return p, r, f


# =========================
# TEST CLASS
# =========================
class TestParserAccuracy:

    def test_parser_accuracy(self):

        total_p = 0
        total_r = 0
        total_f = 0

        for sentence, gold in TEST_SET:
            pred = parse(sentence)

            p, r, f = evaluate(pred, gold)

            total_p += p
            total_r += r
            total_f += f

            print("\n====================")
            print("Sentence:", sentence)
            print("Gold    :", gold)
            print("Pred    :", pred)
            print(f"P/R/F   : {p:.2f} / {r:.2f} / {f:.2f}")

        n = len(TEST_SET)

        print("\n===== FINAL RESULTS =====")
        print(f"Precision: {total_p/n:.3f}")
        print(f"Recall   : {total_r/n:.3f}")
        print(f"F1 Score : {total_f/n:.3f}")

        # baseline requirement for CS paper
        assert (total_f / n) > 0.50


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])