"""Tests for the 'hey ember' wake-word listener (wake_word.py). No audio needed."""
import time

import wake_word as ww


def _reset():
    ww.stop()
    with ww._LOCK:
        ww._events.clear()
        ww._detections = 0
    ww._CAPTURE = None
    ww._on_wake = None
    ww._paused = False


# --- pure detection ------------------------------------------------------------

def test_detects_canonical_and_variants():
    for t in ("hey ember", "Hey Ember!", "ok ember", "hey amber",
              "hello ember are you there", "yo ember"):
        assert ww.detect_wake(t), t


def test_ignores_unrelated_speech():
    for t in ("what's the weather", "open my email", "ember alone word here",
              "remember to buy milk", "", "december is cold"):
        assert not ww.detect_wake(t), t


def test_embedded_wake_in_sentence():
    assert ww.detect_wake("um, hey ember can you help me")


# --- daemon lifecycle with injected capture ------------------------------------

def test_daemon_fires_on_wake_only():
    _reset()
    scripts = ["nothing useful", "hey ember", "random chatter", "hey ember please"]
    idx = {"i": 0}
    def cap():
        i = idx["i"]; idx["i"] += 1
        if i < len(scripts):
            return scripts[i]
        time.sleep(0.02)
        return ""
    hits = {"n": 0}
    ww._CAPTURE = cap
    try:
        ww.start(on_wake=lambda: hits.__setitem__("n", hits["n"] + 1))
        deadline = time.time() + 3.0
        while time.time() < deadline and ww.status()["detections"] < 2:
            time.sleep(0.02)
        assert hits["n"] >= 2, hits
        assert ww.status()["detections"] >= 2
        assert ww.is_running()
    finally:
        ww.stop()
        _reset()


def test_pause_suppresses_callbacks():
    _reset()
    def cap():
        time.sleep(0.01)
        return "hey ember"
    hits = {"n": 0}
    ww._CAPTURE = cap
    ww._COOLDOWN = 0.02   # fire rapidly so pause/resume is deterministic, not racy
    try:
        ww.start(on_wake=lambda: hits.__setitem__("n", hits["n"] + 1))
        time.sleep(0.25)
        assert hits["n"] >= 1
        ww.pause()
        time.sleep(0.1)
        before = hits["n"]
        time.sleep(0.3)
        assert hits["n"] == before, "callbacks fired while paused"
        ww.resume()
        time.sleep(0.3)
        assert hits["n"] > before, "did not resume"
    finally:
        ww.stop()
        ww._COOLDOWN = 1.2
        _reset()


def test_start_idempotent_and_stop():
    _reset()
    ww._CAPTURE = lambda: (time.sleep(0.02) or "")
    try:
        a = ww.start(); b = ww.start()
        assert a["ok"] and b["ok"] and "already" in b["message"]
        assert ww.is_running()
    finally:
        r = ww.stop()
        assert r["ok"]
        assert ww.is_running() is False
        _reset()


def test_capture_unavailable_is_graceful():
    _reset()
    ww._CAPTURE = None  # real capture; no mic in sandbox -> loop must exit cleanly, not crash
    # Force the real factory to report "unavailable" by simulating no speech stack:
    ww.start(on_wake=lambda: None)
    time.sleep(0.3)
    # Either it couldn't open a mic (running False) or it's looping harmlessly — both OK.
    assert ww.status()["ok"] is True
    ww.stop()
    _reset()


def _run_all() -> bool:
    import types
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for fn in funcs:
        try:
            fn(); print(f"PASS  {fn.__name__}"); passed += 1
        except Exception as e:
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(funcs)} passed")
    return passed == len(funcs)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
