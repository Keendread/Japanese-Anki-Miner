from pynput import keyboard
from pipeline import JAMPipeline

pipeline = JAMPipeline()

def run():
    result = pipeline.run()

    print("\n--- OCR TEXT ---")
    print(result["text"])

    print("\n--- TOKENS ---")
    print(result["tokens"])


def on_press(key):
    if key == keyboard.Key.f8:
        run()

print("JAM Pipeline running... Press F8")

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()