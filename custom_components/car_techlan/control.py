"""Выполнение действий на выбранных устройствах."""
from __future__ import annotations

import asyncio
import logging

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_COND_DAYS,
    CONF_COND_PLATES,
    CONF_COND_TIME_FROM,
    CONF_COND_TIME_TO,
    CONF_ACTION_KNOWN,
    CONF_ACTION_UNKNOWN,
    CONF_COOLDOWN,
    CONF_DEVICES_KNOWN,
    CONF_DEVICES_UNKNOWN,
    CONF_HOLD_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# какое действие в какую службу HA превращается
_SERVICE = {
    "open": ("cover", "open_cover"),
    "close": ("cover", "close_cover"),
    "toggle": ("homeassistant", "toggle"),
    "turn_on": ("homeassistant", "turn_on"),
    "turn_off": ("homeassistant", "turn_off"),
}


async def _call(hass, entity_id: str, action: str, hold: float) -> None:
    """Выполнить действие над одной сущностью."""
    if action == "none":
        return
    if action == "impulse":
        # импульс: включить -> пауза -> выключить
        await hass.services.async_call("homeassistant", "turn_on",
                                       {"entity_id": entity_id}, blocking=False)
        await asyncio.sleep(max(0.1, float(hold)))
        await hass.services.async_call("homeassistant", "turn_off",
                                       {"entity_id": entity_id}, blocking=False)
        return
    dom, svc = _SERVICE.get(action, (None, None))
    if not dom:
        _LOGGER.warning("car_techlan: неизвестное действие %s", action)
        return
    try:
        await hass.services.async_call(dom, svc, {"entity_id": entity_id}, blocking=False)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("car_techlan: не удалось %s для %s: %s", action, entity_id, err)


def _norm(p: str) -> str:
    return "".join(ch for ch in str(p or "").upper() if ch.isalnum())


def conditions_ok(opts: dict, plate: dict) -> tuple[bool, str]:
    """Проверить расширенные условия: дни недели, время, номера.

    Возвращает (разрешено, причина_отказа).
    """
    import datetime as _dt
    now = _dt.datetime.now()

    # 1. дни недели
    days = opts.get(CONF_COND_DAYS) or []
    if days:
        try:
            wd = now.weekday()          # 0 = понедельник
            if wd not in [int(d) for d in days]:
                return False, f"день недели ({wd}) не разрешён"
        except Exception:
            pass

    # 2. время (поддерживает переход через полночь, напр. 22:00–06:00)
    tf = str(opts.get(CONF_COND_TIME_FROM) or "").strip()
    tt = str(opts.get(CONF_COND_TIME_TO) or "").strip()
    if tf and tt:
        try:
            def _m(x):
                h, _, m = x.partition(":")
                return int(h) * 60 + int(m or 0)
            cur = now.hour * 60 + now.minute
            a, b = _m(tf), _m(tt)
            inside = (a <= cur <= b) if a <= b else (cur >= a or cur <= b)
            if not inside:
                return False, f"время {now:%H:%M} вне {tf}–{tt}"
        except Exception:
            pass

    # 3. номера
    want = [x for x in (opts.get(CONF_COND_PLATES) or []) if str(x).strip()]
    if want:
        cur = _norm(plate.get("plate"))
        if not any(_norm(w) in cur or cur in _norm(w) for w in want if _norm(w)):
            return False, "номер не в списке условий"

    return True, ""


async def apply_rules(hass, opts: dict, plate: dict, known: bool) -> int:
    """Применить правила управления. Возвращает число затронутых устройств."""
    ok, why = conditions_ok(opts, plate)
    if not ok:
        _LOGGER.info("car_techlan: условия не выполнены (%s) — действие пропущено", why)
        return 0
    if known:
        devices = opts.get(CONF_DEVICES_KNOWN) or []
        action = opts.get(CONF_ACTION_KNOWN, "open")
    else:
        devices = opts.get(CONF_DEVICES_UNKNOWN) or []
        action = opts.get(CONF_ACTION_UNKNOWN, "none")
    if not devices or action == "none":
        return 0
    hold = opts.get(CONF_HOLD_SECONDS, 1)
    for ent in devices:
        await _call(hass, ent, action, hold)
    _LOGGER.info("car_techlan: %s — действие %s для %s",
                 plate.get("plate"), action, ", ".join(devices))
    return len(devices)
