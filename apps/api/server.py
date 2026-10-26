import os
import time
from typing import Optional, Any
import json
import http.server
import threading
from urllib.parse import urlparse
try:
    from aiohttp import web
    _HAS_AIOHTTP = True
except ImportError:
    class MockWeb:
        Request = Any
        Response = Any
        Application = None
        AppRunner = None
        TCPSite = None
        @staticmethod
        def json_response(*args, **kwargs):
            return None
    web = MockWeb()
    _HAS_AIOHTTP = False
from config.settings import settings
from core.logging.logger import logger
from core.audit.audit_log import AuditLog
from database.database import database
from plugins.MomentumOneToolkit.tickets.api import handle_tickets_api
from .auth import handle_auth_routes

class ApiServer:
    def __init__(self, bot_manager: Any = None):
        self.bot_manager = bot_manager
        self.app = web.Application() if _HAS_AIOHTTP else None
        self.started_at = time.time()
        self.public_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "public")
        )
        if self.app is not None:
            self._setup_routes()

    def set_bot_manager(self, manager: Any) -> None:
        self.bot_manager = manager

    def _env_status(self) -> dict:
        return {
            "BOT_TOKEN": "configured" if settings.BOT_TOKEN else "missing",
            "DATABASE_URL": "configured" if settings.MONGODB_URI else "missing",
            "API_SECRET": "configured" if settings.API_SECRET else "missing",
            "CLIENT_ID": "configured" if settings.CLIENT_ID else "missing",
            "CLIENT_SECRET": "configured" if settings.CLIENT_SECRET else "missing",
            "NODE_ENV": settings.ENVIRONMENT,
        }

    def _bot_status(self) -> dict:
        if not self.bot_manager:
            return {
                "state": "offline",
                "reason": "bot_process_not_started",
                "process": False,
                "discordReady": False,
            }
        return self.bot_manager.status()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/index.html", self._handle_index)

        # Health & Bot Status
        self.app.router.add_get("/api/health", self._handle_health)
        self.app.router.add_get("/api/bot/status", self._handle_bot_status)
        self.app.router.add_get("/api/bot/info", self._handle_bot_status)
        self.app.router.add_get("/api/environment/status", self._handle_env_status)
        self.app.router.add_get("/api/database/status", self._handle_db_status)
        self.app.router.add_get("/api/audit-logs", self._handle_audit_logs)
        self.app.router.add_get("/api/config", self._handle_config)
        self.app.router.add_get("/api/registry", self._handle_registry)
        self.app.router.add_post("/api/restart", self._handle_restart)

        # Catch-all middleware/handlers for Auth & Tickets
        self.app.router.add_route("*", "/api/tickets{tail:.*}", self._handle_tickets_proxy)
        self.app.router.add_route("*", "/api/auth/{tail:.*}", self._handle_auth_proxy)

        # Static assets if public directory exists
        if os.path.isdir(self.public_dir):
            self.app.router.add_static("/static/", path=self.public_dir, name="static")

    async def _handle_index(self, request: web.Request) -> web.Response:
        index_file = os.path.join(self.public_dir, "index.html")
        if os.path.isfile(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html")
        return web.Response(text="<h1>MomentumOne Control Center</h1>", content_type="text/html")

    async def _handle_health(self, request: web.Request) -> web.Response:
        uptime = int((time.time() - self.started_at) * 1000)
        return web.json_response({
            "api": "reachable",
            "bot": self._bot_status(),
            "uptime": uptime
        })

    async def _handle_bot_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._bot_status())

    async def _handle_env_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._env_status())

    async def _handle_db_status(self, request: web.Request) -> web.Response:
        is_ok = await database.ping()
        if is_ok:
            return web.json_response({"state": "connected"})
        return web.json_response({"state": "unavailable", "error": "Database not reachable"}, status=503)

    async def _handle_audit_logs(self, request: web.Request) -> web.Response:
        page = max(1, int(request.query.get("page", 1)))
        limit = min(100, max(1, int(request.query.get("limit", 25))))
        entries = await AuditLog.list(skip=(page - 1) * limit, limit=limit)
        total = await AuditLog.count()
        return web.json_response({
            "entries": entries,
            "page": page,
            "limit": limit,
            "total": total
        })

    async def _handle_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            "environment": settings.ENVIRONMENT,
            "botEnabled": settings.BOT_ENABLED,
            "editable": []
        })

    async def _handle_registry(self, request: web.Request) -> web.Response:
        if self.bot_manager:
            return web.json_response(self.bot_manager.registry())
        return web.json_response({"commands": [], "plugins": [], "events": []})

    async def _handle_restart(self, request: web.Request) -> web.Response:
        return web.json_response({"error": "Restart is unavailable in this deployment"}, status=501)

    async def _handle_tickets_proxy(self, request: web.Request) -> web.Response:
        return await handle_tickets_api(request, self.bot_manager)

    async def _handle_auth_proxy(self, request: web.Request) -> web.Response:
        res = await handle_auth_routes(request, self.bot_manager)
        if res:
            return res
        return web.json_response({"error": "Auth route not found"}, status=404)

    async def start(self) -> None:
        base_port = int(os.getenv("API_PORT", 3000))
        host = settings.HOST

        if _HAS_AIOHTTP and self.app is not None:
            runner = web.AppRunner(self.app)
            await runner.setup()
            for offset in range(10):
                target_port = base_port + offset
                try:
                    site = web.TCPSite(runner, host=host, port=target_port)
                    await site.start()
                    if offset > 0:
                        logger.warn(f"[Server] Port {base_port} in use, bound to fallback port {target_port}")
                    else:
                        logger.info(f"[Server] MomentumOne Web API & Control Center listening on http://{host}:{target_port}")
                    return
                except OSError as e:
                    if e.errno == 98 or "address already in use" in str(e).lower():
                        continue
                    raise
            logger.error(f"[Server] Could not bind web server to any port in range {base_port}-{base_port+9}")
        else:
            server_ref = self
            class StdlibHandler(http.server.BaseHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass

                def do_GET(self):
                    parsed = urlparse(self.path)
                    path = parsed.path
                    if path in ("/", "/index.html"):
                        index_file = os.path.join(server_ref.public_dir, "index.html")
                        if os.path.isfile(index_file):
                            with open(index_file, "rb") as f:
                                body = f.read()
                            self.send_response(200)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(body)
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(b"<!DOCTYPE html><html><head><title>Sentinel Control Platform</title></head><body><h1>Sentinel Control Platform</h1><p>MomentumOne Server Active</p></body></html>")
                        return
                    elif path == "/api/health":
                        uptime = int((time.time() - server_ref.started_at) * 1000)
                        self._send_json({"api": "reachable", "bot": server_ref._bot_status(), "uptime": uptime})
                        return
                    elif path in ("/api/bot/status", "/api/bot/info"):
                        self._send_json(server_ref._bot_status())
                        return
                    elif path == "/api/environment/status":
                        self._send_json(server_ref._env_status())
                        return
                    elif path == "/api/config":
                        self._send_json({"environment": settings.ENVIRONMENT, "botEnabled": settings.BOT_ENABLED, "editable": []})
                        return
                    elif path == "/api/registry":
                        reg = server_ref.bot_manager.registry() if server_ref.bot_manager else {"commands": [], "plugins": [], "events": []}
                        self._send_json(reg)
                        return
                    elif path.startswith("/static/"):
                        rel_path = path[len("/static/"):].lstrip("/")
                        file_path = os.path.join(server_ref.public_dir, rel_path)
                        if os.path.isfile(file_path):
                            with open(file_path, "rb") as f:
                                body = f.read()
                            self.send_response(200)
                            self.end_headers()
                            self.wfile.write(body)
                            return
                    self.send_response(404)
                    self.end_headers()

                def do_POST(self):
                    self._send_json({"error": "Action unavailable"}, status=501)

                def _send_json(self, data, status=200):
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode("utf-8"))

            for offset in range(10):
                target_port = base_port + offset
                try:
                    httpd = http.server.ThreadingHTTPServer((host, target_port), StdlibHandler)
                    t = threading.Thread(target=httpd.serve_forever, daemon=True)
                    t.start()
                    logger.info(f"[Server] MomentumOne Web API & Control Center listening on http://{host}:{target_port}")
                    return
                except OSError as e:
                    if e.errno == 98 or "address already in use" in str(e).lower():
                        continue
                    raise
            logger.error(f"[Server] Could not bind stdlib web server to any port in range {base_port}-{base_port+9}")
