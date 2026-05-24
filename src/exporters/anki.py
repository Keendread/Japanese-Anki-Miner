import requests

def add_to_anki(note):
    try:
        requests.post(
            "http://localhost:8765",
            json={
                "action": "addNote",
                "version": 6,
                "params": {"note": note}
            },
            timeout=1
        )
    except Exception:
        print("[JAM] Anki not running → skipping export")