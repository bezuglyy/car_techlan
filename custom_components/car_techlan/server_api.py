"""Клиент Car-Techlan-Server (HTTP API :8096) — читает данные и управляет сервером.

Используется сервисами интеграции (управление сервером) и, при необходимости, сенсорами.
Все ошибки логируются и не выбрасываются в HA.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_SERVER_HOST = "192.168.100.110"
DEFAULT_SERVER_PORT = 8096
DEFAULT_TIMEOUT = 15


class CarTechlanServer:
    """Минимальный async-клиент сервера (ключ API — опционален)."""

    def __init__(self, host: str = DEFAULT_SERVER_HOST, port: int = DEFAULT_SERVER_PORT,
                 api_key: str = "", use_ssl: bool = False, session: aiohttp.ClientSession | None = None) -> None:
        self.host = host
        self.port = int(port)
        self.api_key = (api_key or "").strip()
        self.use_ssl = use_ssl
        self._session = session

    @property
    def base_url(self) -> str:
        return "%s://%s:%d" % ("https" if self.use_ssl else "http", self.host, self.port)

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def _request(self, method: str, path: str, params: dict | None = None) -> tuple[int, Any]:
        url = self.base_url + path
        try:
            if self._session is not None:
                async with self._session.request(method, url, headers=self._headers(),
                                                 params=params, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)) as r:
                    txt = await r.text()
                    return r.status, _maybe_json(txt)
            async with aiohttp.ClientSession() as s:
                async with s.request(method, url, headers=self._headers(),
                                     params=params, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)) as r:
                    txt = await r.text()
                    return r.status, _maybe_json(txt)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("car_techlan: %s %s — %s", method, path, err)
            return 0, None

    # --- чтение ---
    async def get_health(self):
        return await self._request("GET", "/health")

    async def get_all(self):
        return await self._request("GET", "/api/all")

    async def get_checks(self):
        return await self._request("GET", "/api/srv/checks")

    async def get_incidents(self):
        return await self._request("GET", "/api/srv/incidents")

    async def get_service_status(self):
        return await self._request("GET", "/api/srv/service/status")

    async def get_tts_stats(self):
        return await self._request("GET", "/api/tts/cache/stats")

    # --- управление ---
    async def restart_web(self):
        return await self._request("POST", "/api/service/restart")

    async def restart_service(self):
        return await self._request("POST", "/api/service/restart")

    async def clear_tts_cache(self, days: int = 30):
        return await self._request("POST", "/api/maintenance/cleanup", params={"days": int(days)})

    async def camera_restart(self, camera: str):
        return await self._request("POST", "/api/cameras/restart", params={"cam": camera})


def _maybe_json(text: str):
    try:
        import json
        return json.loads(text)
    except Exception:
        return text
