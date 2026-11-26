"""Localization: English (default), Spanish, Russian.

The active language is resolved at start-up from, in order:
``MCP_LOCALE``, ``LANGUAGE``, ``LANG``. Anything unsupported falls back to
English, so the server never fails because of a locale.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

__all__ = ["DEFAULT_LOCALE", "SUPPORTED_LOCALES", "Locale", "detect_locale"]

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "es", "ru")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "server.instructions": (
            "Live Steam Store prices. search_games finds an app id from a name, "
            "get_game_price returns the current price, discount and release data "
            "for one app in one store region, and list_specials lists what is on "
            "sale right now. Prices are region-specific: pass a country code such "
            "as 'ru' or 'us' when the user's region is known. No API key."
        ),
        "tool.get_game_price.title": "Get Steam game price",
        "tool.search_games.title": "Search Steam games",
        "tool.list_specials.title": "List Steam discounts",
        "tool.get_game_price.description": (
            "Return the current Steam Store price for one app: final and list "
            "price, discount percent, currency, whether it is free, platforms, "
            "genres, release date, developer, publisher, Metacritic score and "
            "recommendation count. Prices depend on the store region. A brand-new "
            "store page may not be indexed yet. Example: app_id=1245620, "
            "country='us'."
        ),
        "tool.search_games.description": (
            "Search the Steam Store by title and return matching apps with their "
            "app ids and current prices in the chosen region. Use this first when "
            "you only know the game's name, then call get_game_price with the app "
            "id for full details. Example: query='elden ring', country='ru'."
        ),
        "tool.list_specials.description": (
            "List games currently discounted in the Steam Store for a region, "
            "sorted by discount size, with original and final price and when the "
            "discount ends. Example: country='us', limit=10."
        ),
        "param.app_id": (
            "Steam app id as a number, for example 1245620 for ELDEN RING. Find it "
            "with search_games if you only know the title."
        ),
        "param.query": "Game title to search for, for example 'elden ring' or 'portal 2'.",
        "param.country": (
            "Store region as a two-letter code: 'us' (default), 'ru', 'de', 'br', "
            "'kz', 'ua', 'tr', 'jp'. Prices differ per region. Full names such as "
            "'Germany' are also accepted."
        ),
        "param.limit": "Maximum number of results to return (1-25 for search, 1-50 for discounts).",
        "err.empty_app_id": "No app id was given. Pass a Steam app id such as 1245620.",
        "err.invalid_app_id": (
            "'{value}' is not a Steam app id. Expected a positive number such as "
            "1245620."
        ),
        "err.empty_query": "The search query is empty. Pass a game title such as 'portal 2'.",
        "err.empty_country": "No region was given. Pass a two-letter code such as 'us'.",
        "err.invalid_country": (
            "'{country}' is not a store region. Expected a two-letter country code "
            "such as 'us', 'de' or 'ru'."
        ),
        "err.not_found": (
            "Steam has no store page for app id {app_id}. Check the id: it may be a "
            "removed, unreleased or non-store app."
        ),
        "err.not_available_in_region": (
            "App id {app_id} exists on Steam but is not sold in the '{country}' "
            "store region, so it has no price there. Try another region."
        ),
        "err.rate_limited": (
            "Steam is rate limiting this server. Wait a few seconds and try again."
        ),
        "err.timeout": "Steam did not answer in time. Try again.",
        "err.network_error": "Could not reach the Steam Store. Check connectivity and retry.",
        "err.upstream_unavailable": "The Steam Store is temporarily unavailable. Retry later.",
        "err.upstream_rejected": "Steam rejected the request. Check the arguments.",
        "err.bad_payload": "Steam returned an unexpected response shape.",
        "msg.price_not_available": (
            "No price is published for this app in this region: it may be "
            "region-locked, unreleased or removed from sale."
        ),
        "msg.no_results": (
            "No Steam app matched '{query}'. Try a shorter query or the exact title."
        ),
        "msg.coming_soon": "This app has not been released yet, so it may have no price.",
    },
    "es": {
        "server.instructions": (
            "Precios en vivo de la tienda de Steam. search_games encuentra el id "
            "de una aplicación a partir de su nombre, get_game_price devuelve el "
            "precio actual, el descuento y los datos de lanzamiento de una "
            "aplicación en una región concreta, y list_specials muestra las "
            "ofertas activas ahora. Los precios dependen de la región: pasa un "
            "código de país como 'es' o 'us' cuando se conozca la región. Sin "
            "clave de API."
        ),
        "tool.get_game_price.title": "Consultar precio en Steam",
        "tool.search_games.title": "Buscar juegos en Steam",
        "tool.list_specials.title": "Ver descuentos de Steam",
        "tool.get_game_price.description": (
            "Devuelve el precio actual en la tienda de Steam para una aplicación: "
            "precio final y de catálogo, porcentaje de descuento, moneda, si es "
            "gratis, plataformas, géneros, fecha de lanzamiento, desarrollador, "
            "editor, nota de Metacritic y número de recomendaciones. Los precios "
            "dependen de la región. Ejemplo: app_id=1245620, country='es'."
        ),
        "tool.search_games.description": (
            "Busca en la tienda de Steam por título y devuelve las aplicaciones "
            "coincidentes con su id y su precio actual en la región elegida. Úsalo "
            "primero cuando solo conozcas el nombre del juego y luego llama a "
            "get_game_price con el id. Ejemplo: query='elden ring', country='es'."
        ),
        "tool.list_specials.description": (
            "Enumera los juegos con descuento ahora mismo en la tienda de Steam "
            "para una región, ordenados por tamaño del descuento, con precio "
            "original, precio final y cuándo termina la oferta. Ejemplo: "
            "country='es', limit=10."
        ),
        "param.app_id": (
            "Id de aplicación de Steam como número, por ejemplo 1245620 para "
            "ELDEN RING. Búscalo con search_games si solo conoces el título."
        ),
        "param.query": "Título del juego a buscar, por ejemplo 'elden ring' o 'portal 2'.",
        "param.country": (
            "Región de la tienda como código de dos letras: 'us' (por defecto), "
            "'es', 'de', 'br', 'kz', 'ua', 'tr', 'jp'. Los precios cambian según la "
            "región. También se aceptan nombres completos como 'España'."
        ),
        "param.limit": "Número máximo de resultados (1-25 en búsqueda, 1-50 en descuentos).",
        "err.empty_app_id": "No se indicó ningún id. Pasa un id de Steam como 1245620.",
        "err.invalid_app_id": (
            "'{value}' no es un id de Steam. Se espera un número positivo como "
            "1245620."
        ),
        "err.empty_query": "La búsqueda está vacía. Pasa un título como 'portal 2'.",
        "err.empty_country": "No se indicó región. Pasa un código de dos letras como 'us'.",
        "err.invalid_country": (
            "'{country}' no es una región de la tienda. Se espera un código de dos "
            "letras como 'us', 'de' o 'ru'."
        ),
        "err.not_found": (
            "Steam no tiene página de tienda para el id {app_id}. Revisa el id: "
            "puede ser una aplicación retirada, sin lanzar o ajena a la tienda."
        ),
        "err.not_available_in_region": (
            "El id {app_id} existe en Steam pero no se vende en la región "
            "'{country}', así que no tiene precio allí. Prueba otra región."
        ),
        "err.rate_limited": (
            "Steam está limitando las peticiones de este servidor. Espera unos "
            "segundos y vuelve a intentarlo."
        ),
        "err.timeout": "Steam no respondió a tiempo. Inténtalo de nuevo.",
        "err.network_error": "No se pudo contactar con la tienda de Steam. Reintenta.",
        "err.upstream_unavailable": "La tienda de Steam no está disponible ahora. Reintenta más tarde.",
        "err.upstream_rejected": "Steam rechazó la petición. Revisa los argumentos.",
        "err.bad_payload": "Steam devolvió una respuesta con formato inesperado.",
        "msg.price_not_available": (
            "No hay precio publicado para esta aplicación en esta región: puede "
            "estar bloqueada por región, sin lanzar o retirada de la venta."
        ),
        "msg.no_results": (
            "Ninguna aplicación de Steam coincide con '{query}'. Prueba una "
            "búsqueda más corta o el título exacto."
        ),
        "msg.coming_soon": (
            "Esta aplicación aún no se ha lanzado, por lo que puede no tener precio."
        ),
    },
    "ru": {
        "server.instructions": (
            "Актуальные цены магазина Steam. search_games находит id приложения по "
            "названию, get_game_price возвращает текущую цену, скидку и данные о "
            "выходе для одного приложения в выбранном регионе магазина, а "
            "list_specials показывает, что сейчас на распродаже. Цены зависят от "
            "региона: передавайте код страны, например 'ru' или 'us', если регион "
            "пользователя известен. Ключ API не нужен."
        ),
        "tool.get_game_price.title": "Цена игры в Steam",
        "tool.search_games.title": "Поиск игр в Steam",
        "tool.list_specials.title": "Скидки в Steam",
        "tool.get_game_price.description": (
            "Возвращает текущую цену в магазине Steam для одного приложения: "
            "итоговую и базовую цену, процент скидки, валюту, признак "
            "бесплатности, платформы, жанры, дату выхода, разработчика, "
            "издателя, оценку Metacritic и число рекомендаций. Цены зависят от "
            "региона магазина. Совсем новая страница может ещё не попасть в "
            "индекс. Пример: app_id=1245620, country='ru'."
        ),
        "tool.search_games.description": (
            "Ищет в магазине Steam по названию и возвращает найденные приложения "
            "с их id и текущими ценами в выбранном регионе. Сначала используйте "
            "этот инструмент, если известно только название игры, затем вызовите "
            "get_game_price с полученным id. Пример: query='elden ring', "
            "country='ru'."
        ),
        "tool.list_specials.description": (
            "Показывает игры со скидками в магазине Steam для выбранного региона, "
            "отсортированные по размеру скидки, с исходной и итоговой ценой и "
            "временем окончания акции. Пример: country='ru', limit=10."
        ),
        "param.app_id": (
            "Id приложения Steam числом, например 1245620 для ELDEN RING. Если "
            "известно только название, найдите id через search_games."
        ),
        "param.query": (
            "Название игры для поиска, например 'elden ring' или 'portal 2'."
        ),
        "param.country": (
            "Регион магазина в виде двухбуквенного кода: 'us' (по умолчанию), "
            "'ru', 'de', 'br', 'kz', 'ua', 'tr', 'jp'. Цены в разных регионах "
            "отличаются. Полные названия вроде 'Россия' тоже принимаются."
        ),
        "param.limit": (
            "Максимальное число результатов (1-25 для поиска, 1-50 для скидок)."
        ),
        "err.empty_app_id": (
            "Не передан id приложения. Укажите id Steam, например 1245620."
        ),
        "err.invalid_app_id": (
            "«{value}» не является id приложения Steam. Ожидается положительное "
            "число вроде 1245620."
        ),
        "err.empty_query": (
            "Поисковый запрос пуст. Укажите название игры, например 'portal 2'."
        ),
        "err.empty_country": (
            "Не указан регион. Передайте двухбуквенный код, например 'us'."
        ),
        "err.invalid_country": (
            "«{country}» не является регионом магазина. Ожидается двухбуквенный "
            "код страны, например 'us', 'de' или 'ru'."
        ),
        "err.not_found": (
            "У Steam нет страницы магазина для приложения {app_id}. Проверьте id: "
            "возможно, приложение удалено, ещё не вышло или продаётся не в "
            "магазине."
        ),
        "err.not_available_in_region": (
            "Приложение {app_id} существует в Steam, но не продаётся в регионе "
            "«{country}», поэтому цены для него там нет. Попробуйте другой регион."
        ),
        "err.rate_limited": (
            "Steam ограничивает частоту запросов этого сервера. Подождите "
            "несколько секунд и повторите."
        ),
        "err.timeout": "Steam не ответил вовремя. Повторите попытку.",
        "err.network_error": (
            "Не удалось связаться с магазином Steam. Проверьте соединение и повторите."
        ),
        "err.upstream_unavailable": (
            "Магазин Steam временно недоступен. Повторите попытку позже."
        ),
        "err.upstream_rejected": "Steam отклонил запрос. Проверьте аргументы.",
        "err.bad_payload": "Steam вернул ответ неожиданного формата.",
        "msg.price_not_available": (
            "Для этого приложения в данном регионе цена не публикуется: возможно, "
            "оно заблокировано по региону, ещё не вышло или снято с продажи."
        ),
        "msg.no_results": (
            "Ни одно приложение Steam не совпало с «{query}». Попробуйте более "
            "короткий запрос или точное название."
        ),
        "msg.coming_soon": (
            "Приложение ещё не вышло, поэтому цены может не быть."
        ),
    },
}

_LOCALE_RE = re.compile(r"^([a-z]{2,3})")


def detect_locale(candidates: Iterable[str | None] | None = None) -> str:
    """Resolve the requested locale, defaulting to English.

    Accepts values such as ``ru_RU.UTF-8``, ``es-419`` or ``EN`` and reduces
    them to a supported two-letter code.
    """
    if candidates is None:
        candidates = (
            os.getenv("MCP_LOCALE"),
            os.getenv("LANGUAGE"),
            os.getenv("LANG"),
        )
    for raw in candidates:
        if not raw:
            continue
        match = _LOCALE_RE.match(raw.strip().lower())
        if match and match.group(1) in SUPPORTED_LOCALES:
            return match.group(1)
    return DEFAULT_LOCALE


class Locale:
    """Lookup helper that never raises: falls back to English, then to the key."""

    def __init__(self, code: str | None = None) -> None:
        if code in SUPPORTED_LOCALES:
            self.code = code
        elif code:
            # An explicit, unsupported code falls back to detection (then English).
            self.code = detect_locale((code,))
        else:
            # No explicit choice: honour MCP_LOCALE / LANGUAGE / LANG.
            self.code = detect_locale()
        self._table = MESSAGES[self.code]
        self._fallback = MESSAGES[DEFAULT_LOCALE]

    def t(self, key: str, **kwargs: object) -> str:
        template = self._table.get(key) or self._fallback.get(key) or key
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Locale({self.code!r})"
