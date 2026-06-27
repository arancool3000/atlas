"""Workflow recorder — record real low-level mouse/keyboard input and replay it.

The heavier sibling of `macros.py`: where a macro stores a natural-language task
description, a *workflow* records the actual stream of input events (mouse moves,
clicks, scrolls, key presses) and can replay them later honoring their timing.

Recording/replaying needs `pynput` (absent on the build machine, present on the
user's Mac). It is imported LAZILY inside the record/replay functions so this
module always imports with only the standard library; if pynput is missing the
relevant tools return a friendly {"ok": False, ...} instead of raising.

Every tool returns {"ok": True, ...} or {"ok": False, "error": "..."} — never raises.
Workflows are JSON files under WORKFLOW_DIR (a module-level Path tests monkeypatch).
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def _data_dir() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).parent
    home = Path.home()
    if sys.platform == "darwin":
        d = home / "Library" / "Application Support" / "Ember"
    elif sys.platform.startswith("win"):
        d = home / "AppData" / "Roaming" / "Ember"
    else:
        d = home / ".ember"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


# Module-level workflows directory. Tests monkeypatch this to a tmp_path.
WORKFLOW_DIR = _data_dir() / "workflows"

# Throttle mouse-move events to ~10/s so a long recording stays small.
_MOVE_MIN_INTERVAL = 0.1
_PYNPUT_HINT = "pynput not installed — pip install pynput"

# ---- module-level recording state (guarded by _lock) --------------------------
_lock = threading.Lock()
_recording = False
_events: list = []
_start_time = 0.0
_listeners: list = []
_workflow_name = ""
_last_move_t = 0.0
_backend_active = False

# Pluggable capture backend. On macOS the UI registers a main-thread NSEvent recorder here
# (see ui._MacInputRecorder) because pynput's background event tap HARD-CRASHES the process
# on macOS. A backend is any object with `start(handlers) -> bool` and `stop()`, where
# `handlers` is {"move","click","scroll","key"} of callables matching the pynput signatures.
_capture_backend = None


def set_capture_backend(backend) -> None:
    """Register (or clear with None) the platform capture backend used instead of pynput."""
    global _capture_backend
    _capture_backend = backend


# ---- helpers -----------------------------------------------------------------
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "workflow"


def _ensure_dir() -> None:
    try:
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _path_for(name: str) -> Path:
    return WORKFLOW_DIR / (_slug(name) + ".json")


# ---- PURE event builders (testable without pynput) ---------------------------
def _serialize_key(key) -> str:
    """Turn a pynput key (or anything) into a stable string token.

    Regular character keys -> their character (e.g. "a"); special keys -> their
    name (e.g. "space", "enter"). Pure: accepts plain strings too so it can be
    unit-tested with no pynput present.
    """
    if key is None:
        return ""
    if isinstance(key, str):
        return key
    # pynput KeyCode has .char; special Key has .name.
    char = getattr(key, "char", None)
    if char:
        return char
    name = getattr(key, "name", None)
    if name:
        return name
    # Fall back to a cleaned repr (e.g. "Key.space" -> "space").
    text = str(key)
    if text.startswith("Key."):
        return text[4:]
    return text


def _record_move(x, y, t: float) -> dict:
    return {"t": round(float(t), 4), "type": "move", "x": int(x), "y": int(y)}


def _record_click(x, y, button, pressed: bool, t: float) -> dict:
    return {"t": round(float(t), 4), "type": "click", "x": int(x), "y": int(y),
            "button": _button_name(button), "pressed": bool(pressed)}


def _record_scroll(x, y, dx, dy, t: float) -> dict:
    return {"t": round(float(t), 4), "type": "scroll", "x": int(x), "y": int(y),
            "dx": int(dx), "dy": int(dy)}


def _record_key(key, t: float) -> dict:
    return {"t": round(float(t), 4), "type": "key", "key": _serialize_key(key)}


def _button_name(button) -> str:
    if button is None:
        return "left"
    if isinstance(button, str):
        return button
    name = getattr(button, "name", None)
    if name:
        return name
    text = str(button)
    if text.startswith("Button."):
        return text[7:]
    return text


# ---- persistence (testable without pynput) -----------------------------------
def _save_workflow(name: str, events: list, duration: float) -> dict:
    """Write a workflow JSON file. Returns {ok, name, path, event_count, duration}."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "a workflow name is required"}
    _ensure_dir()
    payload = {
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(),
        "duration": round(float(duration), 4),
        "events": list(events or []),
    }
    path = _path_for(name)
    try:
        path.write_text(json.dumps(payload, indent=2), "utf-8")
    except OSError as e:
        return {"ok": False, "error": f"could not save workflow: {e}"}
    return {"ok": True, "name": name, "path": str(path),
            "event_count": len(payload["events"]), "duration": payload["duration"]}


def _load_workflow(name: str) -> dict | None:
    path = _path_for(name)
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


