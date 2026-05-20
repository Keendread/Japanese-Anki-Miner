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
VOICEVOX_SPEAKER_ID: int = 3 # Default speaker ID for VOICEVOX (can be customized by user later)

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
    Fetch audio from VOICEVOX: queries, synthesizes, saves to disk.
    Used for both word and sentence audio.
    
    Note: No cache check needed here. Since duplicate check happens before
    audio fetching, we only fetch audio for fresh words (first time mined).
    """
    query = await _voicevox_audio_query(session, text)
    if query is None:
        return None

    audio_bytes = await _voicevox_synthesize(session, query)
    if audio_bytes is None:
        return None

    cache_path = _get_path(cache_key, cache_reading)
    if await _save_audio(audio_bytes, cache_path):
        return cache_path

    return None

async def fetch_audio(word: Word) -> Optional[AudioFile]:
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

    async with aiohttp.ClientSession() as session:
        # Build tasks
        word_task = _fetch_single(
            session,
            text=word.reading,
            cache_key=word.dictionary_form,
            cache_reading=word.reading,
        )

        sentence_fallback: str | None = None
        if (word.glossary and len(word.glossary) > 0):
            sentence_fallback = word.glossary[0].get("example_jp")

        sentence_task = None
        sentence = word.full_sentence or sentence_fallback

        if (sentence_fallback and sentence == word.surface):
            sentence = sentence_fallback
            
        if sentence:
            sentence_task = _fetch_single(
                session,
                text=sentence,
                cache_key=sentence,
                cache_reading=sentence,
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