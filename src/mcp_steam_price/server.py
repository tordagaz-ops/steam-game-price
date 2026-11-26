"""MCP server: Steam Store prices.

Three read-only tools over three cached public endpoints:

* ``search_games``     — title to app id, with prices for a region
* ``get_game_price``   — one app in one store region, with discount and metadata
* ``list_specials``    — what is discounted right now, biggest discount first

Note: annotations are evaluated eagerly here on purpose. Tool signatures are
built inside :func:`build_server` and reference the locale lookup closure, which
``from __future__ import annotations`` would turn into unresolvable strings.
"""

import os
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .core import UpstreamError, clamp, err
from .i18n import Locale
from .regions import CountryFormatError, DEFAULT_COUNTRY, normalize_country
from .steam import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SPECIALS_LIMIT,
    MAX_SEARCH_LIMIT,
    MAX_SPECIALS_LIMIT,
    AppIdFormatError,
    SteamClient,
    normalize_app_id,
)

__all__ = ["build_server", "main"]

SERVER_NAME = "steam-game-price"

_ERROR_KEYS = (
    "rate_limited",
    "timeout",
    "network_error",
    "upstream_unavailable",
    "upstream_rejected",
    "bad_payload",
)


def _upstream_payload(exc: UpstreamError, locale: Locale, **extra: Any) -> dict[str, Any]:
    """Translate a transport failure into a stable, localized payload."""
    code = exc.code
    # Steam signals throttling with 429, which the shared client reports as
    # "unavailable"; for this API "rate limited" is the more useful answer.
    if code == "upstream_unavailable" and exc.status == 429:
        code = "rate_limited"
    key = code if code in _ERROR_KEYS else "upstream_unavailable"
    fields: dict[str, Any] = dict(extra)
    if exc.status is not None:
        fields["upstream_status"] = exc.status
    if exc.detail:
        fields["detail"] = exc.detail[:200]
    return err(code, locale.t(f"err.{key}", **fields), **fields)


def _country_or_error(raw: object, locale: Locale) -> tuple[str | None, dict[str, Any] | None]:
    try:
        return normalize_country(raw), None
    except CountryFormatError as exc:
        if exc.code == "empty":
            return None, err("empty_country", locale.t("err.empty_country"))
        return None, err(
            "invalid_country",
            locale.t("err.invalid_country", country=str(raw)[:32]),
            input=str(raw)[:32],
        )


def build_server(
    locale: Locale | None = None, client: SteamClient | None = None
) -> FastMCP:
    """Create the FastMCP server with descriptions rendered in ``locale``."""
    locale = locale or Locale()
    steam = client or SteamClient()
    t = locale.t

    server = FastMCP(name=SERVER_NAME, instructions=t("server.instructions"))

    # ---------------------------------------------------------------- tools
    @server.tool(
        name="search_games",
        description=t("tool.search_games.description"),
        annotations=ToolAnnotations(
            title=t("tool.search_games.title"),
            readOnlyHint=True,
            openWorldHint=True,
        ),
    )
    async def search_games(
        query: Annotated[str, Field(description=t("param.query"))],
        country: Annotated[str, Field(description=t("param.country"))] = DEFAULT_COUNTRY,
        limit: Annotated[
            int, Field(description=t("param.limit"), ge=1, le=MAX_SEARCH_LIMIT)
        ] = DEFAULT_SEARCH_LIMIT,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if not text:
            return err("empty_query", t("err.empty_query"))

        code, failure = _country_or_error(country, locale)
        if failure is not None:
            return failure

        try:
            payload = await steam.search(text, code, clamp(limit, 1, MAX_SEARCH_LIMIT))
        except UpstreamError as exc:
            return _upstream_payload(exc, locale, country=code)

        payload["limit"] = clamp(limit, 1, MAX_SEARCH_LIMIT)
        if not payload["results"]:
            payload["message"] = t("msg.no_results", query=text)
        return payload

    @server.tool(
        name="get_game_price",
        description=t("tool.get_game_price.description"),
        annotations=ToolAnnotations(
            title=t("tool.get_game_price.title"),
            readOnlyHint=True,
            openWorldHint=True,
        ),
    )
    async def get_game_price(
        app_id: Annotated[int, Field(description=t("param.app_id"), ge=1)],
        country: Annotated[str, Field(description=t("param.country"))] = DEFAULT_COUNTRY,
    ) -> dict[str, Any]:
        try:
            app = normalize_app_id(app_id)
        except AppIdFormatError as exc:
            if exc.code == "empty":
                return err("empty_app_id", t("err.empty_app_id"))
            return err(
                "invalid_app_id",
                t("err.invalid_app_id", value=str(app_id)[:32]),
                input=str(app_id)[:32],
            )

        code, failure = _country_or_error(country, locale)
        if failure is not None:
            return failure

        try:
            result = await steam.lookup(app, code)
        except UpstreamError as exc:
            return _upstream_payload(exc, locale, app_id=app, country=code)

        if result.status == "not_available_in_region":
            return err(
                "not_available_in_region",
                t(
                    "err.not_available_in_region",
                    app_id=app,
                    country=code,
                ),
                app_id=app,
                country=code,
            )
        if result.status != "ok" or result.payload is None:
            return err(
                "not_found",
                t("err.not_found", app_id=app),
                app_id=app,
                country=code,
            )

        payload = result.payload
        if payload.get("coming_soon"):
            payload["message"] = t("msg.coming_soon")
        if payload.get("price_note"):
            payload["price_note_message"] = t("msg.price_not_available")
        return payload

    @server.tool(
        name="list_specials",
        description=t("tool.list_specials.description"),
        annotations=ToolAnnotations(
            title=t("tool.list_specials.title"),
            readOnlyHint=True,
            openWorldHint=True,
        ),
    )
    async def list_specials(
        country: Annotated[str, Field(description=t("param.country"))] = DEFAULT_COUNTRY,
        limit: Annotated[
            int, Field(description=t("param.limit"), ge=1, le=MAX_SPECIALS_LIMIT)
        ] = DEFAULT_SPECIALS_LIMIT,
    ) -> dict[str, Any]:
        code, failure = _country_or_error(country, locale)
        if failure is not None:
            return failure

        try:
            payload = await steam.specials(code, clamp(limit, 1, MAX_SPECIALS_LIMIT))
        except UpstreamError as exc:
            return _upstream_payload(exc, locale, country=code)
        payload["limit"] = clamp(limit, 1, MAX_SPECIALS_LIMIT)
        return payload

    return server


def main() -> None:
    """Entry point: stdio by default, streamable HTTP when ``MCP_TRANSPORT=http``."""
    locale = Locale()
    server = build_server(locale)
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower().replace("_", "-")
    if transport in {"http", "streamable-http"}:
        server.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
        server.settings.port = int(os.getenv("MCP_PORT", "8000"))
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
