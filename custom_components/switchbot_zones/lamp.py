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

    async def _command(self, key: str) -> int:
        """Send one command; no answer at all is an error, the status byte is
        returned for the caller to judge."""
        result = await self._send_command(key)
        if not result:
            raise LampCommandError(f"{key} -> no response")
        return result[0]

    async def _checked(self, key: str) -> None:
        if (status := await self._command(key)) != 1:
            raise LampCommandError(f"{key} -> status {status:02x}")

    async def power(self, on: bool) -> None:
        await self._checked(CMD_TURN_ON if on else CMD_TURN_OFF)

    async def global_brightness(self, percent: int) -> None:
        await self._checked(CMD_BRIGHTNESS.format(percent))

    async def write_frame(self, frame: list[RGB], per_packet: int) -> None:
        """Step mode, then every segment, each packet with the commit flag.

        Once the lamp is already in step mode it only shows packets that carry
        the flag themselves; unflagged ones are acknowledged and dropped.

        A status other than 01 does not abort the frame: whatever the lamp
        says to each packet is collected and reported once."""
        sent: list[tuple[str, int]] = [
            (CMD_STEP_MODE, await self._command(CMD_STEP_MODE))
        ]
        for start in range(0, len(frame), per_packet):
            chunk = frame[start : start + per_packet]
            meta = start | SEGMENT_COMMIT
            colors = "".join(f"{r:02X}{g:02X}{b:02X}" for r, g, b in chunk)
            key = CMD_SEGMENT.format(meta, colors)
            sent.append((key, await self._command(key)))

        rejected = [f"{key} -> {status:02x}" for key, status in sent if status != 1]
        if rejected:
            _LOGGER.warning(
                "%s: %d of %d packets not acknowledged: %s",
                self.name,
                len(rejected),
                len(sent),
                ", ".join(rejected),
            )
        else:
            _LOGGER.debug("%s: wrote %d segments", self.name, len(frame))
