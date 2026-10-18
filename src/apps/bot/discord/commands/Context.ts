import type {
    ChatInputCommandInteraction,
    Client,
	Message
} from "discord.js";
import type PluginContext from "@core/plugins/PluginContext";
import type PrefixCommand from "@bot/discord/commands/PrefixCommand";
import type SlashCommand from "@bot/discord/commands/SlashCommand";

export interface PrefixCommandContext {
    client: Client;
    plugin: PluginContext;
    message: Message;
    args: string[];
    command: PrefixCommand;
}

export interface SlashCommandContext {
    client: Client;
    plugin: PluginContext;
    interaction: ChatInputCommandInteraction;
    command: SlashCommand;
}