# findmy-zoo 📍

Самохостовая карта: где всё твоё «эппловское» было за последние сутки. Раз в несколько
минут опрашивает Apple, копит трек в SQLite (скользящее окно 24 ч) и рисует его на карте
(Leaflet) — по одной цветной линии и маркеру «последняя точка» на сущность.

Ставится одним systemd-сервисом, весь код публичный, **все секреты (Apple ID, ключи
меток, сессии) — только в локальном конфиге на сервере и в репо не попадают.**

## Что трекается (и что реально работает)

| Слой | Источник | История за сутки | Статус |
|---|---|---|---|
| 🟠 **Метки** — AirTag'и и DIY-метки (OpenHaystack) | [FindMy.py](https://github.com/malmeloo/FindMy.py) + anisette | ✅ отдаёт Apple (`fetch_location_history`) | рабочее |
| 🔵 **Устройства** — iPhone/Mac/Watch/AirPods из Find My | [pyicloud](https://github.com/picklepete/pyicloud) `api.devices` | ⚠️ только текущая точка → трек копим сами опросами | рабочее |
| 🟢 **Люди** — кто делится геопозицией через Find My | — | — | **недоступно, см. ниже** |

### Про слой «Люди»

Отдельного публичного API «Find My Friends» у Apple больше нет — его давно свернули в
общий Find My, а старый `fmf`-эндпоинт закрыт. В [pyicloud](https://github.com/picklepete/pyicloud)
сервис друзей так и остался в неслитом PR. Поэтому **через поддерживаемые открытые
библиотеки в 2026 слой «люди» не строится**, и фейковый модуль сюда не заводился.
Оставлена чистая точка расширения (`sources.icloud.people.enabled=false`): если появится
рабочий способ (или ты сам будешь толкать локации семьи из iOS-шортката), допишется одним
источником в `collector/sources.py`.

## Этика и границы 🔒

Только **твоё** и только те люди, кто **сам** тебе расшарил геопозицию в Find My. Это
инструмент для своих девайсов/меток и согласившихся близких, не для слежки за посторонними.
У Apple на этот счёт ещё и анти-сталкерская защита. Никаких чужих ключей/аккаунтов.

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/anton-vinogradov/findmy-zoo/main/install.sh | bash
# или от root:  … | sudo bash
```

install.sh: venv + зависимости, копирует `config.json` из примера, поднимает
**macless anisette-контейнер** (`dadoum/anisette-v3-server` на `127.0.0.1:6969`, docker/podman),
регистрирует systemd-сервис `findmy-zoo` на порту **8815**.

Затем один раз залогинься в Apple (пароль вводится с клавиатуры, в репо/конфиг не пишется):

```bash
cd /opt/findmy-zoo
.venv/bin/python collector/login.py apple   # iCloud-сессия для устройств
.venv/bin/python collector/login.py tags    # аккаунт FindMy.py для меток
```

## Настройка меток

Ключи AirTag/DIY кладём в `data/tags/*.json` (формат FindMy.py — можно
сконвертировать из OpenHaystack/macless-haystack, см. примеры в репе FindMy.py) и
перечисляем в `collector/config.json`:

```json
"accessories": [
  { "name": "Ключи",  "file": "data/tags/keys.json" },
  { "name": "Рюкзак", "b64key": "<base64-приватный-ключ>" }
]
```

Не хочешь контейнер — поставь `sources.tags.anisetteUrl: null`, FindMy.py сгенерит
anisette встроенно.

## Как устроено

```
collector/hub.py      — фоновые опросы источников + HTTP (stdlib) + /api/points
collector/sources.py  — TagSource (FindMy.py) и IcloudSource (pyicloud)
collector/store.py    — SQLite, дедуп по (entity_id, ts), окно retentionH
collector/login.py    — разовый интерактивный логин в Apple (getpass + 2FA)
index.html/app.js/... — Leaflet-карта, фильтры по типу, автообновление 30 с
install.sh            — systemd + macless anisette-контейнер
```

Тайлы карты по умолчанию с OpenStreetMap (нужен интернет у сервера). Всё остальное —
локально/оффлайн.

## Приватность данных

`data/history.db`, сессии Apple и ключи меток — в `.gitignore` и наружу HTTP не
отдаются (`/data` и `/collector` заблокированы). Публичный только код.
