import {
	TextDisplayBuilder as DiscordTextDisplayBuilder,
} from "discord.js";

export default class TextDisplayBuilder {
	private readonly builder: DiscordTextDisplayBuilder;

	public constructor() {
		this.builder = new DiscordTextDisplayBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	public add(
		content?: string
	): this {
		if (content !== undefined) {
			this.setContent(content);
		}

		return this;
	}

	public setContent(
		content: string
	): this {
		this.builder.setContent(content);

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

	public build(): DiscordTextDisplayBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}