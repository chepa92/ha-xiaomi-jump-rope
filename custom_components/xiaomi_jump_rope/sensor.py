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
        key="today_jumps",
        translation_key="today_jumps",
        icon="mdi:counter",
        native_unit_of_measurement="jumps",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c, s: c.today_totals.jumps + (c.tracker.session.jumps if c.tracker.session else 0),
    ),
    JumpRopeSensorDescription(
        key="today_calories",
        translation_key="today_calories",
        icon="mdi:fire",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c, s: c.today_totals.calories + (c.tracker.session.calories if c.tracker.session else 0),
    ),
    JumpRopeSensorDescription(
        key="today_duration",
        translation_key="today_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c, s: c.today_totals.duration + (c.tracker.session.duration if c.tracker.session else 0),
    ),
    JumpRopeSensorDescription(
        key="today_sessions",
        translation_key="today_sessions",
        icon="mdi:numeric",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c, s: c.today_totals.sessions + (1 if c.tracker.session else 0),
    ),
    JumpRopeSensorDescription(
        key="last_session_jumps",
        translation_key="last_session_jumps",
        icon="mdi:history",
        native_unit_of_measurement="jumps",
        value_fn=lambda c, s: c.today.last.get("jumps"),
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
