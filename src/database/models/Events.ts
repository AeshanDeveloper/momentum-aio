import DatabaseManager from "@database/Database";
import type EventRecord from "@shared/types/EventRecord";
import type { Filter } from "mongodb";

export default class eventModel {
	private readonly database;

	constructor() {
		this.database = DatabaseManager;
	}

	/**
	 * Normalize a MongoDB document into the same
	 * shape returned by the old MySQL model.
	 *
	 * MongoDB adds _id automatically, but _id was not
	 * present in the old MySQL EventRecord output.
	 */
	private normalize(document: any): EventRecord {
		if (!document) return document;

		const {
			_id,
			event_id,
			plugin_id,
			registered_by,
			...event
		} = document;

		return {
			eventId: event_id ?? _id,
			pluginId: plugin_id ?? event.pluginId,
			registeredBy: registered_by ?? event.registeredBy,
			...event,
		} as EventRecord;
	}

	/**
	 * Register an event.
	 */
	async register(
		event: EventRecord
	): Promise<void> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		await collection.insertOne({
			event_id: event.eventId,
			plugin_id: event.pluginId,
			name: event.name,
			description: event.description,
			enabled: event.enabled,
			status: event.status,
			checksum: event.checksum,
			registered_by: event.registeredBy,
		} as any);
	}

	/**
	 * Update an event.
	 */
	async update(
		id: string,
		event: any
	): Promise<void> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		await collection.updateOne(
			{
				event_id: id,
			} as Filter<EventRecord>,
			{
				$set: {
					plugin_id: event.pluginId,
					name: event.name,
					description: event.description,
					enabled: event.enabled,
					status: event.status,
					checksum: event.checksum,
					registered_by: event.registeredBy,
				},
			}
		);
	}

	/**
	 * Delete an event.
	 *
	 * Returns true if an event was deleted,
	 * false if it did not exist.
	 */
	async delete(
		eventId: string
	): Promise<boolean> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const result =
			await collection.deleteOne({
				event_id: eventId,
			} as Filter<EventRecord>);

		return result.deletedCount > 0;
	}

	/**
	 * Alias for delete().
	 */
	async unregister(
		eventId: string
	): Promise<boolean> {
		return this.delete(eventId);
	}

	/**
	 * Get events by any EventRecord field.
	 */
	async get<K extends keyof EventRecord>(
		field: K,
		value: EventRecord[K]
	): Promise<EventRecord[]> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const rows =
			await collection.find({
				[field as string]: value,
			} as Filter<EventRecord>).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Get all events.
	 */
	async getAll(): Promise<EventRecord[]> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const rows =
			await collection.find({}).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Find an event by ID.
	 */
	async findById(
		eventId: string
	): Promise<EventRecord | null> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const event =
			await collection.findOne({
				event_id: eventId,
			} as Filter<EventRecord>);

		return event
			? this.normalize(event)
			: null;
	}

	/**
	 * Find all events belonging to a plugin.
	 */
	async findByPluginId(
		pluginId: string
	): Promise<EventRecord[]> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const rows =
			await collection.find({
				$or: [{ plugin_id: pluginId }, { pluginId: pluginId }],
			} as any).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Check whether an event exists.
	 */
	async exists(
		eventId: string
	): Promise<boolean> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const event =
			await collection.findOne(
				{
					event_id: eventId,
				} as Filter<EventRecord>,
				{
					projection: {
						_id: 1,
					},
				}
			);

		return event !== null;
	}

	/**
	 * Check whether an event exists by
	 * plugin ID + event name.
	 */
	async existsByPluginNameType(
		pluginId: string,
		name: string
	): Promise<boolean> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		const event =
			await collection.findOne(
				{
					plugin_id: pluginId,
					name,
				} as Filter<EventRecord>,
				{
					projection: {
						_id: 1,
					},
				}
			);

		return event !== null;
	}

	/**
	 * Update event status.
	 */
	async setStatus(
		eventId: string,
		status: any
	): Promise<void> {
		const collection =
			await this.database.collection<EventRecord>(
				"shop_events"
			);

		await collection.updateOne(
			{
				event_id: eventId,
			} as Filter<EventRecord>,
			{
				$set: {
					status,
				},
			}
		);
	}
}