"""The SwitchBot Zones integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ADDRESS,
    CONF_BLEND_MODE,
    CONF_COLORS_PER_PACKET,
    CONF_ENCRYPTION_KEY,
    CONF_KEY_ID,
    CONF_ZONES,
    DEFAULT_BLEND_MODE,
    DEFAULT_COLORS_PER_PACKET,
    DEFAULT_ZONES,
    SEGMENT_COUNT,
)
from .coordinator import SwitchbotZonesCoordinator
from .gradient import parse_zones
from .lamp import FloorLamp

PLATFORMS: list[Platform] = [Platform.LIGHT]

type SwitchbotZonesConfigEntry = ConfigEntry[SwitchbotZonesCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: SwitchbotZonesConfigEntry
) -> bool:
    """Set up SwitchBot Zones from a config entry."""
    address: str = entry.data[CONF_ADDRESS].upper()
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"{address} has not been seen by any connectable Bluetooth adapter or proxy"
        )

    lamp = FloorLamp(
        device=ble_device,
        key_id=entry.data[CONF_KEY_ID],
        encryption_key=entry.data[CONF_ENCRYPTION_KEY],
    )
    options = entry.options
    coordinator = SwitchbotZonesCoordinator(
        hass,
        entry,
        lamp,
        address,
        parse_zones(options.get(CONF_ZONES, DEFAULT_ZONES), SEGMENT_COUNT),
        options.get(CONF_BLEND_MODE, DEFAULT_BLEND_MODE),
        options.get(CONF_COLORS_PER_PACKET, DEFAULT_COLORS_PER_PACKET),
    )
    entry.runtime_data = coordinator

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator.async_handle_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=address, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(
        bluetooth.async_track_unavailable(
            hass, coordinator.async_handle_unavailable, address, connectable=True
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: SwitchbotZonesConfigEntry
) -> None:
    # Zone layout decides how many entities exist, so a reload is the simple
    # and correct answer. It does not need a Home Assistant restart.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: SwitchbotZonesConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
