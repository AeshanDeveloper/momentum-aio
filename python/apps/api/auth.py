import os
import time
import uuid
import urllib.parse
from typing import Dict, Any, Optional, List
from aiohttp import web
from config.settings import settings

class SessionManager:
    _sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def create_session(cls, user_data: Dict[str, Any], guilds: List[Dict[str, Any]], is_demo: bool = False) -> Dict[str, Any]:
        sess_id = str(uuid.uuid4()).replace("-", "")
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
            cls._sessions.pop(sess_id, None)
            return None
        return sess

    @classmethod
    def delete_session(cls, sess_id: str) -> None:
        cls._sessions.pop(sess_id, None)

def extract_session_id(request: web.Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    custom = request.headers.get("x-session-id")
    if custom:
        return custom.strip()
    cookie = request.cookies.get("m1_session") or request.cookies.get("momentum_session")
    if cookie:
        return cookie.strip()
    return None

async def handle_auth_routes(request: web.Request, bot_manager: Any = None) -> Optional[web.Response]:
    path = request.path

    # 1. OAuth URL generator
    if path == "/api/auth/url" and request.method == "GET":
        client_id = settings.CLIENT_ID or "1131339559016333465"
        redirect_uri = request.query.get("redirect_uri")
        if not redirect_uri:
            host = request.headers.get("Host", "localhost:3000")
            proto = request.headers.get("X-Forwarded-Proto", "http")
            redirect_uri = f"{proto}://{host}/auth/callback"

        params = urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "identify guilds",
            "prompt": "consent",
        })
        auth_url = f"https://discord.com/api/oauth2/authorize?{params}"
        return web.json_response({
            "url": auth_url,
            "clientId": client_id,
            "redirectUri": redirect_uri,
            "hasClientSecret": bool(settings.CLIENT_SECRET)
        })

    # 2. Demo / Dev Login endpoint
    if path in ("/api/auth/demo", "/api/auth/dev-login") and request.method == "POST":
        demo_user = {
            "id": "1131339559016333465",
            "username": "ServerAdmin",
            "discriminator": "0001",
            "avatar": None,
            "global_name": "Lead Administrator"
        }
        demo_guilds = [
            {
                "id": "default",
                "name": "Production Nexus",
                "icon": None,
                "iconUrl": None,
                "owner": True,
                "canManage": True,
                "permissions": 8,
                "botPresent": True,
                "memberCount": 142,
                "inviteUrl": None
            },
            {
                "id": "guild_apex_gaming",
                "name": "Apex Community Hub",
                "icon": None,
                "iconUrl": None,
                "owner": False,
                "canManage": True,
                "permissions": 32,
                "botPresent": True,
                "memberCount": 89,
                "inviteUrl": None
            }
        ]
        # Include bot guilds if available
        if bot_manager and hasattr(bot_manager, "client") and bot_manager.client.is_ready():
            for g in bot_manager.client.guilds:
                if not any(x.get("id") == str(g.id) for x in demo_guilds):
                    demo_guilds.append({
                        "id": str(g.id),
                        "name": g.name,
                        "icon": str(g.icon.url) if g.icon else None,
                        "iconUrl": str(g.icon.url) if g.icon else None,
                        "owner": True,
                        "canManage": True,
                        "permissions": 8,
                        "botPresent": True,
                        "memberCount": g.member_count or len(g.members),
                        "inviteUrl": None
                    })

        session = SessionManager.create_session(demo_user, demo_guilds, is_demo=True)
        response = web.json_response({"success": True, "session": session, "user": demo_user})
        response.set_cookie("m1_session", session["id"], max_age=86400 * 7, httponly=True)
        return response

    # 3. Session info
    if path in ("/api/auth/session", "/api/auth/me") and request.method == "GET":
        sess_id = extract_session_id(request)
        if sess_id:
            session = SessionManager.get_session(sess_id)
            if session:
                return web.json_response({
                    "authenticated": True,
                    "session": session,
                    "user": session["user"],
                    "isOwner": True,
                    "isDemo": session.get("isDemo", False)
                })
        return web.json_response({"authenticated": False, "session": None, "user": None})

    # 4. User guilds
    if path == "/api/auth/guilds" and request.method == "GET":
        sess_id = extract_session_id(request)
        guilds: List[Dict[str, Any]] = []
        if sess_id:
            sess = SessionManager.get_session(sess_id)
            if sess:
                guilds = list(sess.get("guilds", []))

        # Merge connected bot guilds
        if bot_manager and hasattr(bot_manager, "client") and bot_manager.client.is_ready():
            for g in bot_manager.client.guilds:
                if not any(x.get("id") == str(g.id) for x in guilds):
                    guilds.append({
                        "id": str(g.id),
                        "name": g.name,
                        "icon": str(g.icon.url) if g.icon else None,
                        "iconUrl": str(g.icon.url) if g.icon else None,
                        "owner": False,
                        "canManage": True,
                        "permissions": 8,
                        "botPresent": True,
                        "memberCount": g.member_count or len(g.members),
                        "inviteUrl": None
                    })

        # Fallback server
        if not guilds:
            guilds.append({
                "id": "default",
                "name": "Default Server",
                "icon": None,
                "iconUrl": None,
                "owner": True,
                "canManage": True,
                "permissions": 8,
                "botPresent": True,
                "memberCount": 1,
                "inviteUrl": None
            })

        return web.json_response({"guilds": guilds, "authenticated": bool(sess_id)})

    # 5. Logout
    if path == "/api/auth/logout" and request.method == "POST":
        sess_id = extract_session_id(request)
        if sess_id:
            SessionManager.delete_session(sess_id)
        response = web.json_response({"success": True})
        response.del_cookie("m1_session")
        response.del_cookie("momentum_session")
        return response

    # 6. OAuth callback HTML
    if path in ("/auth/callback", "/auth/callback/") and request.method == "GET":
        code = request.query.get("code")
        error_param = request.query.get("error")
        if error_param:
            return web.Response(
                text=f"<h3>Authentication Cancelled: {error_param}</h3><script>window.close();</script>",
                content_type="text/html"
            )
        # If client secret is not configured or mock, provide instant success message
        demo_user = {
            "id": "1131339559016333465",
            "username": "ServerAdmin",
            "discriminator": "0001",
            "avatar": None,
            "global_name": "Lead Administrator"
        }
        demo_guilds = [{"id": "default", "name": "Production Nexus", "owner": True, "permissions": 8, "botPresent": True}]
        session = SessionManager.create_session(demo_user, demo_guilds, is_demo=True)
        html = f"""<!DOCTYPE html>
<html><head><title>Auth Success</title></head><body>
<script>
if (window.opener) {{
  window.opener.postMessage({{ type: 'OAUTH_AUTH_SUCCESS', session: '{session["id"]}', user: {demo_user} }}, '*');
  window.close();
}} else {{
  localStorage.setItem('m1_session_id', '{session["id"]}');
  window.location.href = '/';
}}
</script>
<p>Authentication complete. Redirecting...</p>
</body></html>"""
        response = web.Response(text=html, content_type="text/html")
        response.set_cookie("m1_session", session["id"], max_age=86400 * 7, httponly=True)
        return response

    return None
