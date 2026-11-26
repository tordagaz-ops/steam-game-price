"""Live tests against the real Steam Store API.

Run with ``pytest -m live``. They use well-known apps, so a failure means either
the store changed its contract or the network is gone — both worth knowing
before a release. Steam throttles aggressively, so a throttled run skips rather
than fails.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_steam_price.core import UpstreamError
from mcp_steam_price.steam import SteamClient

from .helpers import CYBERPUNK, DOTA2, ELDEN_RING

pytestmark = pytest.mark.live


def run(coro_factory):
    """Run one coroutine with a fresh client, skipping on upstream throttling."""

    async def wrapper():
        client = SteamClient()
        try:
            return await coro_factory(client)
        finally:
            await client.aclose()

    try:
        return asyncio.run(wrapper())
    except UpstreamError as exc:  # pragma: no cover - network dependent
        pytest.skip(f"Steam unavailable: {exc.code} {exc.detail}")


def test_live_lookup_of_a_paid_game():
    result = run(lambda client: client.lookup(ELDEN_RING, "us"))
    assert result.status == "ok"
    payload = result.payload
    assert payload is not None
    assert payload["name"] == "ELDEN RING"
    assert payload["type"] == "game"
    assert payload["is_free"] is False
    assert payload["price"] is not None
    assert payload["price"]["currency"] == "USD"
    assert payload["price"]["final"] and payload["price"]["final"] > 0
    assert payload["release_date"]
    assert payload["unknown_fields"] == []


def test_live_lookup_of_a_free_game():
    payload = run(lambda client: client.lookup(DOTA2, "us")).payload
    assert payload is not None
    assert payload["is_free"] is True
    assert payload["price"] is not None
    assert payload["price"]["final"] == 0.0


def test_live_prices_differ_between_regions():
    us = run(lambda client: client.lookup(ELDEN_RING, "us")).payload
    ru = run(lambda client: client.lookup(ELDEN_RING, "ru")).payload
    assert us is not None and ru is not None
    if ru.get("price") is None:
        pytest.skip("this app has no Russian store price today")
    assert us["price"]["currency"] != ru["price"]["currency"]
    assert us["price"]["final"] != ru["price"]["final"]


def test_live_region_lock_is_detected():
    result = run(lambda client: client.lookup(CYBERPUNK, "ru"))
    # If the store ever sells it in Russia again, the lookup must be "ok".
    assert result.status in {"not_available_in_region", "ok"}


def test_live_unknown_app_is_not_found():
    assert run(lambda client: client.lookup(999_999_999, "us")).status == "not_found"


def test_live_search_finds_a_well_known_title():
    payload = run(lambda client: client.search("portal 2", "us", 5))
    assert payload["count"] >= 1
    names = [row["name"] for row in payload["results"]]
    assert any("Portal 2" in name for name in names)


def test_live_search_returns_no_results_for_nonsense():
    payload = run(lambda client: client.search("qzxwvbnmplk", "us", 5))
    assert payload["count"] == 0
    assert payload["total_matches"] in (0, None)


def test_live_specials_have_discounts_and_end_dates():
    payload = run(lambda client: client.specials("us", 10))
    assert payload["count"] >= 1
    for deal in payload["deals"]:
        assert deal["discount_percent"] > 0
        assert deal["final_price"] is not None
        assert deal["original_price"] is not None
        assert deal["final_price"] < deal["original_price"]
        assert deal["store_url"].startswith("https://store.steampowered.com/app/")
