"""Tests for updater.py — the bits that don't touch the network: the SSL context, and the
raise_on_error contract that lets a USER-initiated check tell "up to date" apart from "couldn't
reach the server" (the bug where a failed HTTPS fetch was misreported as 'up to date').
Run: python test_updater.py"""
import urllib.request

import updater
import version


def test_ssl_context_is_usable():
    ctx = updater._ssl_context()
    # Either a real SSLContext (certifi or system) or None — never raises.
    import ssl
    assert ctx is None or isinstance(ctx, ssl.SSLContext)


def test_check_raises_on_error_when_asked(monkeypatch=None):
    # Force "configured" so we reach the fetch, then make the fetch blow up.
    orig_configured = version.is_configured
    orig_urlopen = urllib.request.urlopen
    version.is_configured = lambda: True
    def _boom(*a, **k):
        raise OSError("simulated network/SSL failure")
    urllib.request.urlopen = _boom
    try:
        # Default: swallow the error and report "no update" (None) — never disrupts the app.
        assert updater.check_for_update() is None
        # raise_on_error=True: the caller must be able to see the failure.
        raised = False
        try:
            updater.check_for_update(raise_on_error=True)
        except Exception:
            raised = True
        assert raised, "check_for_update(raise_on_error=True) should propagate fetch errors"
    finally:
        version.is_configured = orig_configured
        urllib.request.urlopen = orig_urlopen


def test_check_returns_manifest_when_newer():
    orig_configured = version.is_configured
    orig_urlopen = urllib.request.urlopen
    orig_current = updater.current_version
    version.is_configured = lambda: True
    updater.current_version = lambda: "1.0.0"

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"version": "9.9.9", "downloads": {}}'
    urllib.request.urlopen = lambda *a, **k: _Resp()
    try:
        m = updater.check_for_update(raise_on_error=True)
        assert m and m.get("version") == "9.9.9", m
        # Not newer -> None.
        updater.current_version = lambda: "9.9.9"
        assert updater.check_for_update() is None
    finally:
        version.is_configured = orig_configured
        urllib.request.urlopen = orig_urlopen
        updater.current_version = orig_current


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} updater tests passed")
