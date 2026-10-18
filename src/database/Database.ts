import fs from "node:fs";
import path from "node:path";
import {
	MongoClient,
	type Db,
	type Collection,
	type Document,
	type Filter,
	type OptionalId,
	type WithId,
	type UpdateFilter,
	type UpdateResult,
	type DeleteResult,
	type InsertOneResult,
	type InsertManyResult,
	type FindOptions,
	type CountDocumentsOptions,
	type IndexDescription,
	type FindOneAndUpdateOptions,
	type ReturnDocument
} from "mongodb";

import config from "@config";
import logger from "@logger";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

const MOCK_DB_FILE = path.resolve(process.cwd(), ".data/local_db.json");

function loadMockDataFromFile(): Record<string, any[]> {
	try {
		if (fs.existsSync(MOCK_DB_FILE)) {
			const raw = fs.readFileSync(MOCK_DB_FILE, "utf-8");
			return JSON.parse(raw);
		}
	} catch {
		// Ignore read error
	}
	return {};
}

function saveMockDataToFile(collectionName: string, items: any[]): void {
	try {
		const dir = path.dirname(MOCK_DB_FILE);
		if (!fs.existsSync(dir)) {
			fs.mkdirSync(dir, { recursive: true });
		}
		const allData = loadMockDataFromFile();
		allData[collectionName] = items;
		fs.writeFileSync(MOCK_DB_FILE, JSON.stringify(allData, null, 2), "utf-8");
	} catch {
		// Ignore write error
	}
}

function getNestedValue(obj: any, path: string): any {
	if (!obj || typeof obj !== "object") return undefined;
	if (path in obj) return obj[path];
	const parts = path.split(".");
	let curr = obj;
	for (const p of parts) {
		if (curr === null || curr === undefined || typeof curr !== "object") return undefined;
		curr = curr[p];
	}
	return curr;
}

function setNestedValue(obj: any, path: string, val: any): void {
	const parts = path.split(".");
	let curr = obj;
	for (let i = 0; i < parts.length - 1; i++) {
		const p = parts[i];
		if (!curr[p] || typeof curr[p] !== "object") {
			curr[p] = {};
		}
		curr = curr[p];
	}
	curr[parts[parts.length - 1]] = val;
}

function applyMockUpdate(item: any, update: any): any {
	const result = { ...item };
	if (update.$set) {
		for (const [k, v] of Object.entries(update.$set)) {
			setNestedValue(result, k, v);
		}
	}
	if (update.$inc) {
		for (const [k, v] of Object.entries(update.$inc)) {
			const currentVal = Number(getNestedValue(result, k) || 0);
			setNestedValue(result, k, currentVal + Number(v));
		}
	}
	if (update.$unset) {
		for (const k of Object.keys(update.$unset)) {
			const parts = k.split(".");
			let curr = result;
			for (let i = 0; i < parts.length - 1; i++) {
				if (!curr[parts[i]]) break;
				curr = curr[parts[i]];
			}
			if (curr && typeof curr === "object") {
				delete curr[parts[parts.length - 1]];
			}
		}
	}
	if (!update.$set && !update.$inc && !update.$unset) {
		Object.assign(result, update);
	}
	return result;
}

class MockCursor {
	private items: any[];
	private sortSpec: any = null;
	private skipCount = 0;
	private limitCount: number | null = null;

	constructor(items: any[]) {
		this.items = items;
	}

	sort(spec: any) {
		this.sortSpec = spec;
		return this;
	}

	skip(n: number) {
		this.skipCount = n;
		return this;
	}

	limit(n: number) {
		this.limitCount = n;
		return this;
	}

