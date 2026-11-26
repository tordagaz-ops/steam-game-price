# Steam Game Price — MCP-сервер

[![MCP](https://img.shields.io/badge/MCP-compatible-1f6feb)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Спросите у ИИ-ассистента «сколько сейчас стоит ELDEN RING в Турции?» и получите
настоящую цену магазина, в настоящей валюте, с настоящей скидкой.

Сервер оборачивает публичный API **магазина Steam** — без ключа и без аккаунта —
и отдаёт его тремя MCP-инструментами только для чтения: найти игру по названию,
узнать её текущую цену в любом регионе магазина и посмотреть, что сегодня со
скидкой.

**Языки:** [English](README.md) · [Español](README.es.md) · Русский

> Продукт использует Steam Store API, но не одобрен и не сертифицирован Valve.

---

## Зачем это нужно

Цена в Steam — не одна цена. Одна и та же игра стоит $59.99 в США, 3 599 ₽ в
России, эквивалент 1 400 ₽ в Японии, а в некоторые регионы она вообще не
продаётся. Языковая модель, которую просят назвать цену, выдаст правдоподобное
число из своих обучающих данных — и ошибётся, причём молча.

Этот сервер отвечает по живому магазину и явно проговаривает то, в чём модели
ошибаются:

- **Регион — это параметр, а не догадка.** `country` принимает код или название
  (`ru`, `US`, `Germany`, `Россия`).
- **«Бесплатно» и «цены нет» — разные ответы.** Бесплатная игра возвращает
  `price.final = 0` и `is_free = true`; игра, заблокированная по региону, —
  ошибку `not_available_in_region`, потому что для Steam это одно и то же «нет
  цены».
- **Скидка вычисляется, а не угадывается.** Итоговая цена, базовая цена, процент
  и та строка, которую показывает сам Steam.

## Инструменты

### `search_games`

| Аргумент | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `query` | string | — | Название игры, например `elden ring` |
| `country` | string | `"us"` | Регион магазина: `us`, `ru`, `de`, `br`, `kz`, `ua`, `tr`, `jp`… |
| `limit` | integer | `10` | 1–25 |

Возвращает найденные приложения с id и ценами — чтобы затем запросить детали:

```json
{
  "query": "elden ring",
  "country": "ru",
  "region_name": "Russia",
  "count": 3,
  "total_matches": 3,
  "results": [
    {
      "app_id": 1245620,
      "name": "ELDEN RING",
      "type": "app",
      "country": "ru",
      "price": {
        "currency": "RUB",
        "final": 3599.0,
        "initial": 3599.0,
        "discount_percent": 0,
        "final_formatted": null,
        "initial_formatted": null,
        "is_discounted": false
      },
      "currency": "RUB",
      "platforms": ["windows"],
      "metacritic_score": null,
      "store_url": "https://store.steampowered.com/app/1245620/"
    }
  ],
  "source": "steam"
}
```

Строки поиска намеренно краткие: эндпоинт поиска не отдаёт готовые строки цены,
поэтому `final_formatted` там `null` — форматированную строку Steam возвращает
только `get_game_price`. Строка без цены содержит
`price_note: "no_price_listed"`: поиск не говорит, значит это «бесплатно» или
«не продаётся в регионе» — это различает только `get_game_price`.

### `get_game_price`

| Аргумент | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `app_id` | integer | — | Id приложения Steam, например `1245620` |
| `country` | string | `"us"` | Регион магазина |

```json
{
  "app_id": 1245620,
  "name": "ELDEN RING",
  "type": "game",
  "country": "us",
  "region_name": "United States",
  "is_free": false,
  "currency": "USD",
  "price": {
    "currency": "USD",
    "final": 59.99,
    "initial": 59.99,
    "discount_percent": 0,
    "final_formatted": "$59.99",
    "initial_formatted": null,
    "is_discounted": false
  },
  "platforms": ["windows"],
  "genres": ["Action", "RPG"],
  "developers": ["FromSoftware, Inc."],
  "publishers": ["FromSoftware, Inc.", "Bandai Namco Entertainment"],
  "release_date": "Feb 24, 2022",
  "coming_soon": false,
  "metacritic_score": 94,
  "recommendations": 840194,
  "required_age": 16,
  "short_description": "THE NEW FANTASY ACTION RPG…",
  "store_url": "https://store.steampowered.com/app/1245620/",
  "unknown_fields": [],
  "source": "steam",
  "fetched_at": "2026-01-01T00:00:00Z"
}
```

Пояснения к полям:

- `price.final` / `price.initial` — обычные суммы (`59.99`), пересчитанные из
  целых «минорных единиц» Steam. `final_formatted` — та строка, которую
  показывает сам Steam; если валюта когда-нибудь разойдётся, верьте ей.
- `price` равен `null`, а `price_note` равен `"not_available_in_region"`, если
  магазин не публикует цену для этого региона.
- `unknown_fields` перечисляет всё, что магазин не сообщил: пустой список
  означает «все поля есть», а не «всё хорошо».
- Игры с `coming_soon` могут ещё не иметь цены — в ответе это сказано прямо.

### `list_specials`

| Аргумент | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `country` | string | `"us"` | Регион магазина |
| `limit` | integer | `10` | 1–50 |

Текущие скидки, самые крупные первыми:

```json
{
  "country": "us",
  "region_name": "United States",
  "currency": "USD",
  "count": 2,
  "deals": [
    {
      "app_id": 3240220,
      "name": "SOME GAME",
      "country": "us",
      "currency": "USD",
      "discount_percent": 56,
      "original_price": 44.99,
      "final_price": 19.79,
      "saving": 25.2,
      "discount_ends_at": "2026-01-05T18:00:00Z",
      "store_url": "https://store.steampowered.com/app/3240220/"
    }
  ],
  "source": "steam"
}
```

## Регионы

`country` принимает код ISO-3166 alpha-2 в любом регистре (`US`, `de`) и набор
человеческих названий и псевдонимов: `usa`, `uk`, `great britain`, `germany`,
`deutschland`, `espana`/`españa`, `russia`, `рф`, `казахстан`, `türkiye`,
`brasil`, `japan` и ещё около восьмидесяти. Неизвестное значение отклоняется с
ошибкой `invalid_country`, а не подменяется по умолчанию: неверный регион — это
неверная цена.

Steam поддерживает гораздо больше регионов, чем мы документируем; любой
двухбуквенный код передаётся как есть.

## Установка

```bash
pip install git+https://github.com/tordagaz-ops/steam-game-price
```

или из клона:

```bash
git clone https://github.com/tordagaz-ops/steam-game-price
cd steam-game-price
pip install .
```

## Подключение

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "steam-game-price": {
      "command": "python",
      "args": ["-m", "mcp_steam_price"],
      "env": { "MCP_LOCALE": "ru" }
    }
  }
}
```

### Smithery

В репозитории есть `smithery.yaml`, поэтому Smithery соберёт и разместит сервер
самостоятельно — язык выбирается в форме настройки.

### HTTP-транспорт

```bash
MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8000 python -m mcp_steam_price
# адрес: http://localhost:8000/mcp
```

### Docker

```bash
docker build -t steam-game-price .
docker run -i --rm steam-game-price
```

## Пример диалога

> **Вы:** Сколько стоит ELDEN RING в России и есть ли скидка?
>
> **Ассистент:** *(вызывает `search_games`, затем `get_game_price` с
> `country: "ru"`)*
> 3 999 ₽ в российском магазине, скидки сейчас нет — базовая и итоговая цена
> совпадают. В американском магазине та же игра стоит $59.99.

> **Вы:** Что сегодня со скидкой дешевле двадцати долларов?
>
> **Ассистент:** *(вызывает `list_specials` с `country: "us"`)*
> Самые крупные скидки сейчас — … (по убыванию процента, с датами окончания).

> **Вы:** Цена Cyberpunk 2077 в России?
>
> **Ассистент:** Российской страницы магазина у этого приложения нет — в этом
> регионе оно не продаётся. В американском магазине оно есть.

## Ошибки

Сбои возвращаются как данные, никогда как исключение или стектрейс:

```json
{ "error": "not_available_in_region", "message": "…", "app_id": 1091500, "country": "ru" }
```

| `error` | Значение | Что делать |
| --- | --- | --- |
| `empty_query` | Пустой поисковый запрос | Спросить название игры |
| `empty_app_id` | Не передан id | Сначала вызвать `search_games` |
| `invalid_app_id` | Не положительное число | Перечитать id |
| `invalid_country` | Не код региона и не известное название | Использовать `us`, `de`, `ru`… |
| `empty_country` | Регион не указан | Передать код или опустить для `us` |
| `not_found` | Нет страницы магазина для этого id | Проверить id |
| `not_available_in_region` | Приложение есть, но не продаётся там | Попробовать другой регион |
| `rate_limited` | Steam ограничил частоту | Подождать и повторить |
| `timeout` | Провайдер не ответил вовремя | Повторить |
| `network_error` | Соединение не установлено | Повторить |
| `upstream_unavailable` | Steam вернул 5xx после повторов | Повторить позже |
| `upstream_rejected` | Steam отклонил запрос | Проверить аргументы |
| `bad_payload` | Неожиданная структура ответа | Сообщить как об ошибке |

## Поведение и ограничения

- **Кэширование.** Цены кэшируются на 15 минут на пару «приложение + регион»,
  результаты поиска — на 30 минут, списки скидок — на 10 минут. Одновременные
  одинаковые запросы объединяются в один запрос к магазину.
- **Повторы.** Коды 408/425/429/5xx повторяются с дрожащей задержкой и учётом
  `Retry-After`; остальные 4xx не повторяются.
- **Регион не определяется автоматически.** IP сервера ничего не говорит о
  регионе магазина пользователя, поэтому по умолчанию `us`, а настоящий регион
  нужно передавать явно.
- **Ограничения частоты.** Публичные эндпоинты работают без ключа и довольно
  щедры, но плотный цикл из сотен вызовов упрётся в троттлинг — сервер ответит
  `rate_limited`, а не промолчит.
- **Покрытие.** Совсем новые, не вышедшие или снятые с продажи приложения могут
  не иметь записи в магазине — они вернутся как `not_found`.
- **Только чтение.** Ни аккаунта, ни вишлиста, ни корзины, ни покупок, ни ключа.

## Языки

Задайте `MCP_LOCALE` как `en`, `es` или `ru`. Переменная управляет названиями
инструментов, описаниями, текстом параметров и всеми сообщениями об ошибках.
По умолчанию английский; если `MCP_LOCALE` не задан, сервер смотрит на
`LANGUAGE` / `LANG`, затем откатывается к английскому.

## Разработка

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; в других системах source .venv/bin/activate
pip install -e ".[dev]"

pytest -m "not live and not e2e"   # юнит: разбор ответов, регионы, замоканный магазин
pytest -m e2e                      # e2e: реальный stdio-процесс и протокол
pytest -m live                     # live: настоящий магазин Steam
pytest                             # всё сразу
```

Структура:

```
src/mcp_steam_price/
  server.py   подключение FastMCP, сигнатуры инструментов, маппинг ошибок
  steam.py    разбор ответов, нормализация цен, клиент с кэшем
  regions.py  коды стран, псевдонимы, читаемые названия
  i18n.py     строки en / es / ru
  core.py     HTTP-клиент с повторами, TTL-кэш, локализация
```

## Атрибуция

Данные и цены приходят из публичного Steam Store API и остаются собственностью
Valve Corporation. Продукт использует Steam Store API, но не одобрен и не
сертифицирован Valve. Проект является независимой обёрткой.

Цены меняются постоянно и предоставляются «как есть»; проверяйте перед
покупкой. Это не инвестиционный совет.

## Лицензия

MIT — см. [LICENSE](LICENSE).
