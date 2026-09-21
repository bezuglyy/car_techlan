"""Кнопки управления Car-Techlan-Server (управление сервером из HA)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (DOMAIN, CONF_SERVER_HOST, CONF_SERVER_PORT, CONF_SERVER_KEY,
                    DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
from .server_api import CarTechlanServer

_LOGGER = logging.getLogger(__name__)


def _srv(entry: ConfigEntry) -> CarTechlanServer:
    d = dict(entry.data or {}); o = dict(entry.options or {})
    host = o.get(CONF_SERVER_HOST) or d.get(CONF_SERVER_HOST) or DEFAULT_SERVER_HOST
    port = int(o.get(CONF_SERVER_PORT) or d.get(CONF_SERVER_PORT) or DEFAULT_SERVER_PORT)
    return CarTechlanServer(host, port, o.get(CONF_SERVER_KEY) or d.get(CONF_SERVER_KEY) or "")


class CarTechlanButton(ButtonEntity):
    """Кнопка, вызывающая действие на сервере."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str, action, icon: str = "mdi:cog") -> None:
        self.hass = hass
        self._entry = entry
        self._action = action
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_btn_{key}"

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)}, name="Car Techlan")

    async def async_press(self) -> None:
        try:
            code, payload = await self._action(_srv(self._entry))
            self.hass.bus.async_fire(f"{DOMAIN}_button", {"button": self._attr_name, "status": code, "data": payload})
            _LOGGER.warning("car_techlan: кнопка «%s» -> HTTP %s", self._attr_name, code)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("car_techlan: кнопка «%s» ошибка: %s", self._attr_name, err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    ents = [
        CarTechlanButton(hass, entry, "restart_web", "Перезапустить веб-панель", lambda s: s.restart_web(), "mdi:web-refresh"),
        CarTechlanButton(hass, entry, "restart_service", "Перезапустить службу распознавания", lambda s: s.restart_service(), "mdi:restart-alert"),
        CarTechlanButton(hass, entry, "clear_tts", "Очистить кэш TTS (30 дней)", lambda s: s.clear_tts_cache(30), "mdi:broom"),
        CarTechlanButton(hass, entry, "checks", "Проверки сервера", lambda s: s.get_checks(), "mdi:clipboard-check"),
        CarTechlanButton(hass, entry, "incidents", "Инциденты сервера", lambda s: s.get_incidents(), "mdi:alert-outline"),
    ]
    async_add_entities(ents, update_before_add=False)
    _LOGGER.warning("car_techlan: кнопки управления созданы: %s", [e.unique_id for e in ents])
