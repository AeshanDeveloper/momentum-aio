import os
import json
from typing import List, Dict, Any

class Settings:
    BOT_NAME: str = os.getenv("BOT_NAME", "Mussoorie")
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
    _raw_owners = os.getenv("OWNER_IDS", os.getenv("OWNER_ID", "1131339559016333465"))
    OWNER_IDS: List[str] = [x.strip() for x in _raw_owners.split(",") if x.strip()]
    BLACKLIST_EXCLUSIONS: List[str] = [x.strip() for x in os.getenv("BLACKLIST_EXCLUSIONS", "").split(",") if x.strip()]
    
    # Intervals (ms)
    CACHE_TTL: int = 60_000
    BLACKLIST_CACHE_SYNC: int = 60_000
    NO_PREFIX_CACHE_SYNC: int = 60_000
    ANTI_SPAM_WINDOW: int = 30_000

    def __init__(self):
        self.bot = {
            "name": self.BOT_NAME,
            "description": "",
            "prefix": self.BOT_PREFIX,
            "owner_ids": self.OWNER_IDS,
            "min_tip": 1,
            "invite": f"https://discord.com/oauth2/authorize?client_id={self.CLIENT_ID}",
            "supportInvite": "https://discord.gg/EaD6efwNpa",
            "currency": {"name": "INR"},
            "team": {"name": "Momentum Development"},
        }
        self.intervals = {
            "leaderboard_refresh": 300_000,
            "anti_spam_window": self.ANTI_SPAM_WINDOW,
            "blacklist_cache_sync": self.BLACKLIST_CACHE_SYNC,
            "no_prefix_cache_sync": self.NO_PREFIX_CACHE_SYNC,
            "cache_ttl": self.CACHE_TTL,
        }
        self.observability = {
            "ga4MeasurementId": os.getenv("GA4_MEASUREMENT_ID", ""),
            "ga4ApiSecret": os.getenv("GA4_API_SECRET", ""),
            "webhookUrl": os.getenv("DISCORD_LOG_WEBHOOK_URL", os.getenv("LOG_WEBHOOK_URL", "")),
            "logLevel": self.LOG_LEVEL,
        }
        self.ai = {
            "defaultModel": self.GEMINI_MODEL,
            "isConfigured": bool(self.GEMINI_API_KEY.strip()),
        }

settings = Settings()

# Helper to find and load json configs from src/config or root
def _load_json_config(filename: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    search_paths = [
        os.path.join(os.getcwd(), "src", "config", filename),
        os.path.join(os.path.dirname(__file__), "..", "..", "src", "config", filename),
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join(os.getcwd(), filename),
    ]
    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        merged = dict(fallback)
                        merged.update(data)
                        return merged
            except Exception:
                pass
    return fallback

DEFAULT_COLORS: Dict[str, str] = {
    "default": "#0844C5",
    "success": "#3FD438",
    "error": "#B21F1F",
    "warn": "#F59E0B",
    "warning": "#F59E0B",
    "info": "#3B82F6",
    "cmd_help": "#0844C5",
    "cmd_help_error": "#B21F1F",
}

DEFAULT_EMOJIS: Dict[str, str] = {
    "help": "📖",
    "info": "💡",
    "error": "❌",
    "success": "✅",
    "warning": "⚠️",
    "loading": "⏳",
    "online": "🟢",
    "offline": "🔴",
    "ping": "📡",
    "latency": "⚡",
    "database": "💾",
    "ticket": "🎫",
    "first": "⏮️",
    "firstPage": "⏮️",
    "previous": "◀️",
    "previousPage": "◀️",
    "next": "▶️",
    "nextPage": "▶️",
    "last": "⏭️",
    "lastPage": "⏭️",
    "arrowLeft": "◀",
    "arrowRight": "▶",
    "refresh": "🔄",
    "command": "▫️",
    "commands": "📊",
    "slash": "⚡",
    "prefix": "⌨️",
    "hybrid": "🔄",
    "developer": "👑",
    "owner": "👑",
    "server": "🗂️",
    "permission": "🔐",
    "permissions": "🔐",
    "logs": "📋",
    "tools": "🛠️",
    "money": "💰",
    "stats": "📊",
    "ban": "🚫",
    "shield": "🛡️",
    "profile": "👤",
}

COLORS: Dict[str, str] = _load_json_config("Colors.json", DEFAULT_COLORS)
EMOJIS: Dict[str, str] = _load_json_config("Emojis.json", DEFAULT_EMOJIS)

class Config:
    def __init__(self):
        self.environment = settings.ENVIRONMENT
        self.enviorment = settings.ENVIRONMENT
        self.bot_token = settings.BOT_TOKEN
        self.settings = settings
        self.Emojis = EMOJIS
        self.Colors = COLORS
        self.emojis = EMOJIS
        self.colors = COLORS
        self.links = {
            "botInvite": settings.bot["invite"],
            "supportServer": settings.bot["supportInvite"],
        }

config = Config()
