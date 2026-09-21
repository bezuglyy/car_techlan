# Car Techlan — интеграция распознавания номеров для Home Assistant

Интеграция связывает Home Assistant с системой распознавания номеров **Car Techlan** (сервер + сервис ALPR):
принимает события о номерах, умеет реагировать на «свой/чужой» (открытие ворот, уведомления) и **управлять сервером**
(перезапуск службы, очистка кэша TTS, перезапуск потоков камер), а также публикует сенсоры состояния.

## Возможности

- **События по номерам** (MQTT `alpr/#`): `car_techlan_plate`, `car_techlan_make`, `car_techlan_blacklist`.
- **Реакции**: свои/чужие номера → действия с устройствами (open/close/toggle/impulse), уведомления,
  условия по дням/времени/списку номеров, пауза между срабатываниями.
- **Управление сервером (кнопки/сервисы)**: `server_restart_service`, `server_clear_tts_cache`,
  `server_camera_restart`, `server_checks`, `server_incidents`.
- **Сенсоры состояния** (18): кадры, распознано номеров, чужих, отбраковано, реестр (подтверждено/добран регион/исправлен регион),
  камеры онлайн/всего, ошибки, свободно на диске, GPU, RAM, последний номер, состояние сервера, проверки.
- **Отладочные сервисы**: `trigger_plate`, `trigger_make` (симуляция событий для автоматизаций и тестов).

## Установка

### HACS (custom repository)
1. HACS → Integrations → ⋮ → Custom repositories → URL этого репозитория, категория **Integration**.
2. Установить **Car Techlan**, перезапустить Home Assistant.

### Вручную
Скопировать `custom_components/car_techlan` в `<config>/custom_components/` и перезапустить HA.

## Настройка

1. **Настройки → Устройства и службы → Добавить интеграцию → Car Techlan**.
2. MQTT-брокер (адрес/порт/логин), `base_topic` (по умолчанию `alpr`).
3. При необходимости в опциях: адрес сервера (`server_host`, `server_port`), интервал опроса `server_poll_seconds`.
4. Действия по «своим/чужим» номерам, уведомления и условия — в том же мастере/опциях.


## Действия и события по каждой камере (v1.2.0)

- Для каждой камеры публикуется **своё событие**: `car_techlan_plate_<камера>` (например `car_techlan_plate_post5`),
  плюс общее `car_techlan_plate` с полем `camera`.
- Действие можно задать **на камеру** сервисом `car_techlan.set_camera_action` (сохраняется в опциях интеграции):

```yaml
service: car_techlan.set_camera_action
data:
  camera: Post5
  action_unknown: impulse
  devices_unknown: [cover.shlagbaum_post5]
  cooldown: 30
  hold_seconds: 1
```

Поля: `action` / `action_known` / `action_unknown` (`open|close|toggle|turn_on|turn_off|impulse|none`),
`devices` / `devices_known` / `devices_unknown` (entity_id, можно несколько), `cooldown`, `hold_seconds`.
Камерные правила имеют приоритет над общими настройками; факт настройки — событие `car_techlan_camera_action_set`.

## Сервисы

| Сервис | Что делает |
|:--|:--|
| `car_techlan.trigger_plate` | симулировать распознавание номера |
| `car_techlan.set_camera_action` | задать действие/устройства для конкретной камеры |
| `car_techlan.server_restart_service` | перезапустить службу распознавания |
| `car_techlan.server_clear_tts_cache` | очистить кэш озвучки |
| `car_techlan.server_camera_restart` | перезапустить поток камеры |
| `car_techlan.server_checks` | диагностика сервера (результат — событием) |
| `car_techlan.server_incidents` | последние инциденты сервера |

## События

`car_techlan_plate`, `car_techlan_make`, `car_techlan_blacklist`, `car_techlan_button`, `car_techlan_server_*`.

## Примечания

- Сервер распознавания публикует **только распознанные номера** в MQTT (флаг `ha_plates_only`).
- Служебные эндпоинты `/api/srv/*` требуют ключ API сервера (задаётся в его настройках).
- Версия интеграции — `1.1.0`.