	async toArray(): Promise<any[]> {
		let res = [...this.items];
		if (this.sortSpec) {
			const [field, direction] = Object.entries(this.sortSpec)[0] || [];
			if (field) {
				res.sort((a, b) => {
					const va = getNestedValue(a, field);
					const vb = getNestedValue(b, field);
					if (va < vb) return (direction as number) === 1 ? -1 : 1;
					if (va > vb) return (direction as number) === 1 ? 1 : -1;
					return 0;
				});
			}
		}
		if (this.skipCount) {
			res = res.slice(this.skipCount);
		}
		if (this.limitCount !== null) {
			res = res.slice(0, this.limitCount);
		}
		return res;
	}

	async hasNext(): Promise<boolean> {
		const arr = await this.toArray();
		return arr.length > 0;
	}
}

const globalMockStore: Map<string, Map<string, any>> = ((globalThis as any).__mockDbStore ??= new Map<string, Map<string, any>>());

class MockCollection {
	private name: string;

	constructor(name: string = "default") {
		this.name = name;
		if (!globalMockStore.has(this.name)) {
			const map = new Map<string, any>();
			const allData = loadMockDataFromFile();
			if (Array.isArray(allData[this.name])) {
				for (const item of allData[this.name]) {
					const _id = String(item._id || item.targetId || item.ticketId || item.userId || item.auditId || `mock_${Math.random()}`);
					map.set(_id, item);
				}
			}
			globalMockStore.set(this.name, map);
		}
	}

	private get items(): Map<string, any> {
		if (!globalMockStore.has(this.name)) {
			globalMockStore.set(this.name, new Map());
		}
		return globalMockStore.get(this.name)!;
	}

	private persist(): void {
		saveMockDataToFile(this.name, Array.from(this.items.values()));
	}

	private matches(item: any, filter: any): boolean {
		if (!filter || Object.keys(filter).length === 0) return true;
		for (const [key, val] of Object.entries(filter)) {
			if (key === "$or" && Array.isArray(val)) {
				if (!val.some(sub => this.matches(item, sub))) return false;
				continue;
			}
			if (key === "$and" && Array.isArray(val)) {
				if (!val.every(sub => this.matches(item, sub))) return false;
				continue;
			}

			const itemVal = getNestedValue(item, key);

			if (val && typeof val === "object" && !(val instanceof Date)) {
				if ("$in" in val && Array.isArray(val.$in)) {
					if (!val.$in.includes(itemVal)) return false;
					continue;
				}
				if ("$nin" in val && Array.isArray(val.$nin)) {
					if (val.$nin.includes(itemVal)) return false;
					continue;
				}
				if ("$ne" in val) {
					if (itemVal === val.$ne) return false;
					continue;
				}
				if ("$gte" in val) {
					const a = itemVal instanceof Date ? itemVal.getTime() : itemVal;
					const b = val.$gte instanceof Date ? val.$gte.getTime() : val.$gte;
					if (a < b) return false;
					continue;
				}
				if ("$lte" in val) {
					const a = itemVal instanceof Date ? itemVal.getTime() : itemVal;
					const b = val.$lte instanceof Date ? val.$lte.getTime() : val.$lte;
					if (a > b) return false;
					continue;
				}
				if ("$gt" in val) {
					const a = itemVal instanceof Date ? itemVal.getTime() : itemVal;
					const b = val.$gt instanceof Date ? val.$gt.getTime() : val.$gt;
					if (a <= b) return false;
					continue;
				}
				if ("$lt" in val) {
					const a = itemVal instanceof Date ? itemVal.getTime() : itemVal;
					const b = val.$lt instanceof Date ? val.$lt.getTime() : val.$lt;
					if (a >= b) return false;
					continue;
				}
				if ("$regex" in val) {
					const pattern = typeof val.$regex === "string" ? val.$regex : (val.$regex as RegExp).source;
					const re = new RegExp(pattern, val.$options || "i");
					if (!re.test(String(itemVal ?? ""))) return false;
					continue;
				}
			}

			if (itemVal !== val) return false;
		}
		return true;
	}

