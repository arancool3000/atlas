"""Hermetic tests for Ember Link's pairing-token auth (remote_server.py) — the mechanism that
lets a device pair once on the LAN (proving it knows the PIN) and then reconnect from ANYWHERE
using a long token instead of the short PIN. Tokens are redirected to a temp dir so tests never
touch the real app-support folder. No network / no GUI (pyautogui/tools stubbed).
Run: python test_pairing.py"""
import sys
import tempfile
import types
from pathlib import Path

if "pyautogui" not in sys.modules:
    pg = types.ModuleType("pyautogui")
    pg.FAILSAFE = False
    pg.PAUSE = 0
    pg.size = lambda: (1920, 1080)
    sys.modules["pyautogui"] = pg
if "tools" not in sys.modules:
    t = types.ModuleType("tools")
    t.run_powershell = lambda cmd, timeout=60: {"ok": True, "ran": cmd}
    t.press_key = lambda *a, **k: None
    t.type_text = lambda *a, **k: None
    sys.modules["tools"] = t

import remote_server as rs


def setup_function(_=None):
    # Fresh temp "app support" dir per test + reset in-memory token/pin state.
    d = Path(tempfile.mkdtemp(prefix="ember_pair_test_"))
    rs._data_dir = lambda: d
    rs._PAIR_TOKENS.clear()
    rs._TOKENS_LOADED = False
    rs._STATE["pin"] = "424242"
    rs._AUTH_FAILS.clear()


def test_issue_and_validate_token():
    tok = rs.issue_pair_token()
    assert len(tok) >= 20
    assert rs._token_valid(tok) is True
    assert rs._token_valid("not-a-real-token-at-all-0000000") is False


def test_token_persists_across_reload():
    tok = rs.issue_pair_token()
    rs._TOKENS_LOADED = False   # simulate a fresh process re-reading from disk
    rs._PAIR_TOKENS.clear()
    assert rs._token_valid(tok) is True


def test_paired_count_and_revoke():
    rs.issue_pair_token()
    rs.issue_pair_token()
    assert rs.paired_count() == 2
    r = rs.revoke_pairings()
    assert r["revoked"] == 2
    assert rs.paired_count() == 0


def test_token_bounded_to_max():
    toks = [rs.issue_pair_token() for _ in range(rs._MAX_TOKENS + 5)]
    assert rs.paired_count() <= rs._MAX_TOKENS
    # the newest token must still be valid even after old ones are trimmed
    assert rs._token_valid(toks[-1]) is True


def test_short_or_empty_token_is_rejected():
    assert rs._token_valid("") is False
    assert rs._token_valid(None) is False
    assert rs._token_valid("short") is False


class _Fake:
    """Minimal stand-in for _Handler to exercise _auth without a real socket."""
    def __init__(self, ip="10.0.0.5"):
        self.client_address = (ip, 12345)
    _auth = rs._Handler._auth


def test_auth_accepts_correct_pin():
    h = _Fake()
    assert h._auth("424242") is True


def test_auth_accepts_valid_token_without_pin():
    tok = rs.issue_pair_token()
    h = _Fake()
    assert h._auth("", tok) is True
    assert h._auth(None, tok) is True


def test_auth_rejects_wrong_pin_and_bad_token():
    h = _Fake(ip="10.0.0.6")
    assert h._auth("000000") is False
    assert h._auth("", "garbage-token-value-xx") is False


def test_pair_endpoint_flow_via_apply_style_dispatch():
    # Simulates the /api/pair contract: PIN-verified request mints a token usable thereafter.
    h = _Fake(ip="10.0.0.7")
    assert h._auth("424242") is True
    tok = rs.issue_pair_token()
    h2 = _Fake(ip="203.0.113.9")   # a totally different (e.g. cellular) IP/network
    assert h2._auth("", tok) is True


# --- the tunnel/PIN threat model: PIN must be LAN-only, never usable through a tunnel --------
def test_is_lan_ip_classifies_correctly():
    assert rs._is_lan_ip("192.168.1.42") is True
    assert rs._is_lan_ip("10.0.0.7") is True
    assert rs._is_lan_ip("172.16.5.5") is True
    assert rs._is_lan_ip("127.0.0.1") is False       # loopback - what tunnel-relayed traffic looks like
    assert rs._is_lan_ip("::1") is False
    assert rs._is_lan_ip("8.8.8.8") is False         # public internet address
    assert rs._is_lan_ip("not-an-ip") is False
    assert rs._is_lan_ip("") is False


def test_correct_pin_from_loopback_is_rejected():
    # This is the exact vulnerability: cloudflared forwards public tunnel traffic to localhost,
    # so a tunnel-relayed request's source IP is 127.0.0.1. If the PIN worked there, anyone who
    # found the public tunnel URL could brute-force the 6-digit PIN over the internet.
    h = _Fake(ip="127.0.0.1")
    assert h._auth("424242") is False        # correct PIN, but NOT from a LAN address -> rejected


def test_correct_pin_from_public_ip_is_rejected():
    h = _Fake(ip="8.8.8.8")
    assert h._auth("424242") is False


def test_correct_pin_from_real_lan_ip_still_works():
    h = _Fake(ip="192.168.1.50")
    assert h._auth("424242") is True


def test_token_still_works_from_loopback_ie_through_the_tunnel():
    # The token (not the PIN) is exactly what SHOULD work when relayed through the tunnel.
    tok = rs.issue_pair_token()
    h = _Fake(ip="127.0.0.1")
    assert h._auth("", tok) is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        setup_function()
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} pairing tests passed")
