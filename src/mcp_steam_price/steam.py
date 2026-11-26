"""Steam Store domain layer: parsing, normalisation and cached access.

Three upstream endpoints, none of which need a key:

* ``/api/appdetails?appids=<id>&cc=<cc>`` — full store record for one app
* ``/api/storesearch/?term=<text>&cc=<cc>`` — name to app id lookup
* ``/api/featuredcategories?cc=<cc>`` — sections including current discounts

Quirks this module absorbs
--------------------------
* ``data`` is normally an object, but comes back as an empty *list* when the
  caller passes ``filters``, and the whole record is missing when the app is
  unknown **or** not sold in the requested region — the two cases are not
  distinguishable from one response, so a second call against the fallback
  region separates them.
* Prices are integers scaled by 100 in every currency, including zero-decimal
  ones (JPY ``140000`` is ¥1,400), so a single ``/100`` rule is correct.
* ``appids`` accepts exactly one id. Passing a comma-separated list yields
  HTTP 400 with a ``null`` body.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from . import regions
from .core import HttpClient, TTLCache, UpstreamError

__all__ = [
    "FALLBACK_COUNTRY",
    "AppIdFormatError",
    "GameLookup",
    "SteamClient",
    "build_game",
    "build_search_item",
    "build_special",
    "normalize_app_id",
]

BASE_URL = "https://store.steampowered.com"
FALLBACK_COUNTRY = "us"

CACHE_TTL = 900.0  # store prices move at store-update cadence, 15 min is safe
SEARCH_TTL = 1800.0
SPECIALS_TTL = 600.0

DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 25
DEFAULT_SPECIALS_LIMIT = 10
MAX_SPECIALS_LIMIT = 50

_PLATFORM_KEYS = (("windows", "windows"), ("mac", "macos"), ("linux", "linux"))
_APP_PATH_RE = re.compile(r"/app/(\d+)")
_STORE_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE)


class AppIdFormatError(ValueError):
    """Raised when a value cannot be read as a Steam app id."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code  # "empty" or "invalid"


@dataclass(frozen=True)
class GameLookup:
    """Outcome of one app lookup, with the region ambiguity already resolved."""

    status: str  # "ok" | "not_found" | "not_available_in_region"
    payload: dict[str, Any] | None = None


# --------------------------------------------------------------------- parsing