	async insertOne(doc: any) {
		const _id =
			doc._id ||
			doc.event_id ||
			doc.eventId ||
			doc.command_id ||
			doc.commandId ||
			doc.ticket_id ||
			doc.ticketId ||
			doc.audit_id ||
			doc.auditId ||
			doc.plugin_id ||
			doc.pluginId ||
			`mock_${Date.now()}_${Math.random()}`;
		const record = { ...doc, _id };
		this.items.set(String(_id), record);
		this.persist();
		return { acknowledged: true, insertedId: _id };
	}

	async insertMany(docs: any[]) {
		const insertedIds: Record<number, any> = {};
		docs.forEach((doc, idx) => {
			const _id =
				doc._id ||
				doc.event_id ||
				doc.eventId ||
				doc.command_id ||
				doc.commandId ||
				doc.ticket_id ||
				doc.ticketId ||
				doc.audit_id ||
				doc.auditId ||
				doc.plugin_id ||
				doc.pluginId ||
				`mock_${Date.now()}_${idx}`;
			this.items.set(String(_id), { ...doc, _id });
			insertedIds[idx] = _id;
		});
		this.persist();
		return { acknowledged: true, insertedCount: docs.length, insertedIds };
	}

	async findOne(filter: any = {}, options?: any) {
		for (const item of this.items.values()) {
			if (this.matches(item, filter)) {
				return { ...item };
			}
		}
		return null;
	}

	find(filter: any = {}, options?: any) {
		const matched: any[] = [];
		for (const item of this.items.values()) {
			if (this.matches(item, filter)) {
				matched.push({ ...item });
			}
		}
		const cursor = new MockCursor(matched);
		if (options?.sort) cursor.sort(options.sort);
		if (options?.skip) cursor.skip(options.skip);
		if (options?.limit) cursor.limit(options.limit);
		return cursor;
	}

	async updateOne(filter: any, update: any, options?: any) {
		let matchedCount = 0;
		let modifiedCount = 0;
		for (const [id, item] of this.items.entries()) {
			if (this.matches(item, filter)) {
				matchedCount++;
				const updated = applyMockUpdate(item, update);
				this.items.set(id, updated);
				modifiedCount++;
				this.persist();
				return { acknowledged: true, matchedCount, modifiedCount, upsertedId: null, upsertedCount: 0 };
			}
		}

		if (options?.upsert) {
			const newDoc: any = {};
			for (const [k, v] of Object.entries(filter)) {
				if (!k.startsWith("$") && (typeof v !== "object" || v === null || v instanceof Date)) {
					setNestedValue(newDoc, k, v);
				}
			}
			const updated = applyMockUpdate(newDoc, update);
			const _id = updated._id || updated.targetId || updated.userId || `mock_${Date.now()}_${Math.random()}`;
			updated._id = _id;
			this.items.set(String(_id), updated);
			this.persist();
			return { acknowledged: true, matchedCount: 0, modifiedCount: 0, upsertedId: _id, upsertedCount: 1 };
		}

		return { acknowledged: true, matchedCount, modifiedCount, upsertedId: null, upsertedCount: 0 };
	}

	async updateMany(filter: any, update: any, options?: any) {
		let matchedCount = 0;
		let modifiedCount = 0;
		for (const [id, item] of this.items.entries()) {
			if (this.matches(item, filter)) {
				matchedCount++;
				const updated = applyMockUpdate(item, update);
				this.items.set(id, updated);
				modifiedCount++;
			}
		}

		if (matchedCount > 0) {
			this.persist();
			return { acknowledged: true, matchedCount, modifiedCount, upsertedId: null, upsertedCount: 0 };
		}

		if (options?.upsert) {
			const newDoc: any = {};
			for (const [k, v] of Object.entries(filter)) {
				if (!k.startsWith("$") && (typeof v !== "object" || v === null || v instanceof Date)) {
					setNestedValue(newDoc, k, v);
				}
			}
			const updated = applyMockUpdate(newDoc, update);
			const _id = updated._id || updated.targetId || updated.userId || `mock_${Date.now()}_${Math.random()}`;
			updated._id = _id;
			this.items.set(String(_id), updated);
			this.persist();
			return { acknowledged: true, matchedCount: 0, modifiedCount: 0, upsertedId: _id, upsertedCount: 1 };
		}

		return { acknowledged: true, matchedCount, modifiedCount, upsertedId: null, upsertedCount: 0 };
	}

