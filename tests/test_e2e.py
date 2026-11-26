"""End-to-end tests: a real ``python -m mcp_steam_price`` process over stdio.

These prove the published entry point works as an MCP server: handshake, tool
discovery, schemas, argument validation and payload shape.
"""

from __future__ import annotations

import json

import pytest

from .helpers import ELDEN_RING
from .mcp_stdio import StdioServer

pytestmark = pytest.mark.e2e


def body(raw: dict) -> dict:
    """Unwrap a structured result, tolerating FastMCP's ``{"result": ...}`` form."""
    if isinstance(raw, dict) and set(raw) == {"result"} and isinstance(raw["result"], dict):
        return raw["result"]
    return raw


@pytest.fixture()
def server():
    with StdioServer() as running:
        running.initialize()
        yield running


def test_handshake_returns_protocol_and_server_info(server):
    result = server.initialize()
    assert "protocolVersion" in result["result"]
    assert result["result"]["serverInfo"]["name"] == "steam-game-price"


def test_server_advertises_three_read_only_tools(server):
    tools = {tool["name"]: tool for tool in server.list_tools()}
    assert set(tools) == {"search_games", "get_game_price", "list_specials"}

    for tool in tools.values():
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"

    search = tools["search_games"]["inputSchema"]
    assert search["required"] == ["query"]
    assert search["properties"]["country"]["default"] == "us"
    assert search["properties"]["limit"]["maximum"] == 25

    price = tools["get_game_price"]["inputSchema"]
    assert price["required"] == ["app_id"]
    assert price["properties"]["app_id"]["minimum"] == 1

    specials = tools["list_specials"]["inputSchema"]
    assert specials["properties"]["limit"]["maximum"] == 50


def test_instructions_are_exposed_during_handshake(server):
    assert server.initialize()["result"].get("instructions")


def test_unknown_region_is_rejected_without_a_network_call(server):
    data = body(
        server.payload("get_game_price", {"app_id": ELDEN_RING, "country": "mars"})
    )
    assert data["error"] == "invalid_country"


def test_blank_query_is_rejected_without_a_network_call(server):
    data = body(server.payload("search_games", {"query": "  "}))
    assert data["error"] == "empty_query"


def test_app_id_below_one_is_rejected_by_the_schema(server):
    result = server.call_tool("get_game_price", {"app_id": 0})
    assert result.get("isError") is True


def test_locale_switches_through_the_environment():
    with StdioServer(env={"MCP_LOCALE": "ru"}) as server:
        server.initialize()
        tools = {tool["name"]: tool for tool in server.list_tools()}
        description = tools["get_game_price"]["description"]
        assert any("\u0400" <= ch <= "\u04ff" for ch in description)
        data = body(server.payload("get_game_price", {"app_id": ELDEN_RING, "country": "mars"}))
        assert data["error"] == "invalid_country"
        assert any("\u0400" <= ch <= "\u04ff" for ch in data["message"])


def test_english_is_the_default_locale():
    with StdioServer() as server:
        server.initialize()
        tools = {tool["name"]: tool for tool in server.list_tools()}
        description = tools["get_game_price"]["description"].lower()
        assert "price" in description
        assert not any("\u0400" <= ch <= "\u04ff" for ch in description)


@pytest.mark.live
def test_live_price_for_a_known_app(server):
    data = body(
        server.payload("get_game_price", {"app_id": ELDEN_RING, "country": "us"})
    )
    if data.get("error") == "rate_limited":  # pragma: no cover - upstream throttle
        pytest.skip("Steam throttled the test run")
    assert "error" not in data, data
    assert data["name"]
    assert data["country"] == "us"
    assert data["price"]["currency"]
    assert data["store_url"].endswith(f"/app/{ELDEN_RING}/")


@pytest.mark.live
def test_live_search_then_price_flow(server):
    found = body(server.payload("search_games", {"query": "portal 2", "limit": 5}))
    if found.get("error") == "rate_limited":  # pragma: no cover
        pytest.skip("Steam throttled the test run")
    assert found["count"] >= 1
    app_id = found["results"][0]["app_id"]
    assert isinstance(app_id, int) and app_id > 0

    price = body(server.payload("get_game_price", {"app_id": app_id, "country": "us"}))
    assert price.get("app_id") == app_id


@pytest.mark.live
def test_live_specials_are_sorted_by_discount(server):
    data = body(server.payload("list_specials", {"country": "us", "limit": 5}))
    if data.get("error") == "rate_limited":  # pragma: no cover
        pytest.skip("Steam throttled the test run")
    assert data["count"] >= 1
    percents = [deal["discount_percent"] for deal in data["deals"]]
    assert percents == sorted(percents, reverse=True)
    assert all(percent > 0 for percent in percents)


@pytest.mark.live
def test_live_region_lock_is_reported_as_data(server):
    data = body(
        server.payload("get_game_price", {"app_id": 1091500, "country": "ru"})
    )
    if data.get("error") == "rate_limited":  # pragma: no cover
        pytest.skip("Steam throttled the test run")
    # Cyberpunk 2077 has no Russian store page; if it ever returns, that is fine
    # too, but the error must never be a stack trace.
    assert data.get("error") in {None, "not_available_in_region", "not_found"}
    json.dumps(data, allow_nan=False)
