import {
	FileBuilder as DiscordFileBuilder,
} from "discord.js";

export default class FileBuilder {
	private readonly builder: DiscordFileBuilder;

	public constructor() {
		this.builder = new DiscordFileBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	/* ─────────────── Configuration ─────────────── */

	public setURL(url: string): this {
		this.builder.setURL(url);

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

	/* ─────────────── Build ─────────────── */

	public build(): DiscordFileBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}