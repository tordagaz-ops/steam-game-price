"""Store regions (``cc`` values) and the aliases people actually type.

Steam prices are region-specific: the same app costs different amounts in ``us``
and ``ru``, and some titles are not sold in some regions at all. The API takes
lowercase ISO-3166 alpha-2 codes; models and users type ``USA``, ``UK``,
``Russia``, ``рф``. This module converts those into codes and rejects anything
that cannot be a code.
"""

from __future__ import annotations

import re

__all__ = [
    "COUNTRY_ALIASES",
    "CountryFormatError",
    "DEFAULT_COUNTRY",
    "is_supported",
    "normalize_country",
    "region_name",
]

DEFAULT_COUNTRY = "us"

#: Human-readable names for the codes we advertise; not a whitelist.
REGIONS: dict[str, str] = {
    "us": "United States",
    "gb": "United Kingdom",
    "de": "Germany",
    "fr": "France",
    "es": "Spain",
    "it": "Italy",
    "nl": "Netherlands",
    "pl": "Poland",
    "cz": "Czechia",
    "pt": "Portugal",
    "se": "Sweden",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "ch": "Switzerland",
    "at": "Austria",
    "be": "Belgium",
    "ie": "Ireland",
    "ru": "Russia",
    "ua": "Ukraine",
    "kz": "Kazakhstan",
    "by": "Belarus",
    "am": "Armenia",
    "ge": "Georgia",
    "tr": "Türkiye",
    "br": "Brazil",
    "ar": "Argentina",
    "mx": "Mexico",
    "cl": "Chile",
    "co": "Colombia",
    "ca": "Canada",
    "au": "Australia",
    "nz": "New Zealand",
    "jp": "Japan",
    "kr": "South Korea",
    "cn": "China",
    "tw": "Taiwan",
    "hk": "Hong Kong",
    "sg": "Singapore",
    "th": "Thailand",
    "id": "Indonesia",
    "my": "Malaysia",
    "ph": "Philippines",
    "vn": "Vietnam",
    "in": "India",
    "ae": "United Arab Emirates",
    "sa": "Saudi Arabia",
    "il": "Israel",
    "za": "South Africa",
    "eg": "Egypt",
}

#: Everything is matched after lowercasing and collapsing separators.
COUNTRY_ALIASES: dict[str, str] = {
    # United States
    "usa": "us", "u s a": "us", "united states": "us", "united states of america": "us",
    "america": "us", "сша": "us", "америка": "us",
    # United Kingdom
    "uk": "gb", "u k": "gb", "great britain": "gb", "britain": "gb", "england": "gb",
    "united kingdom": "gb", "англия": "gb", "великобритания": "gb",
    # Germany / France / Spain / Italy
    "germany": "de", "deutschland": "de", "германия": "de",
    "france": "fr", "франция": "fr",
    "spain": "es", "españa": "es", "espana": "es", "испания": "es",
    "italy": "it", "italia": "it", "италия": "it",
    # Russia and neighbours
    "russia": "ru", "russian federation": "ru", "россия": "ru", "рф": "ru",
    "ukraine": "ua", "украина": "ua",
    "kazakhstan": "kz", "казахстан": "kz",
    "belarus": "by", "беларусь": "by", "белоруссия": "by",
    "armenia": "am", "армения": "am",
    "georgia": "ge", "грузия": "ge",
    # Türkiye
    "turkey": "tr", "türkiye": "tr", "turkiye": "tr", "турция": "tr",
    # Americas
    "brazil": "br", "brasil": "br", "бразилия": "br",
    "argentina": "ar", "аргентина": "ar",
    "mexico": "mx", "méxico": "mx", "мексика": "mx",
    "canada": "ca", "канада": "ca",
    "chile": "cl", "colombia": "co",
    # Asia-Pacific
    "australia": "au", "австралия": "au",
    "new zealand": "nz",
    "japan": "jp", "япония": "jp",
    "south korea": "kr", "korea": "kr", "корея": "kr",
    "china": "cn", "китай": "cn",
    "taiwan": "tw", "hong kong": "hk", "singapore": "sg",
    "thailand": "th", "indonesia": "id", "malaysia": "my",
    "philippines": "ph", "vietnam": "vn",
    "india": "in", "индия": "in",
    # Middle East and Africa
    "uae": "ae", "united arab emirates": "ae",
    "saudi arabia": "sa", "israel": "il",
    "south africa": "za", "egypt": "eg",
    # Europe, rest
    "netherlands": "nl", "holland": "nl", "нидерланды": "nl",
    "poland": "pl", "польша": "pl",
    "czechia": "cz", "czech republic": "cz", "чехия": "cz",
    "portugal": "pt", "португалия": "pt",
    "sweden": "se", "швеция": "se",
    "norway": "no", "норвегия": "no",
    "denmark": "dk", "дания": "dk",
    "finland": "fi", "финляндия": "fi",
    "switzerland": "ch", "швейцария": "ch",
    "austria": "at", "австрия": "at",
    "belgium": "be", "бельгия": "be",
    "ireland": "ie", "ирландия": "ie",
}

_CODE_RE = re.compile(r"^[a-z]{2}$")


class CountryFormatError(ValueError):
    """Raised when a region cannot be interpreted as a store country code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code  # "empty" or "invalid"


def _clean(raw: object) -> str:
    text = str(raw or "").strip().lower()
    text = re.sub(r"[_\-.]+", " ", text)
    return re.sub(r"\s+", " ", text)


def normalize_country(raw: object) -> str:
    """Return a lowercase alpha-2 store code, or raise :class:`CountryFormatError`."""
    text = _clean(raw)
    if not text:
        raise CountryFormatError("empty")
    # Aliases first: "uk" is two letters but means "gb", not the code "uk".
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]
    if len(text) == 2 and _CODE_RE.match(text):
        return text
    compact = text.replace(" ", "")
    if compact in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[compact]
    if len(compact) == 2 and _CODE_RE.match(compact):
        return compact
    raise CountryFormatError("invalid")


def region_name(code: str) -> str | None:
    """Readable region name for the codes we advertise, otherwise ``None``."""
    return REGIONS.get(code)


def is_supported(code: str) -> bool:
    """True for the regions listed in :data:`REGIONS` (a hint, not a limit)."""
    return code in REGIONS
