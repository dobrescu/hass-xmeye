"""The device tree, against a fake recorder: no network needed.

Home Assistant 2026.9 deprecated linking a device to its parent by identifiers.
With go2rtc loaded, as on Home Assistant OS, the first camera yields to the
event loop while it registers, and every camera after it then failed with a
RuntimeError, leaving one camera per recorder (issues #6 and #7).
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.xmeye.const import CONF_CHANNELS, CONF_ENABLE_PANEL, DOMAIN
from custom_components.xmeye.coordinator import XmeyeData
from custom_components.xmeye.entity import VIA_DEVICE_ID
from custom_components.xmeye.xmeyelib import ChannelStatus, DeviceInfo
from homeassistant.components.camera import (
    CameraWebRTCProvider,
    async_register_webrtc_provider,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

CHANNELS = [0, 1, 2, 3]


class YieldingProvider(CameraWebRTCProvider):
    """Registers a camera the way go2rtc does, with a request that yields."""

    @property
    def domain(self) -> str:
        return "yielding_provider"

    def async_is_supported(self, stream_source: str) -> bool:
        return stream_source.startswith("rtsp://")

    async def async_handle_async_webrtc_offer(self, *args) -> None:
        raise NotImplementedError

    async def async_on_webrtc_candidate(self, *args) -> None:
        raise NotImplementedError

    async def async_register_camera(self, camera) -> None:
        await asyncio.sleep(0)


def _data() -> XmeyeData:
    return XmeyeData(
        device=DeviceInfo(hardware="NBD8008R-U", software_version="V4.03", serial_number="sn"),
        channels=[ChannelStatus(index=i, status="Connected") for i in CHANNELS],
        titles=[f"Camera {i + 1}" for i in CHANNELS],
    )


@pytest.fixture
async def entry(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> MockConfigEntry:
    caplog.set_level(logging.WARNING)
    # The integration's dependencies are not needed for the device tree.
    hass.config.components.update({"ffmpeg", "frontend", "http", "stream", "websocket_api"})
    hass.http = MagicMock()
    assert await async_setup_component(hass, "camera", {})
    async_register_webrtc_provider(hass, YieldingProvider())

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="NBD8008R-U",
        unique_id="sn",
        data={"host": "192.0.2.1", "port": 34567, "username": "admin", "password": "x"},
        options={CONF_CHANNELS: CHANNELS, CONF_ENABLE_PANEL: False},
    )
    config_entry.add_to_hass(hass)
    client = MagicMock(close=AsyncMock())
    with (
        patch("custom_components.xmeye.async_create_client", AsyncMock(return_value=client)),
        patch(
            "custom_components.xmeye.coordinator.XmeyeCoordinator._async_update_data",
            AsyncMock(return_value=_data()),
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


def _setup_log(caplog: pytest.LogCaptureFixture) -> list[str]:
    """What was logged while the entry was set up, in the fixture."""
    return [record.getMessage() for record in caplog.get_records("setup")]


async def test_every_camera_registers(
    hass: HomeAssistant, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    registry = er.async_get(hass)
    cameras = [
        item
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if item.domain == "camera"
    ]
    assert not [line for line in _setup_log(caplog) if "Error adding entity" in line]
    assert len(cameras) == 2 * len(CHANNELS)


async def test_channels_hang_under_the_recorder(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    recorder = next(d for d in devices if (DOMAIN, entry.entry_id) in d.identifiers)
    assert recorder.model == "NBD8008R-U"
    channels = [d for d in devices if d.via_device_id == recorder.id]
    assert sorted(d.name for d in channels) == [f"Camera {i + 1}" for i in CHANNELS]


async def test_no_deprecated_parent_link(
    hass: HomeAssistant, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    if not VIA_DEVICE_ID:
        pytest.skip("this Home Assistant has only the link by identifiers")
    assert not [line for line in _setup_log(caplog) if "via_device" in line]
