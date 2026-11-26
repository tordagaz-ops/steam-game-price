# Steam Game Price — servidor MCP

[![MCP](https://img.shields.io/badge/MCP-compatible-1f6feb)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Pregúntale a tu asistente de IA «¿cuánto cuesta ELDEN RING en Turquía ahora
mismo?» y obtén el precio real de la tienda, en la moneda real, con el descuento
real.

Este servidor envuelve la API pública de la **tienda de Steam** — sin clave y sin
cuenta — y la expone como tres herramientas MCP de solo lectura: buscar un juego
por nombre, leer su precio actual en cualquier región de la tienda y ver qué está
de oferta hoy.

**Idiomas:** [English](README.md) · Español · [Русский](README.ru.md)

> Este producto usa la API de la tienda de Steam pero no está respaldado ni
> certificado por Valve.

---

## Por qué existe

El precio de Steam no es un precio único. El mismo juego cuesta 59,99 $ en
Estados Unidos, 3 599 ₽ en Rusia, el equivalente a 1 400 ₽ en Japón, y a veces no
se vende en una región. Un modelo de lenguaje al que se le pide un precio
inventará una cifra plausible a partir de sus datos de entrenamiento — de forma
fiable y silenciosa.

Este servidor responde con la tienda en vivo y explicita justo los casos en los
que los modelos fallan:

- **La región es un parámetro, no una suposición.** `country` acepta un código o
  un nombre (`ru`, `US`, `Germany`, `Россия`).
- **«Gratis» y «sin precio» son respuestas distintas.** Un juego gratuito devuelve
  `price.final = 0` con `is_free = true`; un título bloqueado por región devuelve
  `error = "not_available_in_region"`, porque Steam informa de ambos como «sin
  precio».
- **Los descuentos se calculan, no se adivinan.** Precio final, precio de
  catálogo, porcentaje y la cadena que muestra el propio Steam.

## Herramientas

### `search_games`

| Argumento | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `query` | string | — | Título del juego, p. ej. `elden ring` |
| `country` | string | `"us"` | Región de la tienda: `us`, `es`, `de`, `br`, `kz`, `ua`, `tr`, `jp`… |
| `limit` | integer | `10` | 1–25 |

Devuelve las aplicaciones encontradas con su id y su precio, para pedir después
el detalle:

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

Las filas de búsqueda son deliberadamente breves: el endpoint de búsqueda no
devuelve cadenas formateadas, así que `final_formatted` es `null` — la cadena que
muestra Steam la da solo `get_game_price`. Una fila sin precio lleva
`price_note: "no_price_listed"`: la búsqueda no distingue si es gratis o si no se
vende en esa región.

### `get_game_price`

| Argumento | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `app_id` | integer | — | Id de aplicación de Steam, p. ej. `1245620` |
| `country` | string | `"us"` | Región de la tienda |

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

Notas sobre los campos:

- `price.final` / `price.initial` son importes normales (`59.99`), convertidos de
  las unidades enteras de Steam. `final_formatted` es la cadena que muestra el
  propio Steam y manda si alguna vez discrepa.
- `price` es `null` con `price_note: "not_available_in_region"` cuando la tienda
  no publica precio para esa región.
- `unknown_fields` nombra lo que la tienda no informó: una lista vacía significa
  «están todos los campos», no «todo está bien».
- Los juegos con `coming_soon` pueden no tener precio todavía; el resultado lo
  dice.

### `list_specials`

| Argumento | Tipo | Por defecto | Descripción |
| --- | --- | --- | --- |
| `country` | string | `"us"` | Región de la tienda |
| `limit` | integer | `10` | 1–50 |

Descuentos actuales, los mayores primero:

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

## Regiones

`country` acepta un código ISO-3166 alpha-2 en cualquier caso (`US`, `de`) y un
conjunto de nombres y alias: `usa`, `uk`, `great britain`, `germany`,
`deutschland`, `espana`/`españa`, `russia`, `рф`, `казахстан`, `türkiye`,
`brasil`, `japan` y unos ochenta más. Los valores desconocidos se rechazan con
`invalid_country` en lugar de caer en el valor por defecto, porque una región
equivocada da un precio equivocado.

Steam admite muchas más regiones de las que documentamos; cualquier código de dos
letras se pasa tal cual.

## Instalación

```bash
pip install git+https://github.com/tordagaz-ops/steam-game-price
```

o desde un clon:

```bash
git clone https://github.com/tordagaz-ops/steam-game-price
cd steam-game-price
pip install .
```

## Conexión

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "steam-game-price": {
      "command": "python",
      "args": ["-m", "mcp_steam_price"],
      "env": { "MCP_LOCALE": "es" }
    }
  }
}
```

### Smithery

El repositorio incluye `smithery.yaml`, así que Smithery puede compilarlo y
alojarlo directamente: elige el idioma en el formulario de configuración.

### Transporte HTTP

```bash
MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8000 python -m mcp_steam_price
# endpoint: http://localhost:8000/mcp
```

### Docker

```bash
docker build -t steam-game-price .
docker run -i --rm steam-game-price
```

## Conversación de ejemplo

> **Tú:** ¿Cuánto cuesta ELDEN RING en Rusia y tiene descuento?
>
> **Asistente:** *(llama a `search_games` y luego a `get_game_price` con
> `country: "ru"`)*
> 3 999 ₽ en la tienda rusa, sin descuento ahora mismo: el precio de catálogo y el
> final coinciden. En la tienda estadounidense cuesta 59,99 $.

> **Tú:** ¿Qué está de oferta hoy por menos de veinte dólares?
>
> **Asistente:** *(llama a `list_specials` con `country: "us"`)*
> Los mayores descuentos actuales son… (ordenados por porcentaje, con fecha de
> fin).

> **Tú:** ¿Precio de Cyberpunk 2077 en Rusia?
>
> **Asistente:** Esa aplicación no tiene página en la tienda rusa: no se vende en
> esa región. En la tienda estadounidense sí está.

## Errores

Los fallos vuelven como datos, nunca como excepción ni traza de pila:

```json
{ "error": "not_available_in_region", "message": "…", "app_id": 1091500, "country": "ru" }
```

| `error` | Significado | Qué hacer |
| --- | --- | --- |
| `empty_query` | Sin texto de búsqueda | Pedir un título |
| `empty_app_id` | Sin id | Usar `search_games` primero |
| `invalid_app_id` | No es un número positivo | Volver a leer el id |
| `invalid_country` | Ni código ni nombre conocido | Usar `us`, `de`, `ru`… |
| `empty_country` | Sin región | Pasar un código u omitir para `us` |
| `not_found` | Sin página de tienda para ese id | Comprobar el id |
| `not_available_in_region` | Existe, no se vende allí | Probar otra región |
| `rate_limited` | Steam limitó la frecuencia | Esperar y reintentar |
| `timeout` | El proveedor tardó demasiado | Reintentar |
| `network_error` | Falló la conexión | Reintentar |
| `upstream_unavailable` | Steam devolvió 5xx tras los reintentos | Reintentar más tarde |
| `upstream_rejected` | Steam rechazó la petición | Revisar los argumentos |
| `bad_payload` | Estructura inesperada | Informarlo como error |

## Comportamiento y límites

- **Caché.** Los precios se guardan 15 minutos por aplicación y región, las
  búsquedas 30 minutos y las listas de descuentos 10 minutos. Las peticiones
  idénticas simultáneas comparten una sola llamada.
- **Reintentos.** Los códigos 408/425/429/5xx se reintentan con espera aleatoria y
  respetando `Retry-After`; el resto de 4xx no.
- **La región nunca se detecta sola.** La IP del servidor no dice nada sobre la
  región de la tienda del usuario, así que el valor por defecto es `us` y quien
  llama debe pasar la región real.
- **Límites de frecuencia.** Los endpoints públicos no usan clave y son
  generosos, pero un bucle de cientos de llamadas acabará limitado: el servidor
  responde `rate_limited` en lugar de fallar en silencio.
- **Cobertura.** Aplicaciones muy nuevas, sin lanzar o retiradas pueden no tener
  registro y devuelven `not_found`.
- **Solo lectura.** Sin cuenta, sin lista de deseos, sin carrito, sin compras.

## Idiomas

Configura `MCP_LOCALE` como `en`, `es` o `ru`. Controla los títulos de las
herramientas, las descripciones, el texto de los parámetros y todos los mensajes
de error. Por defecto es inglés; si `MCP_LOCALE` no está definido, el servidor
mira `LANGUAGE` / `LANG` y luego vuelve al inglés.

## Desarrollo

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; en otros sistemas source .venv/bin/activate
pip install -e ".[dev]"

pytest -m "not live and not e2e"   # unitarios: análisis, regiones, tienda simulada
pytest -m e2e                      # extremo a extremo: proceso stdio real
pytest -m live                     # en vivo: tienda de Steam real
pytest                             # todo
```

Estructura:

```
src/mcp_steam_price/
  server.py   conexión FastMCP, firmas de herramientas, mapeo de errores
  steam.py    análisis, normalización de precios, cliente con caché
  regions.py  códigos de país, alias, nombres legibles
  i18n.py     cadenas en / es / ru
  core.py     cliente HTTP con reintentos, caché TTL, localización
```

## Atribución

Los datos y precios provienen de la API pública de la tienda de Steam y siguen
siendo propiedad de Valve Corporation. Este producto usa la API de la tienda de
Steam pero no está respaldado ni certificado por Valve. Este proyecto es un
envoltorio independiente.

Los precios cambian constantemente y se ofrecen «tal cual»; verifícalos antes de
comprar. No es asesoramiento financiero.

## Licencia

MIT — ver [LICENSE](LICENSE).
