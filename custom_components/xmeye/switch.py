"""Switches: motion detection and alarm reporting."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DETECT_SECTIONS, DOMAIN
from .coordinator import XmeyeCoordinator
from .entity import XmeyeChannelEntity
from .xmeyelib import XmeyeError


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: XmeyeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        XmeyeDetectSwitch(coordinator, channel, key, section, translation_key)
        for channel in coordinator.enabled_channels
        for key, (section, translation_key) in DETECT_SECTIONS.items()
    )


class XmeyeDetectSwitch(XmeyeChannelEntity, SwitchEntity):
    """Enable a detector on one channel; the coordinator re-reads them with its slow data."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: XmeyeCoordinator,
        channel: int,
        key: str,
        section: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator, channel, key)
        self._section = section
        self._attr_translation_key = translation_key
        self.entity_description = SwitchEntityDescription(
            key=key, translation_key=translation_key
        )

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.detect_enabled(self._section, self.channel)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            async with self.coordinator.lock:
                config = await self.coordinator.client.get_config(self._section)
                if not isinstance(config, list) or self.channel >= len(config):
                    raise HomeAssistantError(
                        f"The recorder has no {self._section} setting for channel "
                        f"{self.channel + 1}"
                    )
                # The firmware only accepts the whole array, so change one item
                # and send the rest back untouched.
                config[self.channel]["Enable"] = enabled
                await self.coordinator.client.set_config(self._section, config)
        except XmeyeError as err:
            raise HomeAssistantError(f"Could not change {self._section}: {err}") from err
        self.coordinator.async_set_detect(self._section, config)
