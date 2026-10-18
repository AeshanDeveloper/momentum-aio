import os
import json
from typing import Any, Dict

_STRINGS_CACHE: Dict[str, Any] = {}

def load_strings(custom_path: str = None) -> Dict[str, Any]:
    global _STRINGS_CACHE
    if _STRINGS_CACHE:
        return _STRINGS_CACHE

    search_paths = [
        custom_path,
        os.path.join(os.path.dirname(__file__), "..", "Strings.json"),
        os.path.join(os.getcwd(), "Strings.json"),
        os.path.join(os.getcwd(), "src", "config", "Strings.json"),
    ]

    for p in search_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    _STRINGS_CACHE = json.load(f)
                    return _STRINGS_CACHE
            except Exception:
                pass
    return {}

def get_string(key_path: str, default: str = "", **kwargs) -> str:
    """
    Retrieve localized string by dot-path (e.g. 'permissions.missing_user_permission')
    and interpolate any keyword arguments.
    """
    strings = load_strings()
    parts = key_path.split(".")
    curr: Any = strings
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return default.format(**kwargs) if kwargs else default

    if isinstance(curr, str):
        try:
            return curr.format(**kwargs) if kwargs else curr
        except Exception:
            return curr
    return default
