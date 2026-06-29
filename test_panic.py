"""Hermetic tests for panic.py — the emergency-lockdown orchestration, arming, debounce, and
restore. All OS actions are replaced with recording hooks, so nothing real happens.
Run: python test_panic.py"""
import panic


def _recorder():
    calls = []
    def mk(name, ok=True):
        def fn():
            calls.append(name)
            return {"ok": ok, "detail": f"{name} done"}
        return fn
    return calls, mk


def _install(ok=True):
    calls, mk = _recorder()
    panic.set_hooks(lock_screen=mk("lock", ok), cut_network=mk("cut", ok),
                    restore_network=mk("restore", ok), kill_ai=mk("kill", ok))
    return calls


def _reset():
    panic.set_hooks(lock_screen=None, cut_network=None, restore_network=None, kill_ai=None)
    panic.arm_auto(False)
    panic._last_auto_at = 0.0


def test_manual_lockdown_runs_all_steps_in_order():
    calls = _install()
    r = panic.panic_lockdown(reason="test", source="manual", _ts=1000.0)
    assert r["ok"] and r["source"] == "manual"
    assert calls == ["kill", "cut", "lock"]          # AI first, then network, then screen
    assert set(r["succeeded"]) == {"stop_ai", "cut_network", "lock_screen"}
    assert r["failed"] == []
    _reset()


def test_selective_steps():
    calls = _install()
    panic.panic_lockdown(lock=False, cut_network=False, kill_ai=True, _ts=1.0)
    assert calls == ["kill"]
    _reset()


def test_failed_step_is_reported_not_raised():
    _install(ok=False)
    r = panic.panic_lockdown(_ts=2.0)
    assert r["ok"] is True                            # the call itself never fails
    assert set(r["failed"]) == {"stop_ai", "cut_network", "lock_screen"}
    assert r["succeeded"] == []
    _reset()


def test_auto_panic_requires_armed_and_critical():
    calls = _install()
    # not armed -> nothing
    assert panic.maybe_auto_panic("malicious", "evil", _ts=10.0) is None
    assert calls == []
    panic.arm_auto(True)
    # armed but only suspicious -> nothing
    assert panic.maybe_auto_panic("suspicious", "meh", _ts=11.0) is None
    assert calls == []
    # armed + malicious -> fires (use a realistic large timestamp so it's outside the debounce
    # window relative to the reset baseline of 0.0)
    ev = panic.maybe_auto_panic("malicious", "reverse shell", category="network", _ts=10000.0)
    assert ev and ev["source"] == "auto" and "reverse shell" in ev["reason"]
    assert calls == ["kill", "cut", "lock"]
    _reset()


def test_auto_panic_debounced():
    calls = _install()
    panic.arm_auto(True)
    assert panic.maybe_auto_panic("malicious", "a", _ts=100.0) is not None
    # within the debounce window -> suppressed
    assert panic.maybe_auto_panic("malicious", "b", _ts=105.0) is None
    # after the window -> fires again
    assert panic.maybe_auto_panic("malicious", "c", _ts=100.0 + panic._AUTO_MIN_INTERVAL + 1) is not None
    _reset()


def test_restore_and_status():
    calls = _install()
    panic.arm_auto(True)
    panic.restore_network()
    assert "restore" in calls
    st = panic.status()
    assert st["ok"] and st["armed"] is True
    _reset()
    assert panic.status()["armed"] is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} panic tests passed")
