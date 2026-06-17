"""Tests for workflow_recorder — must pass WITHOUT pynput installed.

These exercise the pure event-builder helpers, file persistence, and the
list/delete tools, plus the friendly pynput-missing / not-found error paths.
"""
import json

import pytest

import workflow_recorder as wr


@pytest.fixture(autouse=True)
def _tmp_workflow_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "WORKFLOW_DIR", tmp_path / "workflows")
    yield


def _sample_events():
    """Build a workflow via the pure helpers (no pynput needed)."""
    return [
        wr._record_move(10, 20, 0.0),
        wr._record_click(10, 20, "left", True, 0.5),
        wr._record_scroll(10, 20, 0, -2, 1.0),
        wr._record_key("a", 1.2),
        wr._record_key("space", 1.4),
    ]


# ---- pure event builders -----------------------------------------------------
def test_serialize_key_variants():
    assert wr._serialize_key("a") == "a"
    assert wr._serialize_key(None) == ""

    class _KC:  # mimic pynput KeyCode with a .char
        char = "z"
    assert wr._serialize_key(_KC()) == "z"

    class _SpecialName:  # mimic pynput Key with a .name and no char
        char = None
        name = "enter"
    assert wr._serialize_key(_SpecialName()) == "enter"

    class _ReprOnly:
        char = None
        name = None
        def __str__(self):
            return "Key.space"
    assert wr._serialize_key(_ReprOnly()) == "space"


def test_event_builders_shape():
    mv = wr._record_move(5, 6, 0.1234567)
    assert mv == {"t": 0.1235, "type": "move", "x": 5, "y": 6}

    ck = wr._record_click(1, 2, "left", True, 0.5)
    assert ck["type"] == "click" and ck["button"] == "left" and ck["pressed"] is True

    sc = wr._record_scroll(1, 2, 0, -3, 0.7)
    assert sc["type"] == "scroll" and sc["dx"] == 0 and sc["dy"] == -3

    ky = wr._record_key("a", 0.9)
    assert ky["type"] == "key" and ky["key"] == "a"


# ---- persistence + list + delete --------------------------------------------
def test_save_list_delete_roundtrip():
    events = _sample_events()
    saved = wr._save_workflow("My Demo Flow", events, duration=1.4)
    assert saved["ok"] is True
    assert saved["event_count"] == 5
    assert saved["name"] == "My Demo Flow"

    # File written under the monkeypatched dir as a slug.
    path = wr._path_for("My Demo Flow")
    assert path.exists()
    on_disk = json.loads(path.read_text("utf-8"))
    assert on_disk["name"] == "My Demo Flow"
    assert len(on_disk["events"]) == 5
    assert "created" in on_disk and on_disk["duration"] == 1.4

    listing = wr.list_workflows()
    assert listing["ok"] is True
    assert listing["count"] == 1
    entry = listing["workflows"][0]
    assert entry["name"] == "My Demo Flow"
    assert entry["event_count"] == 5
    assert entry["duration"] == 1.4
    assert entry["created"]

    deleted = wr.delete_workflow("My Demo Flow")
    assert deleted["ok"] is True and deleted["deleted"] is True
    assert not path.exists()
    assert wr.list_workflows()["count"] == 0


def test_list_workflows_empty():
    r = wr.list_workflows()
    assert r["ok"] is True and r["count"] == 0 and r["workflows"] == []


def test_save_requires_name():
    assert wr._save_workflow("", [], 0)["ok"] is False


def test_delete_missing():
    r = wr.delete_workflow("does-not-exist")
    assert r["ok"] is False
    assert "no workflow" in r["error"]


# ---- pynput-missing friendly errors (pynput absent in this env) --------------
def test_record_start_without_pynput():
    r = wr.record_workflow_start("anything")
    assert r["ok"] is False
    assert "pynput" in r["error"].lower()


def test_replay_without_pynput():
    # Save a real workflow first so the failure is the pynput import, not not-found.
    wr._save_workflow("x", _sample_events(), 1.4)
    r = wr.replay_workflow("x")
    assert r["ok"] is False
    assert "pynput" in r["error"].lower()


def test_replay_not_found():
    r = wr.replay_workflow("nope-not-here")
    assert r["ok"] is False
    assert "no workflow" in r["error"]


def test_record_stop_when_not_recording():
    r = wr.record_workflow_stop()
    assert r["ok"] is False


# ---- export integrity --------------------------------------------------------
def test_exports_consistent():
    assert set(wr.TOOL_DISPATCH) == {d["name"] for d in wr.TOOL_DECLARATIONS}
    assert len(wr.TOOL_DECLARATIONS) == 5
    assert wr.READONLY_TOOLS == {"list_workflows"}
    assert wr.INTERACTION_TOOLS == {"record_workflow_start", "record_workflow_stop", "delete_workflow"}
    # replay_workflow is in neither set.
    assert "replay_workflow" not in wr.READONLY_TOOLS
    assert "replay_workflow" not in wr.INTERACTION_TOOLS


def _run():
    import types
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    print(f"discovered {len(fns)} tests (run via pytest)")


if __name__ == "__main__":
    _run()
