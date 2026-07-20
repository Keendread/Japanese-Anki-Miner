from __future__ import annotations

import base64
import logging
import os
import tempfile
import threading
import wave
from typing import Optional


class AudioRecorder:
    def __init__(self) -> None:
        self._pyaudio = None
        self._stream  = None
        self._frames: list[bytes] = []
        self._lock = threading.Lock()
        self._recording = False
        self._channels  = 2
        self._rate      = 48000
        self._sampwidth = 2   # paInt16 = 2 bytes/sample

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _find_loopback_device(self, pa) -> dict:
        import pyaudiowpatch as pyaudio   

        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if default_speakers.get("isLoopbackDevice"):
            return default_speakers

        for loopback in pa.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return loopback

        raise RuntimeError(
            "Default loopback output device not found. "
            "Run `python -m pyaudiowpatch` to list available devices."
        )

    def start(self) -> tuple[bool, Optional[str]]:
        if self._recording:
            logging.warning("[AudioRecorder] start() called while already recording — ignored")
            return True, None

        try:
            import pyaudiowpatch as pyaudio
        except ImportError as e:
            msg = f"PyAudioWPatch not installed or failed to import ({e})"
            logging.error(f"[AudioRecorder] {msg}")
            return False, msg

        try:
            self._pyaudio = pyaudio.PyAudio()
            device = self._find_loopback_device(self._pyaudio)

            self._channels = int(device["maxInputChannels"])
            self._rate     = int(device["defaultSampleRate"])
            self._frames   = []

            def _callback(in_data, frame_count, time_info, status):
                with self._lock:
                    self._frames.append(in_data)
                return (None, pyaudio.paContinue)

            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._rate,
                input=True,
                input_device_index=device["index"],
                frames_per_buffer=512,
                stream_callback=_callback,
            )
            self._stream.start_stream()
            self._recording = True
            logging.info(f"[AudioRecorder] Recording started ({device['name']}, "
                         f"{self._rate}Hz, {self._channels}ch)")
            return True, None

        except Exception as e:
            msg = str(e) or type(e).__name__
            logging.error(f"[AudioRecorder] Failed to start: {e}", exc_info=True)
            self._cleanup()
            return False, msg

    def stop(self) -> Optional[str]:
        if not self._recording:
            logging.warning("[AudioRecorder] stop() called while not recording — ignored")
            return None

        self._recording = False

        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception as e:
            logging.error(f"[AudioRecorder] Error closing stream: {e}")

        with self._lock:
            frames = self._frames
            self._frames = []

        self._cleanup()

        if not frames:
            logging.warning("[AudioRecorder] No audio captured")
            return None

        try:
            fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="jam_rec_")
            os.close(fd)
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(self._channels)
                wf.setsampwidth(self._sampwidth)
                wf.setframerate(self._rate)
                wf.writeframes(b"".join(frames))
            logging.info(f"[AudioRecorder] Saved {len(frames)} chunks -> {temp_path}")
            return temp_path
        except Exception as e:
            logging.error(f"[AudioRecorder] Failed to write WAV: {e}", exc_info=True)
            return None

    def cancel(self) -> None:
        if not self._recording:
            return
        self._recording = False
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass
        with self._lock:
            self._frames = []
        self._cleanup()
        logging.info("[AudioRecorder] Recording cancelled")

    def _cleanup(self) -> None:
        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
        self._pyaudio = None
        self._stream  = None


# ── Module-level singleton ──────────────────────────────────────────────────

_recorder = AudioRecorder()


def start_recording() -> tuple[bool, Optional[str]]:
    return _recorder.start()


def stop_recording() -> Optional[str]:
    return _recorder.stop()


def cancel_recording() -> None:
    _recorder.cancel()


def is_recording() -> bool:
    return _recorder.is_recording


def commit_shared_recording(temp_path: str) -> Optional[str]:
    if not temp_path or not os.path.exists(temp_path):
        logging.warning(f"[AudioRecorder] Temp audio file missing: {temp_path}")
        return None

    from core.anki import _ankiconnect   # reuse the existing AnkiConnect helper

    try:
        with open(temp_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        filename = os.path.basename(temp_path)
        _ankiconnect("storeMediaFile", filename=filename, data=data)
        logging.info(f"[AudioRecorder] Committed shared recording: {filename}")
        return filename
    except Exception as e:
        logging.error(f"[AudioRecorder] Failed to commit shared recording: {e}", exc_info=True)
        return None
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass