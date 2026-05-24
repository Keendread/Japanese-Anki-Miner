from sudachipy import Dictionary

class Tokenizer:
    def __init__(self):
        self.tokenizer = Dictionary().create()

    def tokenize(self, text, mode="C"):
        split_mode = {
            "A": self.tokenizer.SplitMode.A,
            "B": self.tokenizer.SplitMode.B,
            "C": self.tokenizer.SplitMode.C,
        }[mode]

        result = []

        for m in self.tokenizer.tokenize(text, split_mode):
            result.append({
                "surface": m.surface(),
                "dictionary": m.dictionary_form(),
                "reading": m.reading_form(),
                "pos": m.part_of_speech()[0]
            })

        return result