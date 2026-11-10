"""Analog inputs are judged by the video-loss alarm, IP channels by ``NetWork.ChnStatus``."""

from __future__ import annotations

import pytest

from xmeye import XmeyeClient
from xmeye.models import DeviceInfo, WorkState

EMPTY_SLOTS = [{"ChnName": "", "Status": "", "CurRes": "", "MaxRes": ""}] * 32
ANALOG_HVR = {"DigChannel": 0, "VideoInChannel": 4}
LOSS_ON_THIRD = WorkState.from_raw({"AlarmState": {"VideoLoss": "0x4"}})


@pytest.fixture
def chnstatus(monkeypatch: pytest.MonkeyPatch) -> list:
    """What ``NetWork.ChnStatus`` answers; tests replace its contents."""
    answer: list = []

    async def get_config(self, name, **kwargs):
        assert name == "NetWork.ChnStatus"
        return answer

    monkeypatch.setattr(XmeyeClient, "get_config", get_config)
    return answer


async def test_analog_inputs_follow_video_loss(chnstatus) -> None:
    chnstatus.extend(EMPTY_SLOTS)
    info = DeviceInfo.from_raw(ANALOG_HVR)

    statuses = await XmeyeClient("192.0.2.1").channel_statuses(info, LOSS_ON_THIRD)

    assert [c.index for c in statuses] == [0, 1, 2, 3]
    assert [c.online for c in statuses] == [True, True, False, True]
    assert all(c.configured and c.default_enabled for c in statuses)


async def test_analog_inputs_read_the_state_when_not_given(chnstatus, monkeypatch) -> None:
    async def work_state(self):
        return LOSS_ON_THIRD

    monkeypatch.setattr(XmeyeClient, "work_state", work_state)
    info = DeviceInfo.from_raw(ANALOG_HVR)

    statuses = await XmeyeClient("192.0.2.1").channel_statuses(info)

    assert [c.online for c in statuses] == [True, True, False, True]


@pytest.mark.parametrize(
    "system_info",
    [
        {"DigChannel": 3, "VideoInChannel": 0},
        {"DigChannel": 3, "VideoInChannel": 4},
        {},
    ],
    ids=["nvr", "mixed-hvr", "blank-system-info"],
)
async def test_ip_channels_keep_their_reported_state(chnstatus, system_info) -> None:
    chnstatus.extend([{"Status": "Connected"}, {"Status": "NotConnected"}, {"Status": "NoConfig"}])
    info = DeviceInfo.from_raw(system_info)

    statuses = await XmeyeClient("192.0.2.1").channel_statuses(info, LOSS_ON_THIRD)

    assert [c.online for c in statuses] == [True, False, False]
    assert [c.configured for c in statuses] == [True, True, False]
    assert [c.default_enabled for c in statuses] == [True, False, False]
