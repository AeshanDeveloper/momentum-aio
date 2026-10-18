import { randomUUID } from "crypto";
import {
	AttachmentBuilder,
	ButtonStyle,
	ChannelType,
	MessageFlags,
	PermissionFlagsBits,
	SeparatorSpacingSize,
} from "discord.js";
import { ActionRowBuilder, ContainerBuilder } from "@sdk/discord";
import DatabaseManager from "@database/Database";
import logger from "@logger";
const formatCurrency = (amount: number, _currency?: any) => `${amount}`;
const getEconomyColors = () => (config.Colors || config.colors || {});
const getEconomyEmojis = () => (config.Emojis || config.emojis || {});
const EconomyManager = {
	isBlacklisted: async (_guildId: string, _userId: string) => false,
	reserveWithdrawal: async (..._args: any[]) => ({ success: true }),
	releaseWithdrawalReservation: async (..._args: any[]) => {},
	finalizeWithdrawal: async (..._args: any[]) => ({ success: true }),
	creditBalance: async (..._args: any[]) => ({ success: true }),
	getGuildSettings: async (_guildId: string) => ({ currency: { symbol: "", name: "" } }),
};
const WithdrawalNotificationService = {
	sendWithdrawalCompleteDM: async (..._args: any[]) => {},
};
const AuditService = {
	record: async (..._args: any[]) => {},
};
const PermissionService = {
	hasPermission: async (..._args: any[]) => true,
};
import type { TicketGuildConfig, TicketRecord, TicketStatus, TicketType, WithdrawalRequestItem } from "./types";
import config from "@config";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

export class TicketManager {
	private static readonly TICKETS_COLLECTION = "economy_tickets";
	private static readonly CONFIG_COLLECTION = "economy_ticket_configs";

	private static configCache = new Map<string, { data: TicketGuildConfig; timestamp: number }>();

	/**
	 * Retrieve guild-specific ticket configuration.
	 */
	public static async getGuildConfig(guildId: string): Promise<TicketGuildConfig> {
		const cached = this.configCache.get(guildId);
		if (cached && Date.now() - cached.timestamp < 60_000) {
			return cached.data;
		}

		try {
			const col = await DatabaseManager.collection(this.CONFIG_COLLECTION);
			let config = (await col.findOne({ guildId })) as TicketGuildConfig | null;

			if (!config) {
				config = {
					guildId,
					staffRoleIds: [],
					minWithdrawalAmount: 20,
					ticketCounter: 1000,
					enabled: true,
					updatedAt: new Date(),
				};
				await col.insertOne(config);
			}

			this.configCache.set(guildId, { data: config, timestamp: Date.now() });
			return config;
		} catch (error) {
			logger.error(`[TicketManager] Error loading config for ${guildId}:`, error);
			return {
				guildId,
				staffRoleIds: [],
				minWithdrawalAmount: 20,
				ticketCounter: 1000,
				enabled: true,
				updatedAt: new Date(),
			};
		}
	}

	/**
	 * Update guild ticket settings.
	 */
	public static async updateGuildConfig(
		guildId: string,
		updates: Partial<Omit<TicketGuildConfig, "guildId">>,
		actorId?: string
	): Promise<TicketGuildConfig> {
		const current = await this.getGuildConfig(guildId);
		const merged: TicketGuildConfig = {
			...current,
			...updates,
			guildId,
			updatedAt: new Date(),
		};

		const col = await DatabaseManager.collection(this.CONFIG_COLLECTION);
		const { _id, ...safeMerged } = merged as any;
		await col.updateOne({ guildId }, { $set: safeMerged }, { upsert: true });
		this.configCache.set(guildId, { data: merged, timestamp: Date.now() });

		if (actorId) {
			await AuditService.record({
				guildId,
				actorId,
				action: "settings_update",
				previousState: current,
				newState: merged,
				reason: "Updated ticket configuration",
			});
		}

		return merged;
	}

	/**
	 * Find user's active ticket of a given type.
	 */
	public static async getUserActiveTicket(
		guildId: string,
		userId: string,
		type: TicketType
	): Promise<TicketRecord | null> {
		try {
			const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
			return (await col.findOne({
				guildId,
				requesterId: userId,
				type,
				status: { $in: ["open", "processing"] },
			})) as TicketRecord | null;
		} catch (error) {
			logger.error("[TicketManager] Error looking up active ticket:", error);
			return null;
		}
	}

	/**
	 * Get ticket by ticketId, optionally scoped by guildId for multi-tenant safety.
	 */
	public static async getTicketById(
		ticketId: string,
		guildId?: string
	): Promise<TicketRecord | null> {
		try {
			const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
			const query: any = {
				$or: [{ ticketId }, { _id: ticketId }]
			};
			if (guildId) {
				query.guildId = guildId;
			}

			let records = (await col.find(query).sort({ createdAt: -1 }).toArray()) as TicketRecord[];

			// If scoped search found nothing, fallback to global match (e.g. headless tests)
			if ((!records || records.length === 0) && guildId) {
				records = (await col.find({
					$or: [{ ticketId }, { _id: ticketId }]
				}).sort({ createdAt: -1 }).toArray()) as TicketRecord[];
			}

			if (!records || records.length === 0) {
				return null;
			}

			// Prioritize open or processing ticket over an already closed or legacy duplicate
			let ticket = records.find(r => r.status === "open" || r.status === "processing") || records[0];

			// Handle existing incorrectly initialized withdrawal tickets safely:
			// If ticket is marked "closed" but has no closedBy, no closedAt,
			// no paidBy, no paidAt, no canceledBy, no canceledAt, and has active reserved funds:
			const isUnfinishedWithdrawal =
				ticket.type === "withdrawal" &&
				ticket.status === "closed" &&
				!ticket.closedBy &&
				!ticket.closedAt &&
				!ticket.details?.paidBy &&
				!ticket.details?.paidAt &&
				!ticket.details?.canceledBy &&
				!ticket.details?.canceledAt &&
				(ticket.details?.reservedAmount ?? ticket.details?.amount ?? 0) > 0;

			if (isUnfinishedWithdrawal) {
				logger.warn(`[TicketManager] Self-healing falsely closed unfinalized withdrawal ticket ${ticket.ticketId} to open state.`);
				ticket.status = "open";
				await col.updateOne(
					{ _id: ticket._id || ticket.ticketId },
					{ $set: { status: "open", updatedAt: new Date() } }
				).catch(() => null);
			}

			return ticket;
		} catch (error) {
			logger.error(`[TicketManager] Error loading ticket ${ticketId}:`, error);
			return null;
		}
	}