# ---- tools -------------------------------------------------------------------
def record_workflow_start(name: str) -> dict:
    """Begin recording real mouse + keyboard input under a name. Non-blocking:
    returns immediately while events are captured in the background until
    record_workflow_stop() is called.

    macOS uses the registered NSEvent capture backend (set by the UI) on the main run loop —
    NEVER pynput, whose background event tap hard-crashes the app. Other platforms use pynput."""
    global _recording, _events, _start_time, _listeners, _workflow_name, _last_move_t, _backend_active
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "a workflow name is required"}

    def _reset_state():
        global _recording, _events, _listeners, _workflow_name, _backend_active
        _recording = False
        _events = []
        _listeners = []
        _workflow_name = ""
        _backend_active = False

    with _lock:
        if _recording:
            return {"ok": False, "error": f"already recording '{_workflow_name}' — stop it first"}

        _recording = True
        _events = []
        _workflow_name = name
        _start_time = time.time()
        _last_move_t = 0.0
        _listeners = []
        _backend_active = False

        def _now() -> float:
            return time.time() - _start_time

        def _on_move(x, y):
            global _last_move_t
            with _lock:
                if not _recording:
                    return
                t = _now()
                if t - _last_move_t < _MOVE_MIN_INTERVAL:
                    return
                _last_move_t = t
                _events.append(_record_move(x, y, t))

        def _on_click(x, y, button, pressed):
            with _lock:
                if not _recording or not pressed:  # capture button-down only
                    return
                _events.append(_record_click(x, y, button, pressed, _now()))

        def _on_scroll(x, y, dx, dy):
            with _lock:
                if not _recording:
                    return
                _events.append(_record_scroll(x, y, dx, dy, _now()))

        def _on_press(key):
            with _lock:
                if not _recording:
                    return
                _events.append(_record_key(key, _now()))

        handlers = {"move": _on_move, "click": _on_click,
                    "scroll": _on_scroll, "key": _on_press}
        backend = _capture_backend

    # Start the actual capture OUTSIDE _lock: backends (and their handlers) may run on another
    # thread or the GUI run loop and acquire _lock themselves — holding it here could deadlock.
    # The `_recording` flag set above already guards against a concurrent second start.

    # 1) Prefer a registered main-thread capture backend (macOS NSEvent recorder). Required
    #    on macOS — pynput would crash. The backend installs monitors on the GUI run loop.
    if backend is not None:
        try:
            ok = bool(backend.start(handlers))
        except Exception as e:
            with _lock:
                _reset_state()
            return {"ok": False, "error": f"could not start the input recorder: {e}"}
        if not ok:
            with _lock:
                _reset_state()
            return {"ok": False, "error": "could not start the input recorder — grant Ember "
                                          "Accessibility & Input Monitoring in System Settings "
                                          "▸ Privacy & Security, then try recording again."}
        with _lock:
            _backend_active = True
        return {"ok": True, "name": name, "recording": True,
                "message": "Recording — call record_workflow_stop() when done."}

    # 2) macOS without a backend (e.g. headless/agent with no UI): refuse rather than crash.
    if sys.platform == "darwin":
        with _lock:
            _reset_state()
        return {"ok": False, "error": "workflow recording needs Ember's window open on macOS "
                                      "(open Ember, then record). The low-level recorder runs "
                                      "on the app's main thread to stay crash-safe."}

    # 3) Other platforms: pynput listeners (safe off the main thread on Windows/Linux).
    try:
        from pynput import keyboard as _kb
        from pynput import mouse as _ms
    except Exception:
        with _lock:
            _reset_state()
        return {"ok": False, "error": _PYNPUT_HINT}
    try:
        ml = _ms.Listener(on_move=_on_move, on_click=_on_click, on_scroll=_on_scroll)
        kl = _kb.Listener(on_press=_on_press)
        ml.start()
        kl.start()
        with _lock:
            _listeners = [ml, kl]
    except Exception as e:
        with _lock:
            _reset_state()
        return {"ok": False, "error": f"could not start input listeners: {e}"}

    return {"ok": True, "name": name, "recording": True,
            "message": "Recording — call record_workflow_stop() when done."}


def record_workflow_stop() -> dict:
    """Stop the active recording, save it to disk, and return a summary."""
    global _recording, _events, _listeners, _workflow_name, _start_time, _backend_active
    with _lock:
        if not _recording:
            return {"ok": False, "error": "not currently recording"}
        name = _workflow_name
        duration = time.time() - _start_time
        events = list(_events)
        listeners = list(_listeners)
        backend_active = _backend_active
        _recording = False
        _events = []
        _listeners = []
        _workflow_name = ""
        _backend_active = False

    if backend_active and _capture_backend is not None:
        try:
            _capture_backend.stop()
        except Exception:
            pass
    for ln in listeners:
        try:
            ln.stop()
        except Exception:
            pass

    res = _save_workflow(name, events, duration)
    if not res.get("ok"):
        return res
    return {"ok": True, "name": res["name"], "event_count": res["event_count"],
            "path": res["path"], "duration": res["duration"]}


