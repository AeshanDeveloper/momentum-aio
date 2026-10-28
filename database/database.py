import os
import json
import time
import asyncio
from typing import Dict, Any, List, Optional
from config.settings import settings
from core.logging.logger import logger

MOCK_DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".data", "local_db.json"))

_mock_db_cache: Dict[str, List[Dict[str, Any]]] = {}
_mock_db_loaded: bool = False

def _load_mock_data() -> Dict[str, List[Dict[str, Any]]]:
    global _mock_db_cache, _mock_db_loaded
    if _mock_db_loaded:
        return _mock_db_cache
    try:
        if os.path.isfile(MOCK_DB_FILE):
            with open(MOCK_DB_FILE, "r", encoding="utf-8") as f:
                _mock_db_cache = json.load(f)
    except Exception:
        _mock_db_cache = {}
    _mock_db_loaded = True
    return _mock_db_cache

_last_mock_disk_save: float = 0.0

def _save_mock_data(collection_name: str, items: List[Dict[str, Any]]) -> None:
    global _mock_db_cache, _last_mock_disk_save
    _mock_db_cache[collection_name] = items
    now = time.time()
    if now - _last_mock_disk_save < 1.0:
        return
    _last_mock_disk_save = now
    try:
        os.makedirs(os.path.dirname(MOCK_DB_FILE), exist_ok=True)
        with open(MOCK_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(_mock_db_cache, f, default=str)
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

class MockCursor:
    def __init__(self, items: List[Dict[str, Any]]):
        self._items = list(items)
        self._skip = 0
        self._limit = None

    def sort(self, key_or_list: Any, direction: int = 1) -> "MockCursor":
        if isinstance(key_or_list, list):
            for k, d in reversed(key_or_list):
                self._items.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=(d < 0))
        elif isinstance(key_or_list, dict):
            for k, d in reversed(list(key_or_list.items())):
                self._items.sort(key=lambda x: (x.get(k) is None, x.get(k)), reverse=(d < 0))
        elif isinstance(key_or_list, str):
            self._items.sort(key=lambda x: (x.get(key_or_list) is None, x.get(key_or_list)), reverse=(direction < 0))
        return self

    def skip(self, n: int) -> "MockCursor":
        self._skip = max(0, int(n))
        return self

    def limit(self, n: int) -> "MockCursor":
        self._limit = max(0, int(n))
        return self

    def _get_sliced(self) -> List[Dict[str, Any]]:
        res = self._items[self._skip:]
        if self._limit is not None:
            res = res[:self._limit]
        return res

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        res = self._get_sliced()
        if length is not None:
            return res[:length]
        return res

    def __aiter__(self):
        async def _gen():
            for item in self._get_sliced():
                yield item
        return _gen()

    def __await__(self):
        async def _await_helper():
            return self._get_sliced()
        return _await_helper().__await__()


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

    def find(
        self,
        filter_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[Any] = None,
        skip: int = 0,
        limit: Optional[int] = None
    ) -> MockCursor:
        filter_dict = filter_dict or {}
        matches = [dict(item) for item in self._get_items() if _matches_filter(item, filter_dict)]
        cursor = MockCursor(matches)
        if sort:
            cursor.sort(sort)
        if skip:
            cursor.skip(skip)
        if limit is not None:
            cursor.limit(limit)
        return cursor

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

    def find_one(self, col_name: str, filter_dict: Dict[str, Any]) -> Any:
        col = self.collection(col_name)
        if hasattr(col, "find_one"):
            return col.find_one(filter_dict)
        return None

    def insert_one(self, col_name: str, doc: Dict[str, Any]) -> Any:
        col = self.collection(col_name)
        return col.insert_one(doc)

    def update_one(self, col_name: str, filter_dict: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> Any:
        col = self.collection(col_name)
        if hasattr(col, "update_one"):
            res = col.update_one(filter_dict, update, upsert=upsert)
            # If called synchronously in a non-awaited context and loop is running, schedule background task
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running() and asyncio.iscoroutine(res):
                    return loop.create_task(res)
            except RuntimeError:
                pass
            return res
        return None

    def delete_one(self, col_name: str, filter_dict: Dict[str, Any]) -> Any:
        col = self.collection(col_name)
        if hasattr(col, "delete_one"):
            res = col.delete_one(filter_dict)
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running() and asyncio.iscoroutine(res):
                    return loop.create_task(res)
            except RuntimeError:
                pass
            return res
        return None

    def delete_many(self, col_name: str, filter_dict: Dict[str, Any]) -> Any:
        col = self.collection(col_name)
        if hasattr(col, "delete_many"):
            res = col.delete_many(filter_dict)
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running() and asyncio.iscoroutine(res):
                    return loop.create_task(res)
            except RuntimeError:
                pass
            return res
        return None

    def find(self, col_name: str, filter_dict: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        col = self.collection(col_name)
        return col.find(filter_dict or {}, **kwargs)

    def count_documents(self, col_name: str, filter_dict: Optional[Dict[str, Any]] = None) -> Any:
        col = self.collection(col_name)
        return col.count_documents(filter_dict or {})

database = DatabaseManager()

