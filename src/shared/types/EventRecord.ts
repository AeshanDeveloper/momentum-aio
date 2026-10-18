
import { CommandStatus } from "./CommandRecord";

export enum EventStatus {
	ACTIVE = "ACTIVE",
	MISSING = "MISSING",
}

export enum RegisteredBy {
	CORE = "CORE",
	PLUGIN = "PLUGIN",
	SYSTEM = "MomentumOne/system",
	AUTOLOADER = "MomentumOne/AutoLoader"
}

export default interface EventRecord {
	eventId: string;

	pluginId: string;

	name: string;
	description: string | null;
	enabled: boolean;

	status: CommandStatus;

	checksum: string;

	registeredBy: RegisteredBy;

	//registeredAt: Date;
	//updatedAt: Date;
}

