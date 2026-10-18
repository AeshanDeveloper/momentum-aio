import {
	ButtonBuilder as DiscordButtonBuilder,
	ButtonStyle,
} from "discord.js";

export default class ButtonBuilder {
	private readonly builder: DiscordButtonBuilder;

	public constructor() {
		this.builder = new DiscordButtonBuilder();
	}

	public get data() {
		return this.builder.data;
	}

	public get discord() {
		return this.builder;
	}

	public add(
		customId?: string,
		label?: string
	): this {
		if (customId !== undefined) {
			this.setCustomId(customId);
		}

		if (label !== undefined) {
			this.setLabel(label);
		}

		return this;
	}

	public setCustomId(id: string): this {
		this.builder.setCustomId(id);

		return this;
	}

	public setLabel(label: string): this {
		this.builder.setLabel(label);

		return this;
	}

	public setStyle(style: ButtonStyle): this {
		this.builder.setStyle(style);

		return this;
	}

	public setEmoji(emoji: string): this {
		this.builder.setEmoji(emoji);

		return this;
	}

	public setDisabled(
		disabled: boolean = true
	): this {
		this.builder.setDisabled(disabled);

		return this;
	}

	public setURL(url: string): this {
		this.builder.setURL(url);

		return this;
	}

	public setSKUId(skuId: string): this {
		this.builder.setSKUId(skuId);

		return this;
	}

	public build(): DiscordButtonBuilder {
		return this.builder;
	}

	public toJSON() {
		return this.builder.toJSON();
	}
}