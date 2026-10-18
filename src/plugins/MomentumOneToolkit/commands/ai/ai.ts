import {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	type ChatInputCommandInteraction,
	type Message,
} from "discord.js";
import { CommandType, ContainerBuilder } from "@sdk/discord";
import config from "@config";
import logger from "@logger";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";
import { GoogleGenAI } from "@google/genai";

const DEFAULT_MODEL = "gemini-3.8-flash";

function getGenAIClient(): GoogleGenAI | null {
	const apiKey = process.env.GEMINI_API_KEY?.trim();
	if (!apiKey) return null;
	return new GoogleGenAI({ apiKey });
}

export default {
	name: "ai",
	aliases: ["askai", "gemini", "chat"],
	description: "Ask a question or converse with Google Gemini AI.",
	category: "AI",
	usage: "ai <prompt>",
	cooldown: 5000,
	ownerOnly: false,

	builder: new SlashCommandBuilder()
		.setName("ai")
		.setDescription("Ask a question or converse with Google Gemini AI.")
		.addStringOption((opt: any) =>
			opt
				.setName("prompt")
				.setDescription("What would you like to ask the AI?")
				.setRequired(true)
		)
		.addStringOption((opt: any) =>
			opt
				.setName("model")
				.setDescription("Optional Gemini model to use")
				.setRequired(false)
				.addChoices(
					{ name: "Gemini 3.8 Flash (Fast & Smart)", value: "gemini-3.8-flash" },
					{ name: "Gemini 4 Argon (Complex Reasoning)", value: "gemini-4-argon" }
				)
		),

	execute: async (ctx: any, commandType: any, message: ChatInputCommandInteraction | Message | any, args: string[] = []) => {
		const isSlash = commandType === CommandType.SLASH;
		const user = isSlash ? message.user : message.author;

		// Extract prompt and optional model
		let promptText = "";
		let modelChoice: string | undefined;

		if (isSlash) {
			promptText = message.options?.getString("prompt")?.trim() || "";
			modelChoice = message.options?.getString("model")?.trim() || undefined;
		} else {
			promptText = (args || []).join(" ").trim();
		}

		// If no prompt was provided (e.g. empty prefix command)
		if (!promptText) {
			const helpContainer = new ContainerBuilder()
				.setAccentColor(config.Colors?.info || "#3B82F6")
				.addTextDisplay("### 🤖 MomentumOne AI Assistant")
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					"Please provide a question or topic to ask the AI.\n\n" +
					"**Usage Examples:**\n" +
					"• Slash: `/ai prompt:Explain quantum computing in simple terms`\n" +
					"• Prefix: `$ai How do async functions work in TypeScript?`\n\n" +
					`*-# Powered by Google Gemini (${process.env.GEMINI_MODEL?.trim() || DEFAULT_MODEL})*`
				)
				.build();

			if (isSlash) {
				return message.reply({
					components: [helpContainer],
					flags: MessageFlags.IsComponentsV2,
					ephemeral: true,
				});
			}
			return message.reply({
				components: [helpContainer],
				flags: MessageFlags.IsComponentsV2,
			});
		}

		// Defer slash interaction immediately so it never times out
		if (isSlash) {
			await message.deferReply();
		}

		const apiKey = process.env.GEMINI_API_KEY?.trim();
		if (!apiKey) {
			ObservabilityManager.recordEvent("ai_execution", {
				status: "missing_api_key",
				success: 0,
			});

			const noKeyContainer = new ContainerBuilder()
				.setAccentColor(config.Colors?.warning || "#F59E0B")
				.addTextDisplay("### ⚠️ Gemini AI Not Configured")
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					"The AI assistant feature requires a Google Gemini API key to operate.\n\n" +
					"**How to configure:**\n" +
					"1. Obtain a free API key at **[Google AI Studio](https://aistudio.google.com/)**.\n" +
					"2. Set the `GEMINI_API_KEY` environment variable in your `.env` or hosting settings.\n" +
					"3. Restart the bot to start using real-time AI responses."
				)
				.build();

			const payload = {
				components: [noKeyContainer],
				flags: MessageFlags.IsComponentsV2,
			};

			if (isSlash) {
				return message.editReply(payload);
			}
			return message.reply(payload);
		}

		const client = getGenAIClient();
		if (!client) {
			const failContainer = new ContainerBuilder()
				.setAccentColor(config.Colors?.error || "#EF4444")
				.addTextDisplay("### ❌ AI Client Initialization Failed")
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay("Failed to initialize Google GenAI client. Please check `GEMINI_API_KEY`.")
				.build();

			const payload = { components: [failContainer], flags: MessageFlags.IsComponentsV2 };
			if (isSlash) return message.editReply(payload);
			return message.reply(payload);
		}

		const selectedModel = modelChoice || process.env.GEMINI_MODEL?.trim() || DEFAULT_MODEL;
		const startTime = Date.now();

		try {
			// Bounded prompt input to avoid token flooding
			const sanitizedInput = promptText.slice(0, 3000);

			const response = await client.models.generateContent({
				model: selectedModel,
				contents: sanitizedInput,
				config: {
					systemInstruction:
						"You are MomentumOne AI, an intelligent, polite, and helpful assistant in Discord. " +
						"Provide clear, well-structured, concise answers using Discord-friendly markdown (headers, bullet points, codeblocks). " +
						"Do not repeat the user's prompt in the response body.",
					temperature: 0.7,
				},
			});

			const durationMs = Date.now() - startTime;
			let rawText = response.text?.trim() || "No response generated by the AI.";

			// Truncate safely if exceeding Discord Components V2 limit (approx 3800 chars)
			if (rawText.length > 3700) {
				rawText = rawText.slice(0, 3650) + "\n\n*(Response truncated due to Discord length limits)*";
			}

			// Clean quote for prompt display
			const safePromptDisplay = sanitizedInput.length > 150
				? sanitizedInput.slice(0, 147) + "..."
				: sanitizedInput;

			const replyContainer = new ContainerBuilder()
				.setAccentColor(config.Colors?.success || "#10B981")
				.addTextDisplay(`### 🤖 AI Response\n> **Prompt:** *${safePromptDisplay.replace(/\n/g, " ")}*`)
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(rawText)
				.addSeparator({ divider: false, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`-# Model: \`${selectedModel}\` • Latency: \`${durationMs}ms\` • User: <@${user?.id}>`
				)
				.build();

			const payload = {
				components: [replyContainer],
				flags: MessageFlags.IsComponentsV2,
			};

			if (isSlash) {
				await message.editReply(payload);
			} else {
				await message.reply(payload);
			}

			ObservabilityManager.recordEvent("ai_execution", {
				model: selectedModel,
				prompt_len: sanitizedInput.length,
				duration_ms: durationMs,
				success: 1,
			});
		} catch (err: any) {
			const durationMs = Date.now() - startTime;
			logger.error("[AICommand] Gemini generation error:", err);

			ObservabilityManager.recordError(
				"ai_failure",
				`[${selectedModel}] ${err?.message || "Generation failed"}`.slice(0, 100)
			);
			ObservabilityManager.recordEvent("ai_execution", {
				model: selectedModel,
				prompt_len: promptText.length,
				duration_ms: durationMs,
				success: 0,
			});

			let friendlyError = "An unexpected error occurred while communicating with Google Gemini AI.";
			if (err?.message?.includes("quota") || err?.message?.includes("429")) {
				friendlyError = "Gemini API rate limit or quota exceeded. Please try again in a few moments.";
			} else if (err?.message?.includes("API_KEY_INVALID") || err?.message?.includes("403")) {
				friendlyError = "The provided `GEMINI_API_KEY` appears to be invalid or unauthorized.";
			} else if (err?.message?.includes("SAFETY")) {
				friendlyError = "The prompt triggered Gemini safety filters and cannot be answered.";
			}

			const errorContainer = new ContainerBuilder()
				.setAccentColor(config.Colors?.error || "#EF4444")
				.addTextDisplay("### ❌ AI Generation Error")
				.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
				.addTextDisplay(
					`${friendlyError}\n\n` +
					`• **Model:** \`${selectedModel}\`\n` +
					`• **Details:** \`${(err?.message || "Internal error").slice(0, 150)}\``
				)
				.build();

			const payload = {
				components: [errorContainer],
				flags: MessageFlags.IsComponentsV2,
			};

			if (isSlash) {
				await message.editReply(payload).catch(() => null);
			} else {
				await message.reply(payload).catch(() => null);
			}
		}
	},
};