def replay_workflow(name: str, speed: float = 1.0) -> dict:
    """Replay a previously recorded workflow by name, honoring relative timing
    divided by `speed` (clamped to 0.25-8). Requires pynput."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "a workflow name is required"}

    wf = _load_workflow(name)
    if wf is None:
        return {"ok": False, "error": f"no workflow '{name}'"}

    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.25, min(8.0, speed))

    try:
        from pynput import keyboard as _kb
        from pynput import mouse as _ms
    except Exception:
        return {"ok": False, "error": _PYNPUT_HINT}

    events = wf.get("events") or []
    mouse = _ms.Controller()
    kb = _kb.Controller()

    def _resolve_button(bname: str):
        try:
            return getattr(_ms.Button, bname or "left")
        except Exception:
            return _ms.Button.left

    def _resolve_key(token: str):
        if token and len(token) == 1:
            return token
        try:
            return getattr(_kb.Key, token)
        except Exception:
            return token

    replayed = 0
    prev_t = 0.0
    try:
        for ev in events:
            t = float(ev.get("t", 0.0))
            delay = (t - prev_t) / speed
            if delay > 0:
                time.sleep(delay)
            prev_t = t
            etype = ev.get("type")
            if etype == "move":
                mouse.position = (int(ev.get("x", 0)), int(ev.get("y", 0)))
            elif etype == "click":
                mouse.position = (int(ev.get("x", 0)), int(ev.get("y", 0)))
                btn = _resolve_button(ev.get("button"))
                mouse.click(btn, 1)
            elif etype == "scroll":
                mouse.position = (int(ev.get("x", 0)), int(ev.get("y", 0)))
                mouse.scroll(int(ev.get("dx", 0)), int(ev.get("dy", 0)))
            elif etype == "key":
                key = _resolve_key(ev.get("key", ""))
                try:
                    kb.press(key)
                    kb.release(key)
                except Exception:
                    pass
            else:
                continue
            replayed += 1
    except Exception as e:
        return {"ok": False, "error": f"replay failed after {replayed} events: {e}"}

    return {"ok": True, "name": name, "replayed_events": replayed, "speed": speed}


def list_workflows() -> dict:
    """List saved workflows with their metadata."""
    out = []
    try:
        files = sorted(WORKFLOW_DIR.glob("*.json"))
    except Exception:
        files = []
    for f in files:
        try:
            wf = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        out.append({
            "name": wf.get("name", f.stem),
            "created": wf.get("created", ""),
            "duration": wf.get("duration", 0),
            "event_count": len(wf.get("events") or []),
        })
    return {"ok": True, "count": len(out), "workflows": out}


def delete_workflow(name: str) -> dict:
    """Delete a saved workflow by name."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "a workflow name is required"}
    path = _path_for(name)
    if not path.exists():
        return {"ok": False, "error": f"no workflow '{name}'"}
    try:
        path.unlink()
    except OSError as e:
        return {"ok": False, "error": f"could not delete workflow: {e}"}
    return {"ok": True, "name": name, "deleted": True}


# ---- exports for wiring -------------------------------------------------------
TOOL_DECLARATIONS = [
    {"name": "record_workflow_start",
     "description": "Start recording real mouse/keyboard input as a named workflow (runs in the background until stopped). Requires pynput.",
     "parameters": {"type": "OBJECT",
                    "properties": {"name": {"type": "STRING", "description": "name to save the recorded workflow under"}},
                    "required": ["name"]}},
    {"name": "record_workflow_stop",
     "description": "Stop the active workflow recording and save the captured input events to disk.",
     "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "replay_workflow",
     "description": "Replay a previously recorded input workflow (mouse/keyboard) by name.",
     "parameters": {"type": "OBJECT",
                    "properties": {"name": {"type": "STRING"},
                                   "speed": {"type": "NUMBER", "description": "playback speed multiplier 0.25-8 (default 1)"}},
                    "required": ["name"]}},
    {"name": "list_workflows",
     "description": "List all saved input workflows with their event count, duration, and creation time.",
     "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "delete_workflow",
     "description": "Delete a saved input workflow by name.",
     "parameters": {"type": "OBJECT",
                    "properties": {"name": {"type": "STRING"}},
                    "required": ["name"]}},
]

TOOL_DISPATCH = {
    "record_workflow_start": record_workflow_start,
    "record_workflow_stop": record_workflow_stop,
    "replay_workflow": replay_workflow,
    "list_workflows": list_workflows,
    "delete_workflow": delete_workflow,
}

READONLY_TOOLS = {"list_workflows"}
INTERACTION_TOOLS = {"record_workflow_start", "record_workflow_stop", "delete_workflow"}
# Note: replay_workflow is intentionally in NEITHER set — caller classifies it as higher-risk.
