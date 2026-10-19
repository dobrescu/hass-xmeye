"""What the Home Assistant review asked for, held by reading the source.

The integration modules import Home Assistant, which the offline suite does
not have, so these read the code rather than run it — the same way the event
loop checks do. Each one names the review point it keeps from coming back.
"""

from __future__ import annotations

import re
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "xmeye"
PANEL = COMPONENT / "panel" / "xmeye-panel.js"


def source(name: str) -> str:
    return (COMPONENT / name).read_text(encoding="utf-8")


def decorators_of(text: str, function: str) -> str:
    """The decorator lines directly above a function definition.

    Walked line by line, upwards to the blank line that ends the block: a regex
    over the whole module backtracks for minutes on a file this size.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith((f"def {function}(", f"async def {function}(")):
            start = index
            while start > 0 and lines[start - 1].strip():
                start -= 1
            return "\n".join(lines[start:index])
    raise AssertionError(f"{function} is gone; this test needs updating")


# -- 1. administration needs an administrator --------------------------------

ADMIN_COMMANDS = [
    "ws_config_set", "ws_reboot", "ws_config_get", "ws_config_tree", "ws_log", "ws_report",
]


def test_administration_commands_require_an_administrator() -> None:
    text = source("websocket.py")
    for command in ADMIN_COMMANDS:
        assert "@websocket_api.require_admin" in decorators_of(text, command), (
            f"{command} answers non-administrators"
        )


def test_configuration_and_talk_actions_are_admin_services() -> None:
    text = source("services.py")
    for service in ("SERVICE_GET_CONFIG", "SERVICE_SET_CONFIG", "SERVICE_TALK"):
        assert re.search(
            rf"async_register_admin_service\(\s*hass,\s*DOMAIN,\s*{service}", text
        ), f"{service} is callable by any user"


def test_the_get_config_action_masks_its_answer() -> None:
    text = source("services.py")
    body = text.split("async def handle_get_config", 1)[1].split("\n    async def ", 1)[0]
    assert '"value": mask(value)' in body, "get_config hands out stored passwords"


def test_the_panel_shows_administration_tabs_to_administrators_only() -> None:
    text = PANEL.read_text(encoding="utf-8")
    assert re.search(r"const ADMIN_TABS = \[[^\]]*\"settings\"", text)
    assert "this._isAdmin() || !ADMIN_TABS.includes(key)" in text


# -- 2. recorder strings are escaped before they become markup ---------------

#: Values that come from the recorder or the cameras behind it. Each must pass
#: through escapeHtml wherever it is put into a template.
RECORDER_STRINGS = [
    "channel.name", "c.name", "dev.title", "e.type", "e.user", "c.status", "c.resolution",
]


def test_recorder_strings_are_never_interpolated_raw() -> None:
    text = PANEL.read_text(encoding="utf-8")
    raw = [
        f"{name} on line {text[: m.start()].count(chr(10)) + 1}"
        for name in RECORDER_STRINGS
        for m in re.finditer(r"\$\{\s*" + re.escape(name) + r"\b", text)
    ]
    assert not raw, "unescaped recorder strings: " + ", ".join(raw)


# -- 3. no blocking file system calls on the event loop ----------------------


def test_the_debug_log_does_not_touch_the_disk_when_built() -> None:
    text = source("debuglog.py")
    init = text.split("    def __init__", 1)[1].split("\n    def ", 1)[0]
    assert ".exists(" not in init, "DebugLog() asks the disk; it is built from the loop"
    assert "async_add_executor_job(marker_path(hass).exists)" in text


def test_the_download_action_makes_its_folder_in_the_executor() -> None:
    text = source("services.py")
    body = text.split("async def handle_download", 1)[1].split("\n    async def ", 1)[0]
    for line in body.splitlines():
        if ".mkdir(" in line:
            assert "async_add_executor_job" in line, f"mkdir on the event loop: {line.strip()}"
