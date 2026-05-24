import requests
import os

VOICEVOX_URL = "http://127.0.0.1:50021"


class VoiceVox:
    def __init__(self, speaker=1):
        self.speaker = speaker

    def generate_audio(self, text, output_path):
        os.makedirs("audio", exist_ok=True)

        # STEP 1: Create audio query
        query_response = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={
                "text": text,
                "speaker": self.speaker
            }
        )

        query_data = query_response.json()

        # STEP 2: Synthesize audio
        audio_response = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={
                "speaker": self.speaker
            },
            json=query_data
        )

        # STEP 3: Save WAV file
        with open(output_path, "wb") as f:
            f.write(audio_response.content)

        return output_path