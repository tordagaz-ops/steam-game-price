# Steam Game Price — MCP server

[![MCP](https://img.shields.io/badge/MCP-compatible-1f6feb)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Ask your AI assistant "how much is ELDEN RING in Turkey right now?" and get the
actual store price, in the actual currency, with the actual discount.

This server wraps the public **Steam Store** API — no key, no account — and
exposes it as three read-only MCP tools: find a game by name, read its current
price in any store region, and see what is discounted today.

**Languages:** English · [Español](README.es.md) · [Русский](README.ru.md)

> This product uses the Steam Store API but is not endorsed or certified by Valve.

---

## Why this exists

Steam prices are not one price. The same app costs $59.99 in the United States,
3 599 ₽ in Russia, 1 400 ₽-equivalent in Japan, and is sometimes not sold in a
region at all. A language model asked for a price will produce a plausible
number from its training data — reliably wrong, and quietly so.

This server answers from the live store, and it is explicit about the cases
models get wrong:

- **Region is a parameter, not an assumption.** `country` takes a code or a name
  (`ru`, `US`, `Germany`, `Россия`).
- **"Free" and "no price" are different answers.** A free game returns
  `price.final = 0` with `is_free = true`; a region-locked title returns
  `error = "not_available_in_region"`, because Steam reports both as "no price".
- **Discounts are computed, not guessed.** Final price, list price, percent and
  the formatted string Steam itself displays.

## Tools

### `search_games`

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `query` | string | — | Game title, e.g. `elden ring` |
| `country` | string | `"us"` | Store region: `us`, `ru`, `de`, `br`, `kz`, `ua`, `tr`, `jp`… |
| `limit` | integer | `10` | 1–25 |

Returns matching apps with ids and prices, so the model can then ask for
details:

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
      "metacritic_score": 94,
      "store_url": "https://store.steampowered.com/app/1245620/"
    }
  ],
  "source": "steam"
}
```

Search rows are deliberately lean: the search endpoint returns amounts but no
formatted strings, so `final_formatted` is `null` there — `get_game_price` is the
call that returns Steam's own display string. A row without a price carries
`price_note: "no_price_listed"`: the search endpoint does not say whether that
means free or not sold in the region.

### `get_game_price`

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `app_id` | integer | — | Steam app id, e.g. `1245620` |
| `country` | string | `"us"` | Store region |

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

Field notes:

- `price.final` / `price.initial` are plain amounts (`35.99`), converted from
  Steam's integer minor units. `final_formatted` is Steam's own display string
  and is authoritative if a currency ever disagrees.
- `price` is `null` with `price_note: "not_available_in_region"` when the store
  publishes no price for that region.
- `unknown_fields` names anything the store did not report, so an empty list
  means "all fields present", not "all fields good".
- `coming_soon` games may have no price yet; the payload says so.

### `list_specials`

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `country` | string | `"us"` | Store region |
| `limit` | integer | `10` | 1–50 |

Current discounts, biggest first:

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

## Regions

`country` accepts an ISO-3166 alpha-2 code in any case (`US`, `de`) and a set of
human names and aliases — `usa`, `uk`, `great britain`, `germany`, `deutschland`,
`espana`/`españa`, `russia`, `рф`, `казахстан`, `türkiye`, `brasil`, `japan`, and
about eighty more. Unknown values are rejected with `invalid_country` instead of
silently defaulting, because a wrong region means a wrong price.

Steam supports far more store regions than the ones we document; any two-letter
code is passed through.

## Install

```bash
pip install git+https://github.com/tordagaz-ops/steam-game-price
```

or from a clone:

```bash
git clone https://github.com/tordagaz-ops/steam-game-price
cd steam-game-price
pip install .
```

## Connect it

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "steam-game-price": {
      "command": "python",
      "args": ["-m", "mcp_steam_price"],
      "env": { "MCP_LOCALE": "en" }
    }
  }
}
```

### Smithery

The repository ships a `smithery.yaml`, so Smithery can build and host it
directly — pick the language in the configuration form.

### HTTP transport

```bash
MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8000 python -m mcp_steam_price
# endpoint: http://localhost:8000/mcp
```

### Docker

```bash
docker build -t steam-game-price .
docker run -i --rm steam-game-price
```

## Example conversation

