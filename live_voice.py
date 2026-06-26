"""ChatGPT-style natural voice via the Gemini Live API (native-audio).

Unlike the old listen → transcribe → think → TTS pipeline, this opens ONE
bidirectional streaming session: your microphone audio streams up continuously and
Ember's spoken reply streams back as audio — so it hears *how* you speak (accent,
tone, pace), replies in a natural neural voice, and supports server-side barge-in
(start talking and it stops to listen). The native-audio Live models also lift the
per-minute request cap that made the old per-message pipeline hit 429s.

Why this design is testable despite needing a live socket:
  * the network/audio bits (genai client, pyaudio) are imported lazily and live ONLY
    in the real mic/player/connection wrappers;
  * the session STATE MACHINE — what to do with each server message, how the sender
    and receiver loops cooperate, stop/interrupt handling — is pure async logic that
    runs against injected fakes. parse_message() is a pure function.
The live websocket itself is verified on-device; everything around it is unit-tested.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

# Live API audio formats: input 16-bit PCM mono @16k, output PCM @24k.
AUDIO_IN_RATE = 16000
AUDIO_OUT_RATE = 24000
AUDIO_IN_MIME = f"audio/pcm;rate={AUDIO_IN_RATE}"
CHUNK = 1024

# A current native-audio dialog model (overridable from settings).
DEFAULT_MODEL = "gemini-2.5-flash-preview-native-audio-dialog"
DEFAULT_VOICE = "Zephyr"
DEFAULT_API_VERSION = "v1beta"


def _noop(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# Pure message parsing (the most-tested piece)
# ---------------------------------------------------------------------------

def parse_message(msg) -> dict:
    """Extract the bits we care about from one Live API server message, defensively
    (the SDK's shape varies by version). Returns a dict with audio/user_text/
    ember_text/interrupted/turn_complete."""
    out = {"audio": None, "user_text": None, "ember_text": None,
           "interrupted": False, "turn_complete": False}
    if msg is None:
        return out
    data = getattr(msg, "data", None)
    if isinstance(data, (bytes, bytearray)) and len(data) > 0:
        out["audio"] = bytes(data)
    sc = getattr(msg, "server_content", None)
    if sc is not None:
        it = getattr(sc, "input_transcription", None)
        if it is not None:
            t = getattr(it, "text", None)
            if t:
                out["user_text"] = t
        ot = getattr(sc, "output_transcription", None)
        if ot is not None:
            t = getattr(ot, "text", None)
            if t:
                out["ember_text"] = t
        if getattr(sc, "interrupted", False):
            out["interrupted"] = True
        if getattr(sc, "turn_complete", False):
            out["turn_complete"] = True
    # Some builds expose the model's text directly on the message.
    if out["ember_text"] is None:
        t = getattr(msg, "text", None)
        if isinstance(t, str) and t:
            out["ember_text"] = t
    return out


def _audio_blob(frame: bytes):
    """Wrap a PCM frame as the Live API expects, or a plain dict when genai is absent."""
    try:
        from google.genai import types
        return types.Blob(data=frame, mime_type=AUDIO_IN_MIME)
    except Exception:
        return {"data": frame, "mime_type": AUDIO_IN_MIME}


# ---------------------------------------------------------------------------
# Async loops (run against real OR injected session/mic/player)
# ---------------------------------------------------------------------------

async def _sender(session, mic, stop_event: "asyncio.Event") -> None:
    """Stream mic frames up until stop, the mic dries up, or the socket errors."""
    while not stop_event.is_set():
        try:
            frame = await mic.read()
        except Exception:
            break
        if not frame:
            break
        try:
            await session.send_realtime_input(audio=_audio_blob(frame))
        except Exception:
            break


async def _receiver(session, player, handlers: dict, stop_event: "asyncio.Event") -> None:
    """Consume server messages: play audio, surface transcripts, honour barge-in."""
    async for msg in session.receive():
        if stop_event.is_set():
            break
        p = parse_message(msg)
        if p["interrupted"]:
            try:
                player.clear()           # drop buffered Ember audio so barge-in feels instant
            except Exception:
                pass
            handlers.get("on_interrupted", _noop)()
            handlers.get("on_state", _noop)("listening")
        if p["audio"]:
            try:
                await player.feed(p["audio"])
            except Exception:
                pass
            handlers.get("on_state", _noop)("speaking")
        if p["user_text"]:
            handlers.get("on_user_text", _noop)(p["user_text"])
        if p["ember_text"]:
            handlers.get("on_ember_text", _noop)(p["ember_text"])
        if p["turn_complete"]:
            handlers.get("on_turn_complete", _noop)()


async def _drive(session, mic, player, handlers: dict, stop_event: "asyncio.Event") -> None:
    """Run the sender + receiver concurrently against an already-open session."""
    send_task = asyncio.ensure_future(_sender(session, mic, stop_event))
    try:
        await _receiver(session, player, handlers, stop_event)
    finally:
        stop_event.set()
        send_task.cancel()
        try:
            await send_task
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Real audio devices (lazy pyaudio) — only used on-device
# ---------------------------------------------------------------------------

class _PyAudioMic:
    def __init__(self):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1,
                                     rate=AUDIO_IN_RATE, input=True, frames_per_buffer=CHUNK)

    async def read(self):
        return await asyncio.to_thread(self._stream.read, CHUNK, False)

    def close(self):
        for fn in (lambda: self._stream.stop_stream(), self._stream.close, self._pa.terminate):
            try:
                fn()
            except Exception:
                pass


class _PyAudioPlayer:
    def __init__(self):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._out = self._pa.open(format=pyaudio.paInt16, channels=1,
                                  rate=AUDIO_OUT_RATE, output=True)

    async def feed(self, pcm: bytes):
        await asyncio.to_thread(self._out.write, pcm)

    def clear(self):
        # Best-effort flush of buffered output for snappy barge-in.
        try:
            self._out.stop_stream()
            self._out.start_stream()
        except Exception:
            pass

    def close(self):
        for fn in (self._out.stop_stream, self._out.close, self._pa.terminate):
            try:
                fn()
            except Exception:
                pass


def available() -> bool:
    """True only if the real Live-voice path can run (genai + pyaudio present)."""
    try:
        import google.genai  # noqa: F401
        import pyaudio        # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public controller
# ---------------------------------------------------------------------------

class LiveVoice:
    """Start/stop a full-duplex Live API voice session on a background asyncio thread.

    Handlers (all optional, called from the asyncio thread — marshal to your UI):
      on_user_text(str), on_ember_text(str), on_state(str), on_turn_complete(),
      on_interrupted(), on_error(str).
    """

    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, voice: str = DEFAULT_VOICE,
                 api_version: str = DEFAULT_API_VERSION, system_instruction: str = "",
                 on_user_text: Optional[Callable] = None, on_ember_text: Optional[Callable] = None,
                 on_state: Optional[Callable] = None, on_turn_complete: Optional[Callable] = None,
                 on_interrupted: Optional[Callable] = None, on_error: Optional[Callable] = None,
                 max_failures: int = 4):
        self.key = "".join((api_key or "").split())
        self.model = model or DEFAULT_MODEL
        self.voice = voice or DEFAULT_VOICE
        self.api_version = api_version or DEFAULT_API_VERSION
        self.system_instruction = system_instruction or ""
        self.max_failures = max_failures
        self._handlers = {
            "on_user_text": on_user_text or _noop, "on_ember_text": on_ember_text or _noop,
            "on_state": on_state or _noop, "on_turn_complete": on_turn_complete or _noop,
            "on_interrupted": on_interrupted or _noop, "on_error": on_error or _noop,
        }
        self._thread: Optional[threading.Thread] = None
        self._loop_stop: Optional[asyncio.Event] = None
        self._aioloop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_requested = threading.Event()
        self._running = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> dict:
        if self._running and self._thread and self._thread.is_alive():
            return {"ok": True, "running": True, "message": "live voice already running"}
        if not self.key:
            return {"ok": False, "error": "Add a Gemini API key in Settings to use natural voice."}
        if not available():
            return {"ok": False, "error": "Natural voice needs google-genai + pyaudio installed."}
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._thread_main, name="ember-live-voice", daemon=True)
        self._running = True
        self._thread.start()
        return {"ok": True, "running": True, "message": "natural voice listening"}

    def stop(self) -> dict:
        self._stop_requested.set()
        # Wake the async loops from this (other) thread via the running event loop.
        loop, ev = self._aioloop, self._loop_stop
        if loop is not None and ev is not None:
            try:
                loop.call_soon_threadsafe(ev.set)
            except Exception:
                pass
        th = self._thread
        if th is not None:
            th.join(timeout=5.0)
        self._running = False
        return {"ok": True, "message": "natural voice stopped"}

    def is_running(self) -> bool:
        return bool(self._running and self._thread and self._thread.is_alive())

    # -- internals ---------------------------------------------------------
    def _thread_main(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self._handlers["on_error"](f"natural voice ended: {e}")
        finally:
            self._running = False
            self._handlers["on_state"]("idle")

    def _config(self) -> dict:
        # A dict config is tolerated across genai versions (no version-specific type names).
        cfg = {
            "response_modalities": ["AUDIO"],
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": self.voice}}},
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }
        if self.system_instruction:
            cfg["system_instruction"] = self.system_instruction
        return cfg

    async def _main(self):
        from google import genai
        try:
            from google.genai import types
            http_options = types.HttpOptions(api_version=self.api_version)
        except Exception:
            http_options = {"api_version": self.api_version}
        client = genai.Client(api_key=self.key, http_options=http_options)
        config = self._config()
        self._aioloop = asyncio.get_running_loop()
        backoff = 1.0
        failures = 0
        while not self._stop_requested.is_set() and failures < self.max_failures:
            self._loop_stop = asyncio.Event()
            mic = player = None
            try:
                mic, player = _PyAudioMic(), _PyAudioPlayer()
            except Exception as e:
                self._handlers["on_error"](f"microphone/speaker unavailable: {e}")
                return
            try:
                async with client.aio.live.connect(model=self.model, config=config) as session:
                    failures = 0
                    backoff = 1.0
                    self._handlers["on_state"]("listening")
                    await _drive(session, mic, player, self._handlers, self._loop_stop)
            except Exception as e:
                failures += 1
                self._handlers["on_error"](f"connection issue ({failures}/{self.max_failures}): {e}")
                if not self._stop_requested.is_set():
                    await asyncio.sleep(min(backoff, 8.0))
                    backoff *= 2
            finally:
                for d in (mic, player):
                    try:
                        d and d.close()
                    except Exception:
                        pass
            if self._stop_requested.is_set():
                break
