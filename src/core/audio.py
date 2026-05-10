# Module for good to have feature of automatically adding audio to the words
# Uses VOICEVOX and word audio fetching (from popular audio databases)
# Might require some research on how to fetch audio

# Fetches audio from local VOICEVOX HTTP server and caches to disk

import os
import aiohttp
import aiofiles
import asyncio
from typing import Optional, Dict, Any
from src.models.word import Word
from src.models.audio import AudioFile

VOICEVOX_URL: str = "http://localhost:50021"
VOICEVOX_SPEAKER_ID: int = 1 # Default speaker ID for VOICEVOX (can be customized by user later)

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

def _sanitize_filename(text: str) -> str:
    """
    Converts a word to a safe filename.
    Removes problematic characters while preserving readability.
    """
    # Replace path separators and other unsafe chars
    unsafe_chars: str = r'<>:"/\|?*'
    for char in unsafe_chars:
        text = text.replace(char, "_")
    return text

def _get_cache_path(dictionary_form: str, reading: str) -> str:
    """
    Returns the full filesystem path for cached audio file.
    Uses both dictionary_form and reading to ensure uniqueness.
    
    """
    filename: str = f"{_sanitize_filename(dictionary_form)}_{_sanitize_filename(reading)}.wav"
    return os.path.join(_get_audio_dir(), filename)

def _get_cached_audio(dictionary_form: str, reading: str) -> Optional[str]:
    """
    Returns path to cached audio if it exists, None otherwise.
    """
    cache_path: str = _get_cache_path(dictionary_form, reading)
    if os.path.exists(cache_path):
        return cache_path
    return None

async def _voicevox_audio_query(session: aiohttp.ClientSession, text: str) -> Optional[Dict[str, Any]]:
    """
    Get audio synthesis parameters from VOICEVOX.
    """
    try:
        async with session.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": VOICEVOX_SPEAKER_ID},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    except aiohttp.ClientConnectionError:
        print(f"[Audio] VOICEVOX not reachable at {VOICEVOX_URL}. Is it running?")
        return None
    except Exception as e:
        print(f"[Audio] Audio query failed for '{text}': {e}")
        return None

async def _voicevox_synthesize(session: aiohttp.ClientSession, audio_query: Dict[str, Any]) -> Optional[bytes]:
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
            params={"speaker": VOICEVOX_SPEAKER_ID},
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

async def _fetch_single(session: aiohttp.ClientSession, text: str, cache_key: str, cache_reading: str) -> Optional[str]:
    """
    Reusable helper: checks cache, queries, synthesizes, saves.
    Used for both word and sentence audio.
    """
    cached = _get_cached_audio(cache_key, cache_reading)
    if cached:
        print(f"[Audio] Using cached audio: {cached}")
        return cached

    query = await _voicevox_audio_query(session, text)
    if query is None:
        return None

    audio_bytes = await _voicevox_synthesize(session, query)
    if audio_bytes is None:
        return None

    cache_path = _get_cache_path(cache_key, cache_reading)
    if await _save_audio(audio_bytes, cache_path):
        return cache_path

    return None

async def fetch_audio(word: Word) -> Optional[AudioFile]:
    """
    Main entry point: fetches word and sentence audio concurrently.

    Flow:
    1. Check cache for both word and sentence
    2. Fire off both VOICEVOX requests concurrently (asyncio.gather)
    3. Save results to disk
    4. Return AudioFile

    Args:
        word: Word object

    Returns:
        AudioFile with word_audio (and sentence_audio if available), or None if word audio fails
    """

    async with aiohttp.ClientSession() as session:
        # Build tasks
        word_task = _fetch_single(
            session,
            text=word.reading,
            cache_key=word.dictionary_form,
            cache_reading=word.reading,
        )

        sentence_task = None
        if word.example_jp:
            assert word.sentence_furigana is not None
            sentence_task = _fetch_single(
                session,
                text=word.example_jp,
                cache_key=word.example_jp,
                cache_reading=word.sentence_furigana,
            )

        # Run word and sentence concurrently
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