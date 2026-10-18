import BotManager from "@bot/discord/Manager";
import logger from "@logger";

export default class Main {
	bot: BotManager = new BotManager()

	async start() {
		const enabled = process.env.BOT_ENABLED?.trim().toLowerCase();
		if (enabled === "false" || enabled === "0" || enabled === "off") {
			logger.info(`[BOT] Discord bot startup is disabled by BOT_ENABLED=${enabled}.`);
			return;
		}

		const status = await this.bot.setup();
		if (!status.ready) {
			logger.error("[BOT] Discord client setup failed; login was not attempted.");
			return;
		}

		try {
			await this.bot.login();
		} catch (error) {
			logger.error("[BOT] Discord login failed. Check BOT_TOKEN and Discord application settings:", error);
		}
	}
}
