"""Xiaomi / Mijia Smart Jump Rope (XMSR-P803) integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import JumpRopeCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type JumpRopeConfigEntry = ConfigEntry[JumpRopeCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: JumpRopeConfigEntry) -> bool:
    coordinator = JumpRopeCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JumpRopeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
