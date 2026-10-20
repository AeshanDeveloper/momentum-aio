import os
from typing import List, Dict, Any

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

import json

def _load_json_config(filename: str) -> Dict[str, Any]:
    # Check current directory, python/config, src/config, root
    possible_paths = [
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join(os.path.dirname(__file__), "..", "..", "src", "config", filename),
        os.path.join(os.path.dirname(__file__), "..", filename),
        os.path.join(os.getcwd(), "src", "config", filename),
        os.path.join(os.getcwd(), "python", "config", filename),
    ]
    for p in possible_paths:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

_central_colors = _load_json_config("Colors.json")
_central_emojis = _load_json_config("Emojis.json")

# Central Colors with fallback
COLORS: Dict[str, str] = {
    "default": "#FF7B00",
    "success": "#3FD438",
    "error": "#B21F1F",
    "warning": "#F59E0B",
    "warn": "#F59E0B",
    "info": "#3B82F6",
    **_central_colors
}

# Central Emojis with fallback
EMOJIS: Dict[str, str] = {
    "online": "🟢",
    "offline": "🔴",
    "ping": "📡",
    "latency": "⚡",
    "database": "💾",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "warn": "⚠️",
    "info": "ℹ️",
    "shield": "🛡️",
    "owner": "👑",
    "profile": "👤",
    "ticket": "🎫",
    "ban": "🚫",
    "time": "⏱️",
    "search": "🔍",
    "history": "📜",
    "server": "🖥️",
    "user": "👤",
    "cmd": "⚡",
    "commands": "⚡",
    **{k: v for k, v in _central_emojis.items() if v}
}

def get_color(key: str, default: str = "#FF7B00") -> str:
    return COLORS.get(key, default)

def get_emoji(key: str, default: str = "") -> str:
    return EMOJIS.get(key, default)

