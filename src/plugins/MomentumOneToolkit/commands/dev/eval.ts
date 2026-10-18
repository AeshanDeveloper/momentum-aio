const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
} = require("@sdk/discord");

import util from "node:util";
import config from "@config";
import logger from "@logger";
import DatabaseManager from "@database/Database";
import { isBotOwner } from "@core/security/SecurityHelpers";
import { TicketManager } from "../../tickets/TicketManager";
import { EconomyManager } from "../../economy/EconomyManager";
import { LeaderboardManager } from "../../economy/LeaderboardManager";

function redactSecrets(text: string): string {
	if (!text || typeof text !== "string") return text;

	const sensitiveKeys = [
		"BOT_TOKEN",
		"CLIENT_SECRET",
		"API_SECRET",
		"MONGODB_URI",
		"MONGO_URL",
		"MONGODB_URL",
		"DATABASE_URL",
		"TOKEN",
		"SECRET",
		"PASSWORD",
	];

	let sanitized = text;

	for (const key of sensitiveKeys) {
		const val = process.env[key];
		if (val && val.trim().length > 3) {
			const cleanVal = val.trim();
			sanitized = sanitized.replaceAll(cleanVal, `[REDACTED_${key}]`);
		}
	}

	// Also redact raw bot token if accessible via config or client
	const cfgToken = config?.settings?.bot?.token || process.env.BOT_TOKEN;
	if (cfgToken && cfgToken.trim().length > 3) {
		sanitized = sanitized.replaceAll(cfgToken.trim(), "[REDACTED_BOT_TOKEN]");
	}

	return sanitized;
}

function truncateString(str: string, maxLength = 1800): string {
	if (str.length <= maxLength) return str;
	return str.slice(0, maxLength) + "\n... (truncated for component limit)";
}

export default {
	name: "eval",
	aliases: ["evaluate", "e", "js"],
	description: "Execute and evaluate arbitrary JavaScript in the runtime bot process (Bot Owner Only).",
	category: "Owner",
	usage: "eval <code>",
	ownerOnly: true,

	sub_commands: [
		{ name: "<code>", description: "JavaScript expression or statement to evaluate." },
	],

	builder: new SlashCommandBuilder()
		.setName("eval")
		.setDescription("Evaluate JavaScript in the bot process context (Bot Owner Only).")
		.addStringOption((opt: any) =>
			opt.setName("code").setDescription("JavaScript code to evaluate").setRequired(true)
		),

	execute: async (ctx: any, commandType: number, messageOrInteraction: any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? messageOrInteraction.user : messageOrInteraction.author;
		const client = messageOrInteraction.client;

		// 1. Strict Owner Authorization
		if (!isBotOwner(user?.id)) {
			const deniedText = "❌ **Access Denied**: The `eval` command is strictly restricted to authorized bot owners.";
			return isSlash
				? messageOrInteraction.editReply({ content: deniedText })
				: messageOrInteraction.reply({ content: deniedText });
		}

		// 2. Extract code
		let rawCode = "";
		if (isSlash) {
			rawCode = messageOrInteraction.options.getString("code") || "";
		} else {
			rawCode = args.join(" ").trim();
		}

		// Strip markdown codeblocks if user enclosed code in ```js ... ```
		let cleanCode = rawCode.trim();
		if (cleanCode.startsWith("```")) {
			cleanCode = cleanCode.replace(/^```(?:js|javascript|ts)?\n?/, "").replace(/\n?```$/, "");
		}

		if (!cleanCode) {
			const errText = "❌ **Missing Code**: Please provide a JavaScript expression or script to evaluate.";
			return isSlash
				? messageOrInteraction.editReply({ content: errText })
				: messageOrInteraction.reply({ content: errText });
		}

		const E = config.Emojis || config.emojis || {};
		const C = config.Colors || config.colors || {};

		const startTime = process.hrtime.bigint();
		let result: any;
		let isError = false;
		let executionTimeMs = "0.00";

		// 3. Evaluation Context
		// Expose useful runtime objects for owner inspection
		const evalScope = {
			client,
			message: messageOrInteraction,
			interaction: messageOrInteraction,
			ctx,
			args,
			db: DatabaseManager,
			config,
			TicketManager,
			EconomyManager,
			LeaderboardManager,
			logger,
			global,
			process,
		};

		try {
			// Wrap in async IIFE so top-level await works cleanly
			const wrapped = `(async () => {\n${cleanCode}\n})()`;
			// Using Function constructor inside scope
			const fn = new Function(...Object.keys(evalScope), `return ${wrapped};`);
			result = await fn(...Object.values(evalScope));
		} catch (err: any) {
			isError = true;
			result = err;
		} finally {
			const endTime = process.hrtime.bigint();
			executionTimeMs = (Number(endTime - startTime) / 1_000_000).toFixed(2);
		}

		// 4. Format Output and Redact Secrets
		let outputStr = "";
		let resultType = typeof result;

		if (isError) {
			outputStr = result?.stack || result?.message || String(result);
		} else if (result === undefined) {
			outputStr = "undefined";
		} else if (result === null) {
			outputStr = "null";
		} else if (typeof result === "string") {
			outputStr = result;
		} else {
			outputStr = util.inspect(result, {
				depth: 1,
				maxArrayLength: 25,
				showHidden: false,
			});
		}

		const sanitizedInput = redactSecrets(truncateString(cleanCode, 500));
		const sanitizedOutput = redactSecrets(truncateString(outputStr, 1500));

		// 5. Build Components V2 Response
		const container = new ContainerBuilder()
			.setAccentColor(isError ? C.error || "#EF4444" : C.success || "#10B981")
			.addTextDisplay(
				`### ${isError ? "❌ Evaluation Error" : "⚡ JavaScript Evaluation"} (${executionTimeMs}ms)\n` +
				`• **Executor:** <@${user.id}> • **Type:** \`${resultType}\``
			)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`**Input:**\n\`\`\`javascript\n${sanitizedInput}\n\`\`\``)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`**Output:**\n\`\`\`javascript\n${sanitizedOutput}\n\`\`\``)
			.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
			.addTextDisplay(`-# MomentumOne Eval • Execution Time: ${executionTimeMs}ms • Confidential`)
			.build();

		const payload = {
			components: [container],
			flags: MessageFlags.IsComponentsV2,
			ephemeral: true,
		};

		return isSlash
			? messageOrInteraction.editReply(payload)
			: messageOrInteraction.reply(payload);
	},
};
