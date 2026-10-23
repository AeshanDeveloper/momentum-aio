import os
import re
import json
import logging
from typing import Any, Dict, Optional, Union

_logger = logging.getLogger("MomentumOne.Strings")
_STRINGS_CACHE: Dict[str, Any] = {}

def load_strings(custom_path: Optional[str] = None) -> Dict[str, Any]:
    global _STRINGS_CACHE
    if _STRINGS_CACHE:
        return _STRINGS_CACHE

    search_paths = [
        custom_path,
        os.path.join(os.path.dirname(__file__), "Strings.json"),
        os.path.join(os.path.dirname(__file__), "..", "Strings.json"),
        os.path.join(os.getcwd(), "python", "config", "Strings.json"),
        os.path.join(os.getcwd(), "Strings.json"),
        os.path.join(os.getcwd(), "src", "config", "Strings.json"),
    ]

    for p in search_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    _STRINGS_CACHE = json.load(f)
                    return _STRINGS_CACHE
            except Exception as err:
                _logger.warning(f"Failed to load Strings.json from {p}: {err}")
    return {}

def reload_strings() -> Dict[str, Any]:
    global _STRINGS_CACHE
    _STRINGS_CACHE = {}
    return load_strings()

def _get_emoji_value(emoji_key: str) -> str:
    from config.settings import EMOJIS
    val = EMOJIS.get(emoji_key)
    if val:
        return val
    _logger.warning(f"[TemplateRenderer] Unresolved emoji key: {emoji_key}")
    return ""

def render_string(
    template: str,
    variables: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    if not template or not isinstance(template, str):
        return str(template or "")

    combined_vars: Dict[str, Any] = {}
    if variables and isinstance(variables, dict):
        combined_vars.update(variables)
    if kwargs:
        combined_vars.update(kwargs)

    # 1. Resolve emoji placeholders: {emoji:name}
    def _emoji_replacer(match: re.Match) -> str:
        k = match.group(1)
        return _get_emoji_value(k)

    res = re.sub(r"\{emoji:([a-zA-Z0-9_]+)\}", _emoji_replacer, template)

    # 2. Resolve variable placeholders: {var_name}
    def _var_replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in combined_vars:
            val = combined_vars[var_name]
            return str(val) if val is not None else ""
        return match.group(0)

    res = re.sub(r"\{([a-zA-Z0-9_]+)\}", _var_replacer, res)
    return res

def get_string_def(key_path: str) -> Optional[Union[Dict[str, Any], str]]:
    strings = load_strings()
    parts = key_path.split(".")
    curr: Any = strings
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr

def get_string(
    key_path: str,
    default: str = "",
    variables: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    node = get_string_def(key_path)
    combined_vars = dict(variables or {})
    combined_vars.update(kwargs)

    template = ""
    if isinstance(node, dict):
        template = node.get("description") or node.get("desc") or node.get("title") or default
    elif isinstance(node, str):
        template = node
    else:
        template = default

    return render_string(template, combined_vars)
