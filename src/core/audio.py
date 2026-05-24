# Module for good to have feature of automatically adding audio to the words
# Uses VOICEVOX and word audio fetching (from popular audio databases)
# Might require some research on how to fetch audio

# Fetches audio from local VOICEVOX HTTP server and caches to disk
# Asynchronously fetches both word and sentence audio concurrently to avoid UI blocking (might take < 5 seconds)
# As such, audio files are saved (updated essentially) after card creation instead of during the card creation.

import os
import aiohttp
import aiofiles
import asyncio
import hashlib

from typing import Optional, Dict, Any
from src.models.word import Word
from src.models.audio import AudioFile

from random import randint

VOICEVOX_URL: str = "http://localhost:50021"
VOICEVOX_SPEAKER_ID: int = 3  # fallback, overridden by settings at runtime

def get_speaker_id(settings) -> int:
    """Returns the configured speaker ID from settings."""
    return settings.get("voicevox_speaker_id", VOICEVOX_SPEAKER_ID)

# Speaker registry — populated at startup by query_speakers()
# Falls back to known defaults if VOICEVOX is unreachable
VOICEVOX_SPEAKERS = [
    {"japanese": "四国めたん",   "english": "Shikoku Metan",    "id": 2},
    {"japanese": "ずんだもん",   "english": "Zundamon",         "id": 3},
    {"japanese": "春日部つむぎ", "english": "Kasukabe Tsumugi", "id": 8},
    {"japanese": "玄野武宏",     "english": "Kurano Takehiro",  "id": 11},
    {"japanese": "城上虎太郎",   "english": "Jogami Kotaro",    "id": 52},
    {"japanese": "青山龍星",     "english": "Aoyama Ryusei",    "id": 13},
]

_TARGET_NAMES = {s["japanese"] for s in VOICEVOX_SPEAKERS}

def refresh_speaker_ids() -> None:
    """
    Queries VOICEVOX /speakers and updates IDs for ノーマル style.
    Call once at startup in a background thread.
    """
    import urllib.request, json
    try:
        with urllib.request.urlopen(f"{VOICEVOX_URL}/speakers", timeout=3) as resp:
            data = json.loads(resp.read())
        id_map = {}
        for speaker in data:
            if speaker["name"] in _TARGET_NAMES:
                for style in speaker["styles"]:
                    if style["name"] == "ノーマル":
                        id_map[speaker["name"]] = style["id"]
                        break
        for entry in VOICEVOX_SPEAKERS:
            if entry["japanese"] in id_map:
                entry["id"] = id_map[entry["japanese"]]
        print(f"[Audio] Speaker IDs refreshed from VOICEVOX.")
    except Exception as e:
        print(f"[Audio] Could not refresh speaker IDs, using defaults: {e}")

def _get_audio_dir() -> str:
    """
    Returns path to data/audio/voicevox/ directory.
    """
    core_dir: str = os.path.dirname(os.path.abspath(__file__)) # src/core/
    src_dir: str = os.path.dirname(core_dir)                   # src/
    root_dir: str = os.path.dirname(src_dir)                   # project root
    audio_dir: str = os.path.join(root_dir, "data", "audio", "voicevox")
    os.makedirs(audio_dir, exist_ok=True)
    return audio_dir

def _get_path(dictionary_form: str, reading: str) -> str:
    """
    Returns the full filesystem path for the audio file.
    Uses hash to ensure uniqueness.
    
    """
    hash_str = hashlib.sha256(f"{dictionary_form}_{reading}".encode()).hexdigest()[:16]
    filename: str = f"vv_{hash_str}.wav"
    return os.path.join(_get_audio_dir(), filename)

async def _voicevox_audio_query(session: aiohttp.ClientSession, text: str,
                                 speaker_id: int) -> Optional[Dict[str, Any]]:
    """
    Get audio synthesis parameters from VOICEVOX.
    """
    try:
        async with session.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker_id},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    except aiohttp.ClientConnectionError:
        print(f"[Audio] VOICEVOX not reachable at {VOICEVOX_URL}. Is it running?")
        return None
    except Exception as e:
        print(f"[Audio] Audio query failed for '{text}': {e}")
        return None

