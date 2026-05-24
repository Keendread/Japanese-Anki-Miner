import numpy as np

class WordMapper:
    def split_lines(self, binary_image):
        row_sum = np.sum(binary_image, axis=1)

        lines = []
        in_line = False
        start = 0

        for i, val in enumerate(row_sum):
            if val > 0 and not in_line:
                start = i
                in_line = True
            elif val == 0 and in_line:
                lines.append((start, i))
                in_line = False

        return lines