	async deleteOne(filter: any) {
		let deletedCount = 0;
		for (const [id, item] of this.items.entries()) {
			if (this.matches(item, filter)) {
				this.items.delete(id);
				deletedCount = 1;
				this.persist();
				break;
			}
		}
		return { acknowledged: true, deletedCount };
	}

	async deleteMany(filter: any) {
		let deletedCount = 0;
		const toDelete: string[] = [];
		for (const [id, item] of this.items.entries()) {
			if (this.matches(item, filter)) {
				toDelete.push(id);
			}
		}
		for (const id of toDelete) {
			this.items.delete(id);
			deletedCount++;
		}
		if (deletedCount > 0) {
			this.persist();
		}
		return { acknowledged: true, deletedCount };
	}

	async countDocuments(filter: any = {}) {
		let count = 0;
		for (const item of this.items.values()) {
			if (this.matches(item, filter)) count++;
		}
		return count;
	}

	async createIndex(indexSpec: any, options?: any) {
		return "mock_index";
	}

	async findOneAndUpdate(filter: any, update: any, options?: any) {
		for (const [id, item] of this.items.entries()) {
			if (this.matches(item, filter)) {
				const before = { ...item };
				const updated = applyMockUpdate(item, update);
				this.items.set(id, updated);
				this.persist();
				return options?.returnDocument === "after" ? updated : before;
			}
		}

		if (options?.upsert) {
			const newDoc: any = {};
			for (const [k, v] of Object.entries(filter)) {
				if (!k.startsWith("$") && (typeof v !== "object" || v === null || v instanceof Date)) {
					setNestedValue(newDoc, k, v);
				}
			}
			const updated = applyMockUpdate(newDoc, update);
			const _id = updated._id || updated.targetId || updated.userId || `mock_${Date.now()}_${Math.random()}`;
			updated._id = _id;
			this.items.set(String(_id), updated);
			this.persist();
			return updated;
		}

		return null;
	}
}

class DatabaseManager {
	private client: MongoClient | null = null;
	private db: Db | null = null;
	private mockCollections = new Map<string, MockCollection>();
	private isMock = false;