async def _voicevox_synthesize(session: aiohttp.ClientSession,
                                audio_query: Dict[str, Any],
                                speaker_id: int) -> Optional[bytes]:
    """
    Synthesize WAV audio from audio_query.

    Args:
        session: Shared aiohttp session
        audio_query: Result from _voicevox_audio_query()

    Returns:
        WAV audio bytes, or None on error
    """
    try:
        async with session.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker_id},
            json=audio_query,
        ) as resp:
            resp.raise_for_status()
            return await resp.read()
    except Exception as e:
        print(f"[Audio] Synthesis failed: {e}")
        return None

async def _save_audio(audio_bytes: bytes, cache_path: str) -> bool:
    """Saves audio bytes to disk asynchronously."""
    try:
        async with aiofiles.open(cache_path, "wb") as f:
            await f.write(audio_bytes)
        print(f"[Audio] Cached: {cache_path}")
        return True
    except Exception as e:
        print(f"[Audio] Failed to save audio: {e}")
        return False

async def _fetch_single(session: aiohttp.ClientSession, text: str,
                         cache_key: str, cache_reading: str,
                         speaker_id: int) -> Optional[str]:
    """
    Fetch audio from VOICEVOX: queries, synthesizes, saves to disk.
    Used for both word and sentence audio.
    
    Note: No cache check needed here. Since duplicate check happens before
    audio fetching, we only fetch audio for fresh words (first time mined).
    """
    query = await _voicevox_audio_query(session, text, speaker_id)
    if query is None:
        return None
    audio_bytes = await _voicevox_synthesize(session, query, speaker_id)
    if audio_bytes is None:
        return None
    cache_path = _get_path(cache_key, cache_reading)
    if await _save_audio(audio_bytes, cache_path):
        return cache_path
    return None

async def fetch_audio(word: Word, settings=None) -> Optional[AudioFile]:
    """
    Main entry point: fetches word and sentence audio concurrently.

    Flow:
    1. Fire off both VOICEVOX requests concurrently (asyncio.gather)
    2. Save results to disk
    3. Return AudioFile

    Args:
        word: Word object

    Returns:
        AudioFile with word_audio (and sentence_audio if available), or None if word audio fails
    """
    speaker_id = get_speaker_id(settings) if settings else VOICEVOX_SPEAKER_ID

    async with aiohttp.ClientSession() as session:
        word_task = _fetch_single(
            session,
            text=word.reading,
            cache_key=word.dictionary_form,
            cache_reading=word.reading,
            speaker_id=speaker_id,
        )

        sentence_fallback = None
        if word.glossary and len(word.glossary) > 0:
            sentence_fallback = word.glossary[0].get("example_jp")

        sentence = word.full_sentence or sentence_fallback
        if sentence_fallback and sentence == word.surface:
            sentence = sentence_fallback

        sentence_task = None
        if sentence:
            sentence_task = _fetch_single(
                session,
                text=sentence,
                cache_key=sentence,
                cache_reading=sentence,
                speaker_id=speaker_id,
            )

        if sentence_task:
            word_path, sentence_path = await asyncio.gather(word_task, sentence_task)
        else:
            word_path = await word_task
            sentence_path = None

    if word_path is None:
        print(f"[Audio] Could not generate audio for '{word.dictionary_form}'")
        return None

    return AudioFile(
        word=word.surface,
        word_audio=word_path,
        sentence_audio=sentence_path,
    )
    
_preview_cache: dict[int, bytes] = {}

async def preview_speaker(speaker_id: int) -> Optional[bytes]:
    # Return cached bytes if already fetched this session
    if speaker_id in _preview_cache:
        return _preview_cache[speaker_id]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{VOICEVOX_URL}/speakers/voice_samples",
                params={"speaker_id": speaker_id},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    _preview_cache[speaker_id] = data
                    return data
    except Exception as e:
        print(f"[Audio] voice_samples fetch failed: {e}")

    # Fallback: synthesize short phrase
    try:
        preview_text = "よろしくお願いします。"
        async with aiohttp.ClientSession() as session:
            query = await _voicevox_audio_query(session, preview_text, speaker_id)
            if query:
                query["speedScale"] = 1.2
                data = await _voicevox_synthesize(session, query, speaker_id)
                if data:
                    _preview_cache[speaker_id] = data
                    return data
    except Exception as e:
        print(f"[Audio] Preview synthesis fallback failed: {e}")

    return None