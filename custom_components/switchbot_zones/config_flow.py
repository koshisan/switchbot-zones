"""Config and options flow for SwitchBot Zones."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    CONF_ADDRESS,
    CONF_BLEND_MODE,
    CONF_COLORS_PER_PACKET,
    CONF_ENCRYPTION_KEY,
    CONF_KEY_ID,
    CONF_SOURCE_ENTRY,
    CONF_ZONES,
    DEFAULT_BLEND_MODE,
    DEFAULT_COLORS_PER_PACKET,
    DEFAULT_ZONES,
    DOMAIN,
    MAX_COLORS_PER_PACKET,
    SEGMENT_COUNT,
    SWITCHBOT_DOMAIN,
)
from .gradient import MODES, parse_zones
from .lamp import FloorLamp

MANUAL = "manual"
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
KEY_ID_RE = re.compile(r"^[0-9a-f]{2}$")
KEY_RE = re.compile(r"^[0-9a-f]{32}$")


class SwitchbotZonesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Take the key from the core SwitchBot integration, or enter it by hand."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SwitchbotZonesOptionsFlow()

    def _switchbot_sources(self) -> dict[str, ConfigEntry]:
        """Core SwitchBot entries that carry an encryption key."""
        return {
            e.entry_id: e
            for e in self.hass.config_entries.async_entries(SWITCHBOT_DOMAIN)
            if e.data.get(CONF_KEY_ID) and e.data.get(CONF_ENCRYPTION_KEY)
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        sources = self._switchbot_sources()
        if not sources:
            return await self.async_step_manual()

        errors: dict[str, str] = {}
        if user_input is not None:
            choice = user_input[CONF_SOURCE_ENTRY]
            if choice == MANUAL:
                return await self.async_step_manual()
            src = sources[choice]
            # A key in the core entry is not proof that it works: it can be
            # stale, and then every command is answered with 04.
            error = await self._async_verify(
                src.data[CONF_ADDRESS].upper(),
                src.data[CONF_KEY_ID],
                src.data[CONF_ENCRYPTION_KEY],
            )
            if error is None:
                return await self._async_create(
                    src.data[CONF_ADDRESS],
                    src.data[CONF_KEY_ID],
                    src.data[CONF_ENCRYPTION_KEY],
                )
            errors["base"] = "invalid_source_key" if error == "invalid_key" else error

        options = {
            entry_id: f"{e.title} ({e.data.get(CONF_ADDRESS, '?')})"
            for entry_id, e in sources.items()
        }
        options[MANUAL] = "Manual"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_SOURCE_ENTRY): vol.In(options)}),
            errors=errors,
        )

    async def _async_verify(self, address: str, key_id: str, key: str) -> str | None:
        """None if the lamp accepts the key, else an error key."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, address, connectable=True
        )
        if ble_device is None:
            return "not_found"
        if not await FloorLamp.verify_encryption_key(ble_device, key_id, key):
            return "invalid_key"
        return None

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            key_id = user_input[CONF_KEY_ID].strip().lower()
            key = user_input[CONF_ENCRYPTION_KEY].strip().lower()
            if not MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            elif not KEY_ID_RE.match(key_id) or not KEY_RE.match(key):
                errors["base"] = "invalid_key_format"
            elif error := await self._async_verify(address, key_id, key):
                errors["base"] = error
            else:
                return await self._async_create(address, key_id, key)

        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_ADDRESS): str,
                        vol.Required(CONF_KEY_ID): str,
                        vol.Required(CONF_ENCRYPTION_KEY): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def _async_create(
        self, address: str, key_id: str, key: str
    ) -> ConfigFlowResult:
        address = address.upper()
        data = {CONF_ADDRESS: address, CONF_KEY_ID: key_id, CONF_ENCRYPTION_KEY: key}
        await self.async_set_unique_id(address)
        # Adding a lamp that already exists replaces its key and reloads it,
        # which is the way to fix a wrong key without losing the entities.
        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(
            title=f"SwitchBot Floor Lamp {address[-5:]}", data=data
        )


class SwitchbotZonesOptionsFlow(OptionsFlow):
    """Zone layout, blend mode and packet size. Applied by reloading the entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                parse_zones(user_input[CONF_ZONES], SEGMENT_COUNT)
            except ValueError:
                errors[CONF_ZONES] = "invalid_zones"
            else:
                user_input[CONF_COLORS_PER_PACKET] = int(
                    user_input[CONF_COLORS_PER_PACKET]
                )
                return self.async_create_entry(data=user_input)

        current = {
            CONF_ZONES: DEFAULT_ZONES,
            CONF_BLEND_MODE: DEFAULT_BLEND_MODE,
            CONF_COLORS_PER_PACKET: DEFAULT_COLORS_PER_PACKET,
            **self.config_entry.options,
            **(user_input or {}),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_ZONES): str,
                        vol.Required(CONF_BLEND_MODE): SelectSelector(
                            SelectSelectorConfig(
                                options=list(MODES),
                                mode=SelectSelectorMode.DROPDOWN,
                                translation_key=CONF_BLEND_MODE,
                            )
                        ),
                        vol.Required(CONF_COLORS_PER_PACKET): NumberSelector(
                            NumberSelectorConfig(
                                min=1,
                                max=MAX_COLORS_PER_PACKET,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                            )
                        ),
                    }
                ),
                current,
            ),
            errors=errors,
        )
