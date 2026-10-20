import os
import json
import logging
from typing import List, Dict, Any, Optional

_logger = logging.getLogger("MomentumOne.Config")

class Settings:
    BOT_NAME: str = os.getenv("BOT_NAME", "MomentumOne")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_PREFIX: str = os.getenv("BOT_PREFIX", "$")
    CLIENT_ID: str = os.getenv("CLIENT_ID", "")
    CLIENT_SECRET: str = os.getenv("CLIENT_SECRET", "")
    API_SECRET: str = os.getenv("API_SECRET", "")
    ENVIRONMENT: str = os.getenv("NODE_ENV", "production")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 3000))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
    
    # Database
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "momentumone")
    
    # AI
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    
    # Bot Control
    BOT_ENABLED: bool = os.getenv("BOT_ENABLED", "true").lower() not in ("false", "0", "off")
    ENABLE_ALL_PLUGINS: bool = os.getenv("ENABLE_ALL_PLUGINS", "true").lower() in ("true", "1")
    
    # Owners & Exclusions
    OWNER_IDS: List[str] = [x.strip() for x in os.getenv("OWNER_IDS", os.getenv("OWNER_ID", "")).split(",") if x.strip()]
    BLACKLIST_EXCLUSIONS: List[str] = [x.strip() for x in os.getenv("BLACKLIST_EXCLUSIONS", "").split(",") if x.strip()]
    
    # Intervals (ms)
    CACHE_TTL: int = 60_000
    BLACKLIST_CACHE_SYNC: int = 60_000
    NO_PREFIX_CACHE_SYNC: int = 60_000
    ANTI_SPAM_WINDOW: int = 30_000

settings = Settings()

def _load_json_config(filename: str) -> Dict[str, Any]:
    possible_paths = [
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join(os.path.dirname(__file__), "..", filename),
        os.path.join(os.getcwd(), "python", "config", filename),
        os.path.join(os.getcwd(), "src", "config", filename),
        os.path.join(os.getcwd(), filename),
    ]
    for p in possible_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as err:
                _logger.warning(f"Error loading {filename} from {p}: {err}")
    return {}

class AuthoritativeDict(dict):
    def __init__(self, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = name

    def get(self, key: str, default: Any = None) -> Any:
        if key in self and super().__getitem__(key):
            return super().__getitem__(key)
        if default is not None:
            return default
        _logger.warning(f"[{self._name}] Key '{key}' not found in configuration.")
        return ""

    def __getitem__(self, key: str) -> Any:
        if key in self and super().__getitem__(key):
            return super().__getitem__(key)
        _logger.warning(f"[{self._name}] Key '{key}' not found in configuration.")
        return ""

_raw_colors = _load_json_config("Colors.json")
_raw_emojis = _load_json_config("Emojis.json")

COLORS: Dict[str, str] = AuthoritativeDict("ColorsConfig", _raw_colors)
EMOJIS: Dict[str, str] = AuthoritativeDict("EmojisConfig", _raw_emojis)

def get_color(key: str, default: str = "#0844C5") -> str:
    return COLORS.get(key, default) or default

def get_emoji(key: str, default: str = "") -> str:
    return EMOJIS.get(key, default) or default
