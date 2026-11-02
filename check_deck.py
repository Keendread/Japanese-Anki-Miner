import sys
sys.path.append('.')
from src.core.ankiconnect import AnkiConnect
client = AnkiConnect()
notes = client.find_notes('deck:"日本語::Kaishi 1.5k"')
print(f"Found {len(notes)} notes in deck")
