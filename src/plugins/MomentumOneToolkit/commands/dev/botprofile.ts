const {
    MessageFlags,
    AttachmentBuilder,
} = require("discord.js");

const {
    CommandType,
    ContainerBuilder,
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";

export default {
    name: "botprofile",
    aliases: ["botpfp", "botname", "botbio", "serverprofile"],
    description: "Manage the bot's global or server-specific profile.",
    category: "Owner",
    usage: "botprofile <global|server> <avatar|name|bio> <value>",
    ownersOnly: true,

    execute: async (ctx, commandType, message, args) => {
        const E = config.Emojis || {};

        const success = E.success || "✅";
        const error = E.error || "❌";
        const info = E.info || "💡";
        const edit = E.edit || "✏️";

        const client = message.client;
        const guild = message.guild;

        const reply = async (title, description, isError = false) => {
            const container = new ContainerBuilder()
                .setAccentColor(
                    isError
                        ? config.Colors?.error || config.Colors?.default || "#ff0000"
                        : config.Colors?.success || config.Colors?.default || "#00ff00"
                )
                .addTextDisplay(
                    `### ${isError ? error : success} ${title}`
                )
                .addTextDisplay(description);

            return message.reply({
                components: [container.build()],
                flags: MessageFlags.IsComponentsV2,
            });
        };

        const usage = () =>
            reply(
                "Bot Profile",
                [
                    "**Global profile — changes the bot everywhere**",
                    "`!botprofile global avatar <image URL or attachment>`",
                    "`!botprofile global name <new name>`",
                    "`!botprofile global bio <new bio>`",
                    "",
                    "**Server profile — changes appearance in this server only**",
                    "`!botprofile server avatar <image URL or attachment>`",
                    "`!botprofile server name <new name>`",
                    "",
                    `${info} Server profile edits require the bot to support the corresponding guild-member profile API.`
                ].join("\n")
            );

        try {
            const scope = String(args?.[0] || "").toLowerCase();
            const action = String(args?.[1] || "").toLowerCase();
            const value = args?.slice(2).join(" ").trim() || "";

            if (!["global", "server"].includes(scope)) {
                return usage();
            }

            if (!["avatar", "name", "bio"].includes(action)) {
                return usage();
            }

            if (scope === "server" && !guild) {
                return reply(
                    "Server Required",
                    "This operation must be run inside the server whose bot profile you want to change.",
                    true
                );
            }

            if (scope === "server" && action === "bio") {
                return reply(
                    "Unsupported Operation",
                    "Discord does not provide a general-purpose server-specific bot bio field. The global bio is managed through the bot account profile.",
                    true
                );
            }

            let imageUrl = "";

            if (action === "avatar") {
                const attachment = message.attachments?.first();

                imageUrl = attachment?.url || value;

                if (!imageUrl || !/^https?:\/\//i.test(imageUrl)) {
                    return reply(
                        "Image Required",
                        "Attach an image to your message or provide a valid HTTP/HTTPS image URL.",
                        true
                    );
                }
            } else if (!value) {
                return reply(
                    "Value Required",
                    `Provide a value for the ${action}.`,
                    true
                );
            }

            if (scope === "global") {
                switch (action) {
                    case "avatar":
                        await client.user.setAvatar(imageUrl);
                        break;

                    case "name":
                        await client.user.setUsername(value);
                        break;

                    case "bio": {
                        return reply(
                            "Bio Update Unsupported",
                            "Discord.js does not expose a standard client.user method for changing the bot account's About Me/bio. This command cannot safely update it through the regular bot API.",
                            true
                        );
                    }
                }

                logger.info(
                    `[BOT PROFILE] Global ${action} updated by ${message.author.tag} (${message.author.id}).`
                );

                return reply(
                    "Global Profile Updated",
                    `The bot's global ${action} has been updated successfully.\n\n` +
                    `**Scope:** Global\n` +
                    `**Updated by:** ${message.author.tag}`
                );
            }

            /*
             * Server-specific profile.
             *
             * Discord.js supports changing a guild member's nickname,
             * but changing a bot's guild-specific avatar requires an
             * API capability not exposed by the standard GuildMember
             * edit methods. Do not silently change the global avatar.
             */

            if (action === "name") {
                await guild.members.me.setNickname(value);

                logger.info(
                    `[BOT PROFILE] Server nickname updated in ${guild.name} (${guild.id}) by ${message.author.tag} (${message.author.id}).`
                );

                return reply(
                    "Server Name Updated",
                    `The bot's nickname in **${guild.name}** has been updated.\n\n` +
                    `**Nickname:** ${value}\n` +
                    `**Scope:** This server only`
                );
            }

            if (action === "avatar") {
                return reply(
                    "Server Avatar Unsupported",
                    "The standard Discord.js GuildMember API does not expose a general-purpose method to set a bot's guild-specific avatar. The global avatar has not been changed.",
                    true
                );
            }
        } catch (err) {
            logger.error(
                `[BOT PROFILE] Failed to update profile: ${err.stack || err.message}`
            );

            return reply(
                "Update Failed",
                `Discord rejected the profile change.\n\n\`\`\`\n${String(err.message || err).slice(0, 1200)}\n\`\`\``,
                true
            );
        }
    },
};