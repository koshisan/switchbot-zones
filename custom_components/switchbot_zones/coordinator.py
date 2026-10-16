"""Holds the desired state of every zone and pushes full frames to the lamp."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
import logging
import time

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from switchbot import SwitchbotModel, SwitchbotOperationError, parse_advertisement_data

from .const import ADVERTISEMENT_GRACE, DOMAIN, SEGMENT_COUNT, WRITE_DEBOUNCE
from .gradient import RGB, render
from .lamp import FloorLamp, LampCommandError

_LOGGER = logging.getLogger(__name__)

WRITE_ERRORS = (BleakError, TimeoutError, SwitchbotOperationError, LampCommandError)


@dataclass
class Zone:
    """A group of anchor segments, exposed as one light entity."""

    index: int
    segments: list[int]
    on: bool = False
    brightness: int = 255
    hs: tuple[float, float] = field(default=(0.0, 0.0))

    @property
    def rgb(self) -> RGB:
        """Brightness is the V of the colour -- the lamp has one global
        brightness only, which we pin to 100 %."""
        if not self.on:
            return (0, 0, 0)
        hue, sat = self.hs
        r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat / 100.0, self.brightness / 255.0)
        return (round(r * 255), round(g * 255), round(b * 255))


class SwitchbotZonesCoordinator(DataUpdateCoordinator[None]):
    """Single source of truth for the zones. Segment colours cannot be read
    back from the lamp, so this state is optimistic."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        lamp: FloorLamp,
        address: str,
        zones: list[list[int]],
        blend_mode: str,
        colors_per_packet: int,
        bottom_up: bool,
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {address}")
        self.lamp = lamp
        self.address = address
        self.blend_mode = blend_mode
        self.colors_per_packet = colors_per_packet
        self.bottom_up = bottom_up
        self.zones = [Zone(index=i, segments=s) for i, s in enumerate(zones, start=1)]
        self.available = True
        self._device_on: bool | None = None
        self._calibrated = False
        self._last_write = 0.0
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=WRITE_DEBOUNCE,
            immediate=False,
            function=self._async_flush,
        )

    @callback
    def async_handle_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        _change: bluetooth.BluetoothChange,
    ) -> None:
        """Keep the BLEDevice fresh (it may move between proxies) and notice
        when somebody else switches the lamp off."""
        parsed = parse_advertisement_data(
            service_info.device,
            service_info.advertisement,
            SwitchbotModel.RGBICWW_FLOOR_LAMP,
        )
        if not parsed:
            return
        self.lamp.update_from_advertisement(parsed)

        changed = not self.available
        self.available = True

        is_on = self.lamp.is_on()
        recent_write = time.monotonic() - self._last_write < ADVERTISEMENT_GRACE
        if is_on is not None and not recent_write:
            if self._device_on and not is_on:
                for zone in self.zones:
                    zone.on = False
                self._calibrated = False
                changed = True
            self._device_on = is_on

        if changed:
            self.async_update_listeners()

    @callback
    def async_handle_unavailable(
        self, _service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        self.available = False
        self.async_update_listeners()

    async def async_update_zone(
        self,
        index: int,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        hs: tuple[float, float] | None = None,
    ) -> None:
        """Apply a change to one zone and schedule a write of the full frame."""
        zone = self.zones[index - 1]
        if on is not None:
            zone.on = on
        if brightness is not None:
            zone.brightness = brightness
        if hs is not None:
            zone.hs = hs
        await self._debouncer.async_call()

    def frame(self) -> list[RGB]:
        """Segments in the lamp's own order. Zone ranges count from the
        bottom when bottom_up is set; the lamp counts from the top."""
        frame = render(
            [(z.segments, z.rgb) for z in self.zones], SEGMENT_COUNT, self.blend_mode
        )
        return frame[::-1] if self.bottom_up else frame

    async def _async_flush(self) -> None:
        """Every write is a complete frame: the gaps between zones depend on
        all of their neighbours."""
        self._last_write = time.monotonic()
        try:
            if not any(z.on for z in self.zones):
                if self._device_on is not False:
                    await self.lamp.power(False)
                self._device_on = False
                self._calibrated = False
                return

            if not self._device_on:
                await self.lamp.power(True)
                self._device_on = True
            if not self._calibrated:
                # Best effort: the floor lamp answers 04 to this, and the
                # frame must not depend on it.
                try:
                    await self.lamp.global_brightness(100)
                except LampCommandError as err:
                    _LOGGER.debug("global brightness not accepted: %s", err)
                self._calibrated = True
            await self.lamp.write_frame(self.frame(), self.colors_per_packet)
        except WRITE_ERRORS as err:
            _LOGGER.warning("write to %s failed: %s", self.address, err)
            self._calibrated = False
        finally:
            self._last_write = time.monotonic()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        self._debouncer.async_cancel()
