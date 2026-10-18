import time
import uuid
from typing import Dict, Any, List, Optional
from core.logging.logger import logger
from database.database import database

class ErrorTracker:
    COLLECTION = "command_errors"
    _recent_errors: List[Dict[str, Any]] = []

    @classmethod
    def generate_error_id(cls) -> str:
        part = uuid.uuid4().hex[:8].upper()
        return f"ERR-{part}"

    @classmethod
    async def record(
        cls,
        command_name: str,
        error: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        context = context or {}
        error_id = cls.generate_error_id()
        msg = str(getattr(error, "message", error))
        stack = str(getattr(error, "__traceback__", ""))

        record = {
            "error_id": error_id,
            "errorId": error_id,
            "command_name": command_name,
            "commandName": command_name,
            "user_id": context.get("user_id") or context.get("userId"),
            "username": context.get("username"),
            "guild_id": context.get("guild_id") or context.get("guildId"),
            "command_type": context.get("command_type") or context.get("commandType", "PREFIX"),
            "args": context.get("args", []),
            "message": msg,
            "stack": stack,
            "timestamp": time.time(),
        }

        cls._recent_errors.insert(0, record)
        if len(cls._recent_errors) > 100:
            cls._recent_errors.pop()

        try:
            col = database.collection(cls.COLLECTION)
            await col.insert_one(record)
        except Exception as err:
            logger.error(f"[ErrorTracker] Could not persist error {error_id}: {err}")

        logger.error(f"[ErrorTracker] [{error_id}] Error in command '{command_name}': {msg}")
        return record

    @classmethod
    async def list(cls, skip: int = 0, limit: int = 20, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        filter_dict = filter_dict or {}
        try:
            col = database.collection(cls.COLLECTION)
            res = await col.find(filter_dict, sort={"timestamp": -1}, skip=skip, limit=limit)
            if res:
                return res
        except Exception:
            pass

        items = list(cls._recent_errors)
        if filter_dict.get("command_name"):
            cmd = filter_dict["command_name"].lower()
            items = [e for e in items if e.get("command_name", "").lower() == cmd]
        return items[skip : skip + limit]

    @classmethod
    async def get(cls, error_id: str) -> Optional[Dict[str, Any]]:
        target = error_id.upper()
        try:
            col = database.collection(cls.COLLECTION)
            doc = await col.find_one({"error_id": target})
            if doc:
                return doc
        except Exception:
            pass

        for e in cls._recent_errors:
            if e.get("error_id", "").upper() == target:
                return e
        return None

    @classmethod
    async def count(cls, filter_dict: Optional[Dict[str, Any]] = None) -> int:
        filter_dict = filter_dict or {}
        try:
            col = database.collection(cls.COLLECTION)
            return await col.count_documents(filter_dict)
        except Exception:
            return len(cls._recent_errors)

    @classmethod
    async def delete(cls, error_id: str) -> bool:
        target = error_id.upper()
        try:
            col = database.collection(cls.COLLECTION)
            await col.delete_one({"error_id": target})
        except Exception:
            pass

        for i, e in enumerate(cls._recent_errors):
            if e.get("error_id", "").upper() == target:
                del cls._recent_errors[i]
                return True
        return False

    @classmethod
    async def clear(cls) -> int:
        count = len(cls._recent_errors)
        cls._recent_errors.clear()
        try:
            col = database.collection(cls.COLLECTION)
            res = await col.delete_many({})
            if isinstance(res, dict):
                count = res.get("deleted_count", count)
        except Exception:
            pass
        return count
