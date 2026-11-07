"""Binary sensor: is a workout in progress?"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities([JumpRopeActive(entry.runtime_data)])


class JumpRopeActive(JumpRopeEntity, BinarySensorEntity):
    """On while the jump count has recently been changing."""

    _attr_translation_key = "workout_active"
    _attr_icon = "mdi:run-fast"

    def __init__(self, coordinator: JumpRopeCoordinator) -> None:
        super().__init__(coordinator, "workout_active")

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_active
