import time
import uuid
from typing import Dict, Any, Optional, List
from aiohttp import web
from config.settings import settings

class SessionManager:
    _sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def create_session(cls, user_data: Dict[str, Any], guilds: List[Dict[str, Any]], is_demo: bool = False) -> Dict[str, Any]:
        sess_id = str(uuid.uuid4())
        session = {
            "id": sess_id,
            "user": user_data,
            "guilds": guilds,
            "createdAt": time.time(),
            "expiresAt": time.time() + 86400 * 7,
            "isDemo": is_demo
        }
        cls._sessions[sess_id] = session
        return session

    @classmethod
    def get_session(cls, sess_id: str) -> Optional[Dict[str, Any]]:
        sess = cls._sessions.get(sess_id)
        if not sess:
            return None
        if sess["expiresAt"] < time.time():
            del cls._sessions[sess_id]
            return None
        return sess

    @classmethod
    def delete_session(cls, sess_id: str) -> None:
        cls._sessions.pop(sess_id, None)

async def handle_auth_routes(request: web.Request, bot_manager: Any = None) -> Optional[web.Response]:
    path = request.path

    if path == "/api/auth/demo" and request.method == "POST":
        demo_user = {
            "id": "100000000000000001",
            "username": "AdminDemo",
            "discriminator": "0001",
            "avatar": None,
            "global_name": "Demo Administrator"
        }
        demo_guilds = [
            {
                "id": "guild_test_admin",
                "name": "Production Nexus",
                "icon": None,
                "owner": True,
                "permissions": 8,
                "botPresent": True,
                "memberCount": 142
            }
        ]
        session = SessionManager.create_session(demo_user, demo_guilds, is_demo=True)
        response = web.json_response({"success": True, "session": session})
        response.set_cookie("momentum_session", session["id"], max_age=86400 * 7, httponly=True)
        return response

    if path == "/api/auth/session" and request.method == "GET":
        sess_id = request.cookies.get("momentum_session")
        if sess_id:
            session = SessionManager.get_session(sess_id)
            if session:
                return web.json_response({"authenticated": True, "session": session})
        return web.json_response({"authenticated": False, "session": None})

    if path == "/api/auth/guilds" and request.method == "GET":
        sess_id = request.cookies.get("momentum_session")
        guilds = []
        if sess_id:
            sess = SessionManager.get_session(sess_id)
            if sess:
                guilds = sess.get("guilds", [])
        
        # If bot is connected, merge bot guilds
        if bot_manager and hasattr(bot_manager, "client") and bot_manager.client.is_ready():
            for g in bot_manager.client.guilds:
                if not any(x.get("id") == str(g.id) for x in guilds):
                    guilds.append({
                        "id": str(g.id),
                        "name": g.name,
                        "icon": str(g.icon.url) if g.icon else None,
                        "owner": False,
                        "permissions": 8,
                        "botPresent": True,
                        "memberCount": g.member_count or len(g.members)
                    })

        return web.json_response({"guilds": guilds})

    if path == "/api/auth/logout" and request.method == "POST":
        sess_id = request.cookies.get("momentum_session")
        if sess_id:
            SessionManager.delete_session(sess_id)
        response = web.json_response({"success": True})
        response.del_cookie("momentum_session")
        return response

    return None
