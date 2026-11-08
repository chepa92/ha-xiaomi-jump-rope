"""Button: connect to the rope right now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import JumpRopeConfigEntry
from .coordinator import JumpRopeCoordinator
from .entity import JumpRopeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JumpRopeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([JumpRopeConnectButton(entry.runtime_data)])


class JumpRopeConnectButton(JumpRopeEntity, ButtonEntity):
    """Force a connection: read the live counters and download stored workouts."""

    _attr_translation_key = "connect_now"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: JumpRopeCoordinator) -> None:
        super().__init__(coordinator, "connect_now")

    @property
    def available(self) -> bool:
        return True  # usable even before the first successful read

    async def async_press(self) -> None:
        await self.coordinator.async_force_read()