def normalize_app_id(raw: object) -> int:
    """Accept ``1245620``, ``"1245620"`` or a store URL, return the number."""
    if raw is None:
        raise AppIdFormatError("empty")
    if isinstance(raw, bool):
        raise AppIdFormatError("invalid")
    if isinstance(raw, int):
        if raw > 0:
            return raw
        raise AppIdFormatError("invalid")

    text = str(raw).strip()
    if not text:
        raise AppIdFormatError("empty")

    match = _STORE_URL_RE.search(text) or _APP_PATH_RE.search(text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        value = int(text)
        if value > 0:
            return value
    raise AppIdFormatError("invalid")


def _money(minor: object) -> float | None:
    """Steam's integer minor units to a plain amount."""
    if isinstance(minor, bool) or not isinstance(minor, (int, float)):
        return None
    return round(float(minor) / 100.0, 2)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    # Steam is inconsistent: required_age and metascore arrive as strings.
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def price_block(overview: object, is_free: bool) -> dict[str, Any] | None:
    """Normalise ``price_overview`` into one consistent shape.

    Returns ``None`` when the app is neither free nor purchasable in this
    region — a real state that must not be flattened into "free".
    """
    if isinstance(overview, dict) and overview:
        final = _money(overview.get("final"))
        initial = _money(overview.get("initial"))
        return {
            "currency": _text(overview.get("currency")),
            "final": final,
            "initial": initial,
            "discount_percent": _int(overview.get("discount_percent")) or 0,
            "final_formatted": _text(overview.get("final_formatted")),
            "initial_formatted": _text(overview.get("initial_formatted")),
            "is_discounted": bool(
                initial is not None and final is not None and initial > final
            ),
        }
    if is_free:
        return {
            "currency": None,
            "final": 0.0,
            "initial": 0.0,
            "discount_percent": 0,
            "final_formatted": "Free",
            "initial_formatted": None,
            "is_discounted": False,
        }
    return None


def _platforms(data: dict[str, Any]) -> list[str]:
    flags = data.get("platforms") or {}
    return [name for key, name in _PLATFORM_KEYS if isinstance(flags, dict) and flags.get(key)]


def _names(rows: object) -> list[str]:
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            value = _text(row.get("description"))
            if value:
                out.append(value)
    return out


def _texts(rows: object) -> list[str]:
    """Read Steam's ``["fromsoft"]``-style lists, ignoring anything else."""
    if not isinstance(rows, list):
        return []
    return [value for value in (_text(row) for row in rows) if value]


def build_game(data: dict[str, Any], app_id: int, country: str) -> dict[str, Any]:
    """Turn one ``appdetails`` record into the tool's answer."""
    is_free = bool(data.get("is_free"))
    price = price_block(data.get("price_overview"), is_free)

    release = data.get("release_date") or {}
    if not isinstance(release, dict):
        release = {}

    metacritic = data.get("metacritic") or {}
    if not isinstance(metacritic, dict):
        metacritic = {}

    recommendations = data.get("recommendations") or {}
    if not isinstance(recommendations, dict):
        recommendations = {}

    payload: dict[str, Any] = {
        "app_id": app_id,
        "name": _text(data.get("name")),
        "type": _text(data.get("type")),
        "country": country,
        "region_name": regions.region_name(country),
        "is_free": is_free,
        "currency": (price or {}).get("currency"),
        "price": price,
        "platforms": _platforms(data),
        "genres": _names(data.get("genres")),
        "developers": _texts(data.get("developers")),
        "publishers": _texts(data.get("publishers")),
        "release_date": _text(release.get("date")),
        "coming_soon": bool(release.get("coming_soon")),
        "metacritic_score": _int(metacritic.get("score")),
        "recommendations": _int(recommendations.get("total")),
        "required_age": _int(data.get("required_age")),
        "short_description": _text(data.get("short_description")),
        "store_url": f"{BASE_URL}/app/{app_id}/",
        "source": "steam",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Absence is information: name the fields Steam did not report, so "no
    # discount" is never confused with "the price is unknown".
    payload["unknown_fields"] = [
        name
        for name in ("name", "type", "price", "platforms", "genres", "release_date")
        if payload.get(name) in (None, [], {})
    ]
    if price is None and not is_free:
        payload["price_note"] = "not_available_in_region"
    return payload


def build_search_item(item: dict[str, Any], country: str) -> dict[str, Any]:
    """Turn one ``storesearch`` hit into a compact result row."""
    app_id = _int(item.get("id"))
    price = price_block(item.get("price"), False)

    # The search endpoint omits discount_percent; derive it from the amounts.
    if price and price.get("is_discounted") and not price.get("discount_percent"):
        initial, final = price.get("initial"), price.get("final")
        if initial and final is not None:
            price["discount_percent"] = int(round((1 - final / initial) * 100))

    flags = item.get("platforms") or {}
    platforms = [
        name for key, name in _PLATFORM_KEYS if isinstance(flags, dict) and flags.get(key)
    ]

    row: dict[str, Any] = {
        "app_id": app_id,
        "name": _text(item.get("name")),
        "type": _text(item.get("type")),
        "country": country,
        "price": price,
        "currency": (price or {}).get("currency"),
        "platforms": platforms,
        "metacritic_score": _int(item.get("metascore")),
        "store_url": f"{BASE_URL}/app/{app_id}/" if app_id else None,
    }
    if price is None:
        # Search results carry no free/unavailable flag: a missing price here
        # means "free or not sold", which only get_game_price can tell apart.
        row["price_note"] = "no_price_listed"
    return row


def build_special(item: dict[str, Any], country: str) -> dict[str, Any]:
    """Turn one ``featuredcategories`` specials row into a deal."""
    app_id = _int(item.get("id"))
    original = _money(item.get("original_price"))
    final = _money(item.get("final_price"))
    expires = _int(item.get("discount_expiration"))

    return {
        "app_id": app_id,
        "name": _text(item.get("name")),
        "country": country,
        "currency": _text(item.get("currency")),
        "discount_percent": _int(item.get("discount_percent")) or 0,
        "original_price": original,
        "final_price": final,
        "saving": round(original - final, 2)
        if original is not None and final is not None
        else None,
        "discount_ends_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires))
        if expires
        else None,
        "store_url": f"{BASE_URL}/app/{app_id}/" if app_id else None,
    }


# ---------------------------------------------------------------------- client


class SteamClient:
    """Cached, retrying access to the three store endpoints."""

    def __init__(self, http: HttpClient | None = None) -> None:
        self._http = http or HttpClient(BASE_URL, timeout=15.0)
        self._cache = TTLCache()

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        await self._http.aclose()

    # -- raw endpoints ---------------------------------------------------
    async def app_details(self, app_id: int, country: str) -> tuple[bool, dict[str, Any] | None]:
        """Return ``(success, data)`` exactly as Steam reports it."""

        key = f"app:{app_id}:{country}"

        async def fetch() -> tuple[bool, dict[str, Any] | None]:
            payload = await self._http.get_json(
                "/api/appdetails",
                {"appids": app_id, "cc": country, "l": "en"},
            )
            if not isinstance(payload, dict):
                raise UpstreamError("bad_payload", "appdetails returned a non-object payload")
            entry = payload.get(str(app_id))
            if not isinstance(entry, dict):
                # Steam answers 200 with a JSON null for malformed queries.
                raise UpstreamError("bad_payload", "appdetails returned no entry for the app id")
            success = bool(entry.get("success"))
            data = entry.get("data")
            if isinstance(data, list):  # `filters` switches the shape
                data = data[0] if data else None
            if not isinstance(data, dict):
                data = None
            return success, data

        return await self._cache.get_or_set(key, CACHE_TTL, fetch)

    async def search_raw(self, query: str, country: str) -> dict[str, Any]:
        key = f"search:{country}:{query.lower()}"

        async def fetch() -> dict[str, Any]:
            payload = await self._http.get_json(
                "/api/storesearch/", {"term": query, "cc": country, "l": "en"}
            )
            if not isinstance(payload, dict):
                raise UpstreamError("bad_payload", "storesearch returned a non-object payload")
            return payload

        return await self._cache.get_or_set(key, SEARCH_TTL, fetch)

    async def specials_raw(self, country: str) -> dict[str, Any]:
        key = f"specials:{country}"

        async def fetch() -> dict[str, Any]:
            payload = await self._http.get_json(
                "/api/featuredcategories", {"cc": country, "l": "en"}
            )
            if not isinstance(payload, dict):
                raise UpstreamError(
                    "bad_payload", "featuredcategories returned a non-object payload"
                )
            return payload

        return await self._cache.get_or_set(key, SPECIALS_TTL, fetch)

    # -- composed answers ------------------------------------------------
    async def lookup(self, app_id: int, country: str) -> GameLookup:
        """Fetch one game, resolving "unknown" versus "not sold here"."""
        success, data = await self.app_details(app_id, country)
        if success and data:
            return GameLookup("ok", build_game(data, app_id, country))

        if country != FALLBACK_COUNTRY:
            # Steam answers "not purchasable here" the same way as "no such app",
            # so ask the fallback region once to tell the two apart.
            found_elsewhere, _ = await self.app_details(app_id, FALLBACK_COUNTRY)
            if found_elsewhere:
                return GameLookup("not_available_in_region")
        return GameLookup("not_found")

    async def search(self, query: str, country: str, limit: int) -> dict[str, Any]:
        payload = await self.search_raw(query, country)
        items = payload.get("items")
        if not isinstance(items, list):
            raise UpstreamError("bad_payload", "storesearch returned no item list")
        rows = [
            build_search_item(item, country)
            for item in items[:limit]
            if isinstance(item, dict)
        ]
        return {
            "query": query,
            "country": country,
            "region_name": regions.region_name(country),
            "count": len(rows),
            "total_matches": _int(payload.get("total")),
            "results": rows,
            "source": "steam",
        }

    async def specials(self, country: str, limit: int) -> dict[str, Any]:
        payload = await self.specials_raw(country)
        section = payload.get("specials")
        if not isinstance(section, dict):
            # Some responses key sections numerically; find it by id instead.
            section = next(
                (
                    value
                    for value in payload.values()
                    if isinstance(value, dict)
                    and str(value.get("id", "")).endswith("specials")
                ),
                None,
            )
        items = (section or {}).get("items")
        if not isinstance(items, list):
            raise UpstreamError("bad_payload", "featuredcategories returned no specials")

        rows = [build_special(item, country) for item in items if isinstance(item, dict)]
        rows.sort(key=lambda row: row["discount_percent"], reverse=True)
        rows = rows[:limit]
        return {
            "country": country,
            "region_name": regions.region_name(country),
            "currency": rows[0]["currency"] if rows else None,
            "count": len(rows),
            "deals": rows,
            "source": "steam",
        }
