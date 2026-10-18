import config from "@config";
import logger from "@logger";
import { ContainerBuilder } from "@sdk/discord";
import { MessageFlags } from "discord.js";

export class Messages {
    
    static generalError({
        userId,
		title,
		message
	}){
        try {
            let container = new ContainerBuilder()
                .addTextDisplay(
                    `### ${config.Emojis.error}` + title
                    )
                .addSeparator({divider: true})
                .addTextDisplay(`<@${userId}>, ` + message)
                .addSeparator({divider: true})
                .addTextDisplay(`-# If you need any help, feel free to seek help on our [Support Server](${config.settings.bot.support_server || "https://discord.gg/example"})`)
                .setAccentColor(config.Colors.general_error || config.Colors.error || config.Colors.default || "#000000");
            return { 
                components: [container.build()], 
                flags: MessageFlags.IsComponentsV2
            };
        } catch (e) {
            logger.error("[Messages] ", e)
        }
    }
    
    static commandUsageError({
        userId,
        title, 
        message
    }){
        try {
            let container = new ContainerBuilder()
                .addTextDisplay(`### ${config.Emojis.error}` + title)
                .addSeparator({divider: true})
                .addTextDisplay(`<@${userId}>, ` +message)
                .addSeparator({divider: true})
                .addTextDisplay(`-# If you need any help, feel free to seek help on our [Support Server](${config.settings.bot.support_server || "https://discord.gg/example"})`)
                .setAccentColor(config.Colors.command_usage_error || config.Colors.error || config.Colors.default || "#000000");
            return { 
                components: [container.build()], 
                flags: MessageFlags.IsComponentsV2
            };
        } catch (e){
            logger.error("[Messages] ", e)
        }
    }
    
    static internalError({userId, error}){
	    try {
            
            let container = new ContainerBuilder()
                .addTextDisplay(
                    `### ${config.Emojis.internal_error || config.Emojis.error || ""} Internal error`)
                .addSeparator({divider: true})
                .addTextDisplay(
                    `Hey <@${userId}>, an error occurred while processing your request. This is probably **our fault**; the __bot team has been informed__.`)
                .addSeparator({divider: true})
                .addTextDisplay(`-# If you need any help, feel free to seek help on our [Support Server](${config.settings.bot.support_server || "https://discord.gg/example"})`)
                .setAccentColor(config.Colors.internal_error || config.Colors.error || config.Colors.default || "#000000")
            
            if (error instanceof Error){
                logger.error("Error occured: ", error)
            }
            
            return { 
                components: [container.build()], 
                flags: MessageFlags.IsComponentsV2
            };
        } catch (e) {
            logger.error("[Messages] ", e)
        }
    }
}
