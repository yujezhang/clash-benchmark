import locale
import os

from . import en, zh

_LOCALES = {
    "en": en.STRINGS,
    "zh": zh.STRINGS,
}

_current: dict = en.STRINGS


def set_locale(lang: str) -> None:
    """Set the active locale. lang must be 'en' or 'zh'."""
    global _current
    if lang not in _LOCALES:
        raise ValueError(f"Unsupported locale: {lang}. Choose from: {list(_LOCALES)}")
    _current = _LOCALES[lang]


def detect_system_locale() -> str:
    """Return 'zh' if system locale is Chinese, else 'en'."""
    lang = os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "")
    if not lang:
        try:
            lang = locale.getlocale()[0] or ""
        except Exception:
            lang = ""
    lang = lang.lower()
    if lang.startswith("zh"):
        return "zh"
    return "en"


def t(key: str, **kwargs) -> str:
    """Look up a string by key and format it with kwargs."""
    template = _current.get(key) or en.STRINGS.get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template
