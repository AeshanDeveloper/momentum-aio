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

# Colors and Emojis
COLORS: Dict[str, str] = {
    "default": "#FF7B00",
    "success": "#3FD438",
    "error": "#B21F1F",
    "warn": "#F59E0B",
    "info": "#3B82F6",
}

EMOJIS: Dict[str, str] = {
    "online": "🟢",
    "offline": "🔴",
    "ping": "📡",
    "latency": "⚡",
    "database": "💾",
    "success": "✅",
    "error": "❌",
    "warn": "⚠️",
    "info": "ℹ️",
    "shield": "🛡️",
    "owner": "👑",
    "profile": "👤",
    "ticket": "🎫",
    "ban": "🚫",
}
