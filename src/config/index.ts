// Config Files
import serverConfig from "@config/server";
import databaseConfig from "@config/database";
import settingsConfig from "@config/settings";
import emojis from "@config/Emojis.json"
import colors from "@config/Colors.json"

export default new class Config {
	public readonly environment = process.env.NODE_ENV ?? "development";
	public readonly enviorment = this.environment;
	public readonly bot_token: string = process.env.BOT_TOKEN ?? "NO_TOKEN";
	public readonly server = serverConfig;
	public readonly database = databaseConfig;
	public readonly settings = settingsConfig;
	public readonly Emojis = emojis;
	public readonly Colors = colors;
	public readonly emojis = emojis;
	public readonly colors = colors;
}
