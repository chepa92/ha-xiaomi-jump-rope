"""Sensors for the Xiaomi Smart Jump Rope."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import JumpRopeConfigEntry
from .coordinator import JumpRopeCoordinator
from .entity import JumpRopeEntity
from .protocol import RopeStatus


@dataclass(frozen=True, kw_only=True)
class JumpRopeSensorDescription(SensorEntityDescription):
    """Describes a jump rope sensor."""

    value_fn: Callable[[JumpRopeCoordinator, RopeStatus], object]


SENSORS: tuple[JumpRopeSensorDescription, ...] = (
    JumpRopeSensorDescription(
        key="jumps",
        translation_key="jumps",
        icon="mdi:jump-rope",
        native_unit_of_measurement="jumps",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c, s: s.jumps,
    ),
    JumpRopeSensorDescription(
        key="calories",
        translation_key="calories",
        icon="mdi:fire",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c, s: s.calories,
    ),
    JumpRopeSensorDescription(
        key="duration",
        translation_key="duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c, s: s.duration,
    ),
    JumpRopeSensorDescription(
        key="last_read",
        translation_key="last_read",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c, s: c.last_read,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JumpRopeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(JumpRopeSensor(coordinator, d) for d in SENSORS)


class JumpRopeSensor(JumpRopeEntity, SensorEntity):
    """A jump rope sensor."""

    entity_description: JumpRopeSensorDescription

    def __init__(
        self, coordinator: JumpRopeCoordinator, description: JumpRopeSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator, self.coordinator.data)
