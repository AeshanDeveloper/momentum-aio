import type { IncomingMessage, ServerResponse } from "node:http";
import DatabaseManager from "@database/Database";
import logger from "@logger";
import { TicketManager } from "./TicketManager";
import type { TicketRecord } from "./types";

function json(res: ServerResponse, status: number, body: unknown): void {
	if (res.headersSent) return;
	res.writeHead(status, {
		"content-type": "application/json; charset=utf-8",
		"cache-control": "no-store",
	});
	res.end(JSON.stringify(body));
}

async function parseBody(req: IncomingMessage): Promise<any> {
	return new Promise((resolve) => {
		let data = "";
		req.on("data", (chunk) => {
			data += chunk;
		});
		req.on("end", () => {
			try {
				resolve(data ? JSON.parse(data) : {});
			} catch {
				resolve({});
			}
		});
	});
}

export async function handleTicketsApi(
	req: IncomingMessage,
	res: ServerResponse,
	url: URL,
	botManager: any
): Promise<boolean> {
	const method = req.method?.toUpperCase() ?? "GET";
	const pathname = url.pathname;

	if (!pathname.startsWith("/api/tickets")) {
		return false;
	}

	try {
		// Route: /api/tickets/guild/:guildId...
		const guildMatch = pathname.match(/^\/api\/tickets\/guild\/([^/]+)(.*)$/);
		if (guildMatch) {
			const guildId = guildMatch[1];
			const subpath = guildMatch[2];
			const actorId = (req.headers["x-user-id"] as string) || "dashboard_admin";

			// Base Guild Tickets & Config
			if (subpath === "" || subpath === "/") {
				if (method === "GET") {
					const config = await TicketManager.getGuildConfig(guildId);
					const col = await DatabaseManager.collection("economy_tickets");
					const tickets = (await col.find({ guildId }).sort({ createdAt: -1 }).toArray()) as TicketRecord[];

					const stats = {
						total: tickets.length,
						open: tickets.filter((t) => t.status === "open").length,
						approved: tickets.filter((t) => t.status === "approved").length,
						rejected: tickets.filter((t) => t.status === "rejected").length,
						closed: tickets.filter((t) => t.status === "closed").length,
						deposits: tickets.filter((t) => t.type === "deposit").length,
						withdrawals: tickets.filter((t) => t.type === "withdrawal").length,
					};

					json(res, 200, { config, tickets, stats });
					return true;
				}
			}

			// Update Guild Config
			if (subpath === "/config" && (method === "POST" || method === "PUT")) {
				const body = await parseBody(req);
				const updated = await TicketManager.updateGuildConfig(guildId, body, actorId);
				json(res, 200, updated);
				return true;
			}

			// Ticket Specific Actions: /api/tickets/guild/:guildId/:ticketId/(approve|reject|close)
			const actionMatch = subpath.match(/^\/([^/]+)\/(approve|reject|close)$/);
			if (actionMatch && method === "POST") {
				const ticketId = actionMatch[1];
				const action = actionMatch[2];
				const body = await parseBody(req);
				const note = body.note || body.reason || `Action via Dashboard by ${actorId}`;

				const ticket = await TicketManager.getTicketById(ticketId);
				if (!ticket) {
					json(res, 404, { error: `Ticket #${ticketId} not found.` });
					return true;
				}

				const client = botManager?.client;
				const staffUser = { id: actorId, username: actorId };

				if (action === "approve") {
					if (ticket.type === "deposit") {
						const result = await TicketManager.processDeposit(ticketId, staffUser, true, note);
						if (!result.success) {
							json(res, 400, { error: result.error });
							return true;
						}
					} else if (ticket.type === "withdrawal") {
						const result = await TicketManager.processWithdrawal(ticketId, staffUser, true, note, client);
						if (!result.success) {
							json(res, 400, { error: result.error });
							return true;
						}
					} else {
						// For general ticket, mark as approved
						const col = await DatabaseManager.collection("economy_tickets");
						await col.updateOne({ ticketId }, { $set: { status: "approved", assignedStaffId: actorId, updatedAt: new Date() } });
					}
					json(res, 200, { success: true, message: `Ticket #${ticketId} approved.` });
					return true;
				}

				if (action === "reject") {
					if (ticket.type === "deposit") {
						const result = await TicketManager.processDeposit(ticketId, staffUser, false, note);
						if (!result.success) {
							json(res, 400, { error: result.error });
							return true;
						}
					} else if (ticket.type === "withdrawal") {
						const result = await TicketManager.processWithdrawal(ticketId, staffUser, false, note, client);
						if (!result.success) {
							json(res, 400, { error: result.error });
							return true;
						}
					} else {
						const col = await DatabaseManager.collection("economy_tickets");
						await col.updateOne({ ticketId }, { $set: { status: "rejected", assignedStaffId: actorId, updatedAt: new Date() } });
					}
					json(res, 200, { success: true, message: `Ticket #${ticketId} rejected.` });
					return true;
				}

				if (action === "close") {
					const result = await TicketManager.closeTicket(guildId, ticketId, actorId, note, client);
					if (!result.success) {
						json(res, 400, { error: result.error });
						return true;
					}
					json(res, 200, { success: true, message: `Ticket #${ticketId} closed.` });
					return true;
				}
			}
		}

		json(res, 404, { error: "Tickets endpoint not found" });
		return true;
	} catch (error) {
		logger.error("[TicketsApi] Request handling error:", error);
		json(res, 500, { error: error instanceof Error ? error.message : "Internal server error" });
		return true;
	}
}
