import pyautogui
from pynput import keyboard

from ocr.capture import capture_region
from ocr.engine import OCREngine

BOX_SIZE = 300
ocr = OCREngine()

def run_ocr():
    x, y = pyautogui.position()

    left = x - BOX_SIZE // 2
    top = y - BOX_SIZE // 2

    img = capture_region(left, top, BOX_SIZE, BOX_SIZE)
    text = ocr.extract_text(img)

    print("\n--- OCR RESULT ---")
    print(text)


def on_press(key):
    if key == keyboard.Key.f8:
        run_ocr()

print("OCR test running... Press F8")
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()