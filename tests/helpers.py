"""Shared fixtures: a mocked Steam Store and an in-memory MCP session.

Unit tests never touch the network: a fake ``httpx`` transport stands in for the
store, and :func:`session` connects a real MCP client to the real server object
over in-memory streams, so schemas, validation and serialisation are exercised
without spawning a process.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_steam_price.core import HttpClient
from mcp_steam_price.i18n import Locale
from mcp_steam_price.server import build_server
from mcp_steam_price.steam import SteamClient

Handler = Callable[[httpx.Request], httpx.Response]

#: ELDEN RING; stable app id used across all three suites.
ELDEN_RING = 1245620
#: Dota 2; a free game.
DOTA2 = 570
#: Cyberpunk 2077; not sold in the Russian store.
CYBERPUNK = 1091500


def json_response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def app_payload(
    app_id: int, data: dict[str, Any] | None, *, success: bool = True
) -> dict[str, Any]:
    """The ``appdetails`` envelope for one app."""
    entry: dict[str, Any] = {"success": success}
    if data is not None:
        entry["data"] = data
    return {str(app_id): entry}


def search_payload(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {"total": len(items) if total is None else total, "items": items}


def specials_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "specials": {"id": "specials", "name": "Specials", "items": items},
        "top_sellers": {"id": "top_sellers", "name": "Top Sellers", "items": []},
    }


def game_record(**overrides: Any) -> dict[str, Any]:
    """A minimal but realistic ``appdetails`` record."""
    record: dict[str, Any] = {
        "name": "ELDEN RING",
        "type": "game",
        "is_free": False,
        "price_overview": {
            "currency": "USD",
            "initial": 5999,
            "final": 5999,
            "discount_percent": 0,
            "final_formatted": "$59.99",
            "initial_formatted": "",
        },
        "platforms": {"windows": True, "mac": False, "linux": False},
        "genres": [{"id": "1", "description": "Action"}, {"id": "3", "description": "RPG"}],
        "developers": ["FromSoftware, Inc."],
        "publishers": ["FromSoftware, Inc.", "Bandai Namco Entertainment"],
        "release_date": {"coming_soon": False, "date": "Feb 24, 2022"},
        "metacritic": {"score": 94, "url": "https://www.metacritic.com/game/elden-ring/"},
        "recommendations": {"total": 840162},
        "required_age": "16",
        "short_description": "THE NEW FANTASY ACTION RPG.",
    }
    record.update(overrides)
    return record


def make_client(
    handler: Handler, *, attempts: int = 2, base_delay: float = 0.01
) -> SteamClient:
    """A :class:`SteamClient` wired to ``handler`` instead of the network."""
    http = HttpClient(
        "https://store.steampowered.com",
        transport=httpx.MockTransport(handler),
        attempts=attempts,
        base_delay=base_delay,
        max_delay=0.02,
    )
    return SteamClient(http)


def constant_client(payload: Any, status: int = 200) -> SteamClient:
    return make_client(lambda request: json_response(payload, status))


def result_data(result: Any) -> dict[str, Any]:
    """Read a tool result as a plain dict, whatever FastMCP wrapped it in."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        if set(structured) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    text = "".join(
        getattr(block, "text", "")
        for block in getattr(result, "content", [])
        if getattr(block, "type", "") == "text"
    )
    return json.loads(text)


@asynccontextmanager
async def session(
    locale: str = "en", client: SteamClient | None = None
) -> AsyncIterator[Any]:
    """Connect an in-memory MCP client to a server built with ``client``."""
    server: FastMCP = build_server(Locale(locale), client)
    async with create_connected_server_and_client_session(server) as client_session:
        yield client_session
