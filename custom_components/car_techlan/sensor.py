"""Сенсоры Car Techlan: последний распознанный номер."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTR_LAST = [
    "plate", "plate_latin", "camera", "known", "owner", "confidence",
    "votes", "ts", "valid_format",
    "color", "vehicle_type", "make",
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    _LOGGER.warning("car_techlan: платформа sensor — создаю сущности для %s", entry.entry_id)
    try:
        ents = [CarTechlanLastPlate(hass, entry), CarTechlanLastMake(hass, entry)]
        async_add_entities(ents, update_before_add=False)
        # сенсоры сервера (выбор по умолчанию — все; лишние можно отключить в HA)
        try:
            from .const import (CONF_SERVER_HOST, CONF_SERVER_PORT, CONF_SERVER_KEY,
                                DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
            d = dict(entry.data or {}); o = dict(entry.options or {})
            host = o.get(CONF_SERVER_HOST) or d.get(CONF_SERVER_HOST) or DEFAULT_SERVER_HOST
            port = int(o.get(CONF_SERVER_PORT) or d.get(CONF_SERVER_PORT) or DEFAULT_SERVER_PORT)
            key = o.get(CONF_SERVER_KEY) or d.get(CONF_SERVER_KEY) or ""
            await async_setup_server_sensors(hass, entry, async_add_entities, host, port, key)
        except Exception as err2:  # noqa: BLE001
            _LOGGER.error("car_techlan: сенсоры сервера не созданы: %s", err2, exc_info=True)
        _LOGGER.warning("car_techlan: сущности добавлены: %s", [e.unique_id for e in ents])
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("car_techlan: ошибка создания сущности: %s", err, exc_info=True)


class CarTechlanLastMake(SensorEntity):
    """Последняя распознанная марка автомобиля."""

    _attr_has_entity_name = True
    _attr_name = "Последняя марка"
    _attr_icon = "mdi:car-info"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_last_make"
        self._payload: dict = {}
        host = (entry.data or {}).get("host", "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Car Techlan",
            manufacturer="techlan", model="Распознавание автомобильных номеров",
            configuration_url=(f"http://{host}" if host else None))

    @property
    def native_value(self):
        return self._payload.get("make") or None

    @property
    def extra_state_attributes(self) -> dict:
        return {k: self._payload.get(k) for k in ("make", "plate", "camera", "confidence", "ts")
                if k in self._payload}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, f"{DOMAIN}_make_{self._entry.entry_id}", self._update))

    @callback
    def _update(self, payload: dict) -> None:
        self._payload = dict(payload)
        self.async_write_ha_state()


class CarTechlanLastPlate(SensorEntity):
    """Последний распознанный номер (со всеми атрибутами события)."""

    _attr_has_entity_name = True
    _attr_name = "Последний номер"
    _attr_icon = "mdi:car"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_last_plate"
        self._payload: dict = {}
        host = (entry.data or {}).get("host", "")
        port = (entry.data or {}).get("port", 1883)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Car Techlan",
            manufacturer="techlan",
            model="Распознавание автомобильных номеров",
            configuration_url=(f"http://{host}" if host else None),
        )

    @property
    def native_value(self):
        return self._payload.get("plate") or None

    @property
    def extra_state_attributes(self) -> dict:
        a = {k: self._payload.get(k) for k in ATTR_LAST if k in self._payload}
        st = (self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id) or {})
        a["всего_событий"] = st.get("count", 0)
        a["владелец"] = self._payload.get("owner") or ""
        a["свой_номер"] = bool(self._payload.get("known"))
        mk = (self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id) or {}).get("last_make") or {}
        if mk.get("make"):
            a["марка"] = mk.get("make")
        return a

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, f"{DOMAIN}_update_{self._entry.entry_id}", self._update))

    @callback
    def _update(self, payload: dict) -> None:
        self._payload = dict(payload)
        self.async_write_ha_state()

# ================= сенсоры сервера Car-Techlan (опрос /api/all) =================
SERVER_SIGNAL = "car_techlan_server_data"


def _checks_problems(d):
    """Из /api/checks достаём число проблем (устойчиво к разным форматам)."""
    c = (d or {}).get("_checks")
    if c is None:
        return None
    if isinstance(c, dict):
        for k in ("problems", "fail", "errors", "failed"):
            if isinstance(c.get(k), int):
                return c[k]
        for k in ("checks", "items"):
            if isinstance(c.get(k), list):
                return sum(1 for it in c[k] if isinstance(it, dict) and (it.get("ok") is False or it.get("status") == "fail"))
        return None
    if isinstance(c, list):
        return sum(1 for it in c if isinstance(it, dict) and (it.get("ok") is False or it.get("status") == "fail"))
    return None


def _cnt_known(plates, known=True):
    n = 0
    for p in (plates or []):
        if (p or {}).get("kind", "plate") != "plate":
            continue
        if bool((p or {}).get("known")) is known:
            n += 1
    return n


# ключ -> (имя, ед., класс, извлечение значения)
SERVER_SENSORS = {
    "server_state":      ("Состояние сервера", None, None, lambda d: "online" if d else "offline"),
    "server_version":    ("Версия сервера", None, None, lambda d: (d.get("_health") or {}).get("version") or (d.get("_health") or {}).get("ver") or ""),
    "frames":            ("Кадры (сессия)", "кадр", "total_increasing", lambda d: ((d.get("status") or {}).get("frames"))),
    "plates":            ("Распознано номеров", "шт", "total_increasing", lambda d: ((d.get("stats") or {}).get("total"))),
    "unknown":           ("Чужих номеров", "шт", None, lambda d: _cnt_known(d.get("plates"), False)),
    "rejected":          ("Отбраковано чтений", "шт", None, lambda d: sum(int((d.get("status") or {}).get(k) or 0) for k in ("rej_conf", "rej_len", "rej_novote"))),
    "lookup_known":      ("Реестр: подтверждено", "шт", None, lambda d: ((d.get("stats") or {}).get("lookup_known"))),
    "lookup_region":     ("Реестр: добран регион", "шт", None, lambda d: ((d.get("stats") or {}).get("lookup_region"))),
    "lookup_core":       ("Реестр: исправлен регион", "шт", None, lambda d: ((d.get("stats") or {}).get("lookup_core"))),
    "cameras_total":     ("Камер всего", "шт", None, lambda d: len(((d.get("config") or {}).get("cameras") or {}))),
    "cameras_online":    ("Камер онлайн", "шт", None, lambda d: len(d.get("cameras") or {}) or len(((d.get("config") or {}).get("cameras") or {}))),
    "errors":            ("Ошибок распознавания", "шт", None, lambda d: ((d.get("status") or {}).get("errors"))),
    "disk_free":         ("Свободно на диске", "ГБ", None, lambda d: ((d.get("system") or {}).get("disk_free_gb"))),
    "gpu_util":          ("GPU занятость", "%", None, lambda d: ((((d.get("gpu") or {}).get("gpus") or [{}])[0]).get("util"))),
    "ram_used":          ("RAM занято", "%", None, lambda d: ((d.get("system") or {}).get("mem_pct"))),
    "last_plate":        ("Последний номер", None, None, lambda d: ((d.get("plates") or [{}])[0].get("plate"))),
    "server_service":    ("Служба Car-Techlan-Server", None, None, lambda d: ((d.get("_srv_status") or {}).get("state") or (d.get("_srv_status") or {}).get("mode") or "unknown")),
    "checks_problems":   ("Проверки сервера: проблем", "шт", None, _checks_problems),
}


class CarTechlanServerSensor(SensorEntity):
    """Сенсор значения с сервера (данные приходят от поллера через диспетчер)."""

    _attr_has_entity_name = True

    def __init__(self, hass, entry, key: str, spec) -> None:
        self.hass = hass
        self._entry = entry
        self._key = key
        self._name, self._unit, self._cls, self._get = spec
        self._attr_name = self._name
        self._attr_unique_id = f"{entry.entry_id}_srv_{key}"
        self._attr_native_unit_of_measurement = self._unit
        if self._cls:
            try:
                from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
                self._attr_device_class = SensorDeviceClass.ENUM if False else None
                self._attr_state_class = getattr(SensorStateClass, "TOTAL_INCREASING", None) if self._cls == "total_increasing" else None
            except Exception:
                pass
        self._state = None
        self._attrs = {}

    def _domain(self):
        from .const import DOMAIN as _D
        return _D

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(self._domain(), self._entry.entry_id)}, name="Car Techlan")

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attrs

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SERVER_SIGNAL, self._update)
        )
        data = (self.hass.data.get(self._domain(), {}).get(self._entry.entry_id) or {}).get("server_data")
        if data:
            self._update(data)

    @callback
    def _update(self, data: dict) -> None:
        try:
            val = self._get(data or {})
        except Exception:
            val = None
        if val is None:
            return
        self._state = val
        st = (data or {}).get("status") or {}
        _sv = (data or {}).get("_srv_status") or {}
        self._attrs = {"камер": len(((data or {}).get("config") or {}).get("cameras") or {}),
                       "ошибок": st.get("errors"), "кадров": st.get("frames"),
                       "служба_установлена": _sv.get("installed"), "режим": _sv.get("mode"),
                       "задача": _sv.get("taskName") or _sv.get("task")}
        self.async_write_ha_state()


async def _server_poller(hass, entry, host, port, api_key):
    """Раз в N секунд опрашивает /api/all (+ /api/health) и рассылает данные сущностям."""
    from .server_api import CarTechlanServer
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    srv = CarTechlanServer(host, port, api_key)
    n = 0
    while True:
        try:
            _, allj = await srv.get_all()
            if isinstance(allj, dict):
                _, hj = await srv.get_health()
                _, sj = await srv.get_service_status()
                _, cj = await srv.get_checks()
                allj["_srv_status"] = sj
                allj["_checks"] = cj
                if isinstance(hj, dict):
                    allj["_health"] = hj
                hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["server_data"] = allj
                async_dispatcher_send(hass, SERVER_SIGNAL, allj)
                n += 1
                if n in (1, 10):
                    _LOGGER.warning("car_techlan: сервер отвечает, сущностей сервера: %d (опрос #%d)", len(SERVER_SENSORS), n)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("car_techlan: опрос сервера не удался: %s", err)
        await asyncio.sleep(max(5, int((entry.options or {}).get("server_poll_seconds", 15))))


async def async_setup_server_sensors(hass, entry, async_add_entities, host, port, api_key):
    ents = [CarTechlanServerSensor(hass, entry, k, v) for k, v in SERVER_SENSORS.items()]
    async_add_entities(ents, update_before_add=False)
    _LOGGER.warning("car_techlan: сенсоры сервера созданы: %s", [e.unique_id for e in ents][:6])
    hass.async_create_task(_server_poller(hass, entry, host, port, api_key))
