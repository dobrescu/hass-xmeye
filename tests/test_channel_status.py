"""Which channels are online.

An analog HVR (MBD6304T: VideoInChannel 4, DigChannel 0) answers
``NetWork.ChnStatus`` with 32 empty slots, so every camera read as offline and
32 phantom channels showed up as configured. Its inputs are judged by the
video-loss alarm instead.
"""

from __future__ import annotations

import pytest

from xmeye import XmeyeClient
from xmeye.models import DeviceInfo, WorkState

EMPTY_SLOTS = [{"ChnName": "", "Status": "", "CurRes": "", "MaxRes": ""}] * 32


def answering_chnstatus(monkeypatch: pytest.MonkeyPatch, raw: list) -> None:
    async def get_config(self, name, **kwargs):
        assert name == "NetWork.ChnStatus"
        return raw

    monkeypatch.setattr(XmeyeClient, "get_config", get_config)


async def test_analog_inputs_follow_video_loss(monkeypatch) -> None:
    answering_chnstatus(monkeypatch, EMPTY_SLOTS)
    info = DeviceInfo.from_raw({"DigChannel": 0, "VideoInChannel": 4})
    state = WorkState.from_raw({"AlarmState": {"VideoLoss": "0x4"}})

    statuses = await XmeyeClient("192.0.2.1").channel_statuses(info, state)

    assert [c.index for c in statuses] == [0, 1, 2, 3]
    assert [c.online for c in statuses] == [True, True, False, True]


async def test_ip_channels_keep_their_reported_state(monkeypatch) -> None:
    answering_chnstatus(
        monkeypatch, [{"Status": "Connected"}, {"Status": "NotConnected"}, {"Status": "NoConfig"}]
    )
    info = DeviceInfo.from_raw({"DigChannel": 3, "VideoInChannel": 0})

    statuses = await XmeyeClient("192.0.2.1").channel_statuses(info)

    assert [c.online for c in statuses] == [True, False, False]
    assert [c.configured for c in statuses] == [True, True, False]
