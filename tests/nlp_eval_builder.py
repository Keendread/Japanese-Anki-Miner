from datasets import load_dataset
import json

# Directly load Japanese GSD dataset
ds = load_dataset(
    "universal-dependencies/universal_dependencies",
    "ja_gsd",
    split="train",
    streaming=True,
    trust_remote_code=True
)

output_file = "data/nlp_eval.jsonl"

count = 0
MAX_SAMPLES = 2000

with open(output_file, "w", encoding="utf-8") as f:
    for item in ds:
        if count >= MAX_SAMPLES:
            break

        sentence = item["text"]

        # extract token forms
        tokens = item["tokens"]

        if not sentence or not tokens:
            continue

        json.dump(
            {
                "sentence": sentence,
                "tokens": tokens
            },
            f,
            ensure_ascii=False
        )

        f.write("\n")

        count += 1

print(f"Saved {count} entries to {output_file}")