> **You:** How much is ELDEN RING in Russia, and is it discounted?
>
> **Assistant:** *(calls `search_games` → `get_game_price` with `country: "ru"`)*
> 3 999 ₽ on the Russian store, with no discount right now — the list price and
> the final price are the same. On the US store it is $59.99.

> **You:** What's on sale today under 20 dollars?
>
> **Assistant:** *(calls `list_specials` with `country: "us"`)*
> The biggest current discounts are … (sorted by discount, with end dates).

> **You:** Price for Cyberpunk 2077 in Russia?
>
> **Assistant:** Steam has no Russian store page for that app — it is not sold in
> that region. The US store has it.

## Errors

Failures are data, never exceptions or stack traces:

```json
{ "error": "not_available_in_region", "message": "…", "app_id": 1091500, "country": "ru" }
```

| `error` | Meaning | What to do |
| --- | --- | --- |
| `empty_query` | No search text | Ask for a title |
| `empty_app_id` | No id supplied | Use `search_games` first |
| `invalid_app_id` | Not a positive number | Re-read the id |
| `invalid_country` | Not a region code or known name | Use `us`, `de`, `ru`… |
| `empty_country` | No region supplied | Pass a code, or omit for `us` |
| `not_found` | No store page for that app id | Check the id |
| `not_available_in_region` | App exists, not sold there | Try another region |
| `rate_limited` | Steam throttled us | Wait and retry |
| `timeout` | Upstream too slow | Retry |
| `network_error` | Connection failed | Retry |
| `upstream_unavailable` | Steam returned 5xx after retries | Retry later |
| `upstream_rejected` | Steam rejected the request | Check arguments |
| `bad_payload` | Unexpected response shape | Report as a bug |

## Behaviour and limits

- **Caching.** Prices are cached for 15 minutes per app and region, search
  results for 30 minutes, discount lists for 10 minutes. Concurrent identical
  requests share one upstream call.
- **Retries.** 408/425/429/5xx are retried with jittered backoff, honouring
  `Retry-After`; other 4xx are not.
- **Region detection is never automatic.** A server-side IP says nothing about
  the user's store region, so the default is `us` and the caller should pass the
  real region explicitly.
- **Rate limits.** The public endpoints answer without a key and are generous,
  but a tight loop of hundreds of calls will eventually be throttled — the
  server reports `rate_limited` rather than failing silently.
- **Coverage.** Very new, unreleased or delisted apps may have no store record;
  they come back as `not_found`.
- **Read-only.** No account, no wishlist, no cart, no purchases, no key.

## Languages

Set `MCP_LOCALE` to `en`, `es` or `ru`. It controls tool titles, descriptions,
parameter text and every error message. Default is English; when `MCP_LOCALE` is
unset the server falls back to `LANGUAGE` / `LANG`, then to English.

## Development

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]"

pytest -m "not live and not e2e"   # unit: parsing, regions, mocked store
pytest -m e2e                      # end-to-end: real stdio process, real protocol
pytest -m live                     # live: hits the real Steam Store
pytest                             # everything
```

Layout:

```
src/mcp_steam_price/
  server.py   FastMCP wiring, tool signatures, error mapping
  steam.py    parsing, price normalisation, cached client
  regions.py  country codes, aliases, readable names
  i18n.py     en / es / ru strings
  core.py     HTTP client with retries, TTL cache, locale plumbing
```

## Attribution

Game data and prices come from the public Steam Store API and remain the
property of Valve Corporation. This product uses the Steam Store API but is not
endorsed or certified by Valve. This project is an independent wrapper.

Prices change constantly and are provided as-is; verify before buying. This is
not financial advice.

## Free, and donations welcome

This server is free: every tool can be called without payment, registration or
an API key. If it saves you time or money, you can send a donation -- it goes
straight to the developer, with no platform in between.

| Network | Asset | Address |
| --- | --- | --- |
| Base | USDC / ETH | `0x832e9e0FC60c35A07cf80846A9eD27aa7cb4F637` |
| Ethereum | ETH | `0x832e9e0FC60c35A07cf80846A9eD27aa7cb4F637` |

Nothing in the code is gated on donations: no telemetry, no licence check, no
expiring demo. The whole source is MIT-licensed.

## License

MIT — see [LICENSE](LICENSE).
