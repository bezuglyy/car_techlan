"""Настройка интеграции Car Techlan: подключение + выбор устройств управления."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COND_DAYS,
    CONF_COND_PLATES,
    CONF_COND_TIME_FROM,
    CONF_COND_TIME_TO,
    DAYS,
    ACTIONS,
    ACTIONS_KNOWN,
    ACTIONS_UNKNOWN,
    CONF_ACTION_KNOWN,
    CONF_ACTION_UNKNOWN,
    CONF_BASE_TOPIC,
    CONF_CAMERAS,
    CONF_COOLDOWN,
    CONF_DEVICES_KNOWN,
    CONF_DEVICES_UNKNOWN,
    CONF_HOLD_SECONDS,
    CONF_HOST,
    CONF_NOTIFY_KNOWN,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_UNKNOWN,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_BASE_TOPIC,
    DEFAULT_COOLDOWN,
    DEFAULT_HOLD_SECONDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# устройства, которыми разрешено управлять
CONTROL_DOMAINS = ["switch", "cover", "light", "input_boolean", "script", "scene", "button"]


def _devices_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=CONTROL_DOMAINS, multiple=True)
    )


class CarTechlanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Первичная настройка: подключение к MQTT-брокеру."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            if not host:
                errors["base"] = "no_host"
            else:
                await self.async_set_unique_id(f"{host}:{user_input.get(CONF_PORT)}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Car Techlan ({host})",
                    data=user_input,
                    options={
                        CONF_DEVICES_KNOWN: [],
                        CONF_ACTION_KNOWN: "open",
                        CONF_DEVICES_UNKNOWN: [],
                        CONF_ACTION_UNKNOWN: "none",
                        CONF_HOLD_SECONDS: DEFAULT_HOLD_SECONDS,
                        CONF_COOLDOWN: DEFAULT_COOLDOWN,
                        CONF_CAMERAS: "",
                    },
                )
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_USERNAME, default=""): str,
            vol.Optional(CONF_PASSWORD, default=""): str,
            vol.Optional(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        # HA 2026.x: OptionsFlow создаётся без аргументов, config_entry доступен как self.config_entry
        return CarTechlanOptionsFlow()


class CarTechlanOptionsFlow(config_entries.OptionsFlow):
    """Настройки управления: какие устройства и при каком условии активировать."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        opts = dict(self.config_entry.options or {})
        if user_input is not None:
            data = dict(opts)
            data.update(user_input)
            return self.async_create_entry(title="", data=data)

        def d(key, default):
            return opts.get(key, default)

        schema = vol.Schema({
            vol.Optional(CONF_CAMERAS, default=d(CONF_CAMERAS, "")): str,
            # --- свои номера ---
            vol.Optional(CONF_DEVICES_KNOWN, default=d(CONF_DEVICES_KNOWN, [])): _devices_selector(),
            vol.Optional(CONF_ACTION_KNOWN, default=d(CONF_ACTION_KNOWN, "open")):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=ACTIONS_KNOWN, mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="action_known")),
            # --- неизвестные номера ---
            vol.Optional(CONF_DEVICES_UNKNOWN, default=d(CONF_DEVICES_UNKNOWN, [])): _devices_selector(),
            vol.Optional(CONF_ACTION_UNKNOWN, default=d(CONF_ACTION_UNKNOWN, "none")):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=ACTIONS_UNKNOWN, mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="action_unknown")),
            # --- поведение ---
            vol.Optional(CONF_HOLD_SECONDS, default=d(CONF_HOLD_SECONDS, DEFAULT_HOLD_SECONDS)):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=0.1, max=30, step=0.1, mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="с")),
            vol.Optional(CONF_COOLDOWN, default=d(CONF_COOLDOWN, DEFAULT_COOLDOWN)):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=0, max=3600, step=5, mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="с")),
            # --- расширенные условия ---
            vol.Optional(CONF_COND_DAYS, default=d(CONF_COND_DAYS, [])):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[{"value": str(i), "label": n} for i, n in enumerate(DAYS)],
                    multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_COND_TIME_FROM, default=d(CONF_COND_TIME_FROM, "")): str,
            vol.Optional(CONF_COND_TIME_TO, default=d(CONF_COND_TIME_TO, "")): str,
            vol.Optional(CONF_COND_PLATES, default=d(CONF_COND_PLATES, [])):
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[], multiple=True, custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN)),
            # --- уведомления ---
            vol.Optional(CONF_NOTIFY_SERVICE, default=d(CONF_NOTIFY_SERVICE, "")): str,
            vol.Optional(CONF_NOTIFY_KNOWN, default=d(CONF_NOTIFY_KNOWN, False)): bool,
            vol.Optional(CONF_NOTIFY_UNKNOWN, default=d(CONF_NOTIFY_UNKNOWN, True)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
