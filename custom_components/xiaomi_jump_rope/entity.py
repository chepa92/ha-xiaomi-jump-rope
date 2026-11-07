"""Base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JumpRopeCoordinator


class JumpRopeEntity(CoordinatorEntity[JumpRopeCoordinator]):
    """Base class for jump rope entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JumpRopeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        address = coordinator.address
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name="Mijia Smart Jump Rope",
            manufacturer="Xiaomi",
            model="XMSR-P803",
        )

    @property
    def available(self) -> bool:
        # Keep showing the last known values while the rope sleeps.
        return self.coordinator.data is not None
