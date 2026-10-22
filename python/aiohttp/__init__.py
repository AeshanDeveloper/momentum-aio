from unittest.mock import MagicMock, AsyncMock

class ClientSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def post(self, *args, **kwargs):
        return _MockResponseContext()

    def get(self, *args, **kwargs):
        return _MockResponseContext()

class _MockResponseContext:
    async def __aenter__(self):
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={})
        resp.text = AsyncMock(return_value="")
        return resp

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class web:
    Response = object
    Request = object

    @staticmethod
    def json_response(data=None, status=200, **kwargs):
        return {"data": data, "status": status}
