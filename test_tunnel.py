"""Hermetic tests for tunnel.py — the public-tunnel URL parser and the TunnelManager lifecycle.
The process spawn is injected (a fake proc), so nothing is launched. No network.
Run: python test_tunnel.py"""
import tunnel


def test_parse_cloudflare_url():
    line = "2026-06-30 INF |  https://blue-cat-1234.trycloudflare.com  | your quick tunnel"
    assert tunnel.parse_tunnel_url(line) == "https://blue-cat-1234.trycloudflare.com"


def test_parse_ngrok_url():
    assert tunnel.parse_tunnel_url("Forwarding https://ab12cd.ngrok-free.app -> http://localhost:8765") \
        == "https://ab12cd.ngrok-free.app"


def test_parse_none():
    assert tunnel.parse_tunnel_url("just some logs") == ""
    assert tunnel.parse_tunnel_url("") == ""


class _FakeProc:
    def __init__(self, lines):
        self.stdout = iter(lines)
        self._alive = True
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self._alive = False

    def poll(self):
        return None if self._alive else 0


def test_manager_captures_url_from_output():
    proc = _FakeProc(["starting...\n", "INF https://happy-sky-42.trycloudflare.com\n", "ready\n"])
    tm = tunnel.TunnelManager(spawn=lambda port: proc)
    res = tm.start(8765, wait=3)
    assert res["ok"] and res["url"] == "https://happy-sky-42.trycloudflare.com"
    assert tm.status()["running"] is True
    assert tm.status()["url"] == res["url"]


def test_manager_stop_terminates():
    proc = _FakeProc(["INF https://x-y-z.trycloudflare.com\n"])
    tm = tunnel.TunnelManager(spawn=lambda port: proc)
    tm.start(8765, wait=3)
    r = tm.stop()
    assert r["stopped"] is True and proc.terminated is True
    assert tm.status()["running"] is False


def test_manager_start_failure_when_spawn_raises():
    def boom(port):
        raise RuntimeError("no binary")
    tm = tunnel.TunnelManager(spawn=boom)
    res = tm.start(8765, wait=1)
    assert res["ok"] is False and "no binary" in res["error"]


def test_default_spawn_reports_missing_cloudflared():
    # With the default spawn and cloudflared not installed (CI), start() must fail gracefully.
    if tunnel.cloudflared_available():
        return  # skip where cloudflared happens to be installed
    tm = tunnel.TunnelManager()
    res = tm.start(8765, wait=1)
    assert res["ok"] is False and "cloudflared" in res["error"].lower()
    assert "install" in res


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tunnel tests passed")
