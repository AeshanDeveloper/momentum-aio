import {
	ThumbnailBuilder as DiscordThumbnailBuilder,
} from "discord.js";

export default class ThumbnailBuilder {
	private readonly builder: DiscordThumbnailBuilder;

	public constructor() {
		this.builder = new DiscordThumbnailBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	public add(
		url?: string
	): this {
		if (url !== undefined) {
			this.setURL(url);
		}

		return this;
	}

	public setURL(
		url: string
	): this {
		this.builder.setURL(url);

		return this;
	}

	public setDescription(
		description: string
	): this {
		this.builder.setDescription(description);

		return this;
	}

	public clearDescription(): this {
		this.builder.clearDescription();

		return this;
	}

	public setSpoiler(
		spoiler: boolean = true
	): this {
		this.builder.setSpoiler(spoiler);

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

	public build(): DiscordThumbnailBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}