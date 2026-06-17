"""Local Ollama agent — an offline chat brain (no API key, no rate limits).

Exposes the SAME interface as agent.Agent / claude_agent.ClaudeAgent (subscribe /
send_user_message / stop / reset, emitting agent.AgentEvent) so the app can swap to a
local model from the model picker.

Scope (deliberate): this is a CHAT brain. It answers, writes, explains, and reasons fully
offline via your local Ollama models. It does NOT drive the computer — local models are too
small/varied to use Ember's ~288 tools reliably, and sending them all would blow a local
model's context. For computer control (screen/apps/browser/files) pick Gemini or Claude.
The module imports with only stdlib + requests (agent.py, which needs google-genai, is
imported lazily) so it stays testable without the cloud SDKs installed.
"""
from __future__ import annotations

import json
import threading
import traceback
from typing import Callable

import requests

OLLAMA_BASE = "http://localhost:11434"

try:
    from agent import AgentEvent  # the real event type used by the UI in production
except Exception:  # google-genai not installed (dev/test) — keep the module importable
    from dataclasses import dataclass

    @dataclass
    class AgentEvent:  # structurally identical to agent.AgentEvent
        kind: str
        payload: object = None


CHAT_SYSTEM_PROMPT = (
    "You are Ember, running locally on the user's computer via Ollama — fully offline, with "
    "no API key and no rate limits. In this local mode you are a helpful, concise assistant: "
    "answer questions, write and edit text, brainstorm, explain, and reason step by step. "
    "You cannot see the screen or control the computer in local mode; if the user needs Ember "
    "to operate apps, the browser, or files, tell them to switch the model to Gemini or Claude "
    "in Settings, which enables full computer control."
)


def _memory_extras() -> str:
    try:
        from agent import system_extras
        return system_extras() or ""
    except Exception:
        return ""


def _parse_stream_line(line) -> dict:
    """Parse one NDJSON line from Ollama's streaming /api/chat. Returns {} on a bad line."""
    try:
        if isinstance(line, (bytes, bytearray)):
            line = line.decode("utf-8", "replace")
        return json.loads(line)
    except Exception:
        return {}


def resolve_model(preferred: str = "", base_url: str = OLLAMA_BASE) -> dict:
    """Decide which Ollama model to use: the preferred one if given, else the first installed.
    Returns {ok: True, model} or {ok: False, error} with a helpful message."""
    preferred = (preferred or "").strip()
    try:
        import local_ai
        st = local_ai.local_ai_status()
    except Exception as e:
        return {"ok": False, "error": f"cannot reach Ollama: {e}"}
    if not st.get("running"):
        return {"ok": False, "error": st.get("note")
                or "Ollama is not running. Install it from https://ollama.com, then: ollama pull llama3.2"}
    models = st.get("models") or []
    if preferred:
        return {"ok": True, "model": preferred}   # trust the user; the API errors clearly if wrong
    if models:
        return {"ok": True, "model": models[0]}
    return {"ok": False, "error": "Ollama is running but no models are pulled. Run: ollama pull llama3.2"}


class OllamaAgent:
    """Drop-in local chat backend. Same interface the UI uses for Agent / ClaudeAgent."""

    def __init__(self, model_name: str = "", auto_screenshot: bool = True,
                 base_url: str = OLLAMA_BASE, **_kwargs):
        self.requested_model = (model_name or "").strip()
        self.active_model = self.requested_model or "ollama"
        self.base_url = (base_url or OLLAMA_BASE).rstrip("/")
        self.auto_screenshot = auto_screenshot  # accepted for parity; unused (local = no vision)
        self._messages: list[dict] = []
        self._event_subs: list[Callable[[AgentEvent], None]] = []
        self._stop_flag = threading.Event()

    # --- interface parity with Agent/ClaudeAgent ---
    def reset(self):
        self._messages = []

    def stop(self):
        self._stop_flag.set()

    def subscribe(self, fn: Callable[[AgentEvent], None]):
        self._event_subs.append(fn)

    def _emit(self, ev: AgentEvent):
        for fn in self._event_subs:
            try:
                fn(ev)
            except Exception:
                traceback.print_exc()

    def send_user_message(self, text: str):
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _system_prompt(self) -> str:
        return CHAT_SYSTEM_PROMPT + _memory_extras()

    def _run_turn(self, user_text: str):
        self._stop_flag.clear()
        try:
            res = resolve_model(self.requested_model, self.base_url)
            if not res.get("ok"):
                self._emit(AgentEvent("error", res.get("error", "Ollama unavailable")))
                return
            self.active_model = res["model"]
            self._messages.append({"role": "user", "content": user_text})
            payload = {
                "model": self.active_model,
                "messages": [{"role": "system", "content": self._system_prompt()}] + self._messages,
                "stream": True,
            }
            streamed = []
            try:
                with requests.post(f"{self.base_url}/api/chat", json=payload,
                                   stream=True, timeout=300) as r:
                    if r.status_code != 200:
                        self._emit(AgentEvent("error",
                                   f"Ollama returned {r.status_code}: {(r.text or '')[:300]}"))
                        return
                    for line in r.iter_lines():
                        if self._stop_flag.is_set():
                            break
                        if not line:
                            continue
                        chunk = _parse_stream_line(line)
                        if not chunk:
                            continue
                        delta = (chunk.get("message") or {}).get("content") or ""
                        if delta:
                            streamed.append(delta)
                            self._emit(AgentEvent("stream_chunk", delta))
                        if chunk.get("done"):
                            break
            except requests.exceptions.RequestException as e:
                self._emit(AgentEvent("error", f"Local AI unavailable: {e} (is Ollama running?)"))
                return
            if streamed:
                self._emit(AgentEvent("stream_end", None))
                self._messages.append({"role": "assistant", "content": "".join(streamed).strip()})
            else:
                self._emit(AgentEvent("message", "[no response from the local model]"))
        except Exception as e:
            self._emit(AgentEvent("error", f"{type(e).__name__}: {e}"))
        finally:
            self._emit(AgentEvent("done"))
