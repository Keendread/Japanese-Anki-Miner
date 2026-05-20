import json
from sudachipy import Dictionary
from sudachipy import SplitMode

DATA_PATH = "data/nlp_eval.jsonl"

tokenizer = Dictionary().create()
mode = SplitMode.C

def tokenize(text):
    return [m.surface() for m in tokenizer.tokenize(text, mode)]

def evaluate():
    total_tp = 0
    total_fp = 0
    total_fn = 0
    count = 0

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)

            sentence = item["sentence"]
            gold_tokens = item["tokens"]

            pred_tokens = tokenize(sentence)

            gold_set = set(gold_tokens)
            pred_set = set(pred_tokens)

            tp = len(gold_set & pred_set)
            fp = len(pred_set - gold_set)
            fn = len(gold_set - pred_set)

            total_tp += tp
            total_fp += fp
            total_fn += fn

            count += 1

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

    print("\n===== NLP EVALUATION RESULTS =====")
    print(f"Sentences evaluated: {count}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print("==================================\n")


if __name__ == "__main__":
    evaluate()