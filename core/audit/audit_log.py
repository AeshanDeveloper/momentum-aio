import re
import uuid
import time
from typing import Dict, Any, List, Optional
from database.database import database

SENSITIVE_KEYS = re.compile(r"token|secret|password|credential|api[-_]?key|private[-_]?key", re.IGNORECASE)

def redact(value: Any) -> Any:
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if SENSITIVE_KEYS.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    return value

def changed_fields(prev: Any, new: Any) -> List[str]:
    if not isinstance(prev, dict) or not isinstance(new, dict):
        return []
    all_keys = set(prev.keys()).union(set(new.keys()))
    return [k for k in all_keys if prev.get(k) != new.get(k)]

class AuditLog:
    COLLECTION = "audit_logs"
    _in_memory: List[Dict[str, Any]] = []

    @classmethod
    async def record(cls, entry: Dict[str, Any]) -> Dict[str, Any]:
        audit_id = str(uuid.uuid4())
        prev_state = redact(entry.get("previousState") or entry.get("previous_state"))
        new_state = redact(entry.get("newState") or entry.get("new_state"))
        record = {
            "audit_id": audit_id,
            "auditId": audit_id,
            "guild_id": entry.get("guildId") or entry.get("guild_id"),
            "guildId": entry.get("guildId") or entry.get("guild_id"),
            "actor_id": entry.get("actorId") or entry.get("actor_id"),
            "actorId": entry.get("actorId") or entry.get("actor_id"),
            "actor_type": entry.get("actorType") or entry.get("actor_type", "system"),
            "actorType": entry.get("actorType") or entry.get("actor_type", "system"),
            "action": entry.get("action", "unknown"),
            "resource_type": entry.get("resourceType") or entry.get("resource_type", "system"),
            "resourceType": entry.get("resourceType") or entry.get("resource_type", "system"),
            "resource_id": entry.get("resourceId") or entry.get("resource_id"),
            "resourceId": entry.get("resourceId") or entry.get("resource_id"),
            "previous_state": prev_state,
            "previousState": prev_state,
            "new_state": new_state,
            "newState": new_state,
            "changed_fields": changed_fields(prev_state, new_state),
            "changedFields": changed_fields(prev_state, new_state),
            "timestamp": time.time(),
            "source": entry.get("source", "system"),
            "success": bool(entry.get("success", True)),
            "error": entry.get("error"),
        }

        cls._in_memory.insert(0, record)
        if len(cls._in_memory) > 200:
            cls._in_memory.pop()

        try:
            col = database.collection(cls.COLLECTION)
            await col.insert_one(record)
        except Exception:
            pass

        return record

    @classmethod
    async def list(
        cls,
        filter_dict: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        filter_dict = filter_dict or {}
        try:
            col = database.collection(cls.COLLECTION)
            res = await col.find(filter_dict, sort={"timestamp": -1}, skip=skip, limit=limit)
            if res:
                return res
        except Exception:
            pass

        items = list(cls._in_memory)
        if filter_dict.get("action"):
            act = filter_dict["action"]
            if isinstance(act, dict) and "$regex" in act:
                pat = act["$regex"]
                items = [e for e in items if re.search(pat, e.get("action", ""), re.IGNORECASE)]
            elif isinstance(act, str):
                items = [e for e in items if act.lower() in e.get("action", "").lower()]
        return items[skip : skip + limit]

    @classmethod
    async def count(cls, filter_dict: Optional[Dict[str, Any]] = None) -> int:
        filter_dict = filter_dict or {}
        try:
            col = database.collection(cls.COLLECTION)
            return await col.count_documents(filter_dict)
        except Exception:
            return len(cls._in_memory)

    @classmethod
    async def get(cls, audit_id: str) -> Optional[Dict[str, Any]]:
        target = str(audit_id).lower()
        for e in cls._in_memory:
            if (e.get("audit_id") or e.get("auditId") or "").lower() == target:
                return e
        try:
            col = database.collection(cls.COLLECTION)
            return await col.find_one({"$or": [{"audit_id": audit_id}, {"auditId": audit_id}]})
        except Exception:
            return None
