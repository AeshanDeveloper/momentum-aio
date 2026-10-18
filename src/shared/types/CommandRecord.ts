export enum CommandType {
	PREFIX = "PREFIX",
	SLASH = "SLASH",
	CONTEXT_USER = "CONTEXT_USER",
	CONTEXT_MESSAGE = "CONTEXT_MESSAGE",
	HYBRID = "HYBRID",
}

export enum CommandStatus {
	ACTIVE = "ACTIVE",
	MISSING = "MISSING",
}

export enum RegisteredBy {
	CORE = "CORE",
	PLUGIN = "PLUGIN",
	SYSTEM = "MomentumOne/system",
	AUTOLOADER = "MomentumOne/AutoLoader"
}

export default interface CommandRecord {
	commandId: string;

	pluginId: string;

	name: string;
	description: string | null;
	enabled: boolean;
	type: CommandType;

	aliases: string[] | null;

	ownerOnly: string;
	developerOnly: string;
	premiumOnly: string;
	guildOnly: string;
	nsfw: string;
	
	userPermissions: string;
	botPermissions: string;

	status: CommandStatus;
	cooldown: number;

	checksum: string;

	registeredBy: RegisteredBy;

	//registeredAt: Date;
	//updatedAt: Date;
}

