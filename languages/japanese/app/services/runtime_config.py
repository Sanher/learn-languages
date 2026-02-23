from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger("learn_languages.japanese.runtime_config")
DEFAULT_OPTIONS_PATH = "/data/options.json"
OPTIONS_PATH_ENV = "HA_ADDON_OPTIONS_PATH"


def _normalize_key(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def _env_variants(name: str) -> list[str]:
    raw = str(name or "").strip()
    if not raw:
        return []
    normalized = raw.replace("-", "_").replace(".", "_")
    variants = [raw, normalized, raw.upper(), raw.lower(), normalized.upper(), normalized.lower()]
    return list(dict.fromkeys(variant for variant in variants if variant))


def _flatten_options(node: Any, prefix: tuple[str, ...] = ()) -> dict[str, str]:
    flattened: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            flattened.update(_flatten_options(value, prefix + (str(key),)))
        return flattened
    if isinstance(node, list):
        return flattened
    if node is None:
        return flattened

    text = str(node).strip()
    if not text:
        return flattened

    key_candidates = set()
    if prefix:
        key_candidates.add("_".join(prefix))
        key_candidates.add(".".join(prefix))
        key_candidates.add("".join(prefix))
        key_candidates.add(prefix[-1])

    for candidate in key_candidates:
        normalized = _normalize_key(candidate)
        if normalized:
            flattened[normalized] = text
    return flattened


@lru_cache(maxsize=1)
def _load_options() -> dict[str, str]:
    options_path = Path(os.getenv(OPTIONS_PATH_ENV, DEFAULT_OPTIONS_PATH))
    if not options_path.exists():
        return {}

    try:
        raw_data = json.loads(options_path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("config_options_unreadable path=%s", options_path)
        return {}

    if not isinstance(raw_data, dict):
        LOGGER.warning("config_options_invalid_format path=%s", options_path)
        return {}
    return _flatten_options(raw_data)


def get_setting(*, env_names: Iterable[str], option_names: Iterable[str], default: str = "") -> str:
    for env_name in env_names:
        for variant in _env_variants(env_name):
            value = os.getenv(variant)
            if value is not None and str(value).strip():
                return str(value).strip()

    options = _load_options()
    for name in list(option_names) + list(env_names):
        normalized = _normalize_key(name)
        option_value = options.get(normalized)
        if option_value is not None and option_value.strip():
            return option_value.strip()

    return default


def clear_cached_options() -> None:
    _load_options.cache_clear()
