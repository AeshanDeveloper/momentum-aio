from aiohttp import web
from typing import Any
from .manager import TicketManager

async def handle_tickets_api(request: web.Request, bot_manager: Any = None) -> web.Response:
    path = request.path
    if request.method == "GET" and path == "/api/tickets":
        guild_id = request.query.get("guild_id")
        status = request.query.get("status")
        tickets = await TicketManager.list_tickets(guild_id=guild_id, status=status)
        return web.json_response({"tickets": tickets, "count": len(tickets)})

    if request.method == "POST" and path == "/api/tickets/config":
        try:
            body = await request.json()
            guild_id = body.get("guild_id")
            if not guild_id:
                return web.json_response({"error": "guild_id is required"}, status=400)
            res = await TicketManager.update_guild_config(guild_id, body)
            return web.json_response({"success": True, "config": res})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)

    return web.json_response({"error": "Not found"}, status=404)
