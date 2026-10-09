"""Shared interface and CLI translations. English is always the fallback."""
import json
from pathlib import Path

LANGUAGES = ("en", "zh-CN", "ja")
TRANSLATIONS = json.loads((Path(__file__).parent / "web/locales.json").read_text(encoding="utf-8"))


def language(value):
    return value if value in LANGUAGES else "en"


def translate(key, locale="en", **values):
    return TRANSLATIONS[language(locale)].get(key, TRANSLATIONS["en"].get(key, key)).format(**values)


class UserError(ValueError):
    def __init__(self, key, **values):
        self.key = key
        self.values = values
        super().__init__(translate(key, **values))


def error_data(error):
    if isinstance(error, UserError):
        return {"key": error.key, "values": error.values}
    return {"key": "error_generic", "values": {"detail": str(error)}}


def error_message(error, locale="en"):
    data = error_data(error)
    return translate(data["key"], locale, **data["values"])
