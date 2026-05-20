from sudachipy import Dictionary

class Tokenizer:
    def __init__(self):
        self.tokenizer = Dictionary().create()

    def tokenize(self, text, mode="C"):
        """
        Returns list of tokens (words)
        mode:
            A = loose split
            B = balanced
            C = most accurate (BEST for JAM)
        """
        split_mode = {
            "A": self.tokenizer.SplitMode.A,
            "B": self.tokenizer.SplitMode.B,
            "C": self.tokenizer.SplitMode.C,
        }[mode]

        return [m.surface() for m in self.tokenizer.tokenize(text, split_mode)]