	/**
	 * Initialize MongoDB connection.
	 */
	public async initialize(executor = "unknown"): Promise<Db | any> {
		const start = Date.now();

		if (this.db) {
			return this.db;
		}
		if (this.isMock) {
			return null;
		}

		const envUri = (
			process.env.MONGODB_URI ||
			process.env.MONGO_URI ||
			process.env.MONGODB_URL ||
			process.env.MONGO_URL ||
			""
		).trim().replace(/^["']|["']$/g, "");

		const connection = (config.database as any)?.[config.environment]?.connection || config.database?.production?.connection;
		const uri = envUri || connection?.url;
		const databaseName =
			process.env.MONGODB_DB?.trim() ||
			process.env.MONGO_DB?.trim() ||
			process.env.MONGODB_DATABASE?.trim() ||
			connection?.database ||
			"momentumone";

		if (!uri) {
			logger.info("[DB] No MONGODB_URI configured. Running with in-memory store for AI Studio.");
			this.isMock = true;
			global.eBus?.publish?.(global.EventsList?.DATABASE_CONNECTED, {
				executor,
				database: "in-memory-mock",
				duration: Date.now() - start,
			});
			return null;
		}

		try {
			logger.debug("[DB] Initializing database...");
			this.client = new MongoClient(uri, {
				maxPoolSize: 10,
				minPoolSize: 1,
				retryWrites: true,
				serverSelectionTimeoutMS: 15000,
				connectTimeoutMS: 15000,
			});

			await this.client.connect();
			this.db = this.client.db(databaseName);
			await this.db.command({ ping: 1 });

			global.eBus?.publish?.(global.EventsList?.DATABASE_CONNECTED, {
				executor,
				database: databaseName,
				duration: Date.now() - start,
			});

			logger.info("[DB] Connected to MongoDB successfully.");
			ObservabilityManager.recordDatabaseEvent("connect_mongodb", true, Date.now() - start);
			return this.db;
		} catch (error: any) {
			this.client = null;
			this.db = null;
			this.isMock = true;

			logger.info(`[DB] Database note: ${error?.message || "Using mock store"}. Operating with in-memory database store.`);
			ObservabilityManager.recordError("database_connection_failure", error?.message || "Failed to connect to MongoDB", "warn");
			ObservabilityManager.recordDatabaseEvent("connect_mongodb", false, Date.now() - start);
			global.eBus?.publish?.(global.EventsList?.DATABASE_CONNECTED, {
				executor,
				database: "in-memory-mock",
				duration: Date.now() - start,
			});

			return null;
		}
	}

	/**
	 * Get a MongoDB collection.
	 *
	 * Automatically creates the collection when it
	 * does not exist.
	 */
	public async collection<T extends Document = Document>(
		name: string
	): Promise<Collection<T> | any> {
		if (this.isMock || !this.db) {
			if (!this.mockCollections.has(name)) {
				this.mockCollections.set(name, new MockCollection(name));
			}
			return this.mockCollections.get(name)! as any;
		}

		return this.db.collection<T>(name);
	}

	/**
	 * Explicitly create a collection.
	 */
	public async createCollection<T extends Document = Document>(
		name: string
	): Promise<Collection<T> | any> {
		if (this.isMock || !this.db) {
			if (!this.mockCollections.has(name)) {
				this.mockCollections.set(name, new MockCollection(name));
			}
			return this.mockCollections.get(name)! as any;
		}

		const exists =
			await this.db
				.listCollections(
					{ name },
					{ nameOnly: true }
				)
				.hasNext();

		if (exists) {
			return this.db.collection<T>(name);
		}

		const collection =
			await this.db.createCollection<T>(name);

		logger.info(
			`[DB] Created collection "${name}".`
		);

		return collection;
	}

	/**
	 * Drop a collection.
	 */
	public async dropCollection(
		name: string
	): Promise<boolean> {
		if (this.isMock || !this.db) {
			return this.mockCollections.delete(name);
		}

		const result =
			await this.db.dropCollection(name);

		if (result) {
			logger.info(
				`[DB] Dropped collection "${name}".`
			);
		}

		return result;
	}

	/**
	 * Insert one document.
	 */
	public async insertOne<T extends Document>(
		collection: string,
		data: OptionalId<T>
	): Promise<InsertOneResult<T>> {
		const col =
			await this.collection<T>(collection);

		return col.insertOne(data);
	}

	/**
	 * Insert multiple documents.
	 */
	public async insertMany<T extends Document>(
		collection: string,
		data: OptionalId<T>[]
	): Promise<InsertManyResult<T>> {
		const col =
			await this.collection<T>(collection);

		return col.insertMany(data);
	}

	/**
	 * Find one document.
	 */
	public async findOne<T extends Document>(
		collection: string,
		filter: Filter<T> = {}
	): Promise<WithId<T> | null> {
		const col =
			await this.collection<T>(collection);

		return col.findOne(filter);
	}

	/**
	 * Find multiple documents.
	 */
	public async find<T extends Document>(
		collection: string,
		filter: Filter<T> = {},
		options?: FindOptions<T>
	): Promise<WithId<T>[]> {
		const col =
			await this.collection<T>(collection);

		return col
			.find(filter, options)
			.toArray();
	}

	/**
	 * Update one document.
	 */
	public async updateOne<T extends Document>(
		collection: string,
		filter: Filter<T>,
		update: UpdateFilter<T>,
		options?: any
	): Promise<UpdateResult<T>> {
		const col =
			await this.collection<T>(collection);

		return col.updateOne(
			filter,
			update,
			options
		);
	}

	/**
	 * Update multiple documents.
	 */
	public async updateMany<T extends Document>(
		collection: string,
		filter: Filter<T>,
		update: UpdateFilter<T>,
		options?: any
	): Promise<UpdateResult<T>> {
		const col =
			await this.collection<T>(collection);

		return col.updateMany(
			filter,
			update,
			options
		);
	}

	/**
	 * Delete one document.
	 */
	public async deleteOne<T extends Document>(
		collection: string,
		filter: Filter<T>
	): Promise<DeleteResult> {
		const col =
			await this.collection<T>(collection);

		return col.deleteOne(filter);
	}

	/**
	 * Delete multiple documents.
	 */
	public async deleteMany<T extends Document>(
		collection: string,
		filter: Filter<T>
	): Promise<DeleteResult> {
		const col =
			await this.collection<T>(collection);

		return col.deleteMany(filter);
	}

	/**
	 * Count documents.
	 */
	public async count<T extends Document>(
		collection: string,
		filter: Filter<T> = {},
		options?: CountDocumentsOptions
	): Promise<number> {
		const col =
			await this.collection<T>(collection);

		return col.countDocuments(
			filter,
			options
		);
	}

	/**
	 * Check whether a document exists.
	 */
	public async exists<T extends Document>(
		collection: string,
		filter: Filter<T>
	): Promise<boolean> {
		const col =
			await this.collection<T>(collection);

		return (
			await col.countDocuments(
				filter,
				{ limit: 1 }
			)
		) > 0;
	}

	/**
	 * Create an index.
	 */
	public async createIndex<T extends Document>(
		collection: string,
		indexSpec: IndexDescription["key"],
		options?: Omit<IndexDescription, "key">
	): Promise<string> {
		const col =
			await this.collection<T>(collection);

		return col.createIndex(
			indexSpec,
			options
		);
	}

	/**
	 * List collections.
	 */
	public async getCollections(): Promise<string[]> {
		if (this.isMock || !this.db) {
			return Array.from(this.mockCollections.keys());
		}

		const collections =
			await this.db
				.listCollections({}, {
					nameOnly: true,
				})
				.toArray();

		return collections.map(
			collection => collection.name
		);
	}

	/**
	 * Get the raw MongoDB database.
	 */
	public getDatabase(): Db | undefined {
		return this.db ?? undefined;
	}

	/**
	 * Get the raw MongoDB client.
	 */
	public getClient(): MongoClient | undefined {
		return this.client ?? undefined;
	}

	/**
	 * Disconnect from MongoDB.
	 */
	public async disconnect(): Promise<void> {
		if (!this.client) {
			return;
		}

		await this.client.close();

		this.client = null;
		this.db = null;

		logger.info(
			"[DB] Disconnected from MongoDB."
		);
	}

	/**
	 * Ping MongoDB.
	 */
	public async ping(): Promise<void> {
		if (this.isMock) {
			return;
		}
		if (!this.db) {
			throw new Error(
				"Database has not been initialized."
			);
		}

		await this.db.command({
			ping: 1,
		});
	}
	
	/**
    * Find one document and update it.
    */
	public async findOneAndUpdate<T extends Document>(
		collection: string,
		filter: Filter<T>,
		update: UpdateFilter<T>,
		options?: FindOneAndUpdateOptions<T>
	): Promise<WithId<T> | null> {
		const col =
			await this.collection<T>(collection);
	
		return col.findOneAndUpdate(
			filter,
			update,
			options
		);
	}

	/**
	 * Check connection state.
	 */
	public isConnected(): boolean {
		return this.db !== null || this.isMock;
	}
}

const dbManagerInstance: DatabaseManager = ((globalThis as any).__dbManagerInstance ??= new DatabaseManager());
export default dbManagerInstance;

