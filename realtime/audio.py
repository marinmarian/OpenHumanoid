"""
Audio I/O for the Realtime API client.

Captures microphone input as PCM16 24kHz mono, encodes to base64 for the
Realtime API. Plays back audio response chunks through the speaker.
"""

import base64
import ctypes
import queue
import threading

import numpy as np

# Suppress ALSA warnings (import-time and runtime underrun messages).
# The callback reference MUST be kept alive at module scope to avoid segfault.
_ALSA_ERROR_HANDLER = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int,
    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
)

def _null_alsa_handler(filename, line, function, err, fmt):
    pass

_c_alsa_handler = _ALSA_ERROR_HANDLER(_null_alsa_handler)

try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _asound.snd_lib_error_set_handler(_c_alsa_handler)
except OSError:
    pass

import sounddevice as sd

SAMPLE_RATE = 24000  # Realtime API expects 24kHz for pcm16
CHANNELS = 1
BLOCK_SIZE = 2400  # 100ms of audio at 24kHz
DTYPE = "int16"


class AudioInput:
    """Captures microphone audio and provides base64-encoded PCM16 chunks."""

    def __init__(self, sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream = None

    def start(self):
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=self.block_size,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass  # drop warnings for now
        self._queue.put(bytes(indata))

    def get_chunk_base64(self, timeout=0.2) -> str | None:
        """Get the next audio chunk as a base64 string, or None on timeout."""
        try:
            raw = self._queue.get(timeout=timeout)
            return base64.b64encode(raw).decode("ascii")
        except queue.Empty:
            return None


class AudioOutput:
    """Plays back base64-encoded PCM16 audio chunks from the Realtime API."""

    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream = None
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            latency="high",
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def enqueue(self, base64_audio: str):
        """Add a base64-encoded PCM16 chunk to the playback queue."""
        raw = base64.b64decode(base64_audio)
        self._queue.put(raw)

    def clear(self):
        """Clear pending audio (e.g., when user interrupts)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _playback_loop(self):
        while self._running:
            try:
                raw = self._queue.get(timeout=0.1)
                audio = np.frombuffer(raw, dtype=np.int16)
                self._stream.write(audio)
            except queue.Empty:
                continue
            except Exception:
                continue
