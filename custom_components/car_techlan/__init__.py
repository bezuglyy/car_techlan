"""Car Techlan — распознавание номеров: приём событий и управление устройствами."""
from __future__ import annotations

import json
import logging
import time

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BASE_TOPIC,
    CONF_CAMERAS,
    CONF_COOLDOWN,
    CONF_NOTIFY_KNOWN,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_UNKNOWN,
    DEFAULT_BASE_TOPIC,
    DEFAULT_COOLDOWN,
    DOMAIN,
    EVENT_PLATE,
)
from .control import apply_rules

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button"]

SERVICE_TRIGGER = "trigger_plate"
SERVICE_TRIGGER_MAKE = "trigger_make"
SERVICE_TRIGGER_SCHEMA = vol.Schema({
    vol.Required("plate"): cv.string,
    vol.Optional("camera", default="manual"): cv.string,
    vol.Optional("known", default=None): vol.Any(None, cv.boolean),
    vol.Optional("owner", default=""): cv.string,
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Подписка на MQTT и регистрация служб."""
    hass.data.setdefault(DOMAIN, {})
    data = {**entry.data, **entry.options}
    base = (data.get(CONF_BASE_TOPIC) or DEFAULT_BASE_TOPIC).strip()
    topic = f"{base}/+/plate"
    state = {"last": {}, "last_trigger": 0.0, "count": 0}
    hass.data[DOMAIN][entry.entry_id] = state

    @callback
    def _on_plate(msg) -> None:
        """Обработка события распознавания номера."""
        try:
            payload = json.loads(msg.payload) if msg.payload else {}
        except (ValueError, TypeError):
            payload = {"plate": msg.payload.decode("utf-8", "ignore") if msg.payload else ""}
        if not isinstance(payload, dict):
            payload = {"plate": str(payload)}
        # камера: из топика (alpr/<cam>/plate) или из полезной нагрузки
        parts = msg.topic.split("/")
        cam = parts[-2] if len(parts) >= 3 else "?"
        plate = (payload.get("plate") or "").strip()
        if not plate:
            return
        # фильтр по камерам (пусто = все)
        only = [c.strip() for c in str(data.get(CONF_CAMERAS) or "").split(",") if c.strip()]
        if only and cam not in only:
            return
        known = payload.get("known")
        if known is None:
            known = bool(payload.get("owner"))
        payload.update({"camera": cam, "known": bool(known), "topic": msg.topic})
        state["last"] = payload
        state["count"] = state.get("count", 0) + 1
        async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}", payload)
        hass.bus.async_fire(EVENT_PLATE, payload)
        hass.async_create_task(_react(hass, entry, data, state, payload))

    async def _react(hass: HomeAssistant, entry: ConfigEntry, data: dict, state: dict, payload: dict) -> None:
        """Правила управления + уведомления, с защитой от дребезга."""
        now = time.time()
        cooldown = float(data.get(CONF_COOLDOWN) or DEFAULT_COOLDOWN)
        if now - float(state.get("last_trigger") or 0) < cooldown:
            _LOGGER.debug("car_techlan: пауза %s с, пропуск", cooldown)
            return
        known = bool(payload.get("known"))
        touched = await apply_rules(hass, data, payload, known)
        if touched:
            state["last_trigger"] = now
        # уведомления
        svc = (data.get(CONF_NOTIFY_SERVICE) or "").strip()
        want = (known and data.get(CONF_NOTIFY_KNOWN)) or ((not known) and data.get(CONF_NOTIFY_UNKNOWN))
        if svc and want:
            title = "Свой номер" if known else "Неизвестный номер"
            who = payload.get("owner") or ""
            body = f"{payload.get('plate')} · {payload.get('camera')}" + (f" · {who}" if who else "")
            try:
                dom, _, name = svc.partition(".")
                await hass.services.async_call(dom or "persistent_notification",
                                               name or "create",
                                               {"title": title, "message": body},
                                               blocking=False)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("car_techlan: уведомление не отправлено: %s", err)

    # отдельная подписка: марка (приходит позже номера, из потока классификации)
    @callback
    def _on_make(msg) -> None:
        try:
            payload = json.loads(msg.payload) if msg.payload else {}
        except (ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        parts = msg.topic.split("/")
        cam = parts[-2] if len(parts) >= 3 else "?"
        mk = (payload.get("make") or "").strip()
        if not mk:
            return
        payload.update({"camera": cam, "ts": payload.get("ts") or ""})
        state["last_make"] = payload
        async_dispatcher_send(hass, f"{DOMAIN}_make_{entry.entry_id}", payload)
        hass.bus.async_fire(f"{DOMAIN}_make", payload)
        _LOGGER.info("car_techlan: марка %s (%s)", mk, payload.get("plate") or "без номера")

    # чёрный список
    @callback
    def _on_black(msg) -> None:
        try:
            payload = json.loads(msg.payload) if msg.payload else {}
        except (ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        parts = msg.topic.split("/")
        payload["camera"] = parts[-2] if len(parts) >= 3 else "?"
        state["last_blacklist"] = payload
        hass.bus.async_fire(f"{DOMAIN}_blacklist", payload)
        async_dispatcher_send(hass, f"{DOMAIN}_black_{entry.entry_id}", payload)
        _LOGGER.warning("car_techlan: ЧЁРНЫЙ СПИСОК %s", payload.get("plate"))

    unsub = await mqtt.async_subscribe(hass, topic, _on_plate, qos=0)
    unsub_make = await mqtt.async_subscribe(hass, f"{base}/+/make", _on_make, qos=0)
    unsub_black = await mqtt.async_subscribe(hass, f"{base}/+/blacklist", _on_black, qos=0)
    hass.data[DOMAIN][entry.entry_id]["unsub"] = unsub
    hass.data[DOMAIN][entry.entry_id]["unsub_make"] = unsub_make
    hass.data[DOMAIN][entry.entry_id]["unsub_black"] = unsub_black
    _LOGGER.info("car_techlan: подписка на %s", topic)

    # служба ручного запуска (для тестов и автоматизаций)
    async def _service_trigger(call) -> None:
        p = dict(call.data)
        cam = p.get("camera") or "manual"
        known = p.get("known")
        if known is None:
            known = bool(p.get("owner"))
        payload = {"plate": p["plate"], "camera": cam, "known": bool(known),
                   "owner": p.get("owner", ""), "manual": True}
        state["last"] = payload
        state["count"] = state.get("count", 0) + 1
        async_dispatcher_send(hass, f"{DOMAIN}_update_{entry.entry_id}", payload)
        await _react(hass, entry, data, state, payload)
        hass.bus.async_fire(EVENT_PLATE, payload)

    async def _service_make(call) -> None:
        """Ручная установка марки (для тестов/интеграций)."""
        p = dict(call.data)
        payload = {"make": p.get("make", ""), "plate": p.get("plate", ""),
                   "confidence": p.get("confidence", 0), "camera": p.get("camera", "manual"),
                   "ts": ""}
        state["last_make"] = payload
        async_dispatcher_send(hass, f"{DOMAIN}_make_{entry.entry_id}", payload)
        hass.bus.async_fire(f"{DOMAIN}_make", payload)

    if not hass.services.has_service(DOMAIN, SERVICE_TRIGGER_MAKE):
        hass.services.async_register(DOMAIN, SERVICE_TRIGGER_MAKE, _service_make, schema=vol.Schema({
            vol.Required("make"): cv.string,
            vol.Optional("plate", default=""): cv.string,
            vol.Optional("camera", default="manual"): cv.string,
            vol.Optional("confidence", default=0): vol.Coerce(float),
        }, extra=vol.ALLOW_EXTRA))

    if not hass.services.has_service(DOMAIN, SERVICE_TRIGGER):
        hass.services.async_register(DOMAIN, SERVICE_TRIGGER, _service_trigger,
                                     schema=SERVICE_TRIGGER_SCHEMA)

    # --- сервисы управления сервером Car-Techlan (аддитивно) ---
    def _srv(data=None, over: dict | None = None):
        from .server_api import CarTechlanServer
        from .const import (CONF_SERVER_HOST, CONF_SERVER_PORT, CONF_SERVER_KEY, CONF_SERVER_SSL,
                            DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
        d = dict(data or {})
        host = (over or {}).get("host") or d.get(CONF_SERVER_HOST) or DEFAULT_SERVER_HOST
        port = (over or {}).get("port") or d.get(CONF_SERVER_PORT) or DEFAULT_SERVER_PORT
        return CarTechlanServer(host, int(port), d.get(CONF_SERVER_KEY) or "", bool(d.get(CONF_SERVER_SSL)))

    async def _fire(name: str, res) -> None:
        code, payload = res
        hass.bus.async_fire(f"{DOMAIN}_{name}", {"status": code, "data": payload})

    async def _svc_checks(call):
        _fire_task = await _srv(entry.data, {"host": call.data.get("host"), "port": call.data.get("port")}).get_checks()
        await _fire("server_checks", _fire_task)

    async def _svc_incidents(call):
        await _fire("server_incidents", await _srv(entry.data).get_incidents())

    async def _svc_restart_web(call):
        await _fire("server_restart_web", await _srv(entry.data).restart_web())

    async def _svc_restart_service(call):
        await _fire("server_restart_service", await _srv(entry.data).restart_service())

    async def _svc_clear_tts(call):
        await _fire("server_clear_tts_cache", await _srv(entry.data).clear_tts_cache(int(call.data.get("days") or 30)))

    async def _svc_camera_restart(call):
        await _fire("server_camera_restart", await _srv(entry.data).camera_restart(str(call.data.get("camera") or "")))

    if not hass.services.has_service(DOMAIN, "server_checks"):
        hass.services.async_register(DOMAIN, "server_checks", _svc_checks,
                                     schema=vol.Schema({vol.Optional("host"): cv.string,
                                                        vol.Optional("port"): cv.positive_int}, extra=vol.ALLOW_EXTRA))
    if not hass.services.has_service(DOMAIN, "server_incidents"):
        hass.services.async_register(DOMAIN, "server_incidents", _svc_incidents)
    if not hass.services.has_service(DOMAIN, "server_restart_web"):
        hass.services.async_register(DOMAIN, "server_restart_web", _svc_restart_web)
    if not hass.services.has_service(DOMAIN, "server_restart_service"):
        hass.services.async_register(DOMAIN, "server_restart_service", _svc_restart_service)
    if not hass.services.has_service(DOMAIN, "server_clear_tts_cache"):
        hass.services.async_register(DOMAIN, "server_clear_tts_cache", _svc_clear_tts,
                                     schema=vol.Schema({vol.Optional("days"): vol.Coerce(int)}, extra=vol.ALLOW_EXTRA))
    if not hass.services.has_service(DOMAIN, "server_camera_restart"):
        hass.services.async_register(DOMAIN, "server_camera_restart", _svc_camera_restart,
                                     schema=vol.Schema({vol.Required("camera"): cv.string}, extra=vol.ALLOW_EXTRA))

    # ================= по-камерные события и действия (аддитивно) =================
    from .const import CONF_CAMERA_ACTIONS as _CCA

    def _slug(s: str) -> str:
        import re as _re
        return _re.sub(r"[^a-z0-9_]+", "_", (s or "camera").lower()).strip("_") or "camera"

    def _cam_map() -> dict:
        src = dict(entry.data or {})
        src.update(entry.options or {})
        m = src.get(_CCA) or {}
        return m if isinstance(m, dict) else {}

    _last_cam_action: dict = {}

    async def _apply_action(action: str, devices, hold: float = 1.0) -> None:
        import asyncio
        act = (action or "").strip().lower()
        if act in ("", "none"):
            return
        for ent in (devices or []):
            try:
                if act == "open":
                    await hass.services.async_call("cover", "open_cover", {"entity_id": ent}, blocking=False)
                elif act == "close":
                    await hass.services.async_call("cover", "close_cover", {"entity_id": ent}, blocking=False)
                elif act == "toggle":
                    await hass.services.async_call("homeassistant", "toggle", {"entity_id": ent}, blocking=False)
                elif act == "turn_on":
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": ent}, blocking=False)
                elif act == "turn_off":
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": ent}, blocking=False)
                elif act == "impulse":
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": ent}, blocking=False)

                    async def _off(e=ent, h=hold):
                        await asyncio.sleep(max(0.2, float(h or 1)))
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": e}, blocking=False)

                    hass.async_create_task(_off())
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("car_techlan: действие %s для %s — %s", act, ent, err)

    async def _on_plate_camera(event) -> None:
        import time as _t
        d = dict(getattr(event, "data", None) or {})
        cam = str(d.get("camera") or "manual")
        # 1) отдельное событие на камеру: car_techlan_plate_<камера>
        hass.bus.async_fire(f"{DOMAIN}_plate_{_slug(cam)}", d)
        # 2) действие, заданное для этой камеры
        cfg = _cam_map().get(cam)
        if not isinstance(cfg, dict):
            return
        known = bool(d.get("known"))
        act = cfg.get("action_known" if known else "action_unknown") or cfg.get("action")
        devs = cfg.get("devices_known" if known else "devices_unknown") or cfg.get("devices") or []
        cd = float(cfg.get("cooldown") or 0)
        key = (cam, known)
        if cd > 0 and (_t.time() - _last_cam_action.get(key, 0.0)) < cd:
            return
        _last_cam_action[key] = _t.time()
        await _apply_action(act, devs, cfg.get("hold_seconds") or 1)
        _LOGGER.warning("car_techlan: камера %s -> действие %s (номер %s, свой=%s)", cam, act, d.get("plate"), known)

    unsub_cam = hass.bus.async_listen(f"{DOMAIN}_plate", _on_plate_camera)
    entry.async_on_unload(unsub_cam)

    async def _svc_set_camera_action(call) -> None:
        cd = dict(call.data or {})
        cam = str(cd.pop("camera", "") or "").strip()
        if not cam:
            return
        cur = dict(_cam_map())
        cur[cam] = cd
        opts = dict(entry.options or {})
        opts[_CCA] = cur
        hass.config_entries.async_update_entry(entry, options=opts)
        hass.bus.async_fire(f"{DOMAIN}_camera_action_set", {"camera": cam, "config": cd})
        _LOGGER.warning("car_techlan: действия для камеры %s заданы: %s", cam, cd)

    if not hass.services.has_service(DOMAIN, "set_camera_action"):
        hass.services.async_register(DOMAIN, "set_camera_action", _svc_set_camera_action, schema=vol.Schema({
            vol.Required("camera"): cv.string,
            vol.Optional("action"): cv.string,
            vol.Optional("action_known"): cv.string,
            vol.Optional("action_unknown"): cv.string,
            vol.Optional("devices"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("devices_known"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("devices_unknown"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("cooldown"): vol.Coerce(float),
            vol.Optional("hold_seconds"): vol.Coerce(float),
        }, extra=vol.ALLOW_EXTRA))
    # ================= /по-камерные события и действия =================

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Перечитать настройки без перезапуска HA."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    for key in ("unsub", "unsub_make", "unsub_black"):
        if state.get(key):
            try:
                state[key]()
            except Exception:  # noqa: BLE001
                pass
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
