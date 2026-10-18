const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";
import { isBotOwner } from "@core/security/SecurityHelpers";

const PAGE_SIZE = 8;

interface GuildDisplayItem {
	id: string;
	name: string;
	memberCount: string | number;
	ownerId?: string;
	available: boolean;
	joinedAt?: Date | null;
}

function getGuildsList(client: any, query?: string): GuildDisplayItem[] {
	if (!client?.guilds?.cache) return [];

	let guilds = Array.from(client.guilds.cache.values()) as any[];

	if (query && query.trim().length > 0) {
		const q = query.trim().toLowerCase();
		guilds = guilds.filter(
			(g) =>
				g.id.toLowerCase().includes(q) ||
				(g.name && g.name.toLowerCase().includes(q))
		);
	}

	return guilds
		.map((g) => ({
			id: g.id,
			name: g.name || "Unnamed Guild",
			memberCount: g.available ? (typeof g.memberCount === "number" ? g.memberCount : "N/A") : "Unavailable",
			ownerId: g.ownerId || undefined,
			available: Boolean(g.available !== false),
			joinedAt: g.joinedAt || null,
		}))
		.sort((a, b) => {
			const ma = typeof a.memberCount === "number" ? a.memberCount : 0;
			const mb = typeof b.memberCount === "number" ? b.memberCount : 0;
			return mb - ma;
		});
}

function buildServerListContainer(options: {
	client: any;
	page: number;
	query?: string;
}) {
	const { client, page, query } = options;
	const E = config.Emojis || config.emojis || {};
	const C = config.Colors || config.colors || {};

	const emojis = {
		server: E.server || "🖥️",
		member: E.members || E.user || "👥",
		refresh: E.reload || "🔄",
		search: E.search || "🔍",
		crown: E.owner || "👑",
		dot: E.dot || "•",
	};

	const allGuilds = getGuildsList(client, query);
	const total = allGuilds.length;
	const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
	const safePage = Math.max(0, Math.min(page, totalPages - 1));
	const currentGuilds = allGuilds.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

	const totalConnected = client?.guilds?.cache?.size ?? total;
	let totalCachedMembers = 0;
	if (client?.guilds?.cache) {
		for (const g of client.guilds.cache.values()) {
			if (typeof g.memberCount === "number") totalCachedMembers += g.memberCount;
		}
	}

	const container = new ContainerBuilder()
		.setAccentColor(C.default || "#3B82F6")
		.addTextDisplay(`### ${emojis.server} Connected Discord Servers`)
		.addTextDisplay(
			`**Total Connected:** \`${totalConnected}\` servers • **Aggregate Members:** \`${totalCachedMembers}\`\n` +
			`**Page:** \`${safePage + 1}/${totalPages}\`` +
			(query ? ` • **Filter:** \`${query}\` (${total} matches)` : "")
		)
		.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	if (currentGuilds.length === 0) {
		container.addTextDisplay("*(No connected servers match the search criteria).*");
	} else {
		const lines = currentGuilds.map((g, idx) => {
			const indexNum = safePage * PAGE_SIZE + idx + 1;
			const memberStr = typeof g.memberCount === "number" ? `${g.memberCount.toLocaleString()} members` : `${g.memberCount}`;
			const ownerStr = g.ownerId ? ` • ${emojis.crown} <@${g.ownerId}>` : "";
			const availStr = g.available ? "" : " ⚠️ *(Outage / Unavailable)*";

			return (
				`**${indexNum}. ${g.name}**${availStr}\n` +
				`> **ID:** \`${g.id}\` • ${emojis.member} \`${memberStr}\`${ownerStr}`
			);
		});

		container.addTextDisplay(lines.join("\n\n"));
	}

	container.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small });

	// Controls
	container.addActionRow((row: any) => {
		row.addButton({
			custom_id: `listservers:prev:${safePage}${query ? `:${query}` : ""}`,
			label: "Previous",
			disabled: safePage <= 0,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: `listservers:next:${safePage}${query ? `:${query}` : ""}`,
			label: "Next",
			disabled: safePage >= totalPages - 1,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: `listservers:refresh:${safePage}${query ? `:${query}` : ""}`,
			label: "Refresh",
			emoji: emojis.refresh,
			style: ButtonStyle.Secondary,
		});

		row.addButton({
			custom_id: "listservers:close",
			label: "Close",
			style: ButtonStyle.Danger,
		});

		return row;
	});

	return container;
}

