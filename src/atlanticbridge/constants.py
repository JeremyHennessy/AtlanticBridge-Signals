from __future__ import annotations

EU27 = {
    "Austria",
    "Belgium",
    "Bulgaria",
    "Croatia",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Estonia",
    "Finland",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "Ireland",
    "Italy",
    "Latvia",
    "Lithuania",
    "Luxembourg",
    "Malta",
    "Netherlands",
    "Poland",
    "Portugal",
    "Romania",
    "Slovakia",
    "Slovenia",
    "Spain",
    "Sweden",
}

_COUNTRY_ALIASES = {
    "czech republic": "Czechia",
    "the netherlands": "Netherlands",
}


def normalize_country(value: str) -> str:
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return ""
    alias = _COUNTRY_ALIASES.get(cleaned.casefold())
    if alias:
        return alias
    for country in EU27:
        if cleaned.casefold() == country.casefold():
            return country
    return cleaned


def is_eu27_country(value: str) -> bool:
    return normalize_country(value) in EU27
