"""Константы интеграции Car Techlan (распознавание номеров)."""
DOMAIN = "car_techlan"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_BASE_TOPIC = "base_topic"
CONF_CAMERAS = "cameras"

# --- управление ---
CONF_DEVICES_KNOWN = "devices_known"      # устройства при распознавании СВОЕГО номера
CONF_ACTION_KNOWN = "action_known"
CONF_DEVICES_UNKNOWN = "devices_unknown"  # устройства при НЕизвестном номере
CONF_ACTION_UNKNOWN = "action_unknown"
CONF_HOLD_SECONDS = "hold_seconds"        # для импульсного режима
CONF_COOLDOWN = "cooldown"                # пауза между срабатываниями, с
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_KNOWN = "notify_known"
CONF_NOTIFY_UNKNOWN = "notify_unknown"

# --- расширенные условия ---
CONF_COND_DAYS = "cond_days"          # список дней 0=Пн..6=Вс (пусто = все)
CONF_COND_TIME_FROM = "cond_time_from"  # "HH:MM"
CONF_COND_TIME_TO = "cond_time_to"
CONF_COND_PLATES = "cond_plates"      # список номеров/фрагментов (пусто = любые)
CONF_COND_MODE = "cond_mode"          # all | any  (как объединять условия)
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

DEFAULT_BASE_TOPIC = "alpr"
DEFAULT_HOST = "192.168.103.200"
DEFAULT_PORT = 1883
DEFAULT_COOLDOWN = 30
DEFAULT_HOLD_SECONDS = 1

ACTIONS = ["open", "close", "toggle", "turn_on", "turn_off", "impulse", "none"]
ACTIONS_KNOWN = ["open", "impulse", "toggle", "turn_on", "close", "turn_off", "none"]
ACTIONS_UNKNOWN = ["turn_on", "toggle", "turn_off", "open", "close", "none"]

EVENT_PLATE = f"{DOMAIN}_plate"

# --- сервер Car-Techlan (HTTP API :8096) ---
CONF_SERVER_HOST = "server_host"
CONF_SERVER_PORT = "server_port"
CONF_SERVER_KEY = "server_api_key"
CONF_SERVER_SSL = "server_ssl"
CONF_SERVER_SENSORS = "server_sensors"       # список выбранных сенсоров сервера
DEFAULT_SERVER_HOST = "192.168.100.110"
DEFAULT_SERVER_PORT = 8096

# выбираемые сенсоры сервера: ключ -> человекочитаемое имя
SERVER_SENSOR_CHOICES = {
    "server_state": "Сервер: состояние",
    "server_version": "Сервер: версия",
    "frames": "Кадры (за сессию)",
    "plates": "Номеров распознано",
    "unknown": "Чужих номеров",
    "rejected": "Отбраковано чтений",
    "lookup_known": "Реестр: подтверждено",
    "lookup_region": "Реестр: добран регион",
    "lookup_core": "Реестр: исправлен регион",
    "cameras_online": "Камер онлайн",
    "cameras_total": "Камер всего",
    "errors": "Ошибок распознавания",
    "disk_free": "Свободно на диске, ГБ",
    "gpu_util": "GPU занятость, %",
    "ram_used": "RAM занято, %",
    "last_plate": "Последний номер",
}
SERVICE_SERVER_CHECKS = "server_checks"
SERVICE_SERVER_INCIDENTS = "server_incidents"
SERVICE_SERVER_RESTART_WEB = "server_restart_web"
SERVICE_SERVER_RESTART_SERVICE = "server_restart_service"
SERVICE_SERVER_CLEAR_TTS = "server_clear_tts_cache"
SERVICE_SERVER_CAMERA_RESTART = "server_camera_restart"

# --- действия ПО КАМЕРАМ (приоритет над общими) ---
CONF_CAMERA_ACTIONS = "camera_actions"   # {камера: {action, action_known, action_unknown, devices, devices_known, devices_unknown, cooldown, hold_seconds}}
