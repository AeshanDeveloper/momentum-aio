import {
	MediaGalleryBuilder as DiscordMediaGalleryBuilder,
	MediaGalleryItemBuilder,
} from "discord.js";

export default class MediaGalleryBuilder {
	private readonly builder: DiscordMediaGalleryBuilder;

	public constructor() {
		this.builder = new DiscordMediaGalleryBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	/* ─────────────── Items ─────────────── */

	public addItem(
		item: MediaGalleryItemBuilder
	): this {
		this.builder.addItems(item);

		return this;
	}

	public addItems(
		...items: MediaGalleryItemBuilder[]
	): this {
		this.builder.addItems(...items);

		return this;
	}

	/* ─────────────── Configuration ─────────────── */

	public setItems(
		...items: MediaGalleryItemBuilder[]
	): this {
		this.builder.setItems(...items);

		return this;
	}

	public clearItems(): this {
		this.builder.clearItems();

		return this;
	}

	public setId(id: number): this {
		this.builder.setId(id);

		return this;
	}

	public clearId(): this {
		this.builder.clearId();

		return this;
	}

	/* ─────────────── Build ─────────────── */

	public build(): DiscordMediaGalleryBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}