"""Thin layer over PySwitchbot that writes full segment frames."""

from __future__ import annotations

import logging

from switchbot import SwitchbotDevice, SwitchbotModel, SwitchbotRgbicLight

from .const import (
    CMD_BRIGHTNESS,
    CMD_SEGMENT,
    CMD_STEP_MODE,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    SEGMENT_COMMIT,
)
from .gradient import RGB

_LOGGER = logging.getLogger(__name__)


class LampCommandError(Exception):
    """The lamp answered, but not with success."""


class FloorLamp(SwitchbotRgbicLight):
    """RGBICWW Floor Lamp that only talks when we ask it to."""

    _model = SwitchbotModel.RGBICWW_FLOOR_LAMP

    def update_from_advertisement(self, advertisement) -> None:
        # The sequence-device base class connects and polls on every state
        # change it sees. The core integration already does that; we only want
        # the fresh BLEDevice and the cached isOn.
        SwitchbotDevice.update_from_advertisement(self, advertisement)

    async def _command(self, key: str) -> None:
        result = await self._send_command(key)
        if not result or result[0] != 1:
            raise LampCommandError(
                f"{key} -> {result.hex() if result else 'no response'}"
            )

    async def power(self, on: bool) -> None:
        await self._command(CMD_TURN_ON if on else CMD_TURN_OFF)

    async def global_brightness(self, percent: int) -> None:
        await self._command(CMD_BRIGHTNESS.format(percent))

    async def write_frame(self, frame: list[RGB], per_packet: int) -> None:
        """Step mode, then every segment. Only the last packet carries the
        commit flag, so the lamp switches to the new frame in one go."""
        await self._command(CMD_STEP_MODE)
        for start in range(0, len(frame), per_packet):
            chunk = frame[start : start + per_packet]
            last = start + per_packet >= len(frame)
            meta = start | (SEGMENT_COMMIT if last else 0)
            colors = "".join(f"{r:02X}{g:02X}{b:02X}" for r, g, b in chunk)
            await self._command(CMD_SEGMENT.format(meta, colors))
        _LOGGER.debug("%s: wrote %d segments", self.name, len(frame))
