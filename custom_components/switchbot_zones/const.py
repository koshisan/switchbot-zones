"""Constants for the SwitchBot Zones integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "switchbot_zones"

CONF_ADDRESS: Final = "address"
CONF_KEY_ID: Final = "key_id"
CONF_ENCRYPTION_KEY: Final = "encryption_key"
CONF_SOURCE_ENTRY: Final = "source_entry"

CONF_ZONES: Final = "zones"
CONF_BLEND_MODE: Final = "blend_mode"
CONF_COLORS_PER_PACKET: Final = "colors_per_packet"
CONF_BOTTOM_UP: Final = "bottom_up"

# The core SwitchBot integration stores its keys under the same names.
SWITCHBOT_DOMAIN: Final = "switchbot"

SEGMENT_COUNT: Final = 21
DEFAULT_ZONES: Final = "0-2, 9-11, 18-20"
DEFAULT_BLEND_MODE: Final = "oklch"
# Encrypted write = 57 + key id + 2 header bytes + 0F490B + meta + 3 per colour.
# Four colours make 20 bytes, the payload of a write at the default ATT MTU,
# and four is what the SwitchBot app sends.
DEFAULT_COLORS_PER_PACKET: Final = 4
MAX_COLORS_PER_PACKET: Final = 4
# The lamp's segment 0 is at the top. Users count zones from the floor up.
DEFAULT_BOTTOM_UP: Final = True

# Seconds. Bundles the per-zone calls of one scene activation into one frame.
WRITE_DEBOUNCE: Final = 0.15

# Seconds after our own write during which an advertisement saying "off" is
# treated as stale rather than as someone switching the lamp off.
ADVERTISEMENT_GRACE: Final = 10.0

CMD_TURN_ON: Final = "570F490101"
CMD_TURN_OFF: Final = "570F490102"
CMD_BRIGHTNESS: Final = "570F490114{:02X}"
CMD_STEP_MODE: Final = "570F490C01"
CMD_SEGMENT: Final = "570F490B{:02X}{}"
SEGMENT_COMMIT: Final = 0x80