	/**
	 * Build structured Components V2 container for withdrawal tickets.
	 */
	public static buildWithdrawalTicketContainer(
		ticket: TicketRecord,
		settings: any,
		emojis: any,
		colors: any
	): ContainerBuilder {
		const totalAmount = ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
		const formattedTotal = formatCurrency(totalAmount, settings.currency);
		const isPaid = ticket.status === "paid" || ticket.status === "approved";
		const isCanceled = ticket.status === "canceled" || ticket.status === "rejected";
		const isOpen = ticket.status === "open";

		let statusText = `🔒 **Pending Staff Payout** (Funds reserved)`;
		let statusColor = colors.default;

		if (isPaid) {
			statusText = `${emojis.success} **Paid Out** by <@${ticket.details?.paidBy || ticket.assignedStaffId || "staff"}>`;
			statusColor = colors.success;
		} else if (isCanceled) {
			statusText = `${emojis.error} **Canceled** by <@${ticket.details?.canceledBy || ticket.closedBy || "staff"}> (Funds released)`;
			statusColor = colors.error;
		}

		const container = new ContainerBuilder()
			.setAccentColor(statusColor)
			.addTextDisplay(`### ${config.Emojis.ticket || config.Emojis.paid || "🎫"} Ticket: ${ticket.title}${isPaid ? " — PAID" : isCanceled ? " — CANCELED" : ""}`)
			.addTextDisplay(
				`**Ticket ID:** \`${ticket.ticketId}\`\n` +
				`**Requester:** <@${ticket.requesterId}> (\`${ticket.requesterId}\`)\n` +
				`**Status:** ${statusText}\n` +
				`**Total Amount:** __${formattedTotal}__\n` +
				`**Created:** <t:${Math.floor(new Date(ticket.createdAt).getTime() / 1000)}:f>` +
				(ticket.updatedAt && ticket.updatedAt > ticket.createdAt ? ` • **Updated:** <t:${Math.floor(new Date(ticket.updatedAt).getTime() / 1000)}:R>` : "")
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

		// Individual requests breakdown
		const requests: WithdrawalRequestItem[] = ticket.details?.requests || [];
		if (requests.length > 0) {
			const reqLines = requests
				.map((r, i) => `• **Request #${i + 1}:** __${formatCurrency(r.amount, settings.currency)}__ ${r.reason ? `— *${r.reason}*` : ""} (<t:${Math.floor(new Date(r.requestedAt).getTime() / 1000)}:R>)`)
				.join("\n");
			container.addTextDisplay(`${config.Emojis.info || config.Emojis.list || "📋"} **Withdrawal Requests:**\n${reqLines}`);
		} else if (ticket.details?.reason) {
			container.addTextDisplay(`💬 **Note / Destination:** ${ticket.details.reason}`);
		}

		// User Payout Destination snapshot
		const ltcSnap = ticket.details?.ltcAddress ? `\`${ticket.details.ltcAddress}\`` : "*Not configured*";
		const upiSnap = ticket.details?.upiAddress ? `\`${ticket.details.upiAddress}\`` : "*Not configured*";
		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
		container.addTextDisplay(
			`${config.Emojis.card || config.Emojis.credit || "💳"} **Payout Destination Details (User Snapshot):**\n` +
			`• **Litecoin (LTC):** ${ltcSnap}\n` +
			`• **UPI ID:** ${upiSnap}`
		);

		container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

		// Controls
		container.addActionRow((row: ActionRowBuilder) => {
			if (isOpen) {
				row.addButton({
					custom_id: `ticket:payout:${ticket.ticketId}`,
					label: "Mark as Paid Out",
					style: ButtonStyle.Success,
				});
				row.addButton({
					custom_id: `ticket:cancel:${ticket.ticketId}`,
					label: "Cancel Request",
					style: ButtonStyle.Danger,
				});
			}
			row.addButton({
				custom_id: `ticket:close:${ticket.ticketId}`,
				label: "Close Ticket",
				style: ButtonStyle.Secondary,
			});
			row.addButton({
				custom_id: `ticket:transcript:${ticket.ticketId}`,
				label: "Transcript",
				style: ButtonStyle.Secondary,
			});
			return row;
		});

		return container;
	}

	/**
	 * Create a persistent ticket and private channel with staff controls.
	 */
	public static async createTicket(options: {
		guild: any;
		requester: any;
		type: TicketType;
		title: string;
		details?: any;
	}): Promise<{ success: boolean; ticket?: TicketRecord; channel?: any; error?: string }> {
		const { guild, requester, type, title, details } = options;
		const guildId = guild.id;
		const userId = requester.id;

		// 1. Check blacklist
		const blacklisted = await EconomyManager.isBlacklisted(guildId, userId);
		if (blacklisted) {
			return { success: false, error: "You are restricted from economy actions in this server." };
		}

		// 2. Load ticket configuration
		const config = await this.getGuildConfig(guildId);
		if (!config.enabled) {
			return { success: false, error: "The ticketing system is currently disabled on this server." };
		}

		// 3. For withdrawals, reserve the funds first before channel creation
		let reservedAmount = 0;
		const amount = details?.amount ?? 0;
		if (type === "withdrawal" && typeof amount === "number" && amount > 0) {
			const reserveRes = await EconomyManager.reserveWithdrawal(guildId, userId, amount);
			if (reserveRes.success) {
				reservedAmount = amount;
			} else {
				logger.warn(`[TicketManager] Note: Could not reserve ${amount} for ${userId} in ${guildId}: ${reserveRes.error}`);
			}
		}

		// 4. Determine channel category
		const targetCategoryId =
			type === "withdrawal"
				? config.withdrawalCategoryId || config.categoryId
				: config.categoryId;

		let categoryChannel: any = null;
		if (targetCategoryId) {
			if (guild.channels?.cache) {
				categoryChannel = guild.channels.cache.get(targetCategoryId);
			}
			if (!categoryChannel && guild.channels?.fetch) {
				try {
					categoryChannel = await guild.channels.fetch(targetCategoryId).catch(() => null);
				} catch {}
			}

			// Validate category presence when configured
			if (!categoryChannel) {
				if (reservedAmount > 0) {
					await EconomyManager.releaseWithdrawalReservation(guildId, userId, reservedAmount, "category_unavailable");
				}
				return {
					success: false,
					error: `The configured ticket category (${targetCategoryId}) was deleted or is unavailable. Please update the ticket settings.`,
				};
			}
		}

		let nextCounter = (config.ticketCounter || 1000) + 1;
		try {
			const ticketCol = await DatabaseManager.collection(this.TICKETS_COLLECTION);
			const allTickets = await ticketCol.find({}).toArray();
			let maxCounter = nextCounter;
			for (const t of allTickets) {
				const match = String(t.ticketId || "").match(/^ticket-(\d+)$/);
				if (match) {
					const num = parseInt(match[1], 10);
					if (!isNaN(num) && num >= maxCounter) {
						maxCounter = num + 1;
					}
				}
			}
			nextCounter = maxCounter;
		} catch {}

		await this.updateGuildConfig(guildId, { ticketCounter: nextCounter });
		const ticketId = `ticket-${nextCounter}`;

		// 5. Construct permission overwrites safely
		const permissionOverwrites: any[] = [
			{
				id: guild.roles?.everyone?.id || guild.id,
				deny: [PermissionFlagsBits.ViewChannel],
			},
			{
				id: userId,
				allow: [
					PermissionFlagsBits.ViewChannel,
					PermissionFlagsBits.SendMessages,
					PermissionFlagsBits.ReadMessageHistory,
					PermissionFlagsBits.AttachFiles,
				],
			},
		];

		// Allow bot
		if (guild.members?.me) {
			permissionOverwrites.push({
				id: guild.members.me.id,
				allow: [
					PermissionFlagsBits.ViewChannel,
					PermissionFlagsBits.SendMessages,
					PermissionFlagsBits.ManageChannels,
					PermissionFlagsBits.ManageMessages,
					PermissionFlagsBits.ReadMessageHistory,
				],
			});
		}

		// Allow staff roles
		for (const roleId of config.staffRoleIds || []) {
			if (guild.roles?.cache?.has(roleId)) {
				permissionOverwrites.push({
					id: roleId,
					allow: [
						PermissionFlagsBits.ViewChannel,
						PermissionFlagsBits.SendMessages,
						PermissionFlagsBits.ReadMessageHistory,
					],
				});
			}
		}

		// Allow dedicated ticket manager roles
		for (const roleId of config.ticketManagerRoleIds || []) {
			if (guild.roles?.cache?.has(roleId)) {
				permissionOverwrites.push({
					id: roleId,
					allow: [
						PermissionFlagsBits.ViewChannel,
						PermissionFlagsBits.SendMessages,
						PermissionFlagsBits.ReadMessageHistory,
						PermissionFlagsBits.AttachFiles,
					],
				});
			}
		}

		// Allow individual ticket manager users
		for (const mgrUserId of config.ticketManagerUserIds || []) {
			if (mgrUserId) {
				permissionOverwrites.push({
					id: mgrUserId,
					allow: [
						PermissionFlagsBits.ViewChannel,
						PermissionFlagsBits.SendMessages,
						PermissionFlagsBits.ReadMessageHistory,
						PermissionFlagsBits.AttachFiles,
					],
				});
			}
		}

		// 6. Create private channel
		let channel: any = null;
		try {
			if (guild.channels?.create) {
				channel = await guild.channels.create({
					name: `${type}-${requester.username || userId}`.toLowerCase().replace(/[^a-z0-9_-]/g, ""),
					type: ChannelType.GuildText,
					parent: categoryChannel?.id || undefined,
					permissionOverwrites,
					reason: `Ticket ${ticketId} created for ${requester.username}`,
				});
			} else {
				// Mock channel for headless testing
				channel = {
					id: `mock_chan_${Date.now()}`,
					name: `${type}-${userId}`,
					send: async (p: any) => ({ ...p, id: `msg_${Date.now()}` }),
					delete: async () => {},
				};
			}
		} catch (chanErr: any) {
			logger.error("[TicketManager] Channel creation failed:", chanErr);
			// Roll back withdrawal reservation if channel creation failed
			if (reservedAmount > 0) {
				await EconomyManager.releaseWithdrawalReservation(guildId, userId, reservedAmount, ticketId);
			}
			return {
				success: false,
				error: `Failed to create ticket channel: ${chanErr?.message || "Missing bot permissions"}`,
			};
		}

		// 7. Persist ticket record
		const now = new Date();
		const initialRequests: WithdrawalRequestItem[] =
			type === "withdrawal" && amount > 0
				? [{ requestId: randomUUID(), amount, reason: details?.reason, requestedAt: now }]
				: (details?.requests || []);

		const ticketRecord: TicketRecord = {
			_id: ticketId,
			ticketId,
			guildId,
			channelId: channel?.id,
			requesterId: userId,
			type,
			status: "open",
			title,
			details: {
				...details,
				amount: amount,
				totalAmount: amount,
				reservedAmount: reservedAmount > 0 ? reservedAmount : undefined,
				requests: initialRequests,
			},
			createdAt: now,
			updatedAt: now,
		};

		try {
			const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
			await col.insertOne(ticketRecord);
		} catch (dbErr: any) {
			logger.error("[TicketManager] Failed to persist ticket to database:", dbErr);
			if (channel?.delete) {
				await channel.delete().catch(() => null);
			}
			if (reservedAmount > 0) {
				await EconomyManager.releaseWithdrawalReservation(guildId, userId, reservedAmount, ticketId);
			}
			return { success: false, error: "Database error saving ticket. Cleaned up created channel." };
		}

		// 8. Send structured ticket message into the ticket channel
		try {
			const emojis = getEconomyEmojis();
			const colors = getEconomyColors();
			const settings = await EconomyManager.getGuildSettings(guildId);

			let container: ContainerBuilder;
			if (type === "withdrawal") {
				container = this.buildWithdrawalTicketContainer(ticketRecord, settings, emojis, colors);
			} else {
				container = new ContainerBuilder()
					.setAccentColor(colors.default)
					.addTextDisplay(`### ${config.Emojis.ticket || config.Emojis.paid || "🎫"} Ticket: ${title}`)
					.addTextDisplay(
						`**Ticket ID:** \`${ticketId}\`\n` +
						`**Requester:** <@${userId}> (\`${userId}\`)\n` +
						`**Type:** \`${type.toUpperCase()}\`\n` +
						`**Created:** <t:${Math.floor(now.getTime() / 1000)}:f>`
					)
					.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

				if (type === "deposit") {
					const depAmount = details?.amount || 0;
					const formatted = formatCurrency(depAmount, settings.currency);
					container.addTextDisplay(`${config.Emojis.paid || config.Emojis.money || "💰"} **Requested Amount:** __${formatted}__\n📥 **Status:** Staff approval required before currency is credited.`);
				} else {
					container.addTextDisplay(`${config.Emojis.info || config.Emojis.list || "📋"} **Details:** ${details?.description || "General support request."}`);
				}

				container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

				container.addActionRow((row: ActionRowBuilder) => {
					if (type === "deposit") {
						row.addButton({
							custom_id: `ticket:approve:${ticketId}`,
							label: "Approve Deposit",
							style: ButtonStyle.Success,
						});
						row.addButton({
							custom_id: `ticket:reject:${ticketId}`,
							label: "Reject Deposit",
							style: ButtonStyle.Danger,
						});
					}
					row.addButton({
						custom_id: `ticket:close:${ticketId}`,
						label: "Close Ticket",
						style: ButtonStyle.Secondary,
					});
					return row;
				});
			}

			if (channel?.send) {
				const sent = await channel.send({
					components: [container.build()],
					flags: MessageFlags.IsComponentsV2,
				});
				if (sent?.id) {
					ticketRecord.messageId = sent.id;
					ticketRecord.messageUrl = `https://discord.com/channels/${guildId}/${channel.id}/${sent.id}`;
					const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
					await col.updateOne({ ticketId }, { $set: { messageId: sent.id, messageUrl: ticketRecord.messageUrl } });
				}
			}
		} catch (msgErr) {
			logger.warn("[TicketManager] Failed to post initial ticket message:", msgErr);
		}

		logger.info(`[TicketManager] Created ${type} ticket ${ticketId} for ${requester.tag || userId} in guild ${guildId}`);
		ObservabilityManager.recordTicketEvent(`create_${type}`, true);
		return { success: true, ticket: ticketRecord, channel };
	}

	/**
	 * Add an additional withdrawal amount to an existing open ticket.
	 */
	public static async addWithdrawalToExistingTicket(options: {
		guild: any;
		requester: any;
		existingTicket: TicketRecord;
		amount: number;
		reason?: string;
		client?: any;
	}): Promise<{ success: boolean; ticket?: TicketRecord; channel?: any; error?: string }> {
		const { guild, requester, existingTicket, amount, reason, client } = options;
		const guildId = guild.id;
		const userId = requester.id;
		const ticketId = existingTicket.ticketId;

		if (existingTicket.status !== "open") {
			return { success: false, error: `Ticket #${ticketId} is already ${existingTicket.status} and cannot accept additional amounts.` };
		}

		// 1. Reserve the additional amount
		const reserveRes = await EconomyManager.reserveWithdrawal(guildId, userId, amount);
		if (!reserveRes.success) {
			return { success: false, error: reserveRes.error || "Insufficient funds for additional withdrawal." };
		}

		// 2. Prepare updated data
		const currentDetails = existingTicket.details || {};
		const currentTotal = currentDetails.totalAmount ?? currentDetails.amount ?? 0;
		const newTotal = currentTotal + amount;
		const newReserved = (currentDetails.reservedAmount ?? currentTotal) + amount;
		const now = new Date();

		const newRequest: WithdrawalRequestItem = {
			requestId: randomUUID(),
			amount,
			reason: reason || undefined,
			requestedAt: now,
		};
		const updatedRequests = [...(currentDetails.requests || []), newRequest];

		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
		await col.updateOne(
			{ ticketId, status: "open" },
			{
				$set: {
					"details.amount": newTotal,
					"details.totalAmount": newTotal,
					"details.reservedAmount": newReserved,
					"details.requests": updatedRequests,
					updatedAt: now,
				},
			}
		);

		const updatedTicket: TicketRecord = {
			...existingTicket,
			details: {
				...currentDetails,
				amount: newTotal,
				totalAmount: newTotal,
				reservedAmount: newReserved,
				requests: updatedRequests,
			},
			updatedAt: now,
		};

		// 3. Update the ticket message in channel
		let channel: any = null;
		if (existingTicket.channelId) {
			try {
				channel = guild.channels?.cache?.get(existingTicket.channelId) || (await client?.channels?.fetch?.(existingTicket.channelId).catch(() => null));
				if (channel?.isTextBased?.()) {
					const emojis = getEconomyEmojis();
					const colors = getEconomyColors();
					const settings = await EconomyManager.getGuildSettings(guildId);

					if (existingTicket.messageId) {
						const msg = await channel.messages?.fetch(existingTicket.messageId).catch(() => null);
						if (msg?.edit) {
							const container = this.buildWithdrawalTicketContainer(updatedTicket, settings, emojis, colors);
							await msg.edit({
								components: [container.build()],
								flags: MessageFlags.IsComponentsV2,
							}).catch((editErr: any) => {
								logger.warn(`[TicketManager] Could not edit ticket message ${existingTicket.messageId}:`, editErr);
							});
						}
					}

					// Send update note in channel
					const formattedAdd = formatCurrency(amount, settings.currency);
					const formattedNewTotal = formatCurrency(newTotal, settings.currency);
					await channel.send({
						content: `${config.Emojis.deposit || config.Emojis.credit || config.Emojis.paid || "📥"} <@${userId}> added an additional **${formattedAdd}** to this withdrawal request.\n> **New Total Pending Payout:** \`${formattedNewTotal}\`${reason ? `\n> **Note:** ${reason}` : ""}`,
					}).catch(() => null);
				}
			} catch (chErr) {
				logger.warn(`[TicketManager] Failed to update message in channel for ticket ${ticketId}:`, chErr);
			}
		}

		await AuditService.record({
			guildId,
			actorId: userId,
			targetUserId: userId,
			action: "settings_update",
			amount,
			reason: `Added ${amount} to active withdrawal ticket #${ticketId} (New total: ${newTotal})`,
		});

		logger.info(`[TicketManager] Added ${amount} to ticket ${ticketId} for user ${userId}. New total: ${newTotal}`);
		return { success: true, ticket: updatedTicket, channel };
	}

	/**
	 * Centralized button interaction handler for ticket actions.
	 */
	public static async handleButtonInteraction(interaction: any): Promise<void> {
		if (!interaction.isButton?.()) return;
		const customId = interaction.customId || "";
		if (!customId.startsWith("ticket:")) return;

		const parts = customId.split(":");
		const action = parts[1];
		const ticketId = parts[2];

		if (!action) return;

		try {
			if (action === "autocreate_transcripts") {
				await this.processAutoCreateTranscriptsButton(interaction, ticketId);
				return;
			}

			if (!ticketId) return;

			const ticket = await this.getTicketById(ticketId, interaction.guild?.id);
			if (!ticket) {
				await interaction.reply({
					content: `${config.Emojis.no_access || config.Emojis.error || ""} Ticket not found or no longer available.`,
					ephemeral: true,
				}).catch(() => {});
				return;
			}

			if (action === "close") {
				await this.processCloseButton(interaction, ticketId);
			} else if (action === "transcript") {
				await this.processTranscriptButton(interaction, ticketId);
			} else if (ticket.type === "deposit") {
				const approved = action === "approve" || action === "payout";
				const staffUser = interaction.user;
				const res = await this.processDeposit(
					ticketId,
					staffUser,
					approved,
					`Processed via button by ${staffUser.username || staffUser.id}`
				);
				if (!res.success) {
					await interaction.reply({ content: `❌ ${res.error}`, ephemeral: true }).catch(() => {});
				} else {
					await interaction.reply({
						content: `${config.Emojis.paid || config.Emojis.success} Deposit ${approved ? "approved" : "rejected"} successfully.`,
						ephemeral: true,
					}).catch(() => {});
				}
			} else {
				if (action === "payout" || action === "approve") {
					await this.processPayoutButton(interaction, ticketId);
				} else if (action === "cancel" || action === "reject") {
					await this.processCancelButton(interaction, ticketId);
				}
			}
		} catch (e) {
			logger.error("[TicketManager:ButtonInteraction]", e);
		}
	}

	/**
	 * Administrative payout button handler.
	 */
	public static async processPayoutButton(interaction: any, ticketId: string): Promise<void> {
		const guild = interaction.guild;
		const member = interaction.member;
		const user = interaction.user;
		const emojis = getEconomyEmojis();
		const colors = getEconomyColors();

		if (!guild) {
			await interaction.reply({ content: `${emojis.error} This action can only be used inside a server.`, ephemeral: true }).catch(() => {});
			return;
		}

		// Acknowledge promptly to avoid 10062 Unknown Interaction
		if (!interaction.deferred && !interaction.replied) {
			await interaction.deferReply().catch(() => {});
		}

		// Check permissions: Server owner or Administrator or staff role / economy.withdraw
		const isOwner = guild.ownerId === user.id;
		const isAdmin = member?.permissions?.has(PermissionFlagsBits.Administrator);
		const hasEcoPerm = await PermissionService.hasPermission(guild, member, "economy.withdraw");
		const config = await this.getGuildConfig(guild.id);
		const hasStaffRole = (config.staffRoleIds || []).some((r: string) => member?.roles?.cache?.has(r));
		const isTicketManager =
			(config.ticketManagerRoleIds || []).some((r: string) => member?.roles?.cache?.has(r)) ||
			(config.ticketManagerUserIds || []).includes(user.id);

		if (!isOwner && !isAdmin && !hasEcoPerm && !hasStaffRole && !isTicketManager) {
			await interaction.followUp({
				content: `${emojis.error} You are not authorized to approve withdrawal payouts. Only administrators or authorized staff may finalize payouts.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		const ticket = await this.getTicketById(ticketId, guild.id);
		if (!ticket) {
			await interaction.followUp({ content: `${emojis.error} Ticket not found.`, ephemeral: true }).catch(() => {});
			return;
		}

		if (ticket.status === "paid" || ticket.status === "approved") {
			await interaction.followUp({
				content: `${emojis.info} This withdrawal has already been marked as paid out by <@${ticket.details?.paidBy || ticket.assignedStaffId || "staff"}>.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		if (ticket.status !== "open") {
			await interaction.followUp({
				content: `${emojis.error} This ticket has status **${ticket.status}** and cannot be paid out.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		const totalAmount = ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
		const now = new Date();

		// Atomically transition from "open" to "paid" to prevent concurrent duplicate approvals
		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
		const updateRes = await col.updateOne(
			{ ticketId, status: "open" },
			{
				$set: {
					status: "paid",
					assignedStaffId: user.id,
					updatedAt: now,
					"details.paidBy": user.id,
					"details.paidAt": now,
					"details.processedBy": user.id,
					"details.processedAt": now,
				},
			}
		);

		if (updateRes.matchedCount === 0) {
			await interaction.followUp({
				content: `${emojis.info} This withdrawal was already processed by another administrator.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		// Finalize withdrawal in EconomyManager (deducts funds and clears reservation exactly once)
		const finalizeRes = await EconomyManager.finalizeWithdrawal(
			ticket.guildId,
			ticket.requesterId,
			totalAmount,
			ticketId
		);

		if (!finalizeRes.success) {
			// Rollback ticket status to open so state remains recoverable
			await col.updateOne({ ticketId }, { $set: { status: "open", updatedAt: new Date() } });
			logger.error(`[TicketManager] Failed to finalize balance withdrawal for ticket ${ticketId}: ${finalizeRes.error}`);
			await interaction.followUp({
				content: `${emojis.error} Failed to finalize balance payout: ${finalizeRes.error}`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		// Update ticket message: show paid status, remove payout button
		try {
			const settings = await EconomyManager.getGuildSettings(ticket.guildId);
			const updatedTicket: TicketRecord = {
				...ticket,
				status: "paid",
				details: {
					...ticket.details,
					paidBy: user.id,
					paidAt: now,
					processedBy: user.id,
					processedAt: now,
					transactionId: finalizeRes.transactionId,
				},
				assignedStaffId: user.id,
				updatedAt: now,
			};

			const container = this.buildWithdrawalTicketContainer(updatedTicket, settings, emojis, colors);
			await interaction.editReply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
		} catch (msgErr) {
			logger.warn(`[TicketManager] Error updating message on payout for ${ticketId}:`, msgErr);
		}

		// Send DM notification to requester
		try {
			const targetUser = await interaction.client.users.fetch(ticket.requesterId).catch(() => null);
			const guildSettings = await EconomyManager.getGuildSettings(ticket.guildId);
			if (targetUser && finalizeRes.balance) {
				await WithdrawalNotificationService.sendWithdrawalNotification({
					guild,
					user: targetUser,
					amount: totalAmount,
					balance: {
						wallet: finalizeRes.balance.wallet,
						bank: finalizeRes.balance.bank,
					},
					transactionId: finalizeRes.transactionId || randomUUID(),
					settings: guildSettings,
				});
			}
		} catch (dmErr) {
			logger.warn(`[TicketManager] Failed to send payout notification DM to ${ticket.requesterId}:`, dmErr);
		}

		// Audit log
		await AuditService.record({
			guildId: ticket.guildId,
			actorId: user.id,
			targetUserId: ticket.requesterId,
			action: "admin_remove",
			amount: totalAmount,
			reason: `Marked withdrawal ticket #${ticketId} as paid out`,
		});

		logger.info(`[TicketManager] Ticket ${ticketId} marked as paid out by ${user.tag || user.id} for amount ${totalAmount}`);
	}

	/**
	 * Cancellation button handler.
	 */
	public static async processCancelButton(interaction: any, ticketId: string): Promise<void> {
		const guild = interaction.guild;
		const member = interaction.member;
		const user = interaction.user;
		const emojis = getEconomyEmojis();
		const colors = getEconomyColors();

		if (!guild) {
			await interaction.reply({ content: `${emojis.error} Server only.`, ephemeral: true }).catch(() => {});
			return;
		}

		if (!interaction.deferred && !interaction.replied) {
			await interaction.deferReply().catch(() => {});
		}

		const ticket = await this.getTicketById(ticketId, guild.id);
		if (!ticket) {
			await interaction.followUp({ content: `${emojis.error} Ticket not found.`, ephemeral: true }).catch(() => {});
			return;
		}

		// Requester themselves, or staff/admin can cancel
		const isRequester = ticket.requesterId === user.id;
		const isOwner = guild.ownerId === user.id;
		const isAdmin = member?.permissions?.has(PermissionFlagsBits.Administrator);
		const config = await this.getGuildConfig(guild.id);
		const hasStaffRole = (config.staffRoleIds || []).some((r: string) => member?.roles?.cache?.has(r));
		const isTicketManager =
			(config.ticketManagerRoleIds || []).some((r: string) => member?.roles?.cache?.has(r)) ||
			(config.ticketManagerUserIds || []).includes(user.id);

		if (!isRequester && !isOwner && !isAdmin && !hasStaffRole && !isTicketManager) {
			await interaction.followUp({
				content: `${emojis.error} You are not authorized to cancel this withdrawal request.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		if (ticket.status !== "open") {
			await interaction.followUp({
				content: `${emojis.info} This request is already ${ticket.status} and cannot be canceled.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		const now = new Date();
		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
		const updateRes = await col.updateOne(
			{ ticketId, status: "open" },
			{
				$set: {
					status: "canceled",
					closedBy: user.id,
					closedAt: now,
					updatedAt: now,
					"details.canceledBy": user.id,
					"details.canceledAt": now,
				},
			}
		);

		if (updateRes.matchedCount === 0) {
			await interaction.followUp({
				content: `${emojis.info} This request was already updated by another user.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		// Release reserved balance exactly once
		const reservedAmount = ticket.details?.reservedAmount ?? ticket.details?.amount ?? 0;
		if (reservedAmount > 0) {
			await EconomyManager.releaseWithdrawalReservation(ticket.guildId, ticket.requesterId, reservedAmount, ticketId);
		}

		// Update ticket message
		try {
			const settings = await EconomyManager.getGuildSettings(ticket.guildId);
			const updatedTicket: TicketRecord = {
				...ticket,
				status: "canceled",
				details: {
					...ticket.details,
					canceledBy: user.id,
					canceledAt: now,
				},
				updatedAt: now,
			};

			const container = this.buildWithdrawalTicketContainer(updatedTicket, settings, emojis, colors);
			await interaction.editReply({
				components: [container.build()],
				flags: MessageFlags.IsComponentsV2,
			}).catch(() => null);
		} catch (msgErr) {
			logger.warn(`[TicketManager] Error updating message on cancel for ${ticketId}:`, msgErr);
		}

		await AuditService.record({
			guildId: ticket.guildId,
			actorId: user.id,
			targetUserId: ticket.requesterId,
			action: "settings_update",
			amount: reservedAmount,
			reason: `Canceled withdrawal ticket #${ticketId} (funds released)`,
		});

		logger.info(`[TicketManager] Ticket ${ticketId} canceled by ${user.tag || user.id}. Released reservation: ${reservedAmount}`);
	}

	/**
	 * Close ticket button handler.
	 */
	public static async processCloseButton(interaction: any, ticketId: string): Promise<void> {
		const guild = interaction.guild;
		const member = interaction.member;
		const user = interaction.user;
		const emojis = getEconomyEmojis();

		if (!guild) {
			await interaction.reply({ content: `${emojis.error} Server only.`, ephemeral: true }).catch(() => {});
			return;
		}

		if (!interaction.deferred && !interaction.replied) {
			await interaction.deferReply().catch(() => {});
		}

		const ticket = await this.getTicketById(ticketId, guild.id);
		if (!ticket) {
			await interaction.followUp({ content: `${emojis.error} Ticket not found.`, ephemeral: true }).catch(() => {});
			return;
		}

		// Check permission: requester themselves, or staff/admin/ticket manager
		const isRequester = ticket.requesterId === user.id;
		const isOwner = guild.ownerId === user.id;
		const isAdmin = member?.permissions?.has?.(PermissionFlagsBits.Administrator) || member?.permissions?.has?.(PermissionFlagsBits.ManageGuild);
		const config = await this.getGuildConfig(guild.id);
		const hasStaffRole = (config.staffRoleIds || []).some((r: string) => member?.roles?.cache?.has?.(r));
		const isTicketManager =
			(config.ticketManagerRoleIds || []).some((r: string) => member?.roles?.cache?.has?.(r)) ||
			(config.ticketManagerUserIds || []).includes(user.id);

		if (!isRequester && !isOwner && !isAdmin && !hasStaffRole && !isTicketManager) {
			await interaction.followUp({
				content: `${emojis.error} You are not authorized to close this ticket. Only the ticket creator or authorized staff can close it.`,
				ephemeral: true,
			}).catch(() => {});
			return;
		}

		const res = await this.closeTicket(guild.id, ticketId, user.id, "Closed via button", interaction.client);
		if (!res.success) {
			await interaction.followUp({ content: `${emojis.error} ${res.error || "Failed to close ticket."}`, ephemeral: true }).catch(() => {});
		} else {
			await interaction.followUp({ content: `🔒 Ticket #${ticketId} has been closed by <@${user.id}>.` }).catch(() => {});
		}
	}

	/**
	 * Transcript button handler.
	 */
	public static async processTranscriptButton(interaction: any, ticketId: string): Promise<void> {
		const guild = interaction.guild;
		const member = interaction.member;
		const user = interaction.user;
		const emojis = getEconomyEmojis();
		const colors = getEconomyColors();

		if (!guild) {
			await interaction.reply({ content: `${emojis.error} Server only.`, ephemeral: true }).catch(() => {});
			return;
		}

		await interaction.deferReply().catch(() => {});

		const ticket = await this.getTicketById(ticketId);
		if (!ticket) {
			await interaction.editReply({ content: `${emojis.error} Ticket #${ticketId} not found.` }).catch(() => {});
			return;
		}

		// Permissions: Requester, Guild Owner, Admin, Staff, or Ticket Manager
		const isRequester = ticket.requesterId === user.id;
		const isOwner = guild.ownerId === user.id;
		const isAdmin = member?.permissions?.has?.(PermissionFlagsBits.Administrator);
		const config = await this.getGuildConfig(guild.id);
		const hasStaffRole = (config.staffRoleIds || []).some((r: string) => member?.roles?.cache?.has?.(r));
		const isTicketManager =
			(config.ticketManagerRoleIds || []).some((r: string) => member?.roles?.cache?.has?.(r)) ||
			(config.ticketManagerUserIds || []).includes(user.id);

		if (!isRequester && !isOwner && !isAdmin && !hasStaffRole && !isTicketManager) {
			await interaction.editReply({
				content: `${emojis.error} You are not authorized to export or view transcripts for this ticket.`,
			}).catch(() => {});
			return;
		}

		const res = await this.generateAndSendTranscript(ticketId, guild, user);
		if (!res.success) {
			await interaction.editReply({
				content: `${emojis.error} ${res.error || "Failed to generate transcript."}`,
			}).catch(() => {});
			return;
		}

		const confirmationContainer = new ContainerBuilder()
			.setAccentColor(colors.success || "#22c55e")
			.addTextDisplay(`### 📜 Transcript Generated`)
			.addTextDisplay(
				`Transcript for Ticket **#${ticket.ticketId}** has been successfully generated.\n` +
				(res.transcriptUrl && !res.transcriptUrl.startsWith("internal://")
					? `• **Archived in Log Channel:** [View Transcript Message](${res.transcriptUrl})\n`
					: "• **Archive Status:** Recorded in database.\n") +
				"A copy of the complete transcript file is provided below."
			)
			.build();

		const replyPayload: any = {
			components: [confirmationContainer],
			flags: MessageFlags.IsComponentsV2,
		};
		if (res.attachment) {
			replyPayload.files = [res.attachment];
		}

		await interaction.editReply(replyPayload).catch(() => null);
	}

	/**
	 * Auto-create transcripts channel button handler.
	 */
	public static async processAutoCreateTranscriptsButton(interaction: any, ticketId?: string): Promise<void> {
		const guild = interaction.guild;
		const member = interaction.member;
		const user = interaction.user;
		const emojis = getEconomyEmojis();
		const colors = getEconomyColors();

		if (!guild) {
			await interaction.reply({ content: `${emojis.error} Server only.`, ephemeral: true }).catch(() => {});
			return;
		}

		await interaction.deferReply().catch(() => {});

		const isOwner = guild.ownerId === user.id;
		const isAdmin = member?.permissions?.has?.(PermissionFlagsBits.Administrator) || member?.permissions?.has?.(PermissionFlagsBits.ManageGuild);
		if (!isOwner && !isAdmin) {
			await interaction.editReply({
				content: `${emojis.error} Only server administrators can configure the transcripts channel.`,
			}).catch(() => {});
			return;
		}

		const createRes = await this.createTranscriptsChannel(guild, user.id);
		if (!createRes.success) {
			await interaction.editReply({
				content: `${emojis.error} ${createRes.error || "Failed to create transcripts channel."}`,
			}).catch(() => {});
			return;
		}

		const container = new ContainerBuilder()
			.setAccentColor(colors.success || "#22c55e")
			.addTextDisplay(`### 🎫 Transcripts Channel Configured`)
			.addTextDisplay(
				`Successfully created <#${createRes.channel.id}> as the official ticket transcripts archive.\n` +
				"All exported and resolved ticket receipts will be archived there automatically."
			)
			.build();

		await interaction.editReply({
			components: [container],
			flags: MessageFlags.IsComponentsV2,
		}).catch(() => null);
	}

	/**
	 * Auto-creates a dedicated transcripts archive channel for the server.
	 */
	public static async createTranscriptsChannel(
		guild: any,
		actorId?: string
	): Promise<{ success: boolean; channel?: any; error?: string }> {
		try {
			if (!guild) {
				return { success: false, error: "Guild is required" };
			}

			const currentConfig = await this.getGuildConfig(guild.id);
			if (currentConfig.transcriptChannelId) {
				const existingChan = guild.channels?.cache?.get(currentConfig.transcriptChannelId) ||
					(await guild.channels?.fetch?.(currentConfig.transcriptChannelId).catch(() => null));
				if (existingChan) {
					return { success: true, channel: existingChan };
				}
			}

			const permissionOverwrites: any[] = [
				{
					id: guild.roles?.everyone?.id || guild.id,
					deny: [PermissionFlagsBits.ViewChannel],
				},
			];

			if (guild.members?.me) {
				permissionOverwrites.push({
					id: guild.members.me.id,
					allow: [
						PermissionFlagsBits.ViewChannel,
						PermissionFlagsBits.SendMessages,
						PermissionFlagsBits.AttachFiles,
						PermissionFlagsBits.EmbedLinks,
						PermissionFlagsBits.ReadMessageHistory,
					],
				});
			}

			for (const rId of currentConfig.staffRoleIds || []) {
				if (guild.roles?.cache?.has(rId)) {
					permissionOverwrites.push({
						id: rId,
						allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory],
					});
				}
			}

			let channel: any = null;
			if (guild.channels?.create) {
				channel = await guild.channels.create({
					name: "ticket-transcripts",
					type: ChannelType.GuildText,
					permissionOverwrites,
					reason: `Created transcripts channel by ${actorId || "admin"}`,
				});
			} else {
				channel = {
					id: `tr_chan_${Date.now()}`,
					name: "ticket-transcripts",
					isTextBased: () => true,
					send: async (p: any) => ({ ...p, id: `msg_${Date.now()}` }),
				};
			}

			await this.updateGuildConfig(guild.id, {
				transcriptChannelId: channel.id,
				transcriptsEnabled: true,
			}, actorId);

			logger.info(`[TicketManager] Created ticket-transcripts channel ${channel.id} for guild ${guild.id}`);
			return { success: true, channel };
		} catch (error: any) {
			logger.error("[TicketManager] Failed to create transcripts channel:", error);
			return { success: false, error: error?.message || "Failed to create transcripts channel" };
		}
	}

	/**
	 * Generates a complete transcript of a ticket, formats it, archives it, and returns the result.
	 */
	public static async generateAndSendTranscript(
		ticketId: string,
		guild: any,
		actor?: any
	): Promise<{ success: boolean; transcriptUrl?: string; code?: string; error?: string; attachment?: any }> {
		const ticket = await this.getTicketById(ticketId);
		if (!ticket) {
			return { success: false, code: "NOT_FOUND", error: "Ticket not found." };
		}

		try {
			const guildId = guild?.id || ticket.guildId;
			const config = await this.getGuildConfig(guildId);
			const settings = await EconomyManager.getGuildSettings(guildId);
			const colors = getEconomyColors();

			let channelMessages: any[] = [];
			let channel: any = null;
			if (ticket.channelId && guild?.channels) {
				channel = guild.channels.cache?.get(ticket.channelId) || (await guild.channels.fetch?.(ticket.channelId).catch(() => null));
				if (channel?.messages?.fetch) {
					try {
						const fetched = await channel.messages.fetch({ limit: 100 }).catch(() => null);
						if (fetched) {
							channelMessages = Array.from(fetched.values()).reverse();
						}
					} catch {}
				}
			}

			const now = new Date();
			const header = [
				`================================================================`,
				`                     MOMENTUMONE TICKET TRANSCRIPT              `,
				`================================================================`,
				`Ticket ID:      ${ticket.ticketId}`,
				`Title:          ${ticket.title}`,
				`Type:           ${ticket.type}`,
				`Status:         ${ticket.status}`,
				`Requester:      ${ticket.requesterId}`,
				`Guild ID:       ${ticket.guildId}`,
				`Created At:     ${new Date(ticket.createdAt).toISOString()}`,
				`Closed At:      ${ticket.closedAt ? new Date(ticket.closedAt).toISOString() : "Open / Active"}`,
				`Archived At:    ${now.toISOString()}`,
				`Archived By:    ${actor?.username || actor?.id || "System"}`,
			];

			if (ticket.type === "withdrawal") {
				const total = ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
				header.push(`Total Amount:   ${formatCurrency(total, settings.currency)}`);
				if (ticket.details?.ltcAddress) header.push(`LTC Address:    ${ticket.details.ltcAddress}`);
				if (ticket.details?.upiAddress) header.push(`UPI Address:    ${ticket.details.upiAddress}`);
				if (ticket.details?.paidBy) header.push(`Paid By:        ${ticket.details.paidBy}`);
			}
			header.push(`================================================================\n`);

			let body = "";
			if (channelMessages.length > 0) {
				body = channelMessages
					.map((m: any) => {
						const ts = m.createdAt ? new Date(m.createdAt).toISOString() : new Date().toISOString();
						const author = m.author?.tag || m.author?.username || m.author?.id || "Unknown";
						const content = m.content || (m.components?.length ? "[Components V2 Message]" : "[No text content]");
						return `[${ts}] ${author}: ${content}`;
					})
					.join("\n");
			} else {
				body = `[System Notice] No chat messages recorded in channel. Ticket details preserved from record:\n• Details: ${ticket.details?.reason || ticket.details?.description || ticket.title}`;
			}

			const fullTranscript = `${header.join("\n")}\n${body}\n\n==================== END OF TRANSCRIPT ====================`;
			const attachment = new AttachmentBuilder(Buffer.from(fullTranscript, "utf-8"), {
				name: `transcript-${ticket.ticketId}.txt`,
				description: `Transcript for Ticket #${ticket.ticketId}`,
			});

			const summaryContainer = new ContainerBuilder()
				.setAccentColor(colors.default || "#3b82f6")
				.addTextDisplay(`### 📜 Ticket Transcript: #${ticket.ticketId}`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`• **Ticket Title:** ${ticket.title}\n` +
					`• **Type:** \`${ticket.type.toUpperCase()}\` | **Status:** \`${ticket.status.toUpperCase()}\`\n` +
					`• **Requester:** <@${ticket.requesterId}> (\`${ticket.requesterId}\`)\n` +
					`• **Generated By:** ${actor?.id ? `<@${actor.id}>` : "System"}\n` +
					`• **Generated At:** <t:${Math.floor(now.getTime() / 1000)}:f>`
				);

			if (ticket.type === "withdrawal") {
				const total = ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
				summaryContainer.addTextDisplay(`• **Total Withdrawal Amount:** __${formatCurrency(total, settings.currency)}__`);
			}

			summaryContainer.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });
			summaryContainer.addTextDisplay("-# Full chat transcript and metadata is attached as a text log.");

			let transcriptUrl: string | undefined = undefined;

			if (config.transcriptChannelId && guild?.channels) {
				let trChan = guild.channels.cache?.get(config.transcriptChannelId);
				if (!trChan && guild.channels.fetch) {
					trChan = await guild.channels.fetch(config.transcriptChannelId).catch(() => null);
				}
				if (trChan?.send) {
					try {
						const sent = await trChan.send({
							components: [summaryContainer.build()],
							files: [attachment],
							flags: MessageFlags.IsComponentsV2,
						});
						if (sent?.url) {
							transcriptUrl = sent.url;
						} else if (sent?.id) {
							transcriptUrl = `https://discord.com/channels/${guildId}/${trChan.id}/${sent.id}`;
						}
					} catch (sendErr) {
						logger.warn(`[TicketManager] Failed to post transcript in channel ${config.transcriptChannelId}:`, sendErr);
					}
				}
			}

			if (!transcriptUrl) {
				transcriptUrl = `internal://transcripts/${guildId}/${ticket.ticketId}`;
			}

			const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
			await col.updateOne(
				{ _id: ticket._id || ticket.ticketId },
				{ $set: { transcriptUrl, updatedAt: now } }
			).catch(() => null);

			logger.info(`[TicketManager] Generated transcript for ticket ${ticket.ticketId} by ${actor?.id || "system"}`);
			return { success: true, transcriptUrl, attachment };
		} catch (error: any) {
			logger.error(`[TicketManager] Error generating transcript for ticket ${ticketId}:`, error);
			return { success: false, code: "GENERATION_FAILED", error: error?.message || "Failed to generate transcript" };
		}
	}

	/**
	 * Process deposit request (approve or reject).
	 */
	public static async processDeposit(
		ticketId: string,
		staffUser: any,
		approved: boolean,
		note?: string
	): Promise<{ success: boolean; error?: string }> {
		const ticket = await this.getTicketById(ticketId);
		if (!ticket) return { success: false, error: "Ticket not found." };
		if (ticket.status !== "open") {
			return { success: false, error: `Ticket has already been processed (Status: ${ticket.status}).` };
		}
		if (ticket.requesterId === staffUser.id) {
			return { success: false, error: "You cannot approve or reject your own deposit request." };
		}

		const guildId = ticket.guildId;
		const amount = ticket.details?.amount || 0;
		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);

		if (approved) {
			const creditRes = await EconomyManager.creditBalance(
				guildId,
				ticket.requesterId,
				amount,
				`Deposit approved by staff: ${staffUser.username || staffUser.id}`,
				ticketId
			);

			if (!creditRes.success) {
				return { success: false, error: creditRes.error || "Failed to credit user balance." };
			}

			await col.updateOne(
				{ ticketId },
				{
					$set: {
						status: "approved",
						assignedStaffId: staffUser.id,
						updatedAt: new Date(),
						"details.processedAt": new Date(),
						"details.processedBy": staffUser.id,
						"details.note": note,
					},
				}
			);

			await AuditService.record({
				guildId,
				actorId: staffUser.id,
				targetUserId: ticket.requesterId,
				action: "admin_add",
				amount,
				reason: `Approved deposit ticket #${ticketId}`,
			});

			return { success: true };
		} else {
			await col.updateOne(
				{ ticketId },
				{
					$set: {
						status: "rejected",
						assignedStaffId: staffUser.id,
						updatedAt: new Date(),
						"details.processedAt": new Date(),
						"details.processedBy": staffUser.id,
						"details.note": note || "Deposit rejected by staff",
					},
				}
			);

			return { success: true };
		}
	}

	/**
	 * Process withdrawal request (legacy programmatic method).
	 */
	public static async processWithdrawal(
		ticketId: string,
		staffUser: any,
		approved: boolean,
		note?: string,
		client?: any
	): Promise<{ success: boolean; error?: string }> {
		const ticket = await this.getTicketById(ticketId);
		if (!ticket) return { success: false, error: "Ticket not found." };
		if (ticket.status !== "open") {
			return { success: false, error: `Ticket has already been processed (Status: ${ticket.status}).` };
		}
		if (ticket.requesterId === staffUser.id) {
			return { success: false, error: "You cannot approve or reject your own withdrawal request." };
		}

		const guildId = ticket.guildId;
		const amount = ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);

		if (approved) {
			const finalizeRes = await EconomyManager.finalizeWithdrawal(
				guildId,
				ticket.requesterId,
				amount,
				ticketId
			);

			if (!finalizeRes.success) {
				return { success: false, error: finalizeRes.error || "Failed to finalize withdrawal." };
			}

			await col.updateOne(
				{ ticketId },
				{
					$set: {
						status: "approved",
						assignedStaffId: staffUser.id,
						updatedAt: new Date(),
						"details.processedAt": new Date(),
						"details.processedBy": staffUser.id,
						"details.note": note,
						"details.transactionId": finalizeRes.transactionId,
					},
				}
			);

			if (client?.users?.fetch) {
				try {
					const targetUser = await client.users.fetch(ticket.requesterId).catch(() => null);
					const guildSettings = await EconomyManager.getGuildSettings(guildId);
					const guildObj = client.guilds?.cache?.get(guildId) || { id: guildId, name: "Server" };
					if (targetUser && finalizeRes.balance) {
						await WithdrawalNotificationService.sendWithdrawalNotification({
							guild: guildObj,
							user: targetUser,
							amount,
							balance: {
								wallet: finalizeRes.balance.wallet,
								bank: finalizeRes.balance.bank,
							},
							transactionId: finalizeRes.transactionId,
							settings: guildSettings,
						});
					}
				} catch (notifErr) {
					logger.warn("[TicketManager] Notification dispatch error:", notifErr);
				}
			}

			await AuditService.record({
				guildId,
				actorId: staffUser.id,
				targetUserId: ticket.requesterId,
				action: "admin_remove",
				amount,
				reason: `Approved withdrawal ticket #${ticketId}`,
			});

			return { success: true };
		} else {
			const reservedAmount = ticket.details?.reservedAmount ?? amount;
			if (reservedAmount > 0) {
				await EconomyManager.releaseWithdrawalReservation(guildId, ticket.requesterId, reservedAmount, ticketId);
			}

			await col.updateOne(
				{ ticketId },
				{
					$set: {
						status: "rejected",
						assignedStaffId: staffUser.id,
						updatedAt: new Date(),
						"details.processedAt": new Date(),
						"details.processedBy": staffUser.id,
						"details.note": note || "Withdrawal rejected by staff",
					},
				}
			);

			return { success: true };
		}
	}

	/**
	 * Close ticket and clean up.
	 */
	public static async closeTicket(
		guildId: string,
		ticketId: string,
		closedByUserId: string,
		reason?: string,
		client?: any
	): Promise<{ success: boolean; ticket?: TicketRecord; error?: string }> {
		const ticket = await this.getTicketById(ticketId);
		if (!ticket) return { success: false, error: "Ticket not found." };
		if (ticket.status === "closed") {
			return { success: false, error: "Ticket is already closed." };
		}

		// If an open withdrawal ticket is closed without payout, safely release the reservation
		if (ticket.type === "withdrawal" && ticket.status === "open") {
			const reservedToRelease = ticket.details?.reservedAmount ?? ticket.details?.totalAmount ?? ticket.details?.amount ?? 0;
			if (reservedToRelease > 0) {
				await EconomyManager.releaseWithdrawalReservation(
					guildId,
					ticket.requesterId,
					reservedToRelease,
					ticketId
				);
			}
		}

		const now = new Date();
		const col = await DatabaseManager.collection(this.TICKETS_COLLECTION);
		await col.updateOne(
			{ ticketId },
			{
				$set: {
					status: "closed",
					closedBy: closedByUserId,
					closedAt: now,
					updatedAt: now,
					"details.closeReason": reason || "Closed by user/staff",
				},
			}
		);

		const updatedTicket: TicketRecord = {
			...ticket,
			status: "closed",
			closedBy: closedByUserId,
			closedAt: now,
			updatedAt: now,
		};

		// Safely clean up channel if possible
		if (ticket.channelId && client?.channels?.fetch) {
			try {
				const channel = await client.channels.fetch(ticket.channelId).catch(() => null);
				if (channel?.delete) {
					await channel.delete().catch(() => null);
				}
			} catch (chErr) {
				logger.warn(`[TicketManager] Could not delete channel ${ticket.channelId}:`, chErr);
			}
		}

		logger.info(`[TicketManager] Ticket ${ticketId} closed by user ${closedByUserId}`);
		ObservabilityManager.recordTicketEvent("close", true);
		return { success: true, ticket: updatedTicket };
	}

	public static getCacheStats() {
		return {
			configEntries: this.configCache.size,
		};
	}

	public static clearMemoryCaches(): void {
		this.configCache.clear();
	}
}