const listservers = {
	name: "listservers",
	aliases: ["guilds", "servers", "serverlist"],
	description: "Display connected Discord servers, member counts, and statistics (Bot Owner Only).",
	category: "Owner",
	usage: "listservers [query|page]",
	ownerOnly: true,

	sub_commands: [
		{ name: "[query]", description: "Filter connected servers by name or guild ID." },
		{ name: "page <number>", description: "View a specific page of connected servers." },
	],

	builder: new SlashCommandBuilder()
		.setName("listservers")
		.setDescription("Display connected Discord servers with member counts (Bot Owner Only).")
		.addStringOption((opt: any) =>
			opt.setName("query").setDescription("Filter by server name or server ID").setRequired(false)
		)
		.addIntegerOption((opt: any) =>
			opt.setName("page").setDescription("Page number to view").setRequired(false)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const client = messageOrInteraction.client;

		// Bot owner authorization check
		if (!isBotOwner(user?.id)) {
			const errText = "❌ **Access Denied**: This command is strictly restricted to authorized bot owners.";
			return isSlash
				? messageOrInteraction.editReply({ content: errText })
				: messageOrInteraction.reply({ content: errText });
		}

		let query: string | undefined = undefined;
		let page = 0;

		if (isSlash) {
			query = messageOrInteraction.options.getString("query") || undefined;
			const p = messageOrInteraction.options.getInteger("page");
			if (p && p > 0) page = p - 1;
		} else {
			if (args.length > 0) {
				const firstNum = parseInt(args[0], 10);
				if (!isNaN(firstNum) && String(firstNum) === args[0]) {
					page = Math.max(0, firstNum - 1);
				} else {
					query = args.join(" ").trim();
				}
			}
		}

		const container = buildServerListContainer({ client, page, query });
		const payload = { components: [container.build()], flags: MessageFlags.IsComponentsV2 };

		const sentMsg = isSlash
			? await messageOrInteraction.editReply(payload)
			: await messageOrInteraction.reply(payload);

		if (sentMsg?.createMessageComponentCollector) {
			const collector = sentMsg.createMessageComponentCollector({
				filter: (i: any) => i.customId?.startsWith("listservers:"),
				time: 300_000,
			});

			collector.on("collect", async (interaction: any) => {
				await listservers.handleInteraction(interaction);
			});
		}

		return sentMsg;
	},

	/**
	 * Interaction router for listservers component interactions
	 */
	handleInteraction: async (interaction: any): Promise<void> => {
		const customId = interaction.customId || "";
		if (!customId.startsWith("listservers:")) return;

		// Recheck Owner Authorization
		if (!isBotOwner(interaction.user?.id)) {
			if (!interaction.replied && !interaction.deferred) {
				await interaction.reply({
					content: "❌ **Access Denied**: Only authorized bot owners can use server list controls.",
					flags: MessageFlags.Ephemeral,
				}).catch(() => null);
			}
			return;
		}

		const parts = customId.split(":");
		const action = parts[1];

		if (action === "close") {
			await interaction.update({
				content: "🔒 **Server list closed**.",
				components: [],
			}).catch(() => null);
			return;
		}

		let page = parseInt(parts[2] || "0", 10);
		const query = parts[3] || undefined;

		if (action === "prev") page = Math.max(0, page - 1);
		if (action === "next") page = page + 1;

		const container = buildServerListContainer({
			client: interaction.client,
			page,
			query,
		});

		await interaction.update({
			components: [container.build()],
			flags: MessageFlags.IsComponentsV2,
		}).catch(() => null);
	},
};

export default listservers;
