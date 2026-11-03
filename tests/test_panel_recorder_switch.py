"""Switching the recorder in the panel (issue #2).

Everything the panel shows was read from one recorder, and a switch used to
keep most of it. The wall's socket stayed signed for the old recorder, so its
cameras went on playing under the new one's channel names until a camera was
opened; the settings form kept the old recorder's values, and saving it wrote
them into the new one.

Run through node and jsdom, against the panel's own module and two fake
recorders: tests/panel/recorder_switch.mjs drives it and reports what it saw.
Skipped where node or jsdom is missing; CI installs jsdom with
``npm install --prefix tests/panel``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "custom_components" / "xmeye" / "panel" / "xmeye-panel.js"
SCRIPT = HERE / "panel" / "recorder_switch.mjs"


@cache
def _run() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable")
    if not (HERE / "panel" / "node_modules" / "jsdom").is_dir():
        pytest.skip("jsdom is not installed: npm install --prefix tests/panel")
    done = subprocess.run(
        [node, str(SCRIPT), PANEL.as_uri()],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture
def seen() -> dict:
    return _run()


def test_the_wall_follows_the_switch(seen: dict) -> None:
    wall = seen["wall"]
    assert wall["before"] == {
        "tiles": ["1. A-front", "2. A-yard", "3. A-gate", "4. A-garage"],
        "wall": "A",
    }
    assert wall["after"] == {
        "title": "Model B",
        "tiles": ["1. B-door", "2. B-hall"],
        "wall": "B",
    }
    # The old recorder's socket is closed, not left carrying its cameras.
    assert wall["sockets"] == [
        {"recorder": "A", "closed": True},
        {"recorder": "B", "closed": False},
    ]


def test_settings_are_read_again_and_saved_where_they_came_from(seen: dict) -> None:
    settings = seen["settings"]
    assert settings["before"] == "NVR-A"
    assert settings["after"] == "NVR-B"
    assert settings["write"] == {"recorder": "B", "MachineName": "NVR-B", "AutoLogout": 20}


def test_unsaved_settings_keep_their_recorder(seen: dict) -> None:
    """Declining to discard the edits leaves both the edits and the recorder."""
    assert seen["unsaved"] == {
        "recorder": "A",
        "picker": "A",
        "edits": {"AutoLogout": 20},
        "title": "Model A",
    }


def test_a_late_poll_does_not_bring_the_old_recorder_back(seen: dict) -> None:
    assert seen["latePoll"] == {
        "title": "Model B",
        "tiles": ["1. B-door", "2. B-hall"],
        "wall": "B",
        "detail": "B",
    }


def test_the_archive_is_read_from_the_new_recorder(seen: dict) -> None:
    assert seen["archive"]["asked"] == ["A", "B"]
