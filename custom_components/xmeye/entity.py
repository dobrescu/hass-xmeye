"""Shared base classes for XMeye entities."""

from __future__ import annotations

import inspect

from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import XmeyeCoordinator

#: Home Assistant 2026.8 links a device to its parent by the parent's id, and
#: 2026.9 deprecated the link by identifiers: from then on a camera added after
#: go2rtc yields to the event loop fails to register at all. Versions before
#: 2026.8 know only the link by identifiers.
VIA_DEVICE_ID = "via_device_id" in inspect.signature(DeviceRegistry.async_get_or_create).parameters


def recorder_device_info(coordinator: XmeyeCoordinator) -> HaDeviceInfo:
    """The recorder as a Home Assistant device."""
    entry = coordinator.config_entry
    device = coordinator.data.device if coordinator.data else None
    return HaDeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=device.hardware if device else None,
        sw_version=device.software_version if device else None,
        serial_number=device.serial_number if device else None,
        configuration_url=f"http://{entry.data['host']}",
    )


class XmeyeEntity(CoordinatorEntity[XmeyeCoordinator]):
    """An entity attached to the recorder as a whole."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: XmeyeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = recorder_device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class XmeyeChannelEntity(XmeyeEntity):
    """An entity of a single channel.

    Each channel becomes its own Home Assistant device under the recorder, so
    cameras group naturally instead of blurring together.
    """

    def __init__(self, coordinator: XmeyeCoordinator, channel: int, key: str) -> None:
        super().__init__(coordinator, f"ch{channel}_{key}")
        self.channel = channel
        entry = coordinator.config_entry
        if VIA_DEVICE_ID:
            parent = HaDeviceInfo(via_device_id=coordinator.recorder_device_id)
        else:
            parent = HaDeviceInfo(via_device=(DOMAIN, entry.entry_id))
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_ch{channel}")},
            name=self.channel_name,
            manufacturer=MANUFACTURER,
            model="Channel",
            **parent,
        )

    @property
    def channel_name(self) -> str:
        if self.coordinator.data:
            return self.coordinator.data.channel_name(self.channel)
        return f"Channel {self.channel + 1}"

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        statuses = self.coordinator.data.channels
        if self.channel < len(statuses):
            return statuses[self.channel].configured
        return True
