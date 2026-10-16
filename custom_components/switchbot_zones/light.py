"""Light entities, one per zone."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SwitchbotZonesConfigEntry
from .const import DOMAIN
from .coordinator import SwitchbotZonesCoordinator, Zone


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchbotZonesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one light per zone and drop entities of zones that no longer exist."""
    coordinator = entry.runtime_data
    entities = [SwitchbotZoneLight(coordinator, zone) for zone in coordinator.zones]

    wanted = {e.unique_id for e in entities}
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)

    async_add_entities(entities)


class SwitchbotZoneLight(CoordinatorEntity[SwitchbotZonesCoordinator], LightEntity):
    """A zone of the lamp, behaving like an ordinary colour light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.HS}

    def __init__(self, coordinator: SwitchbotZonesCoordinator, zone: Zone) -> None:
        super().__init__(coordinator)
        self._index = zone.index
        self._attr_unique_id = f"{coordinator.address}_zone_{zone.index}"
        self._attr_name = f"Zone {zone.index}"
        # Sharing the Bluetooth connection with the core SwitchBot integration
        # lets Home Assistant put the zones on the same device card.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="SwitchBot",
            model="RGBICWW Floor Lamp",
            name="SwitchBot Floor Lamp",
        )

    @property
    def _zone(self) -> Zone:
        return self.coordinator.zones[self._index - 1]

    @property
    def available(self) -> bool:
        return self.coordinator.available

    @property
    def is_on(self) -> bool:
        return self._zone.on

    @property
    def brightness(self) -> int:
        return self._zone.brightness

    @property
    def hs_color(self) -> tuple[float, float]:
        return self._zone.hs

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"segments": self._zone.segments}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_update_zone(
            self._index,
            on=True,
            brightness=kwargs.get(ATTR_BRIGHTNESS),
            hs=kwargs.get(ATTR_HS_COLOR),
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_update_zone(self._index, on=False)
        self.async_write_ha_state()
