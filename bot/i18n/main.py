from __future__ import annotations
from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any

from bot.misc import EnvKeys
from .strings import TRANSLATIONS, DEFAULT_LOCALE
from bot.logger_mesh import logger

_current_locale: ContextVar[str | None] = ContextVar("current_locale", default=None)


def normalize_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    loc = locale.lower().strip()
    return loc if loc in TRANSLATIONS else None


@lru_cache(maxsize=1)
def get_default_locale() -> str:
    loc = EnvKeys.BOT_LOCALE.lower().strip()
    return loc if loc in TRANSLATIONS else DEFAULT_LOCALE


def get_locale() -> str:
    loc = normalize_locale(_current_locale.get())
    return loc or get_default_locale()


def set_current_locale(locale: str | None) -> Token:
    return _current_locale.set(normalize_locale(locale))


def reset_current_locale(token: Token) -> None:
    _current_locale.reset(token)


def get_supported_locales() -> tuple[str, ...]:
    return tuple(TRANSLATIONS.keys())


def is_supported_locale(locale: str | None) -> bool:
    return normalize_locale(locale) is not None


# Backward-compatible test helper: existing tests call get_locale.cache_clear().
get_locale.cache_clear = get_default_locale.cache_clear  # type: ignore[attr-defined]


def localize(key: str, /, **kwargs: Any) -> str:
    """
    Get translation by key.
    Fallback: current locale -> DEFAULT_LOCALE -> the key itself.
    """
    loc = get_locale()

    text = TRANSLATIONS.get(loc, {}).get(key)
    if text is None:
        text = TRANSLATIONS.get(DEFAULT_LOCALE, {}).get(key)
    if text is None:
        text = key

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to format translation key '{key}' with kwargs {kwargs}: {e}")

    return str(text)
