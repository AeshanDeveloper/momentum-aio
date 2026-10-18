import type {
    PermissionResolvable,
    SlashCommandBuilder,
    SlashCommandOptionsOnlyBuilder,
    SlashCommandSubcommandsOnlyBuilder,
} from "discord.js";

import type { SlashCommandContext } from "@bot/discord/commands/Context";

export default interface SlashCommand {
    id: string;
    data:
        | SlashCommandBuilder
        | SlashCommandOptionsOnlyBuilder
        | SlashCommandSubcommandsOnlyBuilder;
    category?: string;
    botPermissions?: PermissionResolvable[];
    cooldown?: number;
    ownerOnly?: boolean;
    enabled?: boolean;
    hidden?: boolean;
    execute(ctx: SlashCommandContext): Promise<void>;
}
