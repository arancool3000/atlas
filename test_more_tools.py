"""Hermetic tests for more_tools.py's email safety guard.

send_email() imports `ui` internally to read SMTP settings, but only inside a try/except that
falls back to "not configured" on failure - so these tests run fine without PyQt6 (ui.py itself
isn't importable in this environment) as long as no real SMTP host/user/password is passed.
more_tools.py imports `requests` at module load (used by other tools like translate_text), so
that's stubbed too.
Run: python test_more_tools.py"""
import sys
import types

if "requests" not in sys.modules:
    req = types.ModuleType("requests")
    req.exceptions = types.SimpleNamespace(RequestException=Exception)
    sys.modules["requests"] = req

import more_tools as mt  # noqa: E402  (heavy dep stubbed above first)


def test_reserved_domains_are_flagged():
    for addr in ("bob@example.com", "alice@example.org", "x@example.net", "y@EXAMPLE.COM",
                 "z@sub.example.com", "a@foo.test", "b@bar.invalid", "c@baz.localhost"):
        assert mt._is_reserved_placeholder_email(addr), addr


def test_real_looking_domains_are_not_flagged():
    for addr in ("bob@gmail.com", "alice@company.co", "x@outlook.com", "y@my-example-co.com",
                 "z@notexample.com", ""):
        assert not mt._is_reserved_placeholder_email(addr), addr


def test_send_email_refuses_reserved_placeholder_address():
    r = mt.send_email("bob@example.com", "Hi", "body")
    assert r["ok"] is False
    assert "example.com" in r["error"] and "placeholder" in r["error"].lower()


def test_send_email_does_not_block_a_real_looking_address():
    # No SMTP configured in this environment -> fails at the config-check step, NOT the
    # placeholder guard - proves the guard doesn't false-positive on a normal address.
    r = mt.send_email("bob@gmail.com", "Hi", "body")
    assert r["ok"] is False
    assert "placeholder" not in r["error"].lower()
    assert "smtp" in r["error"].lower()


def _run():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    ok = 0
    for fn in fns:
        try:
            fn(); print("PASS", fn.__name__); ok += 1
        except Exception as e:
            print("FAIL", fn.__name__, e)
    print(f"{ok}/{len(fns)} passed")
    return ok == len(fns)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run() else 1)
