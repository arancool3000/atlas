"""macOS permission helpers for Ember.

This module intentionally contains only permission prompts/settings shortcuts. It does not
register macOS Services or any system-wide selected-text menu items.
"""
from __future__ import annotations

import sys


def request_accessibility(prompt: bool = True) -> bool:
    """Ask macOS for Accessibility access, which Ember needs for mouse/keyboard control.

    macOS does not auto-prompt for Accessibility the way it does for Screen Recording, so Ember
    explicitly calls AXIsProcessTrustedWithOptions. Returns True if already trusted. No-ops off
    macOS.
    """
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        try:
            from ApplicationServices import kAXTrustedCheckOptionPrompt as key
        except Exception:
            key = "AXTrustedCheckOptionPrompt"
        return bool(AXIsProcessTrustedWithOptions({key: bool(prompt)}))
    except Exception:
        return False


def has_input_monitoring(prompt: bool = False) -> bool:
    """True if Ember has macOS Input Monitoring (needed to LISTEN to global keyboard/mouse,
    e.g. recording a workflow). CRITICAL: pynput's event tap hard-CRASHES the whole process
    if started without this grant, so callers must preflight here and refuse to start when
    it returns False. Returns True off macOS / when the API is unavailable (can't block)."""
    if sys.platform != "darwin":
        return True
    try:
        import Quartz
    except Exception:
        return True  # no pyobjc-Quartz -> can't check; don't hard-block
    try:
        if prompt and hasattr(Quartz, "CGRequestListenEventAccess"):
            try:
                Quartz.CGRequestListenEventAccess()   # shows the system prompt (once)
            except Exception:
                pass
        if hasattr(Quartz, "CGPreflightListenEventAccess"):
            return bool(Quartz.CGPreflightListenEventAccess())
        return True   # older macOS without the preflight API
    except Exception:
        return True


def open_input_monitoring_settings():
    """Open System Settings directly at Privacy -> Input Monitoring."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"],
            capture_output=True, timeout=10)
    except Exception:
        pass


def open_accessibility_settings():
    """Open System Settings directly at Privacy -> Accessibility."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass
