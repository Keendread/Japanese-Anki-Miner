"""
FULL EVALUATION PIPELINE (FIXED PATH VERSION)
"""

import subprocess
import sys
from pathlib import Path


def run_test(file_path):
    print("\n" + "=" * 60)
    print(f"RUNNING: {file_path}")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(file_path), "-v", "-s"],
        cwd=Path.cwd().parent,  # IMPORTANT FIX
    )

    return result.returncode == 0


def main():

    base = Path("tests")

    tests = [
        base / "test_ocr_latency.py",
        base / "test_ocr_accuracy.py",
        base / "test_parser_latency.py",
        base / "test_parser_accuracy.py",
    ]

    results = {}

    for test in tests:
        results[str(test)] = run_test(test)

    print("\n\n==============================")
    print(" FINAL EVALUATION SUMMARY")
    print("==============================")

    for k, v in results.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")

    if all(results.values()):
        print("\nALL TESTS PASSED ✔")
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED ✖")
        sys.exit(1)


if __name__ == "__main__":
    main()