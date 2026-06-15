"""Ember plans: FREE and PRO.

Every gated capability checks `plan.has("feature")`. The default plan is **PRO**,
so right now *every user gets the full Pro feature set for free* — there is no
paywall, license check, or payment. The structure is here so that IF payments are
ever added later, you only flip DEFAULT_PLAN to "free" and unlock per license; all
the gating already exists.

Override at runtime with the EMBER_PLAN env var ("free" or "pro"), or persist with
set_plan().
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

_LOCK = threading.RLock()

# >>> Everyone is Pro for now. <<<
DEFAULT_PLAN = "pro"

_RANK = {"free": 0, "pro": 1}

# feature key -> minimum plan that unlocks it.
FEATURES = {
    # Available on every plan
    "antivirus": "free",
    "web_protection": "free",
    "audit_log": "free",
    "secret_redaction": "free",
    # Pro
    "advanced_antivirus": "pro",
    "deep_directory_scan": "pro",
    "scheduled_scans": "pro",
    "sandbox": "pro",
    "url_reputation": "pro",
    "capability_modes": "pro",
    "vpn": "pro",
    "vpn_all_locations": "pro",
    "priority_models": "pro",
    "pro_ui": "pro",
    "unlimited_tools": "pro",
}

# Human-readable Pro pitch (used by UI / get_plan).
PRO_BENEFITS = [
    "Advanced antivirus: deep folder scans, scheduled scans, more detection engines",
    "Sandbox: run unknown programs in isolation",
    "VPN: connect through any of your WireGuard locations",
    "Live URL reputation (Safe Browsing / VirusTotal / URLhaus)",
    "Capability modes (read-only / restricted) + tamper-evident audit log",
    "Priority models and the full Pro UI",
]


def _support_dir() -> Path:
    override = os.environ.get("EMBER_SUPPORT_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Ember"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Ember"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "Ember"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path() -> Path:
    return _support_dir() / "plan.json"


def current_plan() -> str:
    env = os.environ.get("EMBER_PLAN")
    if env in _RANK:
        return env
    try:
        p = _path()
        if p.exists():
            v = json.loads(p.read_text("utf-8")).get("plan")
            if v in _RANK:
                return v
    except Exception:
        pass
    return DEFAULT_PLAN


def set_plan(plan: str) -> dict:
    if plan not in _RANK:
        return {"ok": False, "error": "plan must be 'free' or 'pro'"}
    with _LOCK:
        try:
            _path().write_text(json.dumps({"plan": plan}), "utf-8")
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True, "plan": plan}


def has(feature: str) -> bool:
    """True if the current plan unlocks `feature` (unknown features default to free)."""
    need = FEATURES.get(feature, "free")
    return _RANK.get(current_plan(), 1) >= _RANK.get(need, 0)


def require(feature: str) -> dict | None:
    """Return None if allowed; else an error dict a tool can return directly."""
    if has(feature):
        return None
    return {"ok": False, "error": f"'{feature}' requires Ember Pro.", "upgrade_required": True}


def get_plan() -> dict:
    plan = current_plan()
    return {
        "ok": True,
        "plan": plan,
        "is_pro": plan == "pro",
        "everyone_is_pro": DEFAULT_PLAN == "pro",
        "features": {k: has(k) for k in FEATURES},
        "pro_benefits": PRO_BENEFITS,
    }


def list_pro_features() -> dict:
    return {"ok": True,
            "pro_features": sorted(k for k, v in FEATURES.items() if v == "pro"),
            "benefits": PRO_BENEFITS}
