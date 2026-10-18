import {
	SeparatorBuilder as DiscordSeparatorBuilder,
	SeparatorSpacingSize,
} from "discord.js";

export default class SeparatorBuilder {
	private readonly builder: DiscordSeparatorBuilder;

	public constructor() {
		this.builder = new DiscordSeparatorBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	/**
	 * Initializes the separator.
	 *
	 * No arguments are required.
	 */
	public add(): this {
		return this;
	}

	public addDivider(
		divider: boolean = true
	): this {
		this.builder.addDivider(divider);

		return this;
	}

	public setSpacing(
		spacing: SeparatorSpacingSize
	): this {
		this.builder.setSpacing(spacing);

		return this;
	}

	public clearSpacing(): this {
		this.builder.clearSpacing();

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

	public build(): DiscordSeparatorBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}