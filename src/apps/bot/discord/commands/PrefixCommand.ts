import type { PermissionResolvable } from "discord.js";
import type { PrefixCommandContext } from "@bot/discord/commands/Context";

export default interface PrefixCommand {
    id: string;
    name: string;
    aliases?: string[];
    description?: string;
    category?: string;
    usage?: string;
    examples?: string[];
    permissions?: PermissionResolvable[];
    botPermissions?: PermissionResolvable[];
    cooldown?: number;
    guildOnly?: boolean;
    ownerOnly?: boolean;
    nsfw?: boolean;
    enabled?: boolean;
    hidden?: boolean;
    execute(ctx: PrefixCommandContext): Promise<void>;
}