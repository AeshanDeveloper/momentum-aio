import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
from config.settings import settings
from core.logging.logger import logger

MOCK_DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".data", "local_db.json"))

def _load_mock_data() -> Dict[str, List[Dict[str, Any]]]:
    try:
        if os.path.isfile(MOCK_DB_FILE):
            with open(MOCK_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_mock_data(collection_name: str, items: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(MOCK_DB_FILE), exist_ok=True)
        data = _load_mock_data()
        data[collection_name] = items
        with open(MOCK_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass

def _matches_filter(doc: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
    if not filter_dict:
        return True
    for k, v in filter_dict.items():
        if k == "$or" and isinstance(v, list):
            if not any(_matches_filter(doc, sub) for sub in v):
                return False
            continue
        if k == "$and" and isinstance(v, list):
            if not all(_matches_filter(doc, sub) for sub in v):
                return False
            continue
        doc_val = doc.get(k)
        if isinstance(v, dict):
            # Check operators
            if "$in" in v and doc_val not in v["$in"]:
                return False
            if "$nin" in v and doc_val in v["$nin"]:
                return False
            if "$gte" in v and (doc_val is None or doc_val < v["$gte"]):
                return False
            if "$lte" in v and (doc_val is None or doc_val > v["$lte"]):
                return False
            if "$gt" in v and (doc_val is None or doc_val <= v["$gt"]):
                return False
            if "$lt" in v and (doc_val is None or doc_val >= v["$lt"]):
                return False
            if "$ne" in v and doc_val == v["$ne"]:
                return False
        elif doc_val != v:
            return False
    return True

class MockCollection:
    def __init__(self, name: str, memory_store: Dict[str, List[Dict[str, Any]]]):
        self.name = name
        self._store = memory_store

    def _get_items(self) -> List[Dict[str, Any]]:
        if self.name not in self._store:
            self._store[self.name] = []
        return self._store[self.name]

    async def find_one(self, filter_dict: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        filter_dict = filter_dict or {}
        for item in self._get_items():
            if _matches_filter(item, filter_dict):
                return dict(item)
        return None

    async def find(
        self,
        filter_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, int]] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        filter_dict = filter_dict or {}
        matches = [dict(item) for item in self._get_items() if _matches_filter(item, filter_dict)]
        if sort:
            for k, direction in reversed(list(sort.items())):
                matches.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=(direction < 0))
        return matches[skip : skip + limit]

    async def insert_one(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(doc)
        if "_id" not in item:
            item["_id"] = str(time.time_ns())
        items = self._get_items()
        items.append(item)
        _save_mock_data(self.name, items)
        return {"acknowledged": True, "inserted_id": item["_id"]}

    async def insert_many(self, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        ids = []
        for d in docs:
            res = await self.insert_one(d)
            ids.append(res["inserted_id"])
        return {"acknowledged": True, "inserted_ids": ids}

    async def update_one(self, filter_dict: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> Dict[str, Any]:
        items = self._get_items()
        for idx, item in enumerate(items):
            if _matches_filter(item, filter_dict):
                if "$set" in update:
                    item.update(update["$set"])
                if "$inc" in update:
                    for k, val in update["$inc"].items():
                        item[k] = item.get(k, 0) + val
                items[idx] = item
                _save_mock_data(self.name, items)
                return {"acknowledged": True, "matched_count": 1, "modified_count": 1}
        
        if upsert:
            new_item = dict(filter_dict)
            if "$set" in update:
                new_item.update(update["$set"])
            await self.insert_one(new_item)
            return {"acknowledged": True, "matched_count": 0, "modified_count": 0, "upserted_id": new_item.get("_id")}

        return {"acknowledged": True, "matched_count": 0, "modified_count": 0}

    async def delete_one(self, filter_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = self._get_items()
        for idx, item in enumerate(items):
            if _matches_filter(item, filter_dict):
                del items[idx]
                _save_mock_data(self.name, items)
                return {"acknowledged": True, "deleted_count": 1}
        return {"acknowledged": True, "deleted_count": 0}

    async def delete_many(self, filter_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = self._get_items()
        original_len = len(items)
        kept = [item for item in items if not _matches_filter(item, filter_dict)]
        self._store[self.name] = kept
        _save_mock_data(self.name, kept)
        return {"acknowledged": True, "deleted_count": original_len - len(kept)}

    async def count_documents(self, filter_dict: Optional[Dict[str, Any]] = None) -> int:
        filter_dict = filter_dict or {}
        return sum(1 for item in self._get_items() if _matches_filter(item, filter_dict))

class DatabaseManager:
    """
    Unified Database Manager. Supports MongoDB via Motor with automated
    fallback to memory/file storage when MongoDB is not configured or offline.
    """
    def __init__(self):
        self._mongo_client = None
        self._mongo_db = None
        self._is_connected = False
        self._memory_store: Dict[str, List[Dict[str, Any]]] = _load_mock_data()

    async def initialize(self, executor: str = "system") -> bool:
        uri = settings.MONGODB_URI.strip()
        if not uri:
            logger.info("[Database] No MONGODB_URI configured. Running in high-performance in-memory mode.")
            self._is_connected = True
            return True

        try:
            import motor.motor_asyncio
            logger.info(f"[Database] Connecting to MongoDB instance at {uri.split('@')[-1]}...")
            self._mongo_client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
            self._mongo_db = self._mongo_client[settings.MONGODB_DB]
            # Ping test
            await self._mongo_client.admin.command("ping")
            self._is_connected = True
            logger.info(f"[Database] Connected to MongoDB database '{settings.MONGODB_DB}' successfully.")
            return True
        except Exception as err:
            logger.warn(f"[Database] MongoDB connection failed ({err}). Falling back to local storage.")
            self._mongo_client = None
            self._mongo_db = None
            self._is_connected = True
            return False

    def is_connected(self) -> bool:
        return self._is_connected

    async def ping(self) -> bool:
        if self._mongo_client:
            try:
                await self._mongo_client.admin.command("ping")
                return True
            except Exception:
                return False
        return True

    def collection(self, name: str) -> Any:
        if self._mongo_db is not None:
            return self._mongo_db[name]
        return MockCollection(name, self._memory_store)

    async def find_one(self, col_name: str, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        col = self.collection(col_name)
        if hasattr(col, "find_one"):
            return await col.find_one(filter_dict)
        return None

    async def insert_one(self, col_name: str, doc: Dict[str, Any]) -> Any:
        col = self.collection(col_name)
        return await col.insert_one(doc)

database = DatabaseManager()
