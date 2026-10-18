
import logger from "@logger";
import { getAllFiles } from "@shared/helpers";
import path from "node:path";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { createRequire } from "node:module";

import Events from "@database/models/Events";

import {
	EventStatus,
	RegisteredBy,
} from "@shared/types/EventRecord";

const require = createRequire(import.meta.url);

const events = new Events();

interface LoadedEvent {
	file: string;
	checksum: string;
	name: string;
	description: string | null;
	execute: (...args: any[]) => any;
}

export default class EventsLoader {
	client: any;
	
	constructor(client: any){
		this.client = client;
	}

	/**
	 * Discover, synchronize and register all events
	 * belonging to a plugin.
	 */
	async fromPluginId(id: string) {
		if (typeof id !== "string") {
			return logger.silly(
				"[EventLoader] Please provide a valid plugin id."
			);
		}

		try {
			const settings = global.cache.plugins.get(id);

			if (!settings) {
				return logger.silly(
					`[EventLoader] Plugin "${id}" was not found.`
				);
			}

			const eventSettings =
				settings.autoLoader?.events;

			if (!eventSettings?.enabled) {
				return logger.debug(
					`[EventLoader] Event autoloader disabled for "${settings.meta.name}".`
				);
			}

			if (typeof eventSettings.mapping !== "function") {
				return logger.debug(
					`[EventLoader] Event mapping is not configured for "${settings.meta.name}".`
				);
			}

			const eventsDir = path.resolve(
				settings.meta.path,
				eventSettings.directory
			);

			const files = getAllFiles(eventsDir);

			const discovered: LoadedEvent[] = [];

			// ---------------------------
			// Discover events
			// ---------------------------

			for (const file of files) {
				try {
					const raw = require(file);
					const event = raw?.default ?? raw;

					if (
						!event ||
						typeof event !== "object"
					) {
						continue;
					}

					let mapped;

					try {
						mapped = eventSettings.mapping(event);
					} catch (err: any) {
						logger.debug(
							`[EventLoader] Failed to map "${file}"\n${err.message}`
						);
						continue;
					}

					if (
						!mapped ||
						typeof mapped !== "object"
					) {
						logger.debug(
							`[EventLoader] Mapping returned an invalid event for "${file}".`
						);
						continue;
					}

					if (
						typeof mapped.name !== "string" ||
						typeof mapped.execute !== "function"
					) {
						logger.debug(
							`[EventLoader] Invalid event "${file}". Events require "name" and "execute".`
						);
						continue;
					}

					discovered.push({
						file,
						checksum:
							await this.calculateChecksum(file),

						name: mapped.name,

						description:
							mapped.description ?? null,

						execute: mapped.execute,
					});

				} catch (err: any) {
					logger.error(
						`[EventLoader] Failed to load "${file}".`,
						err
					);
				}
			}

			// ---------------------------
			// Database synchronization
			// ---------------------------

			const dbEvents =
				await events.findByPluginId(id);

			const discoveredMap =
				new Map(
					discovered.map(event => [
						`${event.name}:${path.basename(event.file)}`,
						event,
					])
				);

			const dbMap =
				new Map(
					dbEvents.map(event => [
						event.name.includes(":") ? event.name : `${event.name}`,
						event,
					])
				);

			// ---------------------------
			// Register / update
			// ---------------------------

			for (const [key, event] of discoveredMap) {
				const existing =
					dbMap.get(key) || dbMap.get(event.name);

				if (!existing) {
					await events.register({
						eventId: crypto.randomUUID(),
						pluginId: id,
						name: key,
						description: event.description,
						enabled: true,
						status: EventStatus.ACTIVE,
						checksum: event.checksum,
						registeredBy:
							RegisteredBy.AUTOLOADER,
					});

					logger.debug(
						`[EventLoader] Registered "${key}".`
					);

					continue;
				}

				if (
					existing.checksum !==
					event.checksum
				) {
					await events.update(
						existing.eventId,
						{
							pluginId:
								existing.pluginId,

							name: key,

							description:
								event.description,

							enabled:
								existing.enabled,

							status:
								EventStatus.ACTIVE,

							checksum:
								event.checksum,

							registeredBy:
								RegisteredBy.AUTOLOADER,
						}
					);

					logger.debug(
						`[EventLoader] Updated "${key}".`
					);

					continue;
				}

				if (
					existing.status !==
					EventStatus.ACTIVE
				) {
					await events.setStatus(
						existing.eventId,
						EventStatus.ACTIVE
					);

					logger.debug(
						`[EventLoader] Restored "${key}".`
					);
				}
			}

			// ---------------------------
			// Mark missing events
			// ---------------------------

			for (const [name, event] of dbMap) {
				if (
					!discoveredMap.has(name) &&
					!discovered.some(d => d.name === name) &&
					event.status !==
						EventStatus.MISSING
				) {
					await events.setStatus(
						event.eventId,
						EventStatus.MISSING
					);

					logger.debug(
						`[EventLoader] Marked "${name}" as missing.`
					);
				}
			}

			// ---------------------------
			// Register Discord listeners
			// ---------------------------

			await this.registerEvents(
				id,
				discovered
			);

		} catch (err) {
			logger.error(
				`[EventLoader] Failed to synchronize events for "${global.cache.plugins.get(id)?.meta.name}".`,
				err
			);
		}
	}

