"""Unit tests: parsing, regions, pricing and the tool layer. No network."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from mcp_steam_price.core import UpstreamError
from mcp_steam_price.i18n import Locale, MESSAGES, detect_locale
from mcp_steam_price.regions import (
    CountryFormatError,
    is_supported,
    normalize_country,
    region_name,
)
from mcp_steam_price.steam import (
    AppIdFormatError,
    GameLookup,
    SteamClient,
    build_game,
    build_search_item,
    build_special,
    normalize_app_id,
    price_block,
)

from .helpers import (
    CYBERPUNK,
    DOTA2,
    ELDEN_RING,
    app_payload,
    constant_client,
    game_record,
    json_response,
    make_client,
    result_data,
    search_payload,
    session,
    specials_payload,
)

# --------------------------------------------------------------------- regions


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("us", "us"),
        ("US", "us"),
        (" Us ", "us"),
        ("ru", "ru"),
        ("usa", "us"),
        ("U.S.A", "us"),
        ("united states", "us"),
        ("UK", "gb"),
        ("great britain", "gb"),
        ("Germany", "de"),
        ("deutschland", "de"),
        ("España", "es"),
        ("españa", "es"),
        ("Russia", "ru"),
        ("рф", "ru"),
        ("Россия", "ru"),
        ("Kazakhstan", "kz"),
        ("казахстан", "kz"),
        ("Türkiye", "tr"),
        ("turkey", "tr"),
        ("Brasil", "br"),
        ("ukraine", "ua"),
        ("japan", "jp"),
        ("de", "de"),
        ("br", "br"),
        # Codes we do not document are still valid store codes.
        ("xx", "xx"),
    ],
)
def test_normalize_country_accepts_codes_and_names(raw, expected):
    assert normalize_country(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_country_rejects_empty(raw):
    with pytest.raises(CountryFormatError) as excinfo:
        normalize_country(raw)
    assert excinfo.value.code == "empty"


@pytest.mark.parametrize("raw", ["usa!", "germanyy", "1", "a", "zzz", "planet earth"])
def test_normalize_country_rejects_nonsense(raw):
    with pytest.raises(CountryFormatError) as excinfo:
        normalize_country(raw)
    assert excinfo.value.code == "invalid"


def test_region_name_for_documented_regions():
    assert region_name("us") == "United States"
    assert region_name("ru") == "Russia"
    assert region_name("xx") is None


def test_is_supported_flags_only_documented_regions():
    assert is_supported("de") is True
    assert is_supported("xx") is False


# ---------------------------------------------------------------------- app ids


@pytest.mark.parametrize(
    "raw,expected",
    [
        (1245620, 1245620),
        ("1245620", 1245620),
        (" 730 ", 730),
        ("https://store.steampowered.com/app/730/Counter-Strike_2/", 730),
        ("store.steampowered.com/app/570", 570),
        ("/app/1245620", 1245620),
        (1, 1),
    ],
)
def test_normalize_app_id_accepts_numbers_and_urls(raw, expected):
    assert normalize_app_id(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_normalize_app_id_rejects_empty(raw):
    with pytest.raises(AppIdFormatError) as excinfo:
        normalize_app_id(raw)
    assert excinfo.value.code == "empty"


@pytest.mark.parametrize("raw", [0, -5, "abc", "12.5", True, False, "app/0"])
def test_normalize_app_id_rejects_invalid(raw):
    with pytest.raises(AppIdFormatError) as excinfo:
        normalize_app_id(raw)
    assert excinfo.value.code == "invalid"


# ----------------------------------------------------------------------- prices


def test_price_block_converts_minor_units():
    block = price_block(
        {
            "currency": "USD",
            "initial": 5999,
            "final": 3599,
            "discount_percent": 40,
            "final_formatted": "$35.99",
            "initial_formatted": "$59.99",
        },
        False,
    )
    assert block is not None
    assert block["final"] == pytest.approx(35.99)
    assert block["initial"] == pytest.approx(59.99)
    assert block["discount_percent"] == 40
    assert block["is_discounted"] is True
    assert block["final_formatted"] == "$35.99"


def test_price_block_keeps_full_price_when_not_discounted():
    block = price_block({"currency": "RUB", "initial": 359900, "final": 359900}, False)
    assert block is not None
    assert block["is_discounted"] is False
    assert block["final"] == pytest.approx(3599.0)


def test_price_block_of_a_free_game_is_zero_not_missing():
    block = price_block(None, True)
    assert block is not None
    assert block["final"] == 0.0
    assert block["currency"] is None
    assert block["final_formatted"] == "Free"


def test_price_block_is_none_when_unpriced_and_not_free():
    assert price_block(None, False) is None
    assert price_block({}, False) is None


def test_price_block_survives_garbage():
    block = price_block({"initial": "5999", "final": None, "currency": 7}, False)
    assert block is not None
    assert block["final"] is None
    assert block["initial"] is None
    assert block["currency"] is None


# ------------------------------------------------------------------- build_game


def test_build_game_extracts_the_essentials():
    payload = build_game(game_record(), ELDEN_RING, "us")
    assert payload["app_id"] == ELDEN_RING
    assert payload["name"] == "ELDEN RING"
    assert payload["type"] == "game"
    assert payload["country"] == "us"
    assert payload["region_name"] == "United States"
    assert payload["is_free"] is False
    assert payload["currency"] == "USD"
    assert payload["platforms"] == ["windows"]
    assert payload["genres"] == ["Action", "RPG"]
    assert payload["developers"] == ["FromSoftware, Inc."]
    assert payload["publishers"] == ["FromSoftware, Inc.", "Bandai Namco Entertainment"]
    assert payload["release_date"] == "Feb 24, 2022"
    assert payload["coming_soon"] is False
    assert payload["metacritic_score"] == 94
    assert payload["recommendations"] == 840162
    assert payload["required_age"] == 16
    assert payload["store_url"] == f"https://store.steampowered.com/app/{ELDEN_RING}/"
    assert payload["source"] == "steam"
    assert payload["unknown_fields"] == []


def test_build_game_reports_a_free_game_as_zero_price():
    payload = build_game(
        game_record(name="Dota 2", is_free=True, price_overview=None), DOTA2, "us"
    )
    assert payload["is_free"] is True
    assert payload["price"]["final"] == 0.0
    assert "price_note" not in payload


def test_build_game_marks_an_unpriced_region():
    payload = build_game(game_record(is_free=False, price_overview=None), ELDEN_RING, "ru")
    assert payload["price"] is None
    assert payload["price_note"] == "not_available_in_region"
    assert payload["unknown_fields"] == ["price"]


def test_build_game_lists_missing_fields():
    payload = build_game({"name": "Mystery"}, 42, "us")
    assert set(payload["unknown_fields"]) == {
        "type",
        "price",
        "platforms",
        "genres",
        "release_date",
    }


def test_build_game_maps_platforms_in_a_stable_order():
    record = game_record(platforms={"linux": True, "mac": True, "windows": True})
    assert build_game(record, 1, "us")["platforms"] == ["windows", "macos", "linux"]


def test_build_game_tolerates_wrong_types():
    payload = build_game(
        {
            "name": 5,
            "genres": "Action",
            "platforms": ["windows"],
            "release_date": [],
            "metacritic": 94,
            "recommendations": "many",
            "developers": "Valve",
        },
        1,
        "us",
    )
    assert payload["name"] is None
    assert payload["genres"] == []
    assert payload["platforms"] == []
    assert payload["release_date"] is None
    assert payload["metacritic_score"] is None
    assert payload["recommendations"] is None
    assert payload["developers"] == []


# ------------------------------------------------------------ build_search_item


def test_build_search_item_derives_the_discount():
    row = build_search_item(
        {
            "id": 730,
            "name": "Counter-Strike 2",
            "type": "app",
            "price": {"currency": "USD", "initial": 1499, "final": 749},
            "platforms": {"windows": True, "mac": False, "linux": True},
            "metascore": "82",
        },
        "us",
    )
    assert row["app_id"] == 730
    assert row["price"]["discount_percent"] == 50
    assert row["price"]["is_discounted"] is True
    assert row["platforms"] == ["windows", "linux"]
    assert row["metacritic_score"] == 82
    assert "price_note" not in row


def test_build_search_item_marks_a_missing_price():
    row = build_search_item({"id": 570, "name": "Dota 2", "price": None}, "us")
    assert row["price"] is None
    assert row["price_note"] == "no_price_listed"


def test_build_search_item_survives_junk_id():
    row = build_search_item({"name": "X", "id": "abc"}, "us")
    assert row["app_id"] is None
    assert row["store_url"] is None


# --------------------------------------------------------------- build_special


def test_build_special_computes_saving_and_expiry():
    deal = build_special(
        {
            "id": 3240220,
            "name": "SOME GAME",
            "currency": "USD",
            "discount_percent": 56,
            "original_price": 4499,
            "final_price": 1979,
            "discount_expiration": 1767636000,
        },
        "us",
    )
    assert deal["original_price"] == pytest.approx(44.99)
    assert deal["final_price"] == pytest.approx(19.79)
    assert deal["saving"] == pytest.approx(25.2)
    assert deal["discount_ends_at"] == "2026-01-05T18:00:00Z"
    assert deal["store_url"] == "https://store.steampowered.com/app/3240220/"


def test_build_special_without_expiry():
    deal = build_special({"id": 1, "original_price": 1000, "final_price": 500}, "us")
    assert deal["discount_ends_at"] is None
    assert deal["saving"] == pytest.approx(5.0)


# ---------------------------------------------------------------------- client


def test_client_reads_one_app():
    client = constant_client(app_payload(ELDEN_RING, game_record()))

    async def run() -> tuple[bool, dict | None]:
        return await client.app_details(ELDEN_RING, "us")

    success, data = asyncio.run(run())
    assert success is True
    assert data is not None and data["name"] == "ELDEN RING"


def test_client_accepts_the_list_shaped_data():
    client = constant_client({"1245620": {"success": True, "data": [game_record()]}})

    async def run() -> dict | None:
        return (await client.app_details(ELDEN_RING, "us"))[1]

    assert (asyncio.run(run()) or {}).get("name") == "ELDEN RING"


def test_client_accepts_empty_list_data_as_missing():
    client = constant_client({"570": {"success": True, "data": []}})

    async def run() -> tuple[bool, dict | None]:
        return await client.app_details(DOTA2, "us")

    assert asyncio.run(run()) == (True, None)


def test_client_rejects_a_null_body():
    client = constant_client(None)
    with pytest.raises(UpstreamError) as excinfo:
        asyncio.run(client.app_details(1, "us"))
    assert excinfo.value.code == "bad_payload"


def test_client_rejects_a_missing_entry():
    client = constant_client({"something": "else"})
    with pytest.raises(UpstreamError) as excinfo:
        asyncio.run(client.app_details(1, "us"))
    assert excinfo.value.code == "bad_payload"


def test_lookup_returns_the_payload_for_a_known_app():
    client = constant_client(app_payload(ELDEN_RING, game_record()))

    async def run() -> GameLookup:
        return await client.lookup(ELDEN_RING, "us")

    result = asyncio.run(run())
    assert result.status == "ok"
    assert result.payload is not None and result.payload["currency"] == "USD"


def test_lookup_detects_a_region_lock_by_asking_the_fallback_region():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        country = request.url.params.get("cc")
        calls.append(country or "")
        if country == "ru":
            return json_response(app_payload(CYBERPUNK, None, success=False))
        return json_response(app_payload(CYBERPUNK, game_record()))

    client = make_client(handler)

    async def run() -> GameLookup:
        return await client.lookup(CYBERPUNK, "ru")

    result = asyncio.run(run())
    assert result.status == "not_available_in_region"
    assert calls == ["ru", "us"]


def test_lookup_reports_not_found_when_the_fallback_misses_too():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("cc") or "")
        return json_response(app_payload(999999999, None, success=False))

    client = make_client(handler)

    async def run() -> GameLookup:
        return await client.lookup(999999999, "ru")

    assert asyncio.run(run()).status == "not_found"
    assert calls == ["ru", "us"]


def test_lookup_does_not_double_call_for_the_default_region():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return json_response(app_payload(999999999, None, success=False))

    client = make_client(handler)

    async def run() -> GameLookup:
        return await client.lookup(999999999, "us")

    assert asyncio.run(run()).status == "not_found"
    assert len(calls) == 1


def test_client_caches_repeated_lookups():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return json_response(app_payload(ELDEN_RING, game_record()))

    client = make_client(handler)

    async def twice() -> None:
        await client.app_details(ELDEN_RING, "us")
        await client.app_details(ELDEN_RING, "us")

    asyncio.run(twice())
    assert len(calls) == 1


def test_client_retries_a_server_error_then_succeeds():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, text="unavailable")
        return json_response(app_payload(ELDEN_RING, game_record()))

    client = make_client(handler, attempts=2)

    async def run() -> GameLookup:
        return await client.lookup(ELDEN_RING, "us")

    assert asyncio.run(run()).status == "ok"
    assert len(calls) == 2


def test_client_does_not_retry_a_client_error():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, text="bad request")

    client = make_client(handler, attempts=3)
    with pytest.raises(UpstreamError):
        asyncio.run(client.app_details(1, "us"))
    assert len(calls) == 1


def test_client_uses_the_documented_endpoints():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("appdetails"):
            return json_response(app_payload(ELDEN_RING, game_record()))
        if request.url.path.endswith("storesearch/"):
            return json_response(search_payload([]))
        return json_response(specials_payload([]))

    client = make_client(handler)

    async def run() -> None:
        await client.app_details(ELDEN_RING, "de")
        await client.search("z", "de", 5)
        await client.specials("de", 5)

    asyncio.run(run())
    assert seen == [
        "/api/appdetails",
        "/api/storesearch/",
        "/api/featuredcategories",
    ]


def test_search_applies_the_limit_and_reports_totals():
    items = [{"id": i, "name": f"Game {i}", "price": None} for i in range(1, 9)]
    client = constant_client(search_payload(items, total=42))

    async def run() -> dict:
        return await client.search("game", "us", 3)

    payload = asyncio.run(run())
    assert payload["count"] == 3
    assert payload["total_matches"] == 42
    assert [row["app_id"] for row in payload["results"]] == [1, 2, 3]


def test_search_rejects_a_payload_without_items():
    client = constant_client({"total": 0})
    with pytest.raises(UpstreamError) as excinfo:
        asyncio.run(client.search("game", "us", 3))
    assert excinfo.value.code == "bad_payload"


def test_specials_sort_by_discount():
    items = [
        {"id": 1, "name": "A", "currency": "USD", "discount_percent": 20, "original_price": 1000, "final_price": 800},
        {"id": 2, "name": "B", "currency": "USD", "discount_percent": 75, "original_price": 1000, "final_price": 250},
        {"id": 3, "name": "C", "currency": "USD", "discount_percent": 50, "original_price": 1000, "final_price": 500},
    ]
    client = constant_client(specials_payload(items))

    async def run() -> dict:
        return await client.specials("us", 2)

    payload = asyncio.run(run())
    assert [deal["app_id"] for deal in payload["deals"]] == [2, 3]
    assert payload["currency"] == "USD"


def test_specials_find_the_section_by_id_when_keys_are_numeric():
    client = constant_client(
        {
            "0": {"id": "cat_specials", "name": "Specials", "items": [{"id": 9, "discount_percent": 30}]},
            "1": {"id": "cat_top_sellers", "name": "Top Sellers", "items": []},
        }
    )

    async def run() -> dict:
        return await client.specials("us", 5)

    assert [deal["app_id"] for deal in asyncio.run(run())["deals"]] == [9]


def test_specials_reject_a_payload_without_specials():
    client = constant_client({"top_sellers": {"items": []}})
    with pytest.raises(UpstreamError) as excinfo:
        asyncio.run(client.specials("us", 5))
    assert excinfo.value.code == "bad_payload"


# ------------------------------------------------------------------- tool layer


def test_get_game_price_tool_returns_a_full_record():
    async def run() -> dict:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool(
                    "get_game_price", {"app_id": ELDEN_RING, "country": "us"}
                )
            )

    data = asyncio.run(run())
    assert data["name"] == "ELDEN RING"
    assert data["price"]["final"] == pytest.approx(59.99)
    assert data["fetched_at"].endswith("Z")


def test_get_game_price_tool_accepts_a_region_name():
    async def run() -> dict:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool(
                    "get_game_price", {"app_id": ELDEN_RING, "country": "Germany"}
                )
            )

    data = asyncio.run(run())
    assert data["country"] == "de"
    assert data["region_name"] == "Germany"


def test_get_game_price_tool_rejects_an_unknown_region():
    async def run() -> dict:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool(
                    "get_game_price", {"app_id": ELDEN_RING, "country": "mars"}
                )
            )

    assert asyncio.run(run())["error"] == "invalid_country"


def test_get_game_price_tool_rejects_an_empty_region():
    async def run() -> dict:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool("get_game_price", {"app_id": ELDEN_RING, "country": ""})
            )

    assert asyncio.run(run())["error"] == "empty_country"


def test_get_game_price_tool_reports_a_region_lock():
    def handler(request: httpx.Request) -> httpx.Response:
        country = request.url.params.get("cc")
        if country == "ru":
            return json_response(app_payload(CYBERPUNK, None, success=False))
        return json_response(app_payload(CYBERPUNK, game_record()))

    async def run() -> dict:
        async with session("en", make_client(handler)) as mcp:
            return result_data(
                await mcp.call_tool(
                    "get_game_price", {"app_id": CYBERPUNK, "country": "ru"}
                )
            )

    data = asyncio.run(run())
    assert data["error"] == "not_available_in_region"
    assert data["app_id"] == CYBERPUNK
    assert data["country"] == "ru"


def test_get_game_price_tool_reports_not_found():
    async def run() -> dict:
        client = constant_client(app_payload(999999999, None, success=False))
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool("get_game_price", {"app_id": 999999999, "country": "us"})
            )

    data = asyncio.run(run())
    assert data["error"] == "not_found"
    assert data["app_id"] == 999999999


def test_get_game_price_tool_maps_a_throttled_upstream():
    async def run() -> dict:
        client = constant_client({"detail": "slow down"}, status=429)
        async with session("en", client) as mcp:
            return result_data(
                await mcp.call_tool("get_game_price", {"app_id": ELDEN_RING, "country": "us"})
            )

    data = asyncio.run(run())
    assert data["error"] == "rate_limited"
    assert data["upstream_status"] == 429


def test_search_tool_returns_results():
    items = [{"id": 730, "name": "Counter-Strike 2", "price": {"currency": "USD", "initial": 0, "final": 0}}]

    async def run() -> dict:
        client = constant_client(search_payload(items))
        async with session("en", client) as mcp:
            return result_data(await mcp.call_tool("search_games", {"query": "counter"}))
    data = asyncio.run(run())
    assert data["count"] == 1
    assert data["results"][0]["app_id"] == 730


def test_search_tool_explains_an_empty_result_set():
    async def run() -> dict:
        client = constant_client(search_payload([]))
        async with session("en", client) as mcp:
            return result_data(await mcp.call_tool("search_games", {"query": "qzxwv"}))

    data = asyncio.run(run())
    assert data["count"] == 0
    assert "qzxwv" in data["message"]


def test_search_tool_rejects_a_blank_query():
    async def run() -> dict:
        client = constant_client(search_payload([]))
        async with session("en", client) as mcp:
            return result_data(await mcp.call_tool("search_games", {"query": "   "}))

    assert asyncio.run(run())["error"] == "empty_query"


def test_list_specials_tool_returns_deals():
    items = [{"id": 5, "name": "Deal", "discount_percent": 60, "original_price": 2000, "final_price": 800}]

    async def run() -> dict:
        client = constant_client(specials_payload(items))
        async with session("en", client) as mcp:
            return result_data(await mcp.call_tool("list_specials", {"country": "us"}))

    data = asyncio.run(run())
    assert data["count"] == 1
    assert data["deals"][0]["discount_percent"] == 60


def test_tool_schemas_are_read_only_and_bounded():
    async def run() -> dict:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            tools = (await mcp.list_tools()).tools
            return {tool.name: tool for tool in tools}

    tools = asyncio.run(run())
    assert set(tools) == {"search_games", "get_game_price", "list_specials"}
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.inputSchema["type"] == "object"
    assert tools["search_games"].inputSchema["required"] == ["query"]
    assert tools["get_game_price"].inputSchema["required"] == ["app_id"]
    limit = tools["search_games"].inputSchema["properties"]["limit"]
    assert limit["maximum"] == 25
    assert limit["minimum"] == 1


def test_app_id_below_one_is_rejected_by_the_schema():
    async def run() -> bool:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session("en", client) as mcp:
            result = await mcp.call_tool("get_game_price", {"app_id": 0})
            return bool(getattr(result, "isError", False))

    assert asyncio.run(run()) is True


def test_tool_descriptions_follow_the_locale():
    async def run(locale: str) -> str:
        client = constant_client(app_payload(ELDEN_RING, game_record()))
        async with session(locale, client) as mcp:
            tools = (await mcp.list_tools()).tools
            return next(t.description or "" for t in tools if t.name == "get_game_price")

    english = asyncio.run(run("en"))
    russian = asyncio.run(run("ru"))
    assert english != russian
    assert any("\u0400" <= ch <= "\u04ff" for ch in russian)


def test_error_messages_follow_the_locale():
    async def run(locale: str) -> dict:
        client = constant_client(app_payload(999999999, None, success=False))
        async with session(locale, client) as mcp:
            return result_data(
                await mcp.call_tool("get_game_price", {"app_id": 999999999, "country": "us"})
            )

    english = asyncio.run(run("en"))
    spanish = asyncio.run(run("es"))
    assert english["error"] == spanish["error"] == "not_found"
    assert english["message"] != spanish["message"]


# ------------------------------------------------------------------ localization


def test_every_locale_has_the_same_keys():
    english = set(MESSAGES["en"])
    for code in ("es", "ru"):
        assert set(MESSAGES[code]) == english, f"{code} is missing keys"


def test_detect_locale_handles_posix_values(monkeypatch):
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    monkeypatch.delenv("MCP_LOCALE", raising=False)
    monkeypatch.delenv("LANGUAGE", raising=False)
    assert detect_locale() == "ru"


def test_detect_locale_prefers_mcp_locale(monkeypatch):
    monkeypatch.setenv("MCP_LOCALE", "es")
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert detect_locale() == "es"


def test_detect_locale_defaults_to_english(monkeypatch):
    for name in ("MCP_LOCALE", "LANGUAGE", "LANG"):
        monkeypatch.delenv(name, raising=False)
    assert detect_locale() == "en"


def test_unknown_locale_falls_back_to_english():
    assert Locale("de").code == "en"


def test_locale_reads_environment_when_no_code_given(monkeypatch):
    monkeypatch.setenv("MCP_LOCALE", "es")
    assert Locale().code == "es"


def test_locale_never_raises_for_unknown_keys_or_arguments():
    locale = Locale("en")
    assert locale.t("no.such.key") == "no.such.key"
    assert "{value}" in locale.t("err.invalid_app_id")


def test_result_payloads_are_json_serialisable():
    payload = build_game(game_record(), ELDEN_RING, "us")
    assert json.loads(json.dumps(payload))["app_id"] == ELDEN_RING