	/**
	 * Register discovered events with Discord.
	 */
	private async registerEvents(
		id: string,
		discovered: LoadedEvent[]
	): Promise<void> {
		const dbEvents =
			await events.findByPluginId(id);

		if (!this.client._loadedEventHandlers) {
			this.client._loadedEventHandlers = new Set<string>();
		}

		for (const event of discovered) {
			const fileKey = `${event.name}:${path.basename(event.file)}`;
			const dbEvent =
				dbEvents.find(
					db => db.name === fileKey || db.name === event.name
				);

			if (!dbEvent) {
				continue;
			}

			if (
				dbEvent.enabled === false
			) {
				continue;
			}

			if (
				dbEvent.status !==
				EventStatus.ACTIVE
			) {
				continue;
			}

			const handlerKey = `${id}:${fileKey}`;
			if (this.client._loadedEventHandlers.has(handlerKey)) {
				continue;
			}
			this.client._loadedEventHandlers.add(handlerKey);

			if (!this.client._loadedEventMap) {
				this.client._loadedEventMap = new Map<string, { eventName: string; listener: (...args: any[]) => void }>();
			}

			const listener = (...args: any[]) => {
				let pluginContext = global.cache?.plugins?.get(id)?.pluginContext;
				event.execute(pluginContext, ...args);
			};

			this.client._loadedEventMap.set(handlerKey, {
				eventName: event.name,
				listener,
			});

			this.client.on(event.name, listener);

		}
	}

	/**
	 * Safely unregisters all Discord event listeners belonging to a plugin.
	 */
	public unloadPluginEvents(id: string): void {
		if (!this.client._loadedEventMap) return;
		for (const [key, record] of Array.from(this.client._loadedEventMap.entries())) {
			if (key.startsWith(`${id}:`)) {
				this.client.removeListener(record.eventName, record.listener);
				this.client._loadedEventHandlers?.delete(key);
				this.client._loadedEventMap.delete(key);
				logger.debug(`[EventLoader] Unregistered listener for "${key}"`);
			}
		}
	}

	/**
	 * Load all plugin events.
	 */
	async autoLoad(id: string) {
		logger.debug(
			"[EventLoader] Autoloading plugin events..."
		);

		return this.fromPluginId(id);
	}

	/**
	 * Load events from every plugin.
	 */
	async autoLoadAll() {
		for (const [id] of global.cache.plugins) {
			await this.autoLoad(id);
		}
	}

	/**
	 * Calculate SHA-256 checksum for an event file.
	 */
	private async calculateChecksum(
		filePath: string
	): Promise<string> {
		return new Promise(
			(resolve, reject) => {
				const hash =
					createHash("sha256");

				const stream =
					createReadStream(filePath);

				stream.on(
					"error",
					reject
				);

				stream.on(
					"data",
					chunk => {
						hash.update(chunk);
					}
				);

				stream.on(
					"end",
					() => {
						resolve(
							hash.digest("hex")
						);
					}
				);
			}
		);
	}